"""Dashboard statistics queries.

These public functions power the `/stats/dashboard` endpoint and the
chart components on the dashboard page. As of Phase 2 (statistics
agent), the heavy lifting (attendance smart-merge, batched IN queries)
is delegated to `app.services.meeting_stats` so that the dashboard and
the chat-based analytics tools share a single source of truth for every
metric. Public output shapes are UNCHANGED — the dashboard route, its
contract with the frontend charts, and existing tests all still see
identical row shapes.
"""

from typing import Any, Dict, List

from app.services import meeting_stats

from .supabase import supabase

__all__ = [
    "get_meeting_attendance_stats",
    "get_member_meeting_stats",
]


def get_member_meeting_stats(start_date: str | None, end_date: str | None) -> List[Dict[str, Any]]:
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
    # Step 1: Fetch published meetings in date range (shared loader).
    meetings = meeting_stats.load_meetings_in_range(start_date, end_date)
    if not meetings:
        return []

    meeting_ids = [m["id"] for m in meetings]
    meeting_map = {m["id"]: m for m in meetings}

    # Step 2: Fetch segments with role takers (batched).
    def _fetch_segments(chunk: list[str]) -> list[dict]:
        return meeting_stats._execute_all_pages(
            lambda: supabase.table("segments")
            .select("meeting_id, attendee_id, type")
            .in_("meeting_id", chunk)
            .not_.is_("attendee_id", "null")
        )

    segments = meeting_stats._batch_in(_fetch_segments, meeting_ids)
    if not segments:
        return []

    # Step 3: Get unique attendee IDs.
    attendee_ids = list({s["attendee_id"] for s in segments})

    # Step 4: Fetch attendees, filter for actual members.
    def _fetch_attendees(chunk: list[str]) -> list[dict]:
        return meeting_stats._execute_all_pages(
            lambda: supabase.table("attendees").select("id, member_id").in_("id", chunk).not_.is_("member_id", "null")
        )

    attendees = meeting_stats._batch_in(_fetch_attendees, attendee_ids)
    if not attendees:
        return []

    attendee_to_member = {a["id"]: a["member_id"] for a in attendees}
    member_ids = list({a["member_id"] for a in attendees})

    # Step 5: Fetch member details (batched).
    def _fetch_members(chunk: list[str]) -> list[dict]:
        return meeting_stats._execute_all_pages(
            lambda: supabase.table("members").select("id, username, full_name").in_("id", chunk)
        )

    members = meeting_stats._batch_in(_fetch_members, member_ids)
    member_map = {m["id"]: m for m in members}

    # Step 6: Build result — one row per (member, meeting, role).
    result = []
    for segment in segments:
        attendee_id = segment["attendee_id"]
        if attendee_id not in attendee_to_member:
            continue  # not a member

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


def get_meeting_attendance_stats(start_date: str | None, end_date: str | None) -> List[Dict[str, Any]]:
    """
    Get attendance statistics per meeting for Chart 2.

    Delegates the smart-merge logic (segments + checkins, dedupe with
    bidirectional substring matching for guests) to
    `meeting_stats.compute_meeting_attendance`. Public output shape
    matches the historical implementation exactly so chart code on the
    frontend sees no change.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of dicts with meeting_id, meeting_date, meeting_theme, meeting_no,
        member_count, guest_count, member_names, guest_names
    """
    meetings = meeting_stats.load_meetings_in_range(start_date, end_date)
    if not meetings:
        return []

    attendance_map = meeting_stats.compute_meeting_attendance([m["id"] for m in meetings])

    # Resolve member_ids → full_names for the result rows. Single batched
    # fetch for the union of all member_ids that appeared.
    all_member_ids = sorted({mid for att in attendance_map.values() for mid in att.member_ids})

    def _fetch_members(chunk: list[str]) -> list[dict]:
        return meeting_stats._execute_all_pages(
            lambda: supabase.table("members").select("id, full_name").in_("id", chunk)
        )

    members = meeting_stats._batch_in(_fetch_members, all_member_ids)
    member_full_name = {m["id"]: m.get("full_name") or "" for m in members}

    result: List[Dict[str, Any]] = []
    for m in meetings:
        att = attendance_map.get(m["id"])
        if att is None:
            member_names: list[str] = []
            guest_names: list[str] = []
        else:
            member_names = sorted(full_name for mid in att.member_ids if (full_name := member_full_name.get(mid)))
            guest_names = sorted(att.guest_names)
        result.append(
            {
                "meeting_id": m["id"],
                "meeting_date": m["date"],
                "meeting_theme": m["theme"],
                "meeting_no": m["no"],
                "member_count": len(member_names),
                "guest_count": len(guest_names),
                "member_names": member_names,
                "guest_names": guest_names,
            }
        )

    return result
