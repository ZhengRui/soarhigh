import uuid
from typing import Any, Dict, List, Optional, Union

from ..models.users import User
from ..models.wechat_user import WeChatUser
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
        result = supabase.table("attendees").select("id").eq("name", guest_name).eq("type", "Guest").execute()
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
    manager = meeting_data.get("manager") or {}
    member_id = manager.get("member_id") or ""
    name = manager.get("name") or ""

    # Resolve the member_id or name to an attendee_id
    attendee_id = resolve_attendee_id(member_id or name or "TBD")

    # Insert meeting into database
    result = (
        supabase.table("meetings")
        .insert(
            {
                "type": meeting_data.get("type"),
                "no": meeting_data.get("no"),
                "theme": meeting_data.get("theme"),
                "manager_id": attendee_id,
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

    meeting = result.data[0]
    meeting.pop("manager_id")
    meeting["manager"] = manager
    meeting_id = meeting["id"]

    # Insert segments if provided
    if segments_data:
        segments_db = create_segments(segments_data, meeting_id)

        for s, s_db in zip(segments_data, segments_db):
            s["id"] = s_db["id"]

    meeting["segments"] = segments_data

    return meeting


def get_meetings(
    user_id: Optional[str] = None, status: Optional[str] = None, page: int = 1, page_size: int = 10
) -> Dict[str, Any]:
    """
    Get meetings with optional filtering by user_id and status with pagination support.

    Args:
        user_id: Optional ID of user to filter meetings by
        status: Optional status to filter meetings by (draft or published)
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Dictionary containing paginated meetings data and pagination metadata
    """
    # Calculate offset for pagination
    offset = (page - 1) * page_size

    # Base query with select first, then filters
    query = supabase.table("meetings").select("*")

    # Apply filters after select
    if user_id is None:
        query = query.eq("status", "published")
    elif status is not None:
        query = query.eq("status", status)

    # Get total count first for pagination metadata
    # Create a separate count query
    count_query = supabase.table("meetings").select("id", count="exact")  # type: ignore

    # Apply the same filters to the count query
    if user_id is None:
        count_query = count_query.eq("status", "published")
    elif status is not None:
        count_query = count_query.eq("status", status)

    count_result = count_query.execute()
    total_count = count_result.count or 0

    # Now get paginated data
    result = query.order("date", desc=True).range(offset, offset + page_size - 1).execute()
    meetings = result.data

    if not meetings:
        return {
            "items": [],
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "pages": (total_count + page_size - 1) // page_size if total_count > 0 else 1,
        }

    # Process the meetings data as in the original function
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
                "member_id": manager["member_id"] or "",
            }

    # Get all meeting IDs
    meeting_ids = [meeting["id"] for meeting in meetings]

    # Batch fetch all segments for these meetings in a single query
    all_segments_result = (
        supabase.table("segments").select("*").in_("meeting_id", meeting_ids).order("start_time", desc=False).execute()
    )

    # Collect all unique attendee IDs from segments using a set comprehension
    attendee_ids = set(segment["attendee_id"] for segment in all_segments_result.data if segment["attendee_id"])

    # Create a mapping of attendee details if there are any attendees
    attendee_map = {}
    if attendee_ids:
        # Batch fetch all attendee details in a single query
        attendee_details_result = supabase.table("attendees").select("*").in_("id", list(attendee_ids)).execute()

        # Create a mapping of attendee ID to name
        attendee_map = {
            attendee["id"]: {
                "name": attendee.get("name") or "",
                "member_id": attendee.get("member_id") or "",
            }
            for attendee in attendee_details_result.data
        }

    # Group segments by meeting_id
    segments_by_meeting: Dict[str, List[Dict]] = {}
    for segment in all_segments_result.data:
        meeting_id = segment["meeting_id"]
        if meeting_id not in segments_by_meeting:
            segments_by_meeting[meeting_id] = []
        segments_by_meeting[meeting_id].append(segment)

    # Batch fetch all awards for these meetings in a single query
    all_awards_result = supabase.table("awards").select("*").in_("meeting_id", meeting_ids).execute()

    # Group awards by meeting_id
    awards_by_meeting: Dict[str, List[Dict]] = {}
    for award in all_awards_result.data:
        meeting_id = award["meeting_id"]
        if meeting_id not in awards_by_meeting:
            awards_by_meeting[meeting_id] = []
        awards_by_meeting[meeting_id].append(award)

    # Assign segments and awards to meetings
    for meeting in meetings:
        # Process segments
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

        # Process awards
        meeting_awards = awards_by_meeting.get(meeting["id"], [])
        if meeting_awards:
            meeting["awards"] = meeting_awards
        else:
            meeting["awards"] = []

    # Return paginated meetings with metadata
    return {
        "items": meetings,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "pages": (total_count + page_size - 1) // page_size if total_count > 0 else 1,
    }


def get_meeting_by_id(meeting_id: str, user_id: Optional[str] = None) -> Optional[Dict]:
    """
    Get a specific meeting by ID.

    Args:
        meeting_id: ID of the meeting to retrieve
        user_id: Optional user ID. If None, only published meetings are returned.

    Returns:
        Meeting dictionary with segments and awards or None if not found
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
            "member_id": manager["member_id"] or "",
        }

    # Fetch segments for this meeting
    segments_result = (
        supabase.table("segments").select("*").eq("meeting_id", meeting_id).order("start_time", desc=False).execute()
    )
    segments_data = segments_result.data

    # Fetch awards for this meeting
    awards_result = supabase.table("awards").select("*").eq("meeting_id", meeting_id).execute()
    meeting["awards"] = awards_result.data or []

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
                "name": attendee.get("name") or "",
                "member_id": attendee.get("member_id") or "",
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

    existing_segments = existing_meeting.pop("segments", [])

    manager = meeting_data.get("manager") or {}
    member_id = manager.get("member_id") or ""
    name = manager.get("name") or ""

    diff = {}
    for key, value in existing_meeting.items():
        if key == "awards":
            continue

        if key == "manager":
            existing_manager = value or {}
            existing_member_id = existing_manager.get("member_id") or ""
            existing_name = existing_manager.get("name") or ""

            if member_id != existing_member_id or name != existing_name:
                diff["manager_id"] = resolve_attendee_id(member_id or name or "TBD")

        elif key in meeting_data and meeting_data[key] != value:
            diff[key] = meeting_data[key]

    if diff:
        supabase.table("meetings").update(diff).eq("id", meeting_id).execute()

    segments_data = meeting_data.get("segments", [])

    ids = set([segment["id"] for segment in segments_data])
    existing_ids = set([segment["id"] for segment in existing_segments])
    existing_by_ids = {segment["id"]: segment for segment in existing_segments}

    ids_to_delete = list(existing_ids - ids)
    segments_to_add = []
    segments_to_update = []

    for segment in segments_data:
        segment_id = segment["id"]

        if segment_id not in existing_ids:
            segments_to_add.append(segment)
            continue

        existing_segment = existing_by_ids[segment_id]

        for key, value in existing_segment.items():
            if key == "attendee_id":
                role_taker = segment.get("role_taker") or {}
                member_id = role_taker.get("member_id") or ""
                name = role_taker.get("name") or ""

                existing_role_taker = existing_segment.get("role_taker") or {}
                existing_member_id = existing_role_taker.get("member_id") or ""
                existing_name = existing_role_taker.get("name") or ""

                if member_id != existing_member_id or (
                    not member_id and not existing_member_id and name != existing_name
                ):
                    segments_to_update.append(segment)
                    break

            elif value != segment[key]:
                segments_to_update.append(segment)
                break

    if ids_to_delete:
        supabase.table("segments").delete().in_("id", ids_to_delete).execute()

    if segments_to_update:
        segments_to_update = [
            prepare_segment_data(segment, meeting_id, ignore_id=False) for segment in segments_to_update
        ]
        supabase.table("segments").upsert(segments_to_update).execute()

    if segments_to_add:
        segments_to_add = [prepare_segment_data(segment, meeting_id, ignore_id=False) for segment in segments_to_add]
        supabase.table("segments").insert(segments_to_add).execute()

    meeting_data["id"] = meeting_id

    return meeting_data


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
    meeting.pop("manager_id")
    meeting["manager"] = existing_meeting["manager"]

    return meeting


def delete_meeting(meeting_id: str, user_id: str, user_token: str) -> bool:
    """
    Delete a meeting and its associated segments and awards.

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
        # Delete awards first
        user_client.table("awards").delete().eq("meeting_id", meeting_id).execute()

        # Delete votes next
        user_client.table("votes").delete().eq("meeting_id", meeting_id).execute()

        # Delete votes_status next
        user_client.table("votes_status").delete().eq("meeting_id", meeting_id).execute()

        # Delete feedbacks next
        user_client.table("feedbacks").delete().eq("meeting_id", meeting_id).execute()

        # Delete checkins next
        user_client.table("checkins").delete().eq("meeting_id", meeting_id).execute()

        # Delete segments next
        user_client.table("segments").delete().eq("meeting_id", meeting_id).execute()

        # Delete the meeting
        result = user_client.table("meetings").delete().eq("id", meeting_id).execute()

        return len(result.data) > 0
    except Exception as e:
        print(f"Error in delete_meeting: {e}")
        return False


def get_awards_by_meeting(meeting_id: str) -> List[Dict]:
    """
    Get all awards for a specific meeting.

    Args:
        meeting_id: The ID of the meeting to get awards for.

    Returns:
        List[Dict]: A list of award dictionaries.
    """
    result = supabase.table("awards").select("*").eq("meeting_id", meeting_id).execute()

    return result.data


def save_meeting_awards(meeting_id: str, awards_data: List[Dict], user_id: str) -> List[Dict]:
    """
    Replace all awards for a meeting.

    This function deletes all existing awards for the meeting and creates new ones
    based on the provided data.

    Args:
        meeting_id: The ID of the meeting to save awards for.
        awards_data: A list of award dictionaries to save.
        user_id: The ID of the user performing the operation.

    Returns:
        List[Dict]: The newly created awards with IDs.

    Raises:
        ValueError: If the meeting is not found or the user doesn't have permission.
    """
    # Verify the meeting exists and the user has permission to modify it
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise ValueError(f"Meeting with ID {meeting_id} not found")

    # Begin a transaction
    # Step 1: Delete all existing awards for the meeting
    supabase.table("awards").delete().eq("meeting_id", meeting_id).execute()

    # Step 2: Create new awards if there are any
    new_awards = []
    if awards_data:
        # Prepare award data for insertion
        awards_to_insert = []
        for award in awards_data:
            awards_to_insert.append(
                {"meeting_id": meeting_id, "category": award.get("category"), "winner": award.get("winner")}
            )

        # Insert new awards
        if awards_to_insert:
            result = supabase.table("awards").insert(awards_to_insert).execute()
            new_awards = result.data

    return new_awards


def create_segments(segments_data: List[Dict], meeting_id: str) -> List[Dict]:
    """
    Create segments for a meeting.

    Args:
        segments_data: List of dictionaries containing segment information
        meeting_id: ID of the meeting these segments belong to

    Returns:
        List of dictionaries containing the created segments data
    """
    segments_to_insert = [prepare_segment_data(segment, meeting_id) for segment in segments_data]

    if segments_to_insert:
        result = supabase.table("segments").insert(segments_to_insert).execute()
        return result.data

    return []


def prepare_segment_data(segment: Dict, meeting_id: str, ignore_id: bool = True) -> Dict:
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
    role_taker = segment.get("role_taker") or {}
    member_id = role_taker.get("member_id") or ""
    name = role_taker.get("name") or ""
    attendee_id = None

    if member_id or name:
        attendee_id = resolve_attendee_id(member_id or name)

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

    prepared_segment = {
        "meeting_id": meeting_id,
        "attendee_id": attendee_id,
        "type": segment.get("type"),
        "start_time": start_time,
        "duration": formatted_duration,
        "end_time": end_time,
        "title": segment.get("title"),
        "content": segment.get("content"),
        "related_segment_ids": segment.get("related_segment_ids"),
    }

    if not ignore_id and segment.get("id"):
        prepared_segment["id"] = segment["id"]

    return prepared_segment


def get_posts(user_id: Optional[str] = None, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
    """
    Get a paginated list of posts.
    - If user_id is provided, returns all posts
    - If user_id is None, returns only public posts

    Args:
        user_id: The ID of the authenticated user (None for anonymous users)
        page: The page number to retrieve
        page_size: The number of items per page

    Returns:
        A dictionary with pagination info and a list of posts with author details
    """
    # Calculate pagination values
    offset = (page - 1) * page_size

    # First, get the total count
    count_query = supabase.table("posts").select("id", count="exact")  # type: ignore

    # For anonymous users, only return public posts
    if user_id is None:
        count_query = count_query.eq("is_public", True)

    count_response = count_query.execute()
    total = count_response.count or 0

    # Calculate pagination
    pages = (total + page_size - 1) // page_size if total > 0 else 0

    # Now get the actual data with pagination
    data_query = supabase.table("posts").select("*")

    # Apply filters
    if user_id is None:
        data_query = data_query.eq("is_public", True)

    # Apply sorting and pagination
    data_query = data_query.order("created_at", desc=True).range(offset, offset + page_size - 1)

    # Execute the query
    data_response = data_query.execute()
    posts = data_response.data if hasattr(data_response, "data") else []

    # Fetch authors for these posts
    if posts:
        author_ids = [post["author_id"] for post in posts]
        authors_query = supabase.table("members").select("id, full_name").in_("id", author_ids)
        authors_response = authors_query.execute()
        authors = (
            {author["id"]: {"member_id": author["id"], "name": author["full_name"]} for author in authors_response.data}
            if authors_response.data
            else {}
        )

        # Add author information to each post
        for post in posts:
            author_id = post["author_id"]
            post["author"] = authors.get(author_id, {"member_id": author_id, "name": ""})

    return {
        "items": posts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def get_post_by_slug(slug: str, user_id: Optional[str] = None) -> Optional[Dict]:
    """
    Get a post by its slug.
    - If user_id is provided, can access any post
    - If user_id is None, can only access public posts

    Args:
        slug: The slug of the post to retrieve
        user_id: The ID of the authenticated user (None for anonymous users)

    Returns:
        The post data with author information, or None if not found/accessible
    """
    # Build the query
    query = supabase.table("posts").select("*").eq("slug", slug)

    # For anonymous users, only allow access to public posts
    if user_id is None:
        query = query.eq("is_public", True)

    # Execute the query
    response = query.execute()

    if not response.data:
        return None

    post = response.data[0]

    # Fetch author information
    author_id = post["author_id"]
    author_query = supabase.table("members").select("id, full_name").eq("id", author_id)
    author_response = author_query.execute()

    if author_response.data:
        author = author_response.data[0]
        post["author"] = {"member_id": author["id"], "name": author["full_name"]}
    else:
        post["author"] = {"member_id": author_id, "name": ""}

    return post


def create_post(post_data: Dict, user_id: str) -> Dict:
    """
    Create a new post.

    Args:
        post_data: The post data to insert
        user_id: The ID of the authenticated user creating the post

    Returns:
        The created post data with author information
    """
    # Prepare post data for database
    db_post_data = post_data.copy()

    # Add required fields
    db_post_data["author_id"] = user_id

    # Remove nested author if present
    if "author" in db_post_data:
        del db_post_data["author"]

    # Insert the post
    insert_response = supabase.table("posts").insert(db_post_data).execute()

    if not insert_response.data:
        return {}

    # Get the created post
    post = insert_response.data[0]

    # Fetch author information
    author_query = supabase.table("members").select("id, full_name").eq("id", user_id)
    author_response = author_query.execute()

    if author_response.data:
        author = author_response.data[0]
        post["author"] = {"member_id": author["id"], "name": author["full_name"]}
    else:
        post["author"] = {"member_id": user_id, "name": ""}

    return post


def update_post(post_data: Dict, user_id: str) -> Optional[Dict]:
    """
    Update an existing post.

    Args:
        post_data: The updated post data
        user_id: The ID of the authenticated user updating the post

    Returns:
        The updated post data with author information, or None if not found/accessible
    """
    post_id = post_data["id"]
    # First, check if post exists and get its ID
    find_query = supabase.table("posts").select("id, author_id").eq("id", post_id)
    existing_post = find_query.execute().data

    if not existing_post:
        return None

    # Ensure user is the author. Currently disabled to allow editing by any member.
    # if existing_post[0]["author_id"] != user_id:
    #     return None

    # Prepare update data
    update_data = post_data.copy()

    # Remove fields that shouldn't be updated
    if "id" in update_data:
        del update_data["id"]
    if "author_id" in update_data:
        del update_data["author_id"]
    if "author" in update_data:
        del update_data["author"]
    if "created_at" in update_data:
        del update_data["created_at"]

    # Set updated_at to now
    update_data["updated_at"] = "now()"

    # Update the post
    update_response = supabase.table("posts").update(update_data).eq("id", post_id).execute()

    if not update_response.data:
        return None

    # Get the updated post
    post = update_response.data[0]

    # Fetch author information
    author_query = supabase.table("members").select("id, full_name").eq("id", user_id)
    author_response = author_query.execute()

    if author_response.data:
        author = author_response.data[0]
        post["author"] = {"member_id": author["id"], "name": author["full_name"]}
    else:
        post["author"] = {"member_id": user_id, "name": ""}

    return post


def delete_post(slug: str, user_id: str) -> bool:
    """
    Delete a post.

    Args:
        slug: The slug of the post to delete
        user_id: The ID of the authenticated user deleting the post

    Returns:
        True if the post was deleted, False otherwise
    """
    # First, check if post exists and belongs to the user
    find_query = supabase.table("posts").select("id, author_id").eq("slug", slug)
    existing_post = find_query.execute().data

    if not existing_post:
        return False

    post_id = existing_post[0]["id"]

    # Check if user is the author
    is_author = existing_post[0]["author_id"] == user_id

    # Check if user is an admin
    is_admin = is_user_admin(user_id)

    # Ensure user is the author or admin
    if not (is_author or is_admin):
        return False

    # Delete the post
    delete_query = supabase.table("posts").delete().eq("id", post_id)
    response = delete_query.execute()

    return len(response.data) > 0


def get_votes_status(meeting_id: str) -> Optional[Dict]:
    """
    Get the voting status for a meeting.

    Args:
        meeting_id: The ID of the meeting

    Returns:
        Vote status object or None if not found
    """
    response = supabase.table("votes_status").select("*").eq("meeting_id", meeting_id).execute()

    if not response.data:
        return None

    return response.data[0]


def get_votes_by_meeting(meeting_id: str) -> List[Dict]:
    """
    Get all votes for a meeting.

    Args:
        meeting_id: The ID of the meeting

    Returns:
        List of vote objects sorted by creation time
    """
    response = (
        supabase.table("votes").select("*").eq("meeting_id", meeting_id).order("created_at", desc=False).execute()
    )

    return response.data


def update_votes_status(meeting_id: str, is_open: bool, user_id: str) -> Optional[Dict]:
    """
    Update the voting status for a meeting (open or close).

    Args:
        meeting_id: The ID of the meeting
        is_open: True to open voting, False to close
        user_id: The ID of the user making the change

    Returns:
        Updated vote status or None if meeting not found/accessible
    """
    # Check if the meeting exists and user can manage it
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        return None

    # Currently, any member can update voting status
    # TODO: Add permission check if needed

    # Check if status record exists
    existing_status = get_votes_status(meeting_id)

    if existing_status:
        # Update existing status
        update_data = {"open": is_open}

        response = supabase.table("votes_status").update(update_data).eq("id", existing_status["id"]).execute()
        return response.data[0] if response.data else None
    else:
        # Create new status
        new_status = {
            "meeting_id": meeting_id,
            "open": is_open,
        }

        response = supabase.table("votes_status").insert(new_status).execute()
        return response.data[0] if response.data else None


def save_vote_form(meeting_id: str, vote_form: List[Dict], user_id: str) -> List[Dict]:
    """
    Save the vote form configuration for a meeting. This function creates or updates
    vote records for each category and candidate.

    Args:
        meeting_id: The ID of the meeting
        vote_form: List of objects with category and candidates fields
        user_id: The ID of the user saving the form

    Returns:
        List of created/updated vote objects
    """
    # Check if the meeting exists
    meeting = get_meeting_by_id(meeting_id, user_id)
    if not meeting:
        raise ValueError("Meeting not found")

    # Currently, any member can update the vote form
    # TODO: Add permission check if needed

    # Get existing votes to avoid duplicates
    existing_votes = get_votes_by_meeting(meeting_id)
    existing_map = {f"{v['category']}|{v['name']}": v for v in existing_votes}

    # Prepare records to insert and update
    records_to_insert = []
    records_to_update = []
    processed_keys = set()

    # Process each category and candidate
    for category_item in vote_form:
        if "category" not in category_item or "candidates" not in category_item:
            continue

        category = category_item["category"]
        candidates = category_item["candidates"]

        if not category or not isinstance(candidates, list):
            continue

        for candidate in candidates:
            if not candidate:
                continue

            key = f"{category}|{candidate['name']}"

            if key in processed_keys:
                raise ValueError(
                    f"Duplicate candidate '{candidate['name']}' in category '{category}'. "
                    f"Each candidate name must be unique within a category."
                )

            processed_keys.add(key)

            if key in existing_map:
                if candidate["segment"] != existing_map[key]["segment"]:
                    # Include all fields from existing record, then update segment
                    update_record = existing_map[key].copy()
                    update_record["segment"] = candidate["segment"]
                    records_to_update.append(update_record)
            else:
                # New record
                records_to_insert.append(
                    {
                        "meeting_id": meeting_id,
                        "category": category,
                        "name": candidate["name"],
                        "segment": candidate["segment"],
                        "count": 0,
                    }
                )

    # Delete votes that are no longer in the form - in batch if possible
    to_delete_ids = []
    if processed_keys and existing_votes:
        for existing_vote in existing_votes:
            key = f"{existing_vote['category']}|{existing_vote['name']}"
            if key not in processed_keys:
                to_delete_ids.append(existing_vote["id"])

    # Process the database operations
    # Update existing records in batch
    if records_to_update:
        supabase.table("votes").upsert(records_to_update).execute()

    # Insert new records in batch
    if records_to_insert:
        supabase.table("votes").insert(records_to_insert).execute()

    # Delete votes that are no longer in the form - in batch if possible
    if to_delete_ids:
        supabase.table("votes").delete().in_("id", to_delete_ids).execute()

    return vote_form


def cast_votes(meeting_id: str, votes: List[Dict[str, str]]) -> List[Dict]:
    """
    Cast multiple votes at once by incrementing the count for specified candidates in categories.

    Args:
        meeting_id: The ID of the meeting
        votes: List of dicts with 'category' and 'name' keys

    Returns:
        List of updated vote objects
    """
    # First, check if the meeting has ended (current time is after end_time)
    meeting_data = supabase.table("meetings").select("end_time, date").eq("id", meeting_id).execute()

    if meeting_data.data:
        from datetime import datetime

        meeting = meeting_data.data[0]
        meeting_date = meeting.get("date")
        meeting_end_time = meeting.get("end_time")

        if meeting_date and meeting_end_time:
            # Create meeting end datetime
            meeting_datetime_str = f"{meeting_date} {meeting_end_time}"
            try:
                meeting_end = datetime.strptime(meeting_datetime_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Try alternative format if the first one fails
                meeting_end = datetime.strptime(meeting_datetime_str, "%Y-%m-%d %H:%M")

            # Get current time
            current_time = datetime.now()

            # If current time is after meeting end time, treat as closed
            if current_time > meeting_end:
                return []

    # Check if voting is open
    status = get_votes_status(meeting_id)
    if not status or not status["open"]:
        return []

    # Validate and process each vote
    if not votes:
        return []

    # First, get all existing votes for this meeting to validate vote existence
    all_votes = get_votes_by_meeting(meeting_id)
    vote_map = {f"{v['category']}|{v['name']}": v for v in all_votes}

    # Prepare valid votes for batch processing
    valid_votes = []
    for vote in votes:
        if "category" not in vote or "name" not in vote:
            continue

        key = f"{vote['category']}|{vote['name']}"
        if key in vote_map:
            valid_votes.append({"category": vote["category"], "name": vote["name"]})

    # If no valid votes, return early
    if not valid_votes:
        return []

    # Use the PostgreSQL function for atomic increments
    # This handles concurrent voting safely at the database level
    result = supabase.rpc("increment_votes", {"meeting_id_param": meeting_id, "vote_data": valid_votes}).execute()

    if result.data:
        return result.data

    return []


# Checkins functions
def create_checkins(
    meeting_id: str, wxid: str, segment_ids: List[str], name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Create checkins for a user, replacing any existing ones for the same meeting."""
    # First delete existing checkins for this wxid + meeting_id
    supabase.table("checkins").delete().eq("meeting_id", meeting_id).eq("wxid", wxid).execute()

    # Create new checkin records
    checkins_data = []
    for segment_id in segment_ids:
        checkin_data = {"meeting_id": meeting_id, "wxid": wxid, "segment_id": segment_id, "name": name}
        checkins_data.append(checkin_data)

    if checkins_data:
        result = supabase.table("checkins").insert(checkins_data).execute()
        return result.data

    return []


def get_checkins_by_meeting(meeting_id: str, wxid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get checkins for a meeting, optionally filtered by wxid."""
    query = supabase.table("checkins").select("*").eq("meeting_id", meeting_id)

    if wxid:
        query = query.eq("wxid", wxid)

    result = query.execute()
    return result.data


# Feedbacks functions
def create_feedback(
    meeting_id: str,
    wxid: str,
    feedback_type: str,
    value: str,
    segment_id: Optional[str] = None,
    to_attendee_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new feedback record."""
    feedback_data = {
        "meeting_id": meeting_id,
        "from_wxid": wxid,
        "type": feedback_type,
        "value": value,
        "segment_id": segment_id,
        "to_attendee_id": to_attendee_id,
    }

    result = supabase.table("feedbacks").insert(feedback_data).execute()
    return result.data[0] if result.data else {}


def get_feedbacks_by_meeting(
    meeting_id: str,
    wxid: Optional[str] = None,
    user_attendee_id: Optional[str] = None,
    is_admin: bool = False,
    feedback_type: Optional[str] = None,
    segment_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get feedbacks for a meeting with comprehensive access control and filtering.

    Implements sophisticated access control logic to ensure users only see feedbacks
    they are authorized to view:
    - Admin users: Can view all feedbacks for the meeting
    - Users with wxid: Can view feedbacks sent by their wxid + received by their attendee_id
    - Users with attendee_id only: Can view feedbacks received by their attendee_id
    - Additional filtering by feedback type and segment ID is applied on top of access control

    Args:
        meeting_id: The ID of the meeting to retrieve feedbacks for
        wxid: WeChat openid of the user (for sent feedback filtering)
        user_attendee_id: Attendee ID of the user (for received feedback filtering)
        is_admin: Whether the user has admin privileges (bypasses access control)
        feedback_type: Optional filter by feedback type (experience_*, segment, attendee)
        segment_id: Optional filter by specific segment ID

    Returns:
        List of feedback dictionaries matching the access control and filter criteria
    """
    query = supabase.table("feedbacks").select("*").eq("meeting_id", meeting_id)

    # Apply filters
    if feedback_type:
        query = query.eq("type", feedback_type)
    if segment_id:
        query = query.eq("segment_id", segment_id)

    # Get all feedbacks first, then filter based on access control
    result = query.execute()
    feedbacks = result.data

    if is_admin:
        return feedbacks

    # Apply access control filtering
    filtered_feedbacks = []
    for feedback in feedbacks:
        # User can see feedbacks they sent
        if wxid and feedback["from_wxid"] == wxid:
            filtered_feedbacks.append(feedback)
        # User can see feedbacks sent to their attendee_id
        elif user_attendee_id and feedback["to_attendee_id"] == user_attendee_id:
            filtered_feedbacks.append(feedback)

    return filtered_feedbacks


def update_feedback(feedback_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a feedback record."""
    result = supabase.table("feedbacks").update(updates).eq("id", feedback_id).execute()
    return result.data[0] if result.data else {}


def delete_feedback(feedback_id: str) -> bool:
    """Delete a feedback record."""
    result = supabase.table("feedbacks").delete().eq("id", feedback_id).execute()
    return len(result.data) > 0


def get_feedback_by_id(feedback_id: str) -> Optional[Dict[str, Any]]:
    """Get a feedback by ID."""
    result = supabase.table("feedbacks").select("*").eq("id", feedback_id).execute()
    return result.data[0] if result.data else None


def validate_segments_belong_to_meeting(meeting_id: str, segment_ids: List[str]) -> bool:
    """Validate that all segment IDs belong to the given meeting."""
    if not segment_ids:
        return True

    result = supabase.table("segments").select("id").eq("meeting_id", meeting_id).in_("id", segment_ids).execute()
    return len(result.data) == len(segment_ids)


def validate_attendee_id_exists(attendee_id: str) -> bool:
    """Validate that an attendee ID exists."""
    result = supabase.table("attendees").select("id").eq("id", attendee_id).execute()
    return len(result.data) > 0


# User authentication utility functions
def get_user_wxid(user_id: str) -> Optional[str]:
    """Get user's wxid from their attendee record."""
    result = supabase.table("attendees").select("wxid").eq("member_id", user_id).execute()
    if result.data and result.data[0].get("wxid"):
        return result.data[0]["wxid"]
    return None


def get_user_attendee_id(user_id: str) -> Optional[str]:
    """Get user's attendee_id from their member record."""
    result = supabase.table("attendees").select("id").eq("member_id", user_id).execute()
    if result.data:
        return result.data[0]["id"]
    return None


def get_attendee_id_by_wxid(wxid: str) -> Optional[str]:
    """Get attendee_id for a given wxid."""
    result = supabase.table("attendees").select("id").eq("wxid", wxid).execute()
    if result.data:
        return result.data[0]["id"]
    return None


def is_user_admin(user_id: str) -> bool:
    """Check if user is an admin."""
    result = supabase.table("members").select("is_admin").eq("id", user_id).execute()
    return bool(result.data and result.data[0].get("is_admin", False))


def get_user_by_wxid(wxid: str) -> Optional[Dict[str, Any]]:
    """Get user info if wxid is bound to a member."""
    # First find the member_id from attendees table
    attendee_result = supabase.table("attendees").select("member_id").eq("wxid", wxid).execute()
    if not attendee_result.data or not attendee_result.data[0].get("member_id"):
        return None

    member_id = attendee_result.data[0]["member_id"]

    # Get the member info
    member_result = supabase.table("members").select("id, username, full_name").eq("id", member_id).execute()
    if member_result.data:
        member = member_result.data[0]
        return {"uid": member["id"], "username": member["username"], "full_name": member["full_name"]}

    return None


# Extended user utility functions
def get_extended_user_wxid(user: Union[User, WeChatUser]) -> Optional[str]:
    """Extract wxid from User or WeChatUser object."""
    if isinstance(user, WeChatUser):
        return user.wxid
    elif isinstance(user, User):
        return get_user_wxid(user.uid)
    return None


def get_extended_user_attendee_id(user: Union[User, WeChatUser]) -> Optional[str]:
    """Get attendee_id from User or WeChatUser object."""
    if isinstance(user, WeChatUser):
        return user.attendee_id
    elif isinstance(user, User):
        return get_user_attendee_id(user.uid)
    return None


def is_extended_user_admin(user: Union[User, WeChatUser]) -> bool:
    """Check if user is admin."""
    if isinstance(user, User):
        return is_user_admin(user.uid)
    return False
