from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ...db.core import (
    create_experiences,
    create_feedback,
    delete_feedback,
    get_extended_user_attendee_id,
    get_extended_user_wxid,
    get_feedback_by_id,
    get_feedbacks_by_meeting,
    get_meeting_by_id,
    is_extended_user_admin,
    update_feedback,
    validate_attendee_id_exists,
    validate_segments_belong_to_meeting,
)
from ...models.feedback import (
    Feedback,
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackUpdate,
)
from ...models.users import User
from ...models.wechat_user import WeChatUser
from .auth import get_current_extended_user, get_optional_extended_user

feedback_router = r = APIRouter()


@r.post("/meetings/{meeting_id}/feedbacks", response_model=FeedbackResponse)
async def create_meeting_feedback(
    feedback_data: FeedbackCreate,
    meeting_id: str = Path(..., description="The ID of the meeting to create feedback for"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Create feedback for a meeting - supports experience curves and targeted feedback.

    This endpoint enables users to provide structured feedback for meetings using
    the experience curve methodology (opening/peak/valley/ending) as well as
    targeted feedback for specific segments or attendees.

    Authentication requirements:
    - User must have a valid wxid (WeChat openid) bound to their account
    - Members without wxid binding will receive a 403 error
    - WeChat users inherently have wxid from their authentication

    Validation performed:
    - Meeting existence verification
    - Segment ownership validation (if segment_id provided)
    - Attendee existence validation (if to_attendee_id provided)
    - Duplicate feedback prevention (handled by database unique constraints)

    Feedback types supported:
    - Experience feedback: opening, peak, valley, ending (one per user per meeting)
    - Segment feedback: Targeted feedback for specific meeting segments
    - Attendee feedback: Targeted feedback for specific meeting participants

    Args:
        feedback_data: Feedback request containing type, value, and optional targets
        meeting_id: Target meeting ID for the feedback
        current_user: Authenticated user (from JWT token)

    Returns:
        FeedbackResponse with success status and created feedback record

    Raises:
        HTTPException 403: If user lacks wxid binding
        HTTPException 404: If meeting not found
        HTTPException 409: If duplicate feedback type for same meeting
        HTTPException 422: If segment/attendee IDs are invalid
        HTTPException 500: If feedback creation fails
    """
    wxid = get_extended_user_wxid(current_user)
    if not wxid:
        raise HTTPException(status_code=403, detail="User wxid not available")

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Validate segment_id belongs to meeting if provided
    if feedback_data.segment_id:
        if not validate_segments_belong_to_meeting(meeting_id, [feedback_data.segment_id]):
            raise HTTPException(status_code=422, detail="Segment ID does not belong to this meeting")

    # Validate to_attendee_id exists if provided
    if feedback_data.to_attendee_id:
        if not validate_attendee_id_exists(feedback_data.to_attendee_id):
            raise HTTPException(status_code=422, detail="Invalid to_attendee_id")

    # Create feedback
    try:
        feedback_dict = create_feedback(
            meeting_id=meeting_id,
            wxid=wxid,
            feedback_type=feedback_data.type.value,
            value=feedback_data.value,
            segment_id=feedback_data.segment_id,
            to_attendee_id=feedback_data.to_attendee_id,
        )

        feedback = Feedback(**feedback_dict)
        return FeedbackResponse(success=True, feedback=feedback)

    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(status_code=409, detail="Feedback of this type already exists for this meeting")
        raise HTTPException(status_code=500, detail=f"Failed to create feedback: {e!s}")


@r.get("/meetings/{meeting_id}/feedbacks", response_model=FeedbackListResponse)
async def get_meeting_feedbacks(
    meeting_id: str = Path(..., description="The ID of the meeting to retrieve feedbacks for"),
    feedback_type: Optional[str] = Query(None, description="Filter by feedback type"),
    segment_id: Optional[str] = Query(None, description="Filter by segment ID"),
    current_user: Optional[Union[User, WeChatUser]] = Depends(get_optional_extended_user),
):
    """
    Retrieve feedbacks for a meeting with sophisticated access control and filtering.

    This endpoint implements comprehensive access control to ensure users only see
    feedbacks they are authorized to view, supporting both sent and received feedback visibility.

    Access control logic:
    1. Webapp user with wxid bound: Can view feedbacks sent by their wxid + received by their attendee_id
    2. Webapp user without wxid bound: Can only view feedbacks received by their attendee_id
    3. Miniapp user with wxid bound: Can view feedbacks sent by their wxid + received by their attendee_id
    4. Miniapp user without wxid bound: Can only view feedbacks sent by their wxid
    5. Admin users: Can view all feedbacks for the meeting
    6. Unauthenticated users: Receive empty feedback list

    Additional filtering:
    - Optional feedback type filtering (experience_*, segment, attendee)
    - Optional segment ID filtering for segment-specific feedback

    The endpoint uses optional authentication, gracefully handling unauthenticated
    requests by returning empty results rather than authentication errors.

    Args:
        meeting_id: The ID of the meeting to retrieve feedbacks for
        feedback_type: Optional filter by feedback type
        segment_id: Optional filter by segment ID
        current_user: Optional authenticated user (None for unauthenticated requests)

    Returns:
        FeedbackListResponse containing list of feedbacks visible to the user

    Raises:
        HTTPException 404: If meeting not found (only for authenticated users)
    """
    if not current_user:
        return FeedbackListResponse(feedbacks=[])

    wxid = get_extended_user_wxid(current_user)
    user_attendee_id = get_extended_user_attendee_id(current_user)
    is_admin = is_extended_user_admin(current_user)

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # If no wxid and no attendee_id available, return empty list
    if not wxid and not user_attendee_id:
        return FeedbackListResponse(feedbacks=[])

    # Get feedbacks with access control
    feedback_dicts = get_feedbacks_by_meeting(
        meeting_id=meeting_id,
        wxid=wxid,
        user_attendee_id=user_attendee_id,
        is_admin=is_admin,
        feedback_type=feedback_type,
        segment_id=segment_id,
    )

    feedbacks = [Feedback(**feedback_dict) for feedback_dict in feedback_dicts]
    return FeedbackListResponse(feedbacks=feedbacks)


@r.put("/meetings/{meeting_id}/feedbacks/{feedback_id}", response_model=FeedbackResponse)
async def update_meeting_feedback(
    feedback_updates: FeedbackUpdate,
    meeting_id: str = Path(..., description="The ID of the meeting"),
    feedback_id: str = Path(..., description="The ID of the feedback to update"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Update an existing feedback record with ownership validation.

    This endpoint allows users to modify their previously submitted feedback,
    supporting partial updates of feedback content, type, and targeting.

    Authorization requirements:
    - User must have a valid wxid (WeChat openid) bound to their account
    - User must be the original author of the feedback (ownership validation)
    - Admin users can update any feedback regardless of ownership

    Validation performed:
    - Meeting existence verification
    - Feedback existence and ownership validation
    - Meeting-feedback relationship verification
    - Field-level validation for updated values

    Update behavior:
    - Only non-null fields in feedback_updates are applied
    - Supports partial updates (e.g., only changing value, not type)
    - Maintains original creation metadata (created_at, from_wxid)
    - Updates modification timestamp automatically

    Args:
        feedback_updates: Partial feedback data with fields to update
        meeting_id: The ID of the meeting containing the feedback
        feedback_id: The ID of the specific feedback to update
        current_user: Authenticated user (from JWT token)

    Returns:
        FeedbackResponse with success status and updated feedback record

    Raises:
        HTTPException 403: If user lacks wxid or doesn't own the feedback
        HTTPException 404: If meeting or feedback not found
        HTTPException 409: If update creates duplicate feedback type
        HTTPException 422: If feedback doesn't belong to specified meeting
        HTTPException 500: If feedback update fails
    """
    wxid = get_extended_user_wxid(current_user)
    is_admin = is_extended_user_admin(current_user)
    if not wxid and not is_admin:
        raise HTTPException(status_code=403, detail="User wxid not available")

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Get existing feedback
    feedback = get_feedback_by_id(feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    # Check if feedback belongs to this meeting
    if feedback["meeting_id"] != meeting_id:
        raise HTTPException(status_code=422, detail="Feedback does not belong to this meeting")

    # Check ownership
    if feedback["from_wxid"] != wxid and not is_admin:
        raise HTTPException(status_code=403, detail="Can only update your own feedback")

    # Build updates dict
    updates = {}
    if feedback_updates.segment_id is not None:
        updates["segment_id"] = feedback_updates.segment_id
    if feedback_updates.type is not None:
        updates["type"] = feedback_updates.type.value
    if feedback_updates.value is not None:
        updates["value"] = feedback_updates.value
    if feedback_updates.to_attendee_id is not None:
        updates["to_attendee_id"] = feedback_updates.to_attendee_id

    # Update feedback
    try:
        updated_feedback_dict = update_feedback(feedback_id, updates)
        updated_feedback = Feedback(**updated_feedback_dict)
        return FeedbackResponse(success=True, feedback=updated_feedback)

    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(status_code=409, detail="Feedback of this type already exists for this meeting")
        raise HTTPException(status_code=500, detail=f"Failed to update feedback: {e!s}")


@r.delete("/meetings/{meeting_id}/feedbacks/{feedback_id}")
async def delete_meeting_feedback(
    meeting_id: str = Path(..., description="The ID of the meeting"),
    feedback_id: str = Path(..., description="The ID of the feedback to delete"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Delete an existing feedback record with strict ownership validation.

    This endpoint enables users to remove their previously submitted feedback,
    supporting cleanup of incorrect or unwanted feedback entries.

    Authorization requirements:
    - User must have a valid wxid (WeChat openid) bound to their account
    - User must be the original author of the feedback (ownership validation)
    - Admin users can delete any feedback regardless of ownership

    Validation performed:
    - Meeting existence verification
    - Feedback existence and ownership validation
    - Meeting-feedback relationship verification

    Delete behavior:
    - Permanently removes the feedback record from the database
    - Cannot be undone once executed
    - Does not affect related meeting or attendee records
    - Maintains referential integrity

    Use cases:
    - Correcting mistakenly submitted feedback
    - Removing inappropriate or incorrect feedback
    - Administrative cleanup of feedback data

    Args:
        meeting_id: The ID of the meeting containing the feedback
        feedback_id: The ID of the specific feedback to delete
        current_user: Authenticated user (from JWT token)

    Returns:
        JSON response with success status

    Raises:
        HTTPException 403: If user lacks wxid or doesn't own the feedback
        HTTPException 404: If meeting or feedback not found
        HTTPException 422: If feedback doesn't belong to specified meeting
        HTTPException 500: If feedback deletion fails
    """
    wxid = get_extended_user_wxid(current_user)
    is_admin = is_extended_user_admin(current_user)
    if not wxid and not is_admin:
        raise HTTPException(status_code=403, detail="User wxid not available")

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Get existing feedback
    feedback = get_feedback_by_id(feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    # Check if feedback belongs to this meeting
    if feedback["meeting_id"] != meeting_id:
        raise HTTPException(status_code=422, detail="Feedback does not belong to this meeting")

    # Check ownership
    if feedback["from_wxid"] != wxid and not is_admin:
        raise HTTPException(status_code=403, detail="Can only delete your own feedback")

    # Delete feedback
    success = delete_feedback(feedback_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete feedback")

    return {"success": True}


@r.post("/meetings/{meeting_id}/feedbacks/experiences", response_model=FeedbackListResponse)
async def create_meeting_experiences(
    experience_data: dict,
    meeting_id: str = Path(..., description="The ID of the meeting to create experience feedbacks for"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Create experience curve feedbacks for a meeting - batch operation for 4 experience types.

    This endpoint enables users to provide experience curve feedback for meetings using
    the opening/peak/valley/ending methodology. It replaces any existing experience
    feedbacks from the same user for the meeting.

    Authentication requirements:
    - User must have a valid wxid (WeChat openid) bound to their account
    - Members without wxid binding will receive a 403 error
    - WeChat users inherently have wxid from their authentication

    Validation performed:
    - Meeting existence verification
    - Automatic cleanup of existing experience feedbacks

    Experience types supported:
    - opening: Opening experience feedback (None to skip)
    - peak: Peak experience feedback (None to skip)
    - valley: Valley experience feedback (None to skip)
    - ending: Ending experience feedback (None to skip)

    Args:
        experience_data: Dict with opening/peak/valley/ending keys (values can be None)
        meeting_id: Target meeting ID for the experience feedbacks
        current_user: Authenticated user (from JWT token)

    Returns:
        FeedbackListResponse with success status and created experience feedback records

    Raises:
        HTTPException 403: If user lacks wxid binding
        HTTPException 404: If meeting not found
        HTTPException 500: If experience feedback creation fails
    """
    wxid = get_extended_user_wxid(current_user)
    if not wxid:
        raise HTTPException(status_code=403, detail="User wxid required for experience feedback")

    # Validate meeting exists
    meeting = get_meeting_by_id(meeting_id, current_user.uid if isinstance(current_user, User) else None)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Extract experience values (can be None)
    opening = experience_data.get("opening")
    peak = experience_data.get("peak")
    valley = experience_data.get("valley")
    ending = experience_data.get("ending")

    # Create experience feedbacks
    try:
        feedback_dicts = create_experiences(
            meeting_id=meeting_id,
            wxid=wxid,
            opening=opening,
            peak=peak,
            valley=valley,
            ending=ending,
        )

        feedbacks = [Feedback(**feedback_dict) for feedback_dict in feedback_dicts]
        return FeedbackListResponse(feedbacks=feedbacks)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create experience feedbacks: {e!s}")
