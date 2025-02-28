from typing import Dict, List, Optional

from .supabase import supabase


def get_members():
    return supabase.table("members").select("id, username, full_name").execute().data


def create_meeting(meeting_data: Dict, user_id: str) -> Dict:
    """
    Create a new meeting in the database.

    Args:
        meeting_data: Dictionary containing meeting information
        user_id: ID of the user creating the meeting

    Returns:
        Dictionary containing the created meeting data including ID
    """
    # We need to extract segments data before inserting the meeting
    segments_data = meeting_data.pop("segments", [])

    # Insert meeting into database
    result = (
        supabase.table("meetings")
        .insert(
            {
                "type": meeting_data.get("meeting_type"),
                "theme": meeting_data.get("theme"),
                "manager_id": meeting_data.get("meeting_manager"),  # This should be an attendee ID
                "date": meeting_data.get("date"),
                "start_time": meeting_data.get("start_time"),
                "end_time": meeting_data.get("end_time"),
                "location": meeting_data.get("location"),
                "introduction": meeting_data.get("introduction"),
                "status": meeting_data.get("status", "draft"),
            }
        )
        .execute()
    )

    if not result.data:
        raise ValueError("Failed to create meeting")

    meeting_id = result.data[0]["id"]

    # Insert segments if provided
    if segments_data:
        create_segments(segments_data, meeting_id)

    return result.data[0]


def get_meetings(user_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
    """
    Get meetings from the database with optional filtering.

    Args:
        user_id: Optional user ID. If None, only published meetings are returned.
        status: Optional status filter ('draft' or 'published')

    Returns:
        List of meeting dictionaries
    """
    query = supabase.table("meetings").select("*")

    # If no user is provided (public access), only show published meetings
    if user_id is None:
        query = query.eq("status", "published")
    # If status filter is provided, apply it
    elif status is not None:
        query = query.eq("status", status)

    # Execute query
    result = query.execute()

    return result.data


def get_meeting_by_id(meeting_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
    """
    Get a specific meeting by ID.

    Args:
        meeting_id: ID of the meeting to retrieve
        user_id: Optional user ID. If None, only published meetings are returned.

    Returns:
        Meeting dictionary or None if not found
    """
    query = supabase.table("meetings").select("*").eq("id", meeting_id)

    # If no user is provided (public access), only show published meetings
    if user_id is None:
        query = query.eq("status", "published")

    result = query.execute()

    if not result.data:
        return None

    return result.data[0]


def update_meeting(meeting_id: str, meeting_data: Dict, user_id: str) -> Optional[Dict]:
    """
    Update an existing meeting.

    Args:
        meeting_id: ID of the meeting to update
        meeting_data: Dictionary containing updated meeting information
        user_id: ID of the user updating the meeting

    Returns:
        Updated meeting dictionary or None if not found
    """
    # First verify the meeting exists
    existing_meeting = get_meeting_by_id(meeting_id, user_id)
    if not existing_meeting:
        return None

    # Extract segments data before updating the meeting
    segments_data = meeting_data.pop("segments", None)

    # Update meeting in database
    result = (
        supabase.table("meetings")
        .update(
            {
                "type": meeting_data.get("meeting_type"),
                "theme": meeting_data.get("theme"),
                "manager_id": meeting_data.get("meeting_manager"),
                "date": meeting_data.get("date"),
                "start_time": meeting_data.get("start_time"),
                "end_time": meeting_data.get("end_time"),
                "location": meeting_data.get("location"),
                "introduction": meeting_data.get("introduction"),
                # Don't update status here - that's handled by update_meeting_status
            }
        )
        .eq("id", meeting_id)
        .execute()
    )

    if not result.data:
        return None

    # If segments were provided, update them
    # This is a simplistic approach - a more robust solution would need to handle
    # adding, updating, and removing segments
    if segments_data is not None:
        # Delete existing segments
        supabase.table("segments").delete().eq("meeting_id", meeting_id).execute()
        # Create new segments
        create_segments(segments_data, meeting_id)

    return result.data[0]


def update_meeting_status(meeting_id: str, status: str, user_id: str) -> Optional[Dict]:
    """
    Update the status of a meeting.

    Args:
        meeting_id: ID of the meeting to update
        status: New status ('draft' or 'published')
        user_id: ID of the user updating the meeting status

    Returns:
        Updated meeting dictionary or None if not found
    """
    # First verify the meeting exists
    existing_meeting = get_meeting_by_id(meeting_id, user_id)
    if not existing_meeting:
        return None

    # Update meeting status
    result = supabase.table("meetings").update({"status": status}).eq("id", meeting_id).execute()

    if not result.data:
        return None

    return result.data[0]


def create_segments(segments_data: List[Dict], meeting_id: str) -> List[Dict]:
    """
    Create segments for a meeting.

    Args:
        segments_data: List of dictionaries containing segment information
        meeting_id: ID of the meeting these segments belong to

    Returns:
        List of dictionaries containing the created segments data
    """
    segments_to_insert = []

    for segment in segments_data:
        segments_to_insert.append(
            {
                "meeting_id": meeting_id,
                "attendee_id": segment.get("role_taker"),  # This should be an attendee ID
                "type": segment.get("segment_type"),
                "start_time": segment.get("start_time"),
                "duration": segment.get("duration"),
                "end_time": segment.get("end_time"),
                "title": segment.get("title"),
                "content": segment.get("content"),
                "related_segment_ids": segment.get("related_segment_ids"),
            }
        )

    if segments_to_insert:
        result = supabase.table("segments").insert(segments_to_insert).execute()
        return result.data

    return []
