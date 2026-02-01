from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Path

from ...db.core import (
    can_control_timer,
    create_timing,
    create_timings_batch,
    get_extended_user_wxid,
    get_meeting_by_id,
    get_timings_by_meeting,
    validate_segments_belong_to_meeting,
)
from ...models.timing import (
    Timing,
    TimingBatchCreate,
    TimingBatchResponse,
    TimingCreate,
    TimingResponse,
    TimingsListResponse,
)
from ...models.users import User
from ...models.wechat_user import WeChatUser
from .auth import get_current_extended_user, get_optional_extended_user

timing_router = r = APIRouter()


@r.get("/meetings/{meeting_id}/timings", response_model=TimingsListResponse)
async def get_meeting_timings(
    meeting_id: str = Path(..., description="The ID of the meeting"),
    current_user: Optional[Union[User, WeChatUser]] = Depends(get_optional_extended_user),
):
    """
    Get all timing records for a meeting.

    Returns timing records with calculated fields (actual_duration_seconds, dot_color)
    and a can_control flag indicating if the current user can control the timer.

    The can_control flag is True only if:
    - User is authenticated
    - User has a wxid
    - User is checked in as the Timer for this meeting

    Args:
        meeting_id: The ID of the meeting
        current_user: Optional authenticated user

    Returns:
        TimingsListResponse with can_control flag and list of timing records
    """
    # Validate meeting exists (allow public access to timing results)
    user_id = current_user.uid if isinstance(current_user, User) else None
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if user can control timer
    wxid = get_extended_user_wxid(current_user) if current_user else None
    can_control = can_control_timer(meeting_id, wxid)

    # Get timing records
    timings = get_timings_by_meeting(meeting_id)
    timing_models = [Timing(**t) for t in timings]

    return TimingsListResponse(can_control=can_control, timings=timing_models)


@r.post("/meetings/{meeting_id}/timings", response_model=TimingResponse)
async def create_meeting_timing(
    timing_data: TimingCreate,
    meeting_id: str = Path(..., description="The ID of the meeting"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Create a single timing record for a segment.

    Only the person checked in as Timer can create timing records.

    Args:
        timing_data: Timing data with segment_id, planned_duration, and timestamps
        meeting_id: The ID of the meeting
        current_user: Authenticated user (must be the Timer)

    Returns:
        TimingResponse with the created timing record

    Raises:
        HTTPException 403: If user is not the Timer
        HTTPException 404: If meeting not found
        HTTPException 422: If segment doesn't belong to meeting
    """
    # Validate meeting exists
    user_id = current_user.uid if isinstance(current_user, User) else None
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if user can control timer
    wxid = get_extended_user_wxid(current_user)
    if not can_control_timer(meeting_id, wxid):
        raise HTTPException(
            status_code=403,
            detail="Only the Timer can create timing records. Please check in as Timer first.",
        )

    # Validate segment belongs to meeting
    if not validate_segments_belong_to_meeting(meeting_id, [timing_data.segment_id]):
        raise HTTPException(status_code=422, detail="Segment does not belong to this meeting")

    # Create timing record
    try:
        timing = create_timing(
            meeting_id=meeting_id,
            segment_id=timing_data.segment_id,
            planned_duration_minutes=timing_data.planned_duration_minutes,
            actual_start_time=timing_data.actual_start_time,
            actual_end_time=timing_data.actual_end_time,
            name=timing_data.name,
        )
        return TimingResponse(success=True, timing=Timing(**timing))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create timing: {e!s}")


@r.post("/meetings/{meeting_id}/timings/batch", response_model=TimingBatchResponse)
async def create_meeting_timings_batch(
    batch_data: TimingBatchCreate,
    meeting_id: str = Path(..., description="The ID of the meeting"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Create multiple timing records in batch (for Table Topics).

    Only the person checked in as Timer can create timing records.
    This endpoint is designed for Table Topics where multiple speakers
    are timed in succession and saved together.

    Args:
        batch_data: Batch timing data with segment_id and list of timings
        meeting_id: The ID of the meeting
        current_user: Authenticated user (must be the Timer)

    Returns:
        TimingBatchResponse with list of created timing records

    Raises:
        HTTPException 403: If user is not the Timer
        HTTPException 404: If meeting not found
        HTTPException 422: If segment doesn't belong to meeting
    """
    # Validate meeting exists
    user_id = current_user.uid if isinstance(current_user, User) else None
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if user can control timer
    wxid = get_extended_user_wxid(current_user)
    if not can_control_timer(meeting_id, wxid):
        raise HTTPException(
            status_code=403,
            detail="Only the Timer can create timing records. Please check in as Timer first.",
        )

    # Validate segment belongs to meeting
    if not validate_segments_belong_to_meeting(meeting_id, [batch_data.segment_id]):
        raise HTTPException(status_code=422, detail="Segment does not belong to this meeting")

    # Validate we have timings to create
    if not batch_data.timings:
        raise HTTPException(status_code=422, detail="No timings provided")

    # Convert to dict format for db function
    timings_data = [
        {
            "name": t.name,
            "planned_duration_minutes": t.planned_duration_minutes,
            "actual_start_time": t.actual_start_time,
            "actual_end_time": t.actual_end_time,
        }
        for t in batch_data.timings
    ]

    # Create timing records
    try:
        timings = create_timings_batch(
            meeting_id=meeting_id,
            segment_id=batch_data.segment_id,
            timings_data=timings_data,
        )
        timing_models = [Timing(**t) for t in timings]
        return TimingBatchResponse(success=True, timings=timing_models)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create timings: {e!s}")
