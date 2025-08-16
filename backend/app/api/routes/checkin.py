from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Path

from ...db.core import (
    create_checkins,
    get_checkins_by_meeting,
    get_extended_user_wxid,
    get_meeting_by_id,
    validate_segments_belong_to_meeting,
)
from ...models.checkin import (
    Checkin,
    CheckinCreate,
    CheckinListResponse,
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

    Authentication requirements:
    - User must have a valid wxid (WeChat openid) bound to their account
    - Members without wxid binding will receive a 403 error
    - WeChat users inherently have wxid from their authentication

    Validation performed:
    - Meeting existence verification
    - Segment ownership validation (all segments must belong to the specified meeting)
    - Duplicate checkin prevention (handled by database unique constraints)

    Args:
        checkin_data: Checkin request containing segment IDs and optional name
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

    # Validate segments belong to meeting
    if not validate_segments_belong_to_meeting(meeting_id, checkin_data.segment_ids):
        raise HTTPException(status_code=422, detail="One or more segment IDs do not belong to this meeting")

    # Create checkins
    try:
        checkins = create_checkins(
            meeting_id=meeting_id, wxid=wxid, segment_ids=checkin_data.segment_ids, name=checkin_data.name
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
    The visibility is filtered based on the user's identity and wxid availability:

    Access patterns:
    - Unauthenticated users: Receive empty checkin list
    - Users with wxid: Can view checkins made by their wxid (their own checkins)
    - All filtering is handled by the core get_checkins_by_meeting function

    The endpoint uses optional authentication, meaning it accepts requests without
    valid tokens but provides limited functionality. This design supports both
    authenticated member access and potential future public visibility features.

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

    wxid = get_extended_user_wxid(current_user)

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    checkins = get_checkins_by_meeting(meeting_id, wxid=wxid)

    checkin_models = [Checkin(**checkin) for checkin in checkins]
    return CheckinListResponse(checkins=checkin_models)
