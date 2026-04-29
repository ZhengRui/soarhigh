"""Shared statistics primitives.

Used by:
  - The future statistics agent (`app.statistics_agent`) for analytics tools.
  - The dashboard route helpers in `app.db.stats` (refactored to delegate
    here so dashboard and chat agent share a single source of truth for
    every metric).

Design rules:
  - DB is authoritative. The CLUB_MEMBERS list in `app.meeting_agent.prompts`
    is help-text for the LLM, NOT a gate or a fallback for resolution.
  - Every Supabase `.in_(ids)` call goes through `_batch_in` so an "all
    history" leaderboard query doesn't blow past PostgREST's URL-length
    limit. This is the same class of bug that bit the lookup path.
  - Attendance is defined ONCE — `compute_meeting_attendance` — so the
    dashboard's `get_meeting_attendance_stats` and the chat agent's
    `attendance_summary` tool always agree on who attended what.
  - Manager is a meta field (`meetings.manager_id`), not a segment row.
    The "manager as virtual role" framing only happens at the tool /
    user-facing layer; the data layer keeps the two paths separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal

from app.db.supabase import supabase

# ---------- Generic batching ----------


def _batch_in(
    fetch: Callable[[list[str]], list[dict]],
    ids: Iterable[str],
    *,
    chunk_size: int = 50,
) -> list[dict]:
    """Fetch rows in chunks of `chunk_size` to avoid PostgREST's URL-length
    limit on `.in_(very_long_list)`.

    `fetch` is a callable that receives a chunk of ids and returns the
    matching rows. Caller-supplied so each call site can express its own
    select / filter shape. Returns the concatenation of all chunks in
    call order; rows are not deduplicated (caller's responsibility if
    that matters)."""
    out: list[dict] = []
    ids_list = [i for i in ids if i]
    if not ids_list:
        return out
    for i in range(0, len(ids_list), chunk_size):
        chunk = ids_list[i : i + chunk_size]
        out.extend(fetch(chunk))
    return out


def _execute_all_pages(
    build_query: Callable[[], Any],
    *,
    page_size: int = 1000,
) -> list[dict]:
    """Execute a Supabase/PostgREST query until every page is fetched.

    Supabase/PostgREST commonly caps a single response at 1000 rows. This
    helper preserves correctness for broad stats/dashboard queries by
    applying an explicit inclusive `.range(start, end)` window and
    continuing until the returned page is shorter than the requested page.
    `build_query` must return a fresh query builder each time so repeated
    range calls do not mutate a reused builder.
    """
    out: list[dict] = []
    start = 0
    while True:
        page = build_query().range(start, start + page_size - 1).execute().data or []
        out.extend(page)
        if len(page) < page_size:
            return out
        start += page_size


# ---------- Member resolver ----------


@dataclass(frozen=True)
class Member:
    """Canonical member identity. `id` is the load-bearing key for joins
    against `attendees.member_id`; `full_name` and `username` are display."""

    id: str
    full_name: str
    username: str


@dataclass(frozen=True)
class AmbiguousMember:
    """Multiple member rows match the input. The resolver returns this
    instead of guessing — the tool surfaces the candidates and the
    model is expected to ask the user to disambiguate before retrying."""

    candidates: tuple[Member, ...]


def _row_to_member(row: dict) -> Member:
    return Member(
        id=row["id"],
        full_name=(row.get("full_name") or "").strip(),
        username=(row.get("username") or "").strip(),
    )


def resolve_member(name: str) -> Member | AmbiguousMember | None:
    """Resolve a display-style member name into a canonical `Member`.

    Resolution order:
      1. Case-insensitive exact match against `members.full_name`.
      2. Case-insensitive exact match against `members.username`.
      3. Substring match (case-insensitive) against full_name or username.
         Single match → that Member. Multiple matches → AmbiguousMember.

    Returns None if nothing matches anywhere. Callers decide whether to
    error out (stats tools) or treat as a guest (other contexts).

    DB is authoritative. The static CLUB_MEMBERS prompt list is NOT
    consulted — it can drift from reality. Every resolution hits the
    members table."""
    needle = (name or "").strip()
    if not needle:
        return None

    rows = supabase.table("members").select("id, username, full_name").execute().data or []
    members = [_row_to_member(r) for r in rows]
    needle_lower = needle.lower()

    # 1) exact full_name
    exact_full = [m for m in members if m.full_name.lower() == needle_lower]
    if len(exact_full) == 1:
        return exact_full[0]
    if len(exact_full) > 1:
        return AmbiguousMember(candidates=tuple(exact_full))

    # 2) exact username
    exact_user = [m for m in members if m.username.lower() == needle_lower]
    if len(exact_user) == 1:
        return exact_user[0]
    if len(exact_user) > 1:
        return AmbiguousMember(candidates=tuple(exact_user))

    # 3) substring (full_name OR username)
    substring = [m for m in members if needle_lower in m.full_name.lower() or needle_lower in m.username.lower()]
    if len(substring) == 1:
        return substring[0]
    if len(substring) > 1:
        return AmbiguousMember(candidates=tuple(substring))

    return None


# ---------- Meeting loader (date-range scoped) ----------

MeetingType = Literal["Regular", "Workshop", "Custom"]


def load_meetings_in_range(
    date_from: str | None,
    date_to: str | None,
    type_filter: MeetingType | None = None,
) -> list[dict]:
    """Fetch all PUBLISHED meetings whose `date` falls in [date_from, date_to]
    inclusive. Either bound may be None for an open-ended range. Returns
    raw meeting rows (id, no, type, theme, date, manager_id) in
    chronological-ascending order — convenient for time-bucketed
    aggregation.

    For "all history" queries pass both bounds as None; this fetches
    every published meeting using explicit PostgREST pagination."""

    def _build_query():
        q = (
            supabase.table("meetings")
            .select("id, no, type, theme, date, manager_id, status")
            .eq("status", "published")
            .order("date", desc=False)
        )
        if date_from:
            q = q.gte("date", date_from)
        if date_to:
            q = q.lte("date", date_to)
        if type_filter:
            q = q.eq("type", type_filter)
        return q

    return _execute_all_pages(_build_query)


# ---------- Attendance smart-merge (shared with dashboard) ----------


def _is_valid_guest_name(name: str | None) -> bool:
    """Filter placeholder values masquerading as guest names. Mirrors the
    historical dashboard implementation so attendance counts stay
    identical between dashboard and stats agent."""
    if not name or not name.strip():
        return False
    return name.strip().lower() not in ("all", "tbd", "n/a", "na", "none", "-")


def _has_guest_match(name: str, existing_guests: set[str]) -> bool:
    """Bidirectional substring (case-insensitive). Used to dedupe a guest
    name that appears in both segments and checkins for the same meeting
    under slightly different spellings ('Lucas' vs 'Lucas L.')."""
    name_lower = name.lower()
    for existing in existing_guests:
        existing_lower = existing.lower()
        if name_lower in existing_lower or existing_lower in name_lower:
            return True
    return False


@dataclass
class MeetingAttendance:
    """Per-meeting attendance after smart-merge. `member_ids` are
    canonical (joinable against `attendees.member_id`); guests are
    free-text names (no canonical id)."""

    meeting_id: str
    member_ids: set[str]
    guest_names: set[str]


def compute_meeting_attendance(meeting_ids: list[str]) -> dict[str, MeetingAttendance]:
    """Smart-merge attendance for the given meetings. THE SHARED
    DEFINITION of "attended" — every consumer (dashboard, stats agent)
    must use this to stay consistent.

    Logic (extracted from the original dashboard `get_meeting_attendance_stats`):
      - Build segments group: members via attendees.member_id, guests
        via attendees.name (filtered for placeholders).
      - Build checkins group: members via wxid → attendees.member_id,
        guests via raw checkin name (filtered for placeholders).
      - Dedupe segments_guests against segments_members by bidirectional
        substring (same person appearing as both).
      - Pick the larger group as "major", the smaller as "additional"
        (segments wins ties — historical dashboard convention).
      - Merge additional members by exact member_id; merge additional
        guests by bidirectional substring against major guests.

    Returns a dict keyed by meeting_id so tools can look up attendance
    per meeting in O(1) without re-running the merge.
    """
    if not meeting_ids:
        return {}

    # --- segments side ---
    def _fetch_segments(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(
            lambda: supabase.table("segments")
            .select("meeting_id, attendee_id")
            .in_("meeting_id", chunk)
            .not_.is_("attendee_id", "null")
        )

    segments = _batch_in(_fetch_segments, meeting_ids)

    seg_attendee_ids = list({s["attendee_id"] for s in segments if s.get("attendee_id")})

    def _fetch_attendees_by_id(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(
            lambda: supabase.table("attendees").select("id, name, wxid, member_id").in_("id", chunk)
        )

    seg_attendees = _batch_in(_fetch_attendees_by_id, seg_attendee_ids)
    attendee_map = {a["id"]: a for a in seg_attendees}

    # We also need member full_names to dedupe seg_guests against
    # seg_members (a member added as both a member-attendee AND a guest
    # in the same meeting should count once). Same logic as the
    # historical dashboard `get_meeting_attendance_stats`.
    seg_member_ids = list({a["member_id"] for a in seg_attendees if a.get("member_id")})

    def _fetch_member_names(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(lambda: supabase.table("members").select("id, full_name").in_("id", chunk))

    member_name_rows = _batch_in(_fetch_member_names, seg_member_ids)
    member_name_map = {m["id"]: (m.get("full_name") or "") for m in member_name_rows}

    # --- checkins side ---
    def _fetch_checkins(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(
            lambda: supabase.table("checkins").select("meeting_id, wxid, name, is_member").in_("meeting_id", chunk)
        )

    checkins = _batch_in(_fetch_checkins, meeting_ids)

    checkin_wxids = list({c["wxid"] for c in checkins if c.get("wxid")})

    def _fetch_attendees_by_wxid(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(
            lambda: supabase.table("attendees").select("wxid, member_id, name").in_("wxid", chunk)
        )

    wxid_attendees = _batch_in(_fetch_attendees_by_wxid, checkin_wxids)
    wxid_to_attendee = {a["wxid"]: a for a in wxid_attendees if a.get("wxid")}

    # --- group rows by meeting ---
    segments_by_meeting: dict[str, list[dict]] = {}
    for s in segments:
        segments_by_meeting.setdefault(s["meeting_id"], []).append(s)
    checkins_by_meeting: dict[str, list[dict]] = {}
    for c in checkins:
        checkins_by_meeting.setdefault(c["meeting_id"], []).append(c)

    # --- per-meeting smart merge ---
    out: dict[str, MeetingAttendance] = {}
    for meeting_id in meeting_ids:
        seg_members: set[str] = set()
        seg_guests: set[str] = set()
        for seg in segments_by_meeting.get(meeting_id, []):
            attendee = attendee_map.get(seg["attendee_id"])
            if not attendee:
                continue
            if attendee.get("member_id"):
                seg_members.add(attendee["member_id"])
            elif _is_valid_guest_name(attendee.get("name")):
                seg_guests.add(attendee["name"])

        # Dedupe segments_guests against segments_members (rare but real:
        # someone added as both a member-attendee and a guest in the
        # same meeting). Compare guest names against the seg_members'
        # canonical full_names — bidirectional substring match.
        seg_member_names = {member_name_map.get(mid, "") for mid in seg_members}
        seg_member_names.discard("")
        seg_guests = {g for g in seg_guests if not _has_guest_match(g, seg_member_names)}

        ck_members: set[str] = set()
        ck_guests: set[str] = set()
        for ck in checkins_by_meeting.get(meeting_id, []):
            if ck.get("is_member"):
                attendee = wxid_to_attendee.get(ck["wxid"])
                if attendee and attendee.get("member_id"):
                    ck_members.add(attendee["member_id"])
            else:
                if _is_valid_guest_name(ck.get("name")):
                    ck_guests.add(ck["name"])

        # Pick major / additional. Segments wins ties — preserves the
        # dashboard's historical convention so attendance numbers don't
        # drift just because we extracted the merge.
        seg_count = len(seg_members) + len(seg_guests)
        ck_count = len(ck_members) + len(ck_guests)
        if ck_count > seg_count:
            major_m, major_g = ck_members, ck_guests
            add_m, add_g = seg_members, seg_guests
        else:
            major_m, major_g = seg_members, seg_guests
            add_m, add_g = ck_members, ck_guests

        final_members = set(major_m)
        final_members.update(add_m)  # member_id exact-match dedupes naturally

        final_guests = set(major_g)
        for g in add_g:
            if not _has_guest_match(g, final_guests):
                final_guests.add(g)

        out[meeting_id] = MeetingAttendance(
            meeting_id=meeting_id,
            member_ids=final_members,
            guest_names=final_guests,
        )

    return out


# ---------- Aggregation primitives ----------


def count_meetings(
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: MeetingType | None = None,
) -> dict:
    """Total published meetings in scope. Returns {value, scanned_count}."""
    rows = load_meetings_in_range(date_from, date_to, type_filter)
    return {"value": len(rows), "scanned_count": len(rows)}


def group_meetings_by_manager(
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: MeetingType | None = None,
) -> list[dict]:
    """Per-manager meeting counts in scope. Returns list of
    {member_id, full_name, username, count} sorted desc by count.

    A meeting with no manager_id is skipped (counts that as 'no manager'
    would mostly surface drafty/incomplete records and would rarely be
    what a leaderboard question wants)."""
    meetings = load_meetings_in_range(date_from, date_to, type_filter)
    counts: dict[str, int] = {}
    for m in meetings:
        mgr_id = m.get("manager_id")
        if mgr_id:
            counts[mgr_id] = counts.get(mgr_id, 0) + 1

    if not counts:
        return []

    # Resolve attendee_id → member_id → member info. The `manager_id` on
    # a meeting points at attendees.id, not members.id directly.
    def _fetch_attendees(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(lambda: supabase.table("attendees").select("id, member_id").in_("id", chunk))

    attendees = _batch_in(_fetch_attendees, list(counts.keys()))
    attendee_to_member = {a["id"]: a.get("member_id") for a in attendees}
    member_ids = list({mid for mid in attendee_to_member.values() if mid})

    def _fetch_members(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(lambda: supabase.table("members").select("id, username, full_name").in_("id", chunk))

    members_rows = _batch_in(_fetch_members, member_ids)
    member_map = {m["id"]: m for m in members_rows}

    # Roll up: meetings managed by an attendee → that attendee's member_id.
    # Multiple attendees can map to the same member_id (rare but legal),
    # so sum.
    member_counts: dict[str, int] = {}
    for attendee_id, count in counts.items():
        member_id = attendee_to_member.get(attendee_id)
        if not member_id:
            continue
        member_counts[member_id] = member_counts.get(member_id, 0) + count

    out = [
        {
            "member_id": mid,
            "full_name": member_map.get(mid, {}).get("full_name", ""),
            "username": member_map.get(mid, {}).get("username", ""),
            "count": cnt,
        }
        for mid, cnt in member_counts.items()
    ]
    out.sort(key=lambda r: (-r["count"], r["full_name"]))
    return out


def group_meetings_by_type(date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    meetings = load_meetings_in_range(date_from, date_to)
    counts: dict[str, int] = {}
    for m in meetings:
        t = m.get("type") or "Unknown"
        counts[t] = counts.get(t, 0) + 1
    return [{"type": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _bucket_key(date_str: str, by: Literal["month", "quarter", "year"]) -> str:
    """date_str is YYYY-MM-DD. Buckets:
    month   → 'YYYY-MM'
    quarter → 'YYYY-Q1' .. 'YYYY-Q4'
    year    → 'YYYY'
    """
    if not date_str or len(date_str) < 7:
        return "unknown"
    yyyy = date_str[:4]
    mm = date_str[5:7]
    if by == "year":
        return yyyy
    if by == "month":
        return f"{yyyy}-{mm}"
    # quarter
    try:
        m = int(mm)
        q = (m - 1) // 3 + 1
        return f"{yyyy}-Q{q}"
    except ValueError:
        return "unknown"


def time_bucket_meetings(
    metric: Literal["count", "avg_attendance", "member_count", "guest_count"],
    by: Literal["month", "quarter", "year"],
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: MeetingType | None = None,
) -> list[dict]:
    """Meetings grouped by time bucket with the requested metric.
    Returns list of {bucket, value, meeting_count} sorted by bucket asc.

    `count` returns the number of meetings in each bucket.
    `member_count` / `guest_count` / `avg_attendance` aggregate per-meeting
    attendance (smart-merge) within each bucket."""
    meetings = load_meetings_in_range(date_from, date_to, type_filter)
    if not meetings:
        return []

    if metric == "count":
        counts: dict[str, int] = {}
        for m in meetings:
            k = _bucket_key(m.get("date") or "", by)
            counts[k] = counts.get(k, 0) + 1
        return [{"bucket": k, "value": v, "meeting_count": v} for k, v in sorted(counts.items())]

    # Attendance-based metrics need the smart-merge.
    attendance = compute_meeting_attendance([m["id"] for m in meetings])
    by_bucket: dict[str, list[MeetingAttendance]] = {}
    for m in meetings:
        att = attendance.get(m["id"])
        if att is None:
            continue
        k = _bucket_key(m.get("date") or "", by)
        by_bucket.setdefault(k, []).append(att)

    out: list[dict] = []
    for k in sorted(by_bucket.keys()):
        atts = by_bucket[k]
        n = len(atts)
        member_total = sum(len(a.member_ids) for a in atts)
        guest_total = sum(len(a.guest_names) for a in atts)
        if metric == "member_count":
            value: float = member_total
        elif metric == "guest_count":
            value = guest_total
        else:  # avg_attendance
            value = round((member_total + guest_total) / n, 2) if n else 0
        out.append({"bucket": k, "value": value, "meeting_count": n})
    return out


# ---------- Member-centric primitives ----------


def member_attendance_summary(
    member_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Total meetings in scope, member's attended count, and rate.
    Attendance uses the smart-merge definition."""
    meetings = load_meetings_in_range(date_from, date_to)
    if not meetings:
        return {"attended": 0, "total": 0, "rate": 0.0}

    attendance = compute_meeting_attendance([m["id"] for m in meetings])
    attended = 0
    for m in meetings:
        record = attendance.get(m["id"])
        if record is not None and member_id in record.member_ids:
            attended += 1
    total = len(meetings)
    rate = round(attended / total, 4) if total else 0.0
    return {"attended": attended, "total": total, "rate": rate}


