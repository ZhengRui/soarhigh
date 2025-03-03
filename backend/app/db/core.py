import uuid
from typing import Dict, List, Optional

from .supabase import create_user_client, supabase


def get_members():
    return supabase.table("members").select("id, username, full_name").execute().data


def resolve_attendee_id(member_id_or_name: str) -> str:
    """
    Resolves a member ID or custom name to an attendee ID.
    - If input is a valid UUID (member ID): finds or creates an attendee record for that member
    - If input is not a UUID: creates a guest attendee with the provided name

    Args:
        member_id_or_name: Either a member ID (UUID) or a custom name string

    Returns:
        The ID of the corresponding attendee
    """

    # Check if the input is a valid UUID (member ID)
    try:
        uuid.UUID(member_id_or_name)
        is_valid_uuid = True
    except (ValueError, AttributeError):
        is_valid_uuid = False

    # If it's not a valid UUID, create a guest attendee with the provided name
    if not is_valid_uuid:
        guest_name = member_id_or_name

        # Check if the guest name already exists
        # role taker better pass in a member id or a unique name, otherwise it will
        # clash with other guest attendees
        result = supabase.table("attendees").select("id").eq("name", guest_name).execute()
        if result.data:
            return result.data[0]["id"]

        # Create a new guest attendee
        create_result = supabase.table("attendees").insert({"name": guest_name, "type": "Guest"}).execute()

        if not create_result.data:
            raise ValueError("Failed to create guest attendee")

        return create_result.data[0]["id"]

    # If it's a valid UUID, proceed with member lookup
    # First try to find an existing attendee for this member
    result = supabase.table("attendees").select("id").eq("member_id", member_id_or_name).execute()

    if result.data:
        # Attendee exists, return the ID
        return result.data[0]["id"]

    # No attendee exists, get member info to create one
    member_result = supabase.table("members").select("full_name").eq("id", member_id_or_name).execute()

    if not member_result.data:
        raise ValueError(f"Member with ID {member_id_or_name} not found")

    # Create a new attendee for this member
    member_name = member_result.data[0]["full_name"]
    create_result = (
        supabase.table("attendees")
        .insert({"name": member_name, "type": "Member", "member_id": member_id_or_name})
        .execute()
    )

    if not create_result.data:
        raise ValueError("Failed to create attendee for member")

    return create_result.data[0]["id"]


def create_meeting(meeting_data: Dict) -> Dict:
    """
    Create a new meeting in the database.

    Args:
        meeting_data: Dictionary containing meeting information

    Returns:
        Dictionary containing the created meeting data including ID
    """
    # We need to extract segments data before inserting the meeting
    segments_data = meeting_data.get("segments", [])

    # Handle member_id to attendee_id mapping
    member_id = meeting_data.get("meeting_manager_id", "")
    # If meeting_manager_id is empty, set a default value of "TBD"
    if not member_id:
        member_id = "TBD"

    # Resolve the member_id or name to an attendee_id
    attendee_id = resolve_attendee_id(member_id)
    meeting_data["meeting_manager"] = attendee_id

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
        List of meeting dictionaries with their segments
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
    meetings = result.data

    if not meetings:
        return []

    manager_ids = [meeting["manager_id"] for meeting in meetings]
    result = supabase.table("attendees").select("*").in_("id", manager_ids).execute()
    manager_map = {manager["id"]: manager for manager in result.data}
    for meeting in meetings:
        manager_id = meeting.pop("manager_id")
        if manager_id not in manager_map:
            meeting["manager"] = {"id": manager_id, "name": "", "member_id": ""}
        else:
            manager = manager_map[manager_id]
            meeting["manager"] = {
                "id": manager_id,
                "name": manager["name"],
                "member_id": manager["member_id"],
            }

    # Get all meeting IDs
    meeting_ids = [meeting["id"] for meeting in meetings]

    # Batch fetch all segments for these meetings in a single query
    all_segments_result = supabase.table("segments").select("*").in_("meeting_id", meeting_ids).execute()

    # Collect all unique attendee IDs from segments using a set comprehension
    attendee_ids = set(segment["attendee_id"] for segment in all_segments_result.data if segment["attendee_id"])

    # Create a mapping of attendee details if there are any attendees
    attendee_map = {}
    if attendee_ids:
        # Batch fetch all attendee details in a single query
        attendee_details_result = supabase.table("attendees").select("*").in_("id", list(attendee_ids)).execute()

        # Create a mapping of attendee ID to name
        attendee_map = {
            attendee["id"]: {"name": attendee.get("name", ""), "member_id": attendee.get("member_id", "")}
            for attendee in attendee_details_result.data
        }

    # Group segments by meeting_id
    segments_by_meeting: Dict[str, List[Dict]] = {}
    for segment in all_segments_result.data:
        meeting_id = segment["meeting_id"]
        if meeting_id not in segments_by_meeting:
            segments_by_meeting[meeting_id] = []
        segments_by_meeting[meeting_id].append(segment)

    # Assign segments to meetings with proper attendee names
    for meeting in meetings:
        meeting_segments = segments_by_meeting.get(meeting["id"], [])
        processed_segments = []

        for segment in meeting_segments:
            attendee_id = segment["attendee_id"]
            if attendee_id:
                role_taker = attendee_map[attendee_id]
            else:
                role_taker = None

            hours, minutes, _ = map(int, segment["duration"].split(":"))
            duration_minutes = str(hours * 60 + minutes)

            processed_segments.append(
                {
                    "id": segment["id"],
                    "type": segment["type"],
                    "start_time": segment["start_time"][:5],
                    "duration": duration_minutes,
                    "end_time": segment["end_time"][:5],
                    "role_taker": role_taker,
                    "title": segment["title"],
                    "content": segment["content"],
                    "related_segment_ids": segment["related_segment_ids"],
                    # "meeting_id": segment["meeting_id"],
                }
            )

        meeting["segments"] = processed_segments

    return meetings


