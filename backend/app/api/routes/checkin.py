from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Path

from ...db.core import (
    create_checkins,
    get_checkins_by_meeting,
    get_extended_user_wxid,
    get_meeting_by_id,
    get_user_by_wxid,
    reset_segment_checkin,
    validate_segments_belong_to_meeting,
)
from ...models.checkin import (
    Checkin,
    CheckinCreate,
    CheckinListResponse,
    CheckinResetRequest,
    CheckinResetResponse,
    CheckinResponse,
)
from ...models.users import User
from ...models.wechat_user import WeChatUser
from .auth import get_current_extended_user, get_optional_extended_user

checkin_router = r = APIRouter()


@r.post("/meetings/{meeting_id}/checkins", response_model=CheckinResponse)
async def create_meeting_checkins(
    checkin_data: CheckinCreate,
    meeting_id: str = Path(..., description="The ID of the meeting to create checkins for"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Create checkins for meeting segments - allows users to register their participation.

    This endpoint enables both webapp members and WeChat miniapp users to check in
    for multiple meeting segments at once. Checkins serve as attendance records
    and role confirmations for meeting participants.

    Checkin behavior based on segment_ids:
    - None: General attendance (present but no specific role)
    - []: Uncheckin (remove all existing checkins for this meeting)
    - [segment1, segment2, ...]: Checkin for specific segments/roles

    Authentication requirements:
    - User must have a valid wxid (WeChat openid) bound to their account
    - Members without wxid binding will receive a 403 error
    - WeChat users inherently have wxid from their authentication

    Validation performed:
    - Meeting existence verification
    - Segment ownership validation (only when specific segments are provided)
    - Duplicate checkin prevention (handled by database unique constraints)

    Args:
        checkin_data: Checkin request containing optional segment IDs and optional name
        meeting_id: Target meeting ID for the checkins
        current_user: Authenticated user (from JWT token)

    Returns:
        CheckinResponse with success status and list of created checkin records

    Raises:
        HTTPException 403: If user lacks wxid binding
        HTTPException 404: If meeting not found
        HTTPException 422: If segment IDs don't belong to meeting
        HTTPException 500: If checkin creation fails
    """
    # For create operations, members must have wxid binding
    wxid = get_extended_user_wxid(current_user)
    if not wxid:
        raise HTTPException(status_code=403, detail="User wxid not bound to attendee record")

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Validate segments belong to meeting (skip validation for None and empty list)
    if checkin_data.segment_ids and not validate_segments_belong_to_meeting(meeting_id, checkin_data.segment_ids):
        raise HTTPException(status_code=422, detail="One or more segment IDs do not belong to this meeting")

    # Infer membership status from wxid binding
    is_member = get_user_by_wxid(wxid) is not None

    # Create checkins
    try:
        checkins = create_checkins(
            meeting_id=meeting_id,
            wxid=wxid,
            segment_ids=checkin_data.segment_ids,
            name=checkin_data.name,
            referral_source=checkin_data.referral_source,
            is_member=is_member,
        )

        checkin_models = [Checkin(**checkin) for checkin in checkins]
        return CheckinResponse(success=True, checkins=checkin_models)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create checkins: {e!s}")


@r.get("/meetings/{meeting_id}/checkins", response_model=CheckinListResponse)
async def get_meeting_checkins(
    meeting_id: str = Path(..., description="The ID of the meeting to retrieve checkins for"),
    current_user: Optional[Union[User, WeChatUser]] = Depends(get_optional_extended_user),
):
    """
    Retrieve checkins for a meeting with user-specific filtering.

    This endpoint allows authenticated users to view checkin records for a meeting.
    The visibility is filtered based on the user's identity:

    Access patterns:
    - Unauthenticated users: Receive empty checkin list
    - Members (User): Can view ALL checkins for the meeting
    - WeChat users (non-members): Can only view their own checkins (filtered by wxid)

    The endpoint uses optional authentication, meaning it accepts requests without
    valid tokens but provides limited functionality.

    Args:
        meeting_id: The ID of the meeting to retrieve checkins for
        current_user: Optional authenticated user (None for unauthenticated requests)

    Returns:
        CheckinListResponse containing list of checkins visible to the user

    Raises:
        HTTPException 404: If meeting not found (only for authenticated users)
    """
    if not current_user:
        return CheckinListResponse(checkins=[])

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Members can see all checkins, non-members can only see their own
    is_member = isinstance(current_user, User)
    if is_member:
        checkins = get_checkins_by_meeting(meeting_id, wxid=None)
    else:
        wxid = get_extended_user_wxid(current_user)
        checkins = get_checkins_by_meeting(meeting_id, wxid=wxid)

    checkin_models = [Checkin(**checkin) for checkin in checkins]
    return CheckinListResponse(checkins=checkin_models)


@r.post("/meetings/{meeting_id}/checkins/reset", response_model=CheckinResetResponse)
async def reset_meeting_checkin(
    reset_data: CheckinResetRequest,
    meeting_id: str = Path(..., description="The ID of the meeting"),
    current_user: User = Depends(get_current_extended_user),
):
    """
    Reset a segment's checkin (e.g., to release the Timer role).

    This endpoint allows members to reset a checkin for a specific segment.
    The behavior depends on how many checkins the person has in the meeting:
    - If wxid has multiple checkins: DELETE the checkin record for this segment
    - If wxid has only one checkin: NULLIFY segment_id (preserve attendance record)

    Only club members can perform this operation.

    Args:
        reset_data: Contains segment_id to reset
        meeting_id: The ID of the meeting
        current_user: Authenticated member (from JWT token)

    Returns:
        CheckinResetResponse with success status and action taken

    Raises:
        HTTPException 403: If user is not a member
        HTTPException 404: If meeting not found or no checkin found for segment
    """
    # Only members can reset checkins
    if not isinstance(current_user, User):
        raise HTTPException(status_code=403, detail="Only members can reset checkins")

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Reset the checkin
    result = reset_segment_checkin(meeting_id, reset_data.segment_id)
    if not result:
        raise HTTPException(status_code=404, detail="No checkin found for this segment")

    return CheckinResetResponse(success=True, action=result["action"])