def member_segment_history(
    member_id: str,
    segment_types: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Meetings (in scope) where this member appeared as a SEGMENT role
    matching `segment_types` (closed list). If `segment_types` is None,
    returns all segment-role appearances.

    Returns list of {meeting_id, no, date, theme, segment_type} sorted
    by date desc."""
    meetings = load_meetings_in_range(date_from, date_to)
    if not meetings:
        return []
    meeting_map = {m["id"]: m for m in meetings}

    # Find attendee rows for this member (a member can have multiple
    # attendee rows historically; collect them all).
    attendee_rows = _execute_all_pages(lambda: supabase.table("attendees").select("id").eq("member_id", member_id))
    attendee_ids = [a["id"] for a in attendee_rows]
    if not attendee_ids:
        return []

    def _fetch_segments(chunk: list[str]) -> list[dict]:
        return _execute_all_pages(
            lambda: supabase.table("segments")
            .select("meeting_id, type, attendee_id, start_time")
            .in_("attendee_id", chunk)
        )

    segments = _batch_in(_fetch_segments, attendee_ids)

    # Filter by meeting scope and (optionally) segment types.
    type_set = set(segment_types) if segment_types else None
    out: list[dict] = []
    for s in segments:
        mid = s.get("meeting_id")
        if mid not in meeting_map:
            continue
        seg_type = s.get("type") or ""
        if type_set is not None and seg_type not in type_set:
            continue
        m = meeting_map[mid]
        out.append(
            {
                "meeting_id": mid,
                "no": m.get("no"),
                "date": m.get("date"),
                "theme": m.get("theme"),
                "segment_type": seg_type,
                "start_time": s.get("start_time"),
            }
        )
    out.sort(key=lambda r: (r.get("date") or "", r.get("start_time") or ""), reverse=True)
    return out


def meetings_managed_by(
    member_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Meetings where this member is the meeting MANAGER (meta field, not
    a segment role). Returns list of {meeting_id, no, date, theme}
    sorted by date desc.

    `meetings.manager_id` references `attendees.id`, so we resolve the
    attendee IDs that map back to this member first."""
    meetings = load_meetings_in_range(date_from, date_to)
    if not meetings:
        return []

    attendee_rows = _execute_all_pages(lambda: supabase.table("attendees").select("id").eq("member_id", member_id))
    attendee_ids = {a["id"] for a in attendee_rows}
    if not attendee_ids:
        return []

    out = [
        {
            "meeting_id": m["id"],
            "no": m.get("no"),
            "date": m.get("date"),
            "theme": m.get("theme"),
        }
        for m in meetings
        if m.get("manager_id") in attendee_ids
    ]
    out.sort(key=lambda r: (r.get("date") or ""), reverse=True)
    return out


def member_role_distribution(
    member_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    include_manager: bool = False,
) -> dict:
    """Map of segment_type → count for this member across the scope.
    Default excludes meeting-manager (matches dashboard). When
    `include_manager=True`, adds a synthetic 'Meeting Manager' key with
    the manager-meeting count — separate from segment roles so the user
    can tell at a glance."""
    history = member_segment_history(member_id, segment_types=None, date_from=date_from, date_to=date_to)
    counts: dict[str, int] = {}
    for row in history:
        t = row["segment_type"] or "Unknown"
        counts[t] = counts.get(t, 0) + 1
    if include_manager:
        managed = meetings_managed_by(member_id, date_from, date_to)
        if managed:
            counts["Meeting Manager"] = len(managed)
    return counts
