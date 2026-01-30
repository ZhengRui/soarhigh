"""Dashboard statistics and analytics queries."""

from typing import Any, Dict, List

from .supabase import supabase

__all__ = [
    "get_meeting_attendance_stats",
    "get_member_meeting_stats",
]


def get_member_meeting_stats(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Get raw data for member attendance statistics.

    Returns rows of member-meeting-role data for Chart 1.
    Only includes published meetings with assigned role takers (attendee_id not null).

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of dicts with member_id, username, full_name, meeting_id, meeting_date,
        meeting_theme, meeting_no, role
    """
    # Step 1: Fetch published meetings in date range
    meetings_result = (
        supabase.table("meetings")
        .select("id, date, theme, no")
        .eq("status", "published")
        .gte("date", start_date)
        .lte("date", end_date)
        .execute()
    )
    meetings = meetings_result.data
    if not meetings:
        return []

    meeting_ids = [m["id"] for m in meetings]
    meeting_map = {m["id"]: m for m in meetings}

    # Step 2: Fetch segments with role takers for these meetings
    segments_result = (
        supabase.table("segments")
        .select("meeting_id, attendee_id, type")
        .in_("meeting_id", meeting_ids)
        .not_.is_("attendee_id", "null")
        .execute()
    )
    segments = segments_result.data
    if not segments:
        return []

    # Step 3: Get unique attendee IDs
    attendee_ids = list(set(s["attendee_id"] for s in segments))

    # Step 4: Fetch attendees and filter by member_id not null (actual members)
    attendees_result = (
        supabase.table("attendees")
        .select("id, member_id")
        .in_("id", attendee_ids)
        .not_.is_("member_id", "null")
        .execute()
    )
    attendees = attendees_result.data
    if not attendees:
        return []

    # Map attendee_id -> member_id
    attendee_to_member = {a["id"]: a["member_id"] for a in attendees}
    member_ids = list(set(a["member_id"] for a in attendees))

    # Step 5: Fetch member details
    members_result = supabase.table("members").select("id, username, full_name").in_("id", member_ids).execute()
    members = members_result.data
    member_map = {m["id"]: m for m in members}

    # Step 6: Build result - one row per segment (member-meeting-role)
    result = []
    for segment in segments:
        attendee_id = segment["attendee_id"]
        if attendee_id not in attendee_to_member:
            continue  # Not a member

        member_id = attendee_to_member[attendee_id]
        if member_id not in member_map:
            continue

        member = member_map[member_id]
        meeting = meeting_map[segment["meeting_id"]]

        result.append(
            {
                "member_id": member_id,
                "username": member["username"],
                "full_name": member["full_name"],
                "meeting_id": meeting["id"],
                "meeting_date": meeting["date"],
                "meeting_theme": meeting["theme"],
                "meeting_no": meeting["no"],
                "role": segment["type"],
            }
        )

    return result


def get_meeting_attendance_stats(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    Get attendance statistics per meeting for Chart 2.

    Uses smart merge logic:
    - Build two groups: segments (via attendee_id) and checkins (via wxid)
    - Each group has members (by member_id) and guests (by name)
    - Dedupe segments guests against segments members (same person may appear as both)
    - Use larger group as major, smaller as additional (segments wins ties)
    - Merge additional members by exact member_id match
    - Merge additional guests by bidirectional substring match (case-insensitive)

    Guest filtering: Ignores invalid names like "ALL", "TBD", empty strings, etc.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of dicts with meeting_id, meeting_date, meeting_theme, meeting_no,
        member_count, guest_count, member_names, guest_names
    """
    # Step 1: Fetch published meetings in date range
    meetings_result = (
        supabase.table("meetings")
        .select("id, date, theme, no")
        .eq("status", "published")
        .gte("date", start_date)
        .lte("date", end_date)
        .order("date", desc=False)
        .execute()
    )
    meetings = meetings_result.data
    if not meetings:
        return []

    meeting_ids = [m["id"] for m in meetings]

    # Step 2: Batch fetch all checkins for these meetings
    checkins_result = (
        supabase.table("checkins").select("meeting_id, wxid, name, is_member").in_("meeting_id", meeting_ids).execute()
    )
    checkins = checkins_result.data

    # Group checkins by meeting_id
    checkins_by_meeting: Dict[str, List[Dict]] = {}
    for c in checkins:
        mid = c["meeting_id"]
        if mid not in checkins_by_meeting:
            checkins_by_meeting[mid] = []
        checkins_by_meeting[mid].append(c)

    # Step 3: Batch fetch all segments for these meetings
    segments_result = (
        supabase.table("segments")
        .select("meeting_id, attendee_id")
        .in_("meeting_id", meeting_ids)
        .not_.is_("attendee_id", "null")
        .execute()
    )
    segments = segments_result.data

    # Group segments by meeting_id
    segments_by_meeting: Dict[str, List[Dict]] = {}
    for s in segments:
        mid = s["meeting_id"]
        if mid not in segments_by_meeting:
            segments_by_meeting[mid] = []
        segments_by_meeting[mid].append(s)

    # Step 4: Get all unique attendee IDs from segments
    all_attendee_ids = list(set(s["attendee_id"] for s in segments if s["attendee_id"]))

    # Step 5: Fetch all attendees (to get wxid and member_id)
    attendees_result = (
        (supabase.table("attendees").select("id, name, wxid, member_id").in_("id", all_attendee_ids).execute())
        if all_attendee_ids
        else type("obj", (object,), {"data": []})()
    )
    attendees = attendees_result.data

    # Build maps
    attendee_map = {a["id"]: a for a in attendees}

    # Get all wxids from checkins to find which ones are members
    all_checkin_wxids = list(set(c["wxid"] for c in checkins if c["wxid"]))

    # Step 6: Fetch attendees by wxid to determine member status
    wxid_attendees_result = (
        (supabase.table("attendees").select("wxid, member_id, name").in_("wxid", all_checkin_wxids).execute())
        if all_checkin_wxids
        else type("obj", (object,), {"data": []})()
    )
    wxid_attendees = wxid_attendees_result.data

    # Map wxid -> attendee info (for member determination)
    wxid_to_attendee = {a["wxid"]: a for a in wxid_attendees if a["wxid"]}

    # Step 7: Get all member IDs to fetch full_name
    member_ids_from_attendees = [a["member_id"] for a in attendees if a["member_id"]]
    member_ids_from_wxid = [a["member_id"] for a in wxid_attendees if a["member_id"]]
    all_member_ids = list(set(member_ids_from_attendees + member_ids_from_wxid))

    members_result = (
        (supabase.table("members").select("id, full_name").in_("id", all_member_ids).execute())
        if all_member_ids
        else type("obj", (object,), {"data": []})()
    )
    members = members_result.data
    member_map = {m["id"]: m for m in members}

    # Helper to check if a name is valid (not a placeholder)
    def is_valid_guest_name(name: str) -> bool:
        if not name or not name.strip():
            return False
        normalized = name.strip().lower()
        # Filter out placeholder values
        if normalized in ("all", "tbd", "n/a", "na", "none", "-"):
            return False
        return True

    # Helper for bidirectional substring matching
    def has_guest_match(name: str, existing_guests: set) -> bool:
        """Check if name matches any existing guest (bidirectional substring, case-insensitive)."""
        name_lower = name.lower()
        for existing in existing_guests:
            existing_lower = existing.lower()
            if name_lower in existing_lower or existing_lower in name_lower:
                return True
        return False

    # Step 8: Build result for each meeting using smart merge
    result = []
    for meeting in meetings:
        meeting_id = meeting["id"]
        meeting_checkins = checkins_by_meeting.get(meeting_id, [])
        meeting_segments = segments_by_meeting.get(meeting_id, [])

        # Build segments group
        segments_members: set = set()  # member_ids
        segments_guests: set = set()  # guest names
        for segment in meeting_segments:
            attendee_id = segment["attendee_id"]
            if attendee_id not in attendee_map:
                continue
            attendee_info = attendee_map[attendee_id]
            if attendee_info["member_id"]:
                segments_members.add(attendee_info["member_id"])
            elif is_valid_guest_name(attendee_info["name"]):
                segments_guests.add(attendee_info["name"])

        # Dedupe segments_guests against segments_members (same person may appear as both)
        segments_member_names = {member_map[mid]["full_name"] for mid in segments_members if mid in member_map}
        segments_guests = {g for g in segments_guests if not has_guest_match(g, segments_member_names)}

        # Build checkins group (use is_member field for classification)
        checkins_members: set = set()  # member_ids
        checkins_guests: set = set()  # guest names
        for checkin in meeting_checkins:
            if checkin.get("is_member"):
                # Member - look up full_name via wxid
                wxid = checkin["wxid"]
                if wxid in wxid_to_attendee:
                    member_id = wxid_to_attendee[wxid]["member_id"]
                    if member_id:
                        checkins_members.add(member_id)
            else:
                # Guest - use checkin name
                checkin_name = checkin["name"] or ""
                if is_valid_guest_name(checkin_name):
                    checkins_guests.add(checkin_name)

        # Determine major/additional (segments wins ties)
        segments_count = len(segments_members) + len(segments_guests)
        checkins_count = len(checkins_members) + len(checkins_guests)

        if checkins_count > segments_count:
            major_members, major_guests = checkins_members, checkins_guests
            additional_members, additional_guests = segments_members, segments_guests
        else:
            major_members, major_guests = segments_members, segments_guests
            additional_members, additional_guests = checkins_members, checkins_guests

        # Start with major group
        final_member_ids = set(major_members)
        final_guests = set(major_guests)

        # Merge additional members (exact match by member_id)
        for member_id in additional_members:
            if member_id not in final_member_ids:
                final_member_ids.add(member_id)

        # Merge additional guests (bidirectional substring match)
        for guest_name in additional_guests:
            if not has_guest_match(guest_name, final_guests):
                final_guests.add(guest_name)

        # Convert member_ids to full_names
        final_member_names = set()
        for member_id in final_member_ids:
            if member_id in member_map:
                final_member_names.add(member_map[member_id]["full_name"])

        result.append(
            {
                "meeting_id": meeting_id,
                "meeting_date": meeting["date"],
                "meeting_theme": meeting["theme"],
                "meeting_no": meeting["no"],
                "member_count": len(final_member_names),
                "guest_count": len(final_guests),
                "member_names": sorted(list(final_member_names)),
                "guest_names": sorted(list(final_guests)),
            }
        )

    return result
