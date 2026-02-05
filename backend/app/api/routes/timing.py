from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Path

from ...db.core import (
    can_control_timer,
    create_timing,
    create_timings_batch,
    create_timings_batch_all,
    delete_timing,
    get_extended_user_wxid,
    get_meeting_by_id,
    get_timings_by_meeting,
    update_timing,
    validate_segments_belong_to_meeting,
)
from ...models.timing import (
    Timing,
    TimingBatchAllCreate,
    TimingBatchCreate,
    TimingBatchResponse,
    TimingCreate,
    TimingDeleteResponse,
    TimingResponse,
    TimingsListResponse,
    TimingUpdate,
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
    can_control = can_control_timer(meeting_id, wxid, user_id)

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
    if not can_control_timer(meeting_id, wxid, user_id):
        raise HTTPException(
            status_code=403,
            detail="Only the Timer or an admin can create timing records.",
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
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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
    if not can_control_timer(meeting_id, wxid, user_id):
        raise HTTPException(
            status_code=403,
            detail="Only the Timer or an admin can create timing records.",
        )

    # Validate segment belongs to meeting
    if not validate_segments_belong_to_meeting(meeting_id, [batch_data.segment_id]):
        raise HTTPException(status_code=422, detail="Segment does not belong to this meeting")

    # Convert to dict format for db function (empty list is valid - means delete all)
    timings_data = [
        {
            "name": t.name,
            "planned_duration_minutes": t.planned_duration_minutes,
            "actual_start_time": t.actual_start_time,
            "actual_end_time": t.actual_end_time,
        }
        for t in batch_data.timings
    ]

    # Create timing records (or delete all if empty list)
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


@r.post("/meetings/{meeting_id}/timings/batch-all", response_model=TimingBatchResponse)
async def create_meeting_timings_batch_all(
    batch_data: TimingBatchAllCreate,
    meeting_id: str = Path(..., description="The ID of the meeting"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Create timing records for multiple segments in batch.

    Only the person checked in as Timer can create timing records.
    This endpoint saves all segment timings in a single request for better
    network efficiency than multiple individual calls.

    Note: This is not a fully atomic operation. If an error occurs mid-batch,
    some segments may be updated while others are not.

    Each segment's existing timings are deleted before inserting new ones.

    Args:
        batch_data: Batch timing data with list of segments and their timings
        meeting_id: The ID of the meeting
        current_user: Authenticated user (must be the Timer)

    Returns:
        TimingBatchResponse with list of all created timing records

    Raises:
        HTTPException 403: If user is not the Timer
        HTTPException 404: If meeting not found
        HTTPException 422: If any segment doesn't belong to meeting
    """
    # Validate meeting exists
    user_id = current_user.uid if isinstance(current_user, User) else None
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if user can control timer
    wxid = get_extended_user_wxid(current_user)
    if not can_control_timer(meeting_id, wxid, user_id):
        raise HTTPException(
            status_code=403,
            detail="Only the Timer or an admin can create timing records.",
        )

    # Validate all segments belong to meeting
    segment_ids = [seg.segment_id for seg in batch_data.segments]
    if segment_ids and not validate_segments_belong_to_meeting(meeting_id, segment_ids):
        raise HTTPException(status_code=422, detail="One or more segments do not belong to this meeting")

    # Convert to dict format for db function
    segments_data = [
        {
            "segment_id": seg.segment_id,
            "timings": [
                {
                    "name": t.name,
                    "planned_duration_minutes": t.planned_duration_minutes,
                    "actual_start_time": t.actual_start_time,
                    "actual_end_time": t.actual_end_time,
                }
                for t in seg.timings
            ],
        }
        for seg in batch_data.segments
    ]

    # Create timing records
    try:
        timings = create_timings_batch_all(
            meeting_id=meeting_id,
            segments_data=segments_data,
        )
        timing_models = [Timing(**t) for t in timings]
        return TimingBatchResponse(success=True, timings=timing_models)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create timings: {e!s}")


@r.put("/meetings/{meeting_id}/timings/{timing_id}", response_model=TimingResponse)
async def update_meeting_timing(
    timing_data: TimingUpdate,
    meeting_id: str = Path(..., description="The ID of the meeting"),
    timing_id: str = Path(..., description="The ID of the timing record to update"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Update an existing timing record.

    Only users with timer control permission can update timing records.

    Args:
        timing_data: Updated timing fields (all optional)
        meeting_id: The ID of the meeting
        timing_id: The ID of the timing record to update
        current_user: Authenticated user

    Returns:
        TimingResponse with the updated timing record

    Raises:
        HTTPException 403: If user cannot control timer
        HTTPException 404: If meeting or timing not found
        HTTPException 422: If update data is invalid
    """
    # Validate meeting exists
    user_id = current_user.uid if isinstance(current_user, User) else None
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if user can control timer
    wxid = get_extended_user_wxid(current_user)
    if not can_control_timer(meeting_id, wxid, user_id):
        raise HTTPException(
            status_code=403,
            detail="Only members or the Timer can update timing records.",
        )

    # Update timing record
    try:
        timing = update_timing(
            timing_id=timing_id,
            meeting_id=meeting_id,
            name=timing_data.name,
            planned_duration_minutes=timing_data.planned_duration_minutes,
            actual_start_time=timing_data.actual_start_time,
            actual_end_time=timing_data.actual_end_time,
        )
        return TimingResponse(success=True, timing=Timing(**timing))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update timing: {e!s}")


@r.delete("/meetings/{meeting_id}/timings/{timing_id}", response_model=TimingDeleteResponse)
async def delete_meeting_timing(
    meeting_id: str = Path(..., description="The ID of the meeting"),
    timing_id: str = Path(..., description="The ID of the timing record to delete"),
    current_user: Union[User, WeChatUser] = Depends(get_current_extended_user),
):
    """
    Delete a single timing record.

    Only the person checked in as Timer can delete timing records.

    Args:
        meeting_id: The ID of the meeting
        timing_id: The ID of the timing record to delete
        current_user: Authenticated user (must be the Timer)

    Returns:
        TimingDeleteResponse indicating success

    Raises:
        HTTPException 403: If user is not the Timer
        HTTPException 404: If meeting or timing not found
    """
    # Validate meeting exists
    user_id = current_user.uid if isinstance(current_user, User) else None
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Check if user can control timer
    wxid = get_extended_user_wxid(current_user)
    if not can_control_timer(meeting_id, wxid, user_id):
        raise HTTPException(
            status_code=403,
            detail="Only the Timer or an admin can delete timing records.",
        )

    # Delete the timing
    try:
        deleted = delete_timing(timing_id, meeting_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Timing record not found")
        return TimingDeleteResponse(success=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete timing: {e!s}")
