from typing import Dict, List

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