def get_meeting_by_id(meeting_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
    """
    Get a specific meeting by ID.

    Args:
        meeting_id: ID of the meeting to retrieve
        user_id: Optional user ID. If None, only published meetings are returned.

    Returns:
        Meeting dictionary with segments or None if not found
    """
    query = supabase.table("meetings").select("*").eq("id", meeting_id)

    # If no user is provided (public access), only show published meetings
    if user_id is None:
        query = query.eq("status", "published")

    result = query.execute()

    if not result.data:
        return None

    meeting = result.data[0]

    manager_id = meeting.pop("manager_id")
    result = supabase.table("attendees").select("*").eq("id", manager_id).execute()
    if not result.data:
        meeting["manager"] = {"id": manager_id, "name": "", "member_id": ""}
    else:
        manager = result.data[0]
        meeting["manager"] = {
            "id": manager_id,
            "name": manager["name"],
            "member_id": manager["member_id"],
        }

    # Fetch segments for this meeting
    segments_result = supabase.table("segments").select("*").eq("meeting_id", meeting_id).execute()
    segments_data = segments_result.data

    # If there are no segments, return early
    if not segments_data:
        meeting["segments"] = []
        return meeting

    # Collect all unique attendee IDs from segments using a set comprehension
    attendee_ids = set(segment["attendee_id"] for segment in segments_data if segment["attendee_id"])

    # Create a mapping of attendee details if there are any attendees
    attendee_map = {}
    if attendee_ids:
        # Batch fetch all attendee details in a single query
        attendee_details_result = supabase.table("attendees").select("*").in_("id", list(attendee_ids)).execute()

        # Create a mapping of attendee ID to name
        attendee_map = {
            attendee["id"]: {
                "id": attendee["id"],
                "name": attendee.get("name", ""),
                "member_id": attendee.get("member_id", ""),
            }
            for attendee in attendee_details_result.data
        }

    # Process segments with attendee names
    processed_segments = []
    for segment in segments_data:
        attendee_id = segment["attendee_id"]
        if attendee_id:
            role_taker = attendee_map[attendee_id]
        else:
            role_taker = None

        hours, minutes, _ = map(int, segment["duration"].split(":"))
        duration_minutes = str(hours * 60 + minutes)

        processed_segments.append(
            {
                "id": segment["id"],
                "type": segment["type"],
                "start_time": segment["start_time"][:5],
                "duration": duration_minutes,
                "end_time": segment["end_time"][:5],
                "role_taker": role_taker,
                "title": segment["title"],
                "content": segment["content"],
                "related_segment_ids": segment["related_segment_ids"],
                # "meeting_id": segment["meeting_id"],
            }
        )

    meeting["segments"] = processed_segments

    return meeting


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
    segments_data = meeting_data.get("segments", [])

    # Handle member_id to attendee_id mapping
    member_id = meeting_data.pop("meeting_manager_id", "")
    # If meeting_manager_id is empty, set a default value of "TBD"
    if not member_id:
        member_id = "TBD"

    # Resolve the member_id or name to an attendee_id
    attendee_id = resolve_attendee_id(member_id)
    meeting_data["manager_id"] = attendee_id

    # Update meeting in database
    result = (
        supabase.table("meetings")
        .update(
            {
                "type": meeting_data.get("meeting_type"),
                "theme": meeting_data.get("theme"),
                "manager_id": meeting_data.get("manager_id"),
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

    if segments_data:
        supabase.table("segments").delete().eq("meeting_id", meeting_id).execute()
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

    meeting = result.data[0]
    meeting["segments"] = existing_meeting["segments"]
    return meeting


def delete_meeting(meeting_id: str, user_id: str, user_token: str) -> bool:
    """
    Delete a meeting and its associated segments.

    Args:
        meeting_id: ID of the meeting to delete
        user_id: ID of the user deleting the meeting
        user_token: Token of the user deleting the meeting

    Returns:
        Boolean indicating success or failure
    """
    # First verify the meeting exists
    existing_meeting = get_meeting_by_id(meeting_id, user_id)
    if not existing_meeting:
        return False

    user_client = create_user_client(user_token)

    try:
        # Check permission using the database function that respects RLS
        # This will only return true if the user is allowed to delete the meeting
        permission_check = user_client.rpc("can_delete_meeting", {"meeting_id": meeting_id}).execute()

        # If the function returns false, the user doesn't have permission
        if not permission_check.data:
            print("Permission denied: User cannot delete this meeting")
            return False

        # Now we can safely proceed with deletion knowing RLS will allow it
        # Delete segments first (using a transaction would be better but not available in client)
        user_client.table("segments").delete().eq("meeting_id", meeting_id).execute()

        # Delete the meeting
        result = user_client.table("meetings").delete().eq("id", meeting_id).execute()

        return len(result.data) > 0
    except Exception as e:
        print(f"Error in delete_meeting: {e}")
        return False


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
        # For role_taker, we also need to convert member_id or name to attendee_id
        role_taker = segment.get("role_taker")
        attendee_id = None

        if role_taker:
            # This function now handles both member IDs and custom names
            attendee_id = resolve_attendee_id(role_taker)

        # Calculate end_time if it's empty or not provided
        start_time = segment.get("start_time")
        duration = segment.get("duration")
        end_time = segment.get("end_time")

        if start_time and duration and (not end_time or end_time == ""):
            # Convert start_time to minutes
            hours, minutes = map(int, start_time.split(":"))
            start_minutes = hours * 60 + minutes

            # Add duration
            duration_minutes = int(duration)
            total_minutes = start_minutes + duration_minutes

            # Convert back to HH:MM format
            end_hours = total_minutes // 60
            end_minutes = total_minutes % 60
            end_time = f"{end_hours:02d}:{end_minutes:02d}"

        # Format duration as a proper interval with 'minutes' unit
        formatted_duration = f"{duration} minutes" if duration else None

        segments_to_insert.append(
            {
                "meeting_id": meeting_id,
                "attendee_id": attendee_id,  # Use converted attendee ID
                "type": segment.get("segment_type"),
                "start_time": start_time,
                "duration": formatted_duration,  # Now explicitly specify minutes
                "end_time": end_time,
                "title": segment.get("title"),
                "content": segment.get("content"),
                "related_segment_ids": segment.get("related_segment_ids"),
            }
        )

    if segments_to_insert:
        result = supabase.table("segments").insert(segments_to_insert).execute()
        return result.data

    return []


def get_attendee_details(attendee_ids: List[str]) -> List[Dict]:
    """
    Get details about an attendee, including their member_id if available.

    Args:
        attendee_ids: List of IDs of the attendees to look up

    Returns:
        List of dictionaries with attendee details, including member_id and name
    """
    result = supabase.table("attendees").select("*").in_("id", attendee_ids).execute()

    details_map = {}
    for attendee in result.data:
        details_map[attendee["id"]] = {
            "name": attendee.get("name", ""),
            "member_id": attendee.get("member_id", ""),
        }

    attendee_details = []
    for attendee_id in attendee_ids:
        if attendee_id not in details_map:
            attendee_details.append({"name": "", "member_id": ""})
        else:
            attendee_details.append(details_map[attendee_id].copy())

    return attendee_details


def prepare_segment_data(segment: Dict, meeting_id: str) -> Dict:
    """
    Prepare segment data for insertion or update by handling role_taker,
    calculating end_time, and formatting duration.

    Args:
        segment: Dictionary containing segment information
        meeting_id: ID of the meeting this segment belongs to

    Returns:
        Dictionary prepared for database insertion/update
    """
    # For role_taker, convert to attendee_id
    role_taker = segment.get("role_taker", None)
    attendee_id = segment.get("attendee_id", None)
    if role_taker and not attendee_id:
        attendee_id = resolve_attendee_id(role_taker)

    # Calculate end_time if needed
    start_time = segment.get("start_time")
    duration = segment.get("duration")
    end_time = segment.get("end_time")

    if start_time and duration and (not end_time or end_time == ""):
        # Convert start_time to minutes
        hours, minutes = map(int, start_time.split(":"))
        start_minutes = hours * 60 + minutes

        # Add duration
        duration_minutes = int(duration)
        total_minutes = start_minutes + duration_minutes

        # Convert back to HH:MM format
        end_hours = total_minutes // 60
        end_minutes = total_minutes % 60
        end_time = f"{end_hours:02d}:{end_minutes:02d}"

    # Format duration as a proper interval
    formatted_duration = f"{duration} minutes" if duration else None

    return {
        "meeting_id": meeting_id,
        "attendee_id": attendee_id,
        "type": segment.get("segment_type"),
        "start_time": start_time,
        "duration": formatted_duration,
        "end_time": end_time,
        "title": segment.get("title"),
        "content": segment.get("content"),
        "related_segment_ids": segment.get("related_segment_ids"),
    }
