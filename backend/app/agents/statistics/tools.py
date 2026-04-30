"""Dashboard-backed statistics agent tools.

Only the tools agreed for the stats agent live here. They wrap the same
backend functions used by the dashboard, then project the raw rows into
answer-ready envelopes for the chat model.
"""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Literal, cast
from zoneinfo import ZoneInfo

from pydantic_ai import ModelRetry

from app.db.stats import get_meeting_attendance_stats, get_member_award_stats, get_member_meeting_stats
from app.services import meeting_lookup, meeting_stats

MeetingType = Literal["Regular", "Workshop", "Custom"]
AttendanceSortBy = Literal["date", "member_count", "guest_count", "total_count"]
SortOrder = Literal["asc", "desc"]
MatrixRoleKey = Literal[
    "SAA",
    "President",
    "TOM",
    "Timer",
    "Grammarian",
    "HarkMaster",
    "GuestIntroHost",
    "TTM",
    "PreparedSpeech",
    "TTE",
    "IE",
    "GE",
    "MoT",
    "WorkshopSpeaker",
]
MatrixRoleGroup = Literal["evaluation", "speaker", "hosting", "facilitator"]
MatrixGroupBy = Literal["member", "role", "member_role", "meeting"]
MatrixSortBy = Literal["count", "name", "date"]
AwardCategoryKey = Literal[
    "BestPS",
    "BestHost",
    "BestTTS",
    "BestFacilitator",
    "BestEvaluator",
    "BestSupporter",
    "BestMM",
]
AwardGroupBy = Literal["winner", "category", "winner_category", "meeting"]
AwardSortBy = Literal["count", "name", "date"]

_VALID_TYPE_FILTERS = {"Regular", "Workshop", "Custom"}
_VALID_ATTENDANCE_SORTS = {"date", "member_count", "guest_count", "total_count"}
_VALID_SORT_ORDERS = {"asc", "desc"}
_VALID_MATRIX_GROUPS = {"member", "role", "member_role", "meeting"}
_VALID_MATRIX_SORTS = {"count", "name", "date"}
_VALID_AWARD_GROUPS = {"winner", "category", "winner_category", "meeting"}
_VALID_AWARD_SORTS = {"count", "name", "date"}

_MATRIX_ROLES: dict[str, dict[str, object]] = {
    "SAA": {"label": "SAA", "pattern": "Meeting Rules Introduction (SAA)"},
    "President": {"label": "President", "pattern": "Opening Remarks (President)"},
    "TOM": {
        "label": "TOM",
        "pattern": "TOM (Toastmaster of Meeting) Introduction",
    },
    "Timer": {"label": "Timer", "pattern": "Timer"},
    "Grammarian": {"label": "Grammarian", "pattern": "Grammarian"},
    "HarkMaster": {"label": "Hark Master", "pattern": "Hark Master"},
    "GuestIntroHost": {
        "label": "Guest Intro Host",
        "pattern": "Guests Self Introduction (30s per guest)",
    },
    "TTM": {"label": "TTM", "pattern": "TTM (Table Topic Master) Opening"},
    "PreparedSpeech": {
        "label": "Prepared Speech",
        "pattern": re.compile(r"^Prepared Speech(?:\s+\d+)?$"),
    },
    "TTE": {"label": "TTE", "pattern": "Table Topic Evaluation"},
    "IE": {
        "label": "IE",
        "pattern": re.compile(r"^Prepared Speech(?:\s+\d+)?\s+Evaluation$"),
    },
    "GE": {"label": "GE", "pattern": "General Evaluation"},
    "MoT": {"label": "MoT", "pattern": "Moment of Truth"},
    "WorkshopSpeaker": {"label": "Workshop Speaker", "pattern": "Workshop"},
}

_MATRIX_ROLE_GROUPS: dict[str, tuple[str, ...]] = {
    "evaluation": ("TTE", "IE", "GE"),
    "speaker": ("PreparedSpeech", "WorkshopSpeaker"),
    "hosting": ("TOM", "TTM", "GuestIntroHost", "MoT"),
    "facilitator": ("SAA", "Timer", "Grammarian", "HarkMaster"),
}

_STANDARD_AWARD_CATEGORIES: dict[str, str] = {
    "BestPS": "Best Prepared Speaker",
    "BestHost": "Best Host",
    "BestTTS": "Best Table Topic Speaker",
    "BestFacilitator": "Best Facilitator",
    "BestEvaluator": "Best Evaluator",
    "BestSupporter": "Best Supporter",
    "BestMM": "Best Meeting Manager",
}

_REFERENCE_LIMIT = 20


def _validate_dates(date_from: str | None, date_to: str | None) -> None:
    parsed_from = meeting_lookup.parse_iso_date_or_raise("date_from", date_from) if date_from else None
    parsed_to = meeting_lookup.parse_iso_date_or_raise("date_to", date_to) if date_to else None
    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise ModelRetry(f"date_from ({date_from}) must not be after date_to ({date_to}).")


def _today_from_ctx(ctx) -> date:
    raw = getattr(getattr(ctx, "deps", None), "today", "") or ""
    if raw:
        return meeting_lookup.parse_iso_date_or_raise("today", raw)
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _relative_date_hint(message: str, today: date) -> tuple[str, str, str] | None:
    lower = (message or "").lower()
    if "今年" in message or "this year" in lower or "year to date" in lower or "ytd" in lower:
        return ("今年 / this year", f"{today.year}-01-01", today.isoformat())
    if "去年" in message or "last year" in lower:
        return (
            "去年 / last year",
            f"{today.year - 1}-01-01",
            f"{today.year - 1}-12-31",
        )
    if "本月" in message or "这个月" in message or "this month" in lower:
        start, end = _month_range(today.year, today.month)
        return ("本月 / this month", start.isoformat(), min(end, today).isoformat())
    if "上个月" in message or "last month" in lower:
        first_this_month = date(today.year, today.month, 1)
        last_prev_month = first_this_month - timedelta(days=1)
        start, end = _month_range(last_prev_month.year, last_prev_month.month)
        return ("上个月 / last month", start.isoformat(), end.isoformat())
    return None


def _require_relative_dates_if_requested(ctx, date_from: str | None, date_to: str | None) -> None:
    if date_from and date_to:
        return
    message = getattr(getattr(ctx, "deps", None), "current_user_message", "") or ""
    hint = _relative_date_hint(message, _today_from_ctx(ctx))
    if not hint:
        return
    phrase, suggested_from, suggested_to = hint
    raise ModelRetry(
        f"The user asked for a relative date scope ({phrase}). Retry this tool with "
        f'date_from="{suggested_from}" and date_to="{suggested_to}" so the answer '
        "does not accidentally use all-history data."
    )


def _validate_limit(limit: int) -> None:
    if limit < 1:
        raise ModelRetry(f"limit must be >= 1; got {limit}")
    if limit > 500:
        raise ModelRetry("limit must be <= 500 to keep the tool result manageable.")


def _validate_type_filter(type_filter: str | None) -> str | None:
    if type_filter is None:
        return None
    if type_filter not in _VALID_TYPE_FILTERS:
        raise ModelRetry(
            f"type_filter must be one of: {', '.join(sorted(_VALID_TYPE_FILTERS))}. " f"Got: {type_filter!r}."
        )
    return type_filter


def _validate_matrix_role_filter(role_filter: str | None) -> str | None:
    if role_filter is None:
        return None
    if role_filter not in _MATRIX_ROLES:
        raise ModelRetry(f"role_filter must be one of: {', '.join(_MATRIX_ROLES.keys())}. " f"Got: {role_filter!r}.")
    return role_filter


def _validate_matrix_role_group(role_group: str | None) -> str | None:
    if role_group is None:
        return None
    if role_group not in _MATRIX_ROLE_GROUPS:
        raise ModelRetry(
            f"role_group must be one of: {', '.join(_MATRIX_ROLE_GROUPS.keys())}. " f"Got: {role_group!r}."
        )
    return role_group


def _coverage(
    *,
    source: str,
    total_matches: int,
    returned_count: int,
) -> dict:
    if total_matches > returned_count:
        return {
            "status": "truncated",
            "source": source,
            "reason": f"Showing {returned_count} of {total_matches} matches; increase limit for more.",
        }
    return {"status": "complete", "source": source}


def _round_avg(total: int, count: int) -> float:
    return round(total / count, 2) if count else 0.0


def _meeting_type_map(
    date_from: str | None,
    date_to: str | None,
) -> dict[str, str]:
    meetings = meeting_stats.load_meetings_in_range(date_from, date_to)
    return {m["id"]: (m.get("type") or "") for m in meetings}


def _normalize_matrix_role(segment_type: str) -> dict | None:
    trimmed = (segment_type or "").strip()
    for key, spec in _MATRIX_ROLES.items():
        pattern = spec["pattern"]
        if isinstance(pattern, str):
            if trimmed == pattern:
                return {"key": key, "label": spec["label"]}
        else:
            regex = cast(re.Pattern[str], pattern)
            if not regex.match(trimmed):
                continue
            return {"key": key, "label": spec["label"]}
    return None


def _role_label(role_key: str) -> str:
    return str(_MATRIX_ROLES[role_key]["label"])


def _role_group_mapping() -> dict[str, list[str]]:
    return {group_key: list(role_keys) for group_key, role_keys in _MATRIX_ROLE_GROUPS.items()}


def _standard_award_category_mapping() -> dict[str, str]:
    return dict(_STANDARD_AWARD_CATEGORIES)


def _observed_award_categories(rows: list[dict]) -> list[str]:
    return sorted({row.get("category") or "" for row in rows}, key=lambda c: c.lower())


def _resolve_award_category_filters(
    category_filters: list[str] | None,
    observed_categories: list[str],
) -> set[str] | None:
    if not category_filters:
        return None

    observed_lower = {category.lower() for category in observed_categories}
    standard_lower = {category.lower() for category in _STANDARD_AWARD_CATEGORIES.values()}

    resolved: set[str] = set()
    unknown: list[str] = []
    for raw_filter in category_filters:
        value = (raw_filter or "").strip()
        if not value:
            continue
        if value in _STANDARD_AWARD_CATEGORIES:
            resolved.add(_STANDARD_AWARD_CATEGORIES[value].lower())
            continue
        value_lower = value.lower()
        if value_lower in observed_lower or value_lower in standard_lower:
            resolved.add(value_lower)
            continue
        unknown.append(value)

    if unknown:
        observed = ", ".join(observed_categories) if observed_categories else "none"
        standard = ", ".join(f"{key}={label}" for key, label in _STANDARD_AWARD_CATEGORIES.items())
        raise ModelRetry(
            "Unknown award category filter(s): "
            f"{', '.join(unknown)}. Use a standard category key ({standard}) "
            f"or one of the observed raw categories in this date range: {observed}."
        )

    return resolved or None


def _resolve_member_or_retry(name: str) -> meeting_stats.Member:
    result = meeting_stats.resolve_member(name)
    if result is None:
        raise ModelRetry(f"No member matched {name!r}. Ask the user to provide a more specific name.")
    if isinstance(result, meeting_stats.AmbiguousMember):
        candidates = ", ".join(f"{c.full_name} (@{c.username})" for c in result.candidates)
        raise ModelRetry(f"Multiple members matched {name!r}: {candidates}. Ask the user to pick one.")
    return result


async def apply_meeting_attendance_list(
    ctx,
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: str | None = None,
    meeting_no: int | None = None,
    sort_by: str = "date",
    sort_order: str = "asc",
    limit: int = 50,
    include_names: bool = False,
) -> dict:
    """Per-meeting attendance rows using the dashboard attendance source."""
    _require_relative_dates_if_requested(ctx, date_from, date_to)
    _validate_dates(date_from, date_to)
    _validate_limit(limit)
    type_filter = _validate_type_filter(type_filter)
    if sort_by not in _VALID_ATTENDANCE_SORTS:
        raise ModelRetry(f"sort_by must be one of: {', '.join(sorted(_VALID_ATTENDANCE_SORTS))}. " f"Got: {sort_by!r}.")
    if sort_order not in _VALID_SORT_ORDERS:
        raise ModelRetry("sort_order must be 'asc' or 'desc'.")

    dashboard_rows, type_by_meeting = await asyncio.gather(
        asyncio.to_thread(get_meeting_attendance_stats, date_from, date_to),
        asyncio.to_thread(_meeting_type_map, date_from, date_to),
    )

    meetings: list[dict] = []
    for row in dashboard_rows:
        row_type = type_by_meeting.get(row["meeting_id"], "")
        if type_filter and row_type != type_filter:
            continue
        if meeting_no is not None and row.get("meeting_no") != meeting_no:
            continue
        member_count = int(row.get("member_count") or 0)
        guest_count = int(row.get("guest_count") or 0)
        item = {
            "meeting_id": row["meeting_id"],
            "no": row.get("meeting_no"),
            "date": row.get("meeting_date"),
            "theme": row.get("meeting_theme"),
            "type": row_type,
            "member_count": member_count,
            "guest_count": guest_count,
            "total_count": member_count + guest_count,
        }
        if include_names:
            item["member_names"] = row.get("member_names") or []
            item["guest_names"] = row.get("guest_names") or []
        meetings.append(item)

    reverse = sort_order == "desc"
    if sort_by == "date":
        meetings.sort(key=lambda r: (r.get("date") or "", r.get("no") or 0), reverse=reverse)
    else:
        meetings.sort(
            key=lambda r: (r.get(sort_by) or 0, r.get("date") or "", r.get("no") or 0),
            reverse=reverse,
        )

    total_matches = len(meetings)
    capped = meetings[:limit]
    total_member_attendance = sum(m["member_count"] for m in meetings)
    total_guest_attendance = sum(m["guest_count"] for m in meetings)
    total_attendance = total_member_attendance + total_guest_attendance

    return {
        "value": {
            "meetings": capped,
            "total_matches": total_matches,
            "limit": limit,
            "summary": {
                "meeting_count": total_matches,
                "total_member_attendance": total_member_attendance,
                "total_guest_attendance": total_guest_attendance,
                "total_attendance": total_attendance,
                "avg_member_count": _round_avg(total_member_attendance, total_matches),
                "avg_guest_count": _round_avg(total_guest_attendance, total_matches),
                "avg_total_count": _round_avg(total_attendance, total_matches),
            },
        },
        "scope": {
            "date_from": date_from,
            "date_to": date_to,
            "type_filter": type_filter,
            "meeting_no": meeting_no,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_names": include_names,
        },
        "coverage": _coverage(
            source="dashboard_meeting_attendance",
            total_matches=total_matches,
            returned_count=len(capped),
        ),
        "scanned_count": len(dashboard_rows),
    }


def _project_meeting(row: dict) -> dict:
    return {
        "meeting_id": row["meeting_id"],
        "no": row.get("meeting_no"),
        "date": row.get("meeting_date"),
        "theme": row.get("meeting_theme"),
    }


def _project_role_reference(row: dict) -> dict:
    return {
        "meeting_id": row["meeting_id"],
        "no": row.get("meeting_no"),
        "date": row.get("meeting_date"),
        "theme": row.get("meeting_theme"),
        "member_id": row.get("member_id"),
        "username": row.get("username"),
        "full_name": row.get("full_name"),
        "role_key": row.get("role_key"),
        "role_label": row.get("role_label"),
        "segment_type": row.get("role"),
    }


def _role_references(rows: list[dict], *, limit: int = _REFERENCE_LIMIT) -> list[dict]:
    sorted_rows = sorted(
        rows,
        key=lambda r: (
            r.get("meeting_date") or "",
            r.get("meeting_no") or 0,
            r.get("full_name") or "",
            r.get("role_key") or "",
        ),
        reverse=True,
    )
    return [_project_role_reference(row) for row in sorted_rows[:limit]]


def _rows_for_member_role_matrix(
    *,
    date_from: str | None,
    date_to: str | None,
    member: str | None,
    role_filter: str | None,
    role_group: str | None,
) -> tuple[list[dict], list[str]]:
    raw_rows = get_member_meeting_stats(date_from, date_to)
    canonical_member = _resolve_member_or_retry(member) if member else None
    allowed_role_keys: set[str] | None = None
    if role_filter:
        allowed_role_keys = {role_filter}
    elif role_group:
        allowed_role_keys = set(_MATRIX_ROLE_GROUPS[role_group])

    rows: list[dict] = []
    unmapped_roles: set[str] = set()
    for row in raw_rows:
        if canonical_member and row.get("member_id") != canonical_member.id:
            continue
        normalized = _normalize_matrix_role(row.get("role") or "")
        if normalized is None:
            if row.get("role"):
                unmapped_roles.add(row["role"])
            continue
        if allowed_role_keys is not None and normalized["key"] not in allowed_role_keys:
            continue
        rows.append(
            {
                **row,
                "role_key": normalized["key"],
                "role_label": normalized["label"],
            }
        )
    return rows, sorted(unmapped_roles)


def _unique_meetings(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        seen.setdefault(row["meeting_id"], _project_meeting(row))
    return sorted(seen.values(), key=lambda m: (m.get("date") or "", m.get("no") or 0), reverse=True)


def _sort_groups(
    groups: list[dict],
    *,
    group_by: str,
    sort_by: str,
    sort_order: str,
) -> list[dict]:
    reverse = sort_order == "desc"
    if sort_by == "date":
        groups.sort(key=lambda g: (g.get("date") or "", g.get("name") or ""), reverse=reverse)
    elif sort_by == "name":
        groups.sort(key=lambda g: (g.get("name") or "", g.get("role_label") or ""), reverse=reverse)
    else:
        if reverse:
            groups.sort(
                key=lambda g: (
                    -(g.get("count") or 0),
                    -(g.get("meeting_count") or 0),
                    g.get("name") or g.get("role_label") or g.get("date") or "",
                )
            )
        else:
            groups.sort(
                key=lambda g: (
                    g.get("count") or 0,
                    g.get("meeting_count") or 0,
                    g.get("name") or g.get("role_label") or g.get("date") or "",
                )
            )
    if group_by == "meeting" and sort_by == "count":
        groups.sort(
            key=lambda g: (g.get("count") or 0, g.get("date") or "", g.get("no") or 0),
            reverse=reverse,
        )
    return groups


def _build_matrix_groups(
    rows: list[dict],
    *,
    group_by: str,
    include_meetings: bool,
) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        key: tuple[object, ...]
        if group_by == "member":
            key = (row["member_id"],)
        elif group_by == "role":
            key = (row["role_key"],)
        elif group_by == "meeting":
            key = (row["meeting_id"],)
        else:
            key = (row["member_id"], row["role_key"])
        grouped.setdefault(key, []).append(row)

    groups: list[dict] = []
    for key_rows in grouped.values():
        first = key_rows[0]
        meetings = _unique_meetings(key_rows)
        if group_by == "member":
            group = {
                "member_id": first["member_id"],
                "username": first.get("username"),
                "full_name": first.get("full_name"),
                "name": first.get("full_name"),
                "count": len(key_rows),
                "meeting_count": len(meetings),
                "roles": {
                    role_key: sum(1 for r in key_rows if r["role_key"] == role_key)
                    for role_key in sorted({r["role_key"] for r in key_rows})
                },
            }
        elif group_by == "role":
            group = {
                "role_key": first["role_key"],
                "role_label": first["role_label"],
                "count": len(key_rows),
                "member_count": len({r["member_id"] for r in key_rows}),
                "meeting_count": len(meetings),
            }
        elif group_by == "meeting":
            group = {
                **_project_meeting(first),
                "date": first.get("meeting_date"),
                "count": len(key_rows),
                "member_count": len({r["member_id"] for r in key_rows}),
                "roles": sorted({r["role_key"] for r in key_rows}),
                "members": sorted({r["full_name"] for r in key_rows}),
            }
        else:
            group = {
                "member_id": first["member_id"],
                "username": first.get("username"),
                "full_name": first.get("full_name"),
                "name": first.get("full_name"),
                "role_key": first["role_key"],
                "role_label": first["role_label"],
                "count": len(key_rows),
                "meeting_count": len(meetings),
            }
        if include_meetings:
            group["meetings"] = meetings
        groups.append(group)
    return groups


async def apply_member_role_matrix(
    ctx,
    date_from: str | None = None,
    date_to: str | None = None,
    member: str | None = None,
    role_filter: str | None = None,
    role_group: str | None = None,
    group_by: str = "member_role",
    sort_by: str = "count",
    sort_order: str = "desc",
    limit: int = 50,
    include_meetings: bool = True,
) -> dict:
    """Dashboard member-role matrix rows grouped for chat answers."""
    _require_relative_dates_if_requested(ctx, date_from, date_to)
    _validate_dates(date_from, date_to)
    _validate_limit(limit)
    role_filter = _validate_matrix_role_filter(role_filter)
    role_group = _validate_matrix_role_group(role_group)
    if role_filter and role_group:
        raise ModelRetry("Use either role_filter for one exact role or role_group for a broader category, not both.")
    if group_by not in _VALID_MATRIX_GROUPS:
        raise ModelRetry(f"group_by must be one of: {', '.join(sorted(_VALID_MATRIX_GROUPS))}. " f"Got: {group_by!r}.")
    if sort_by not in _VALID_MATRIX_SORTS:
        raise ModelRetry(f"sort_by must be one of: {', '.join(sorted(_VALID_MATRIX_SORTS))}. " f"Got: {sort_by!r}.")
    if sort_order not in _VALID_SORT_ORDERS:
        raise ModelRetry("sort_order must be 'asc' or 'desc'.")

    rows, unmapped_roles = await asyncio.to_thread(
        _rows_for_member_role_matrix,
        date_from=date_from,
        date_to=date_to,
        member=member,
        role_filter=role_filter,
        role_group=role_group,
    )
    groups = _build_matrix_groups(rows, group_by=group_by, include_meetings=include_meetings)
    groups = _sort_groups(groups, group_by=group_by, sort_by=sort_by, sort_order=sort_order)
    capped = groups[:limit]

    return {
        "value": {
            "groups": capped,
            "total_rows": len(rows),
            "total_groups": len(groups),
            "limit": limit,
            "references": _role_references(rows),
            "reference_total": len(rows),
            "reference_limit": _REFERENCE_LIMIT,
            "unmapped_roles": unmapped_roles,
            "role_mapping": {key: _role_label(key) for key in _MATRIX_ROLES},
            "role_groups": _role_group_mapping(),
        },
        "scope": {
            "date_from": date_from,
            "date_to": date_to,
            "member": member,
            "role_filter": role_filter,
            "role_group": role_group,
            "group_by": group_by,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_meetings": include_meetings,
        },
        "coverage": _coverage(
            source="dashboard_member_role_matrix",
            total_matches=len(groups),
            returned_count=len(capped),
        ),
        "scanned_count": len(rows),
    }


async def apply_meeting_manager_matrix(
    ctx,
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: str | None = None,
    sort_by: str = "count",
    sort_order: str = "desc",
    limit: int = 50,
) -> dict:
    """Per-member counts of meetings managed (Meeting Manager role).

    Backed by `meeting_stats.group_meetings_by_manager`, which counts
    meetings.manager_id grouped by resolved member_id. Always
    server-side aggregated — never have the LLM count cards.
    """
    _require_relative_dates_if_requested(ctx, date_from, date_to)
    _validate_dates(date_from, date_to)
    _validate_limit(limit)
    type_filter = _validate_type_filter(type_filter)
    if sort_by not in ("count", "name"):
        raise ModelRetry(f"sort_by must be 'count' or 'name'. Got: {sort_by!r}.")
    if sort_order not in _VALID_SORT_ORDERS:
        raise ModelRetry("sort_order must be 'asc' or 'desc'.")

    rows = await asyncio.to_thread(
        meeting_stats.group_meetings_by_manager,
        date_from=date_from,
        date_to=date_to,
        type_filter=type_filter,  # type: ignore[arg-type]
    )

    reverse = sort_order == "desc"
    if sort_by == "name":
        rows.sort(key=lambda r: (r.get("full_name") or "").lower(), reverse=reverse)
    else:
        rows.sort(key=lambda r: (r.get("count", 0), (r.get("full_name") or "").lower()), reverse=reverse)

    capped = rows[:limit]
    total_meetings = sum(r.get("count", 0) for r in rows)

    return {
        "value": {
            "groups": capped,
            "total_managers": len(rows),
            "total_meetings": total_meetings,
            "limit": limit,
        },
        "scope": {
            "date_from": date_from,
            "date_to": date_to,
            "type_filter": type_filter,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
        "coverage": _coverage(
            source="meeting_manager_matrix",
            total_matches=len(rows),
            returned_count=len(capped),
        ),
    }


def _winner_key(row: dict) -> str:
    member_id = row.get("member_id")
    if member_id:
        return f"member:{member_id}"
    return f"raw:{row.get('winner_name') or ''}"


def _winner_display_name(row: dict) -> str:
    return row.get("full_name") or row.get("winner_name") or ""


def _winner_fields(row: dict) -> dict:
    return {
        "winner_key": _winner_key(row),
        "winner_name": row.get("winner_name"),
        "winner_resolved": bool(row.get("winner_resolved")),
        "member_id": row.get("member_id"),
        "username": row.get("username"),
        "full_name": row.get("full_name"),
        "name": _winner_display_name(row),
    }


def _project_award_reference(row: dict) -> dict:
    return {
        "award_id": row.get("award_id"),
        "meeting_id": row["meeting_id"],
        "no": row.get("meeting_no"),
        "date": row.get("meeting_date"),
        "theme": row.get("meeting_theme"),
        "category": row.get("category"),
        "winner_name": row.get("winner_name"),
        "winner_resolved": bool(row.get("winner_resolved")),
        "member_id": row.get("member_id"),
        "username": row.get("username"),
        "full_name": row.get("full_name"),
    }


def _award_references(rows: list[dict], *, limit: int = _REFERENCE_LIMIT) -> list[dict]:
    sorted_rows = sorted(
        rows,
        key=lambda r: (
            r.get("meeting_date") or "",
            r.get("meeting_no") or 0,
            _winner_display_name(r),
            r.get("category") or "",
        ),
        reverse=True,
    )
    return [_project_award_reference(row) for row in sorted_rows[:limit]]


def _unresolved_winner_summary(rows: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("winner_resolved"):
            continue
        winner_name = row.get("winner_name") or ""
        counts[winner_name] = counts.get(winner_name, 0) + 1
    return [
        {"winner_name": winner_name, "count": count}
        for winner_name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    ]


def _rows_for_member_award_matrix(
    *,
    date_from: str | None,
    date_to: str | None,
    member: str | None,
    category_filters: list[str] | None,
    meeting_no: int | None,
) -> tuple[list[dict], list[str], set[str] | None]:
    raw_rows = get_member_award_stats(date_from, date_to)
    observed_categories = _observed_award_categories(raw_rows)
    resolved_category_filters = _resolve_award_category_filters(category_filters, observed_categories)
    canonical_member = _resolve_member_or_retry(member) if member else None

    rows: list[dict] = []
    for row in raw_rows:
        if canonical_member and row.get("member_id") != canonical_member.id:
            continue
        if meeting_no is not None and row.get("meeting_no") != meeting_no:
            continue
        category_lower = (row.get("category") or "").lower()
        if resolved_category_filters is not None and category_lower not in resolved_category_filters:
            continue
        rows.append(row)

    return rows, observed_categories, resolved_category_filters


def _build_award_groups(
    rows: list[dict],
    *,
    group_by: str,
    include_meetings: bool,
) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for row in rows:
        key: tuple[object, ...]
        if group_by == "winner":
            key = (_winner_key(row),)
        elif group_by == "category":
            key = (row.get("category") or "",)
        elif group_by == "meeting":
            key = (row["meeting_id"],)
        else:
            key = (_winner_key(row), row.get("category") or "")
        grouped.setdefault(key, []).append(row)

    groups: list[dict] = []
    for key_rows in grouped.values():
        first = key_rows[0]
        meetings = _unique_meetings(key_rows)
        if group_by == "winner":
            group = {
                **_winner_fields(first),
                "count": len(key_rows),
                "meeting_count": len(meetings),
                "categories": {
                    category: sum(1 for r in key_rows if (r.get("category") or "") == category)
                    for category in sorted({r.get("category") or "" for r in key_rows}, key=lambda c: c.lower())
                },
            }
        elif group_by == "category":
            category = first.get("category") or ""
            group = {
                "category": category,
                "name": category,
                "count": len(key_rows),
                "winner_count": len({_winner_key(r) for r in key_rows}),
                "meeting_count": len(meetings),
            }
        elif group_by == "meeting":
            group = {
                **_project_meeting(first),
                "count": len(key_rows),
                "winner_count": len({_winner_key(r) for r in key_rows}),
                "categories": sorted({r.get("category") or "" for r in key_rows}, key=lambda c: c.lower()),
                "winners": sorted({_winner_display_name(r) for r in key_rows}, key=lambda n: n.lower()),
            }
        else:
            category = first.get("category") or ""
            group = {
                **_winner_fields(first),
                "category": category,
                "count": len(key_rows),
                "meeting_count": len(meetings),
            }
        if include_meetings:
            group["meetings"] = meetings
        groups.append(group)
    return groups


def _sort_award_groups(
    groups: list[dict],
    *,
    sort_by: str,
    sort_order: str,
) -> list[dict]:
    reverse = sort_order == "desc"
    if sort_by == "date":
        groups.sort(
            key=lambda g: (
                g.get("date") or "",
                g.get("no") or 0,
                g.get("name") or g.get("category") or "",
            ),
            reverse=reverse,
        )
    elif sort_by == "name":
        groups.sort(
            key=lambda g: (
                g.get("name") or g.get("category") or "",
                g.get("category") or "",
            ),
            reverse=reverse,
        )
    elif reverse:
        groups.sort(
            key=lambda g: (
                -(g.get("count") or 0),
                -(g.get("meeting_count") or 0),
                g.get("name") or g.get("category") or g.get("date") or "",
            )
        )
    else:
        groups.sort(
            key=lambda g: (
                g.get("count") or 0,
                g.get("meeting_count") or 0,
                g.get("name") or g.get("category") or g.get("date") or "",
            )
        )
    return groups


async def apply_member_award_matrix(
    ctx,
    date_from: str | None = None,
    date_to: str | None = None,
    member: str | None = None,
    category_filters: list[str] | None = None,
    meeting_no: int | None = None,
    group_by: str = "winner_category",
    sort_by: str = "count",
    sort_order: str = "desc",
    limit: int = 50,
    include_meetings: bool = True,
) -> dict:
    """Dashboard-style award rows grouped for chat answers."""
    _require_relative_dates_if_requested(ctx, date_from, date_to)
    _validate_dates(date_from, date_to)
    _validate_limit(limit)
    if group_by not in _VALID_AWARD_GROUPS:
        raise ModelRetry(f"group_by must be one of: {', '.join(sorted(_VALID_AWARD_GROUPS))}. " f"Got: {group_by!r}.")
    if sort_by not in _VALID_AWARD_SORTS:
        raise ModelRetry(f"sort_by must be one of: {', '.join(sorted(_VALID_AWARD_SORTS))}. " f"Got: {sort_by!r}.")
    if sort_order not in _VALID_SORT_ORDERS:
        raise ModelRetry("sort_order must be 'asc' or 'desc'.")

    rows, observed_categories, resolved_category_filters = await asyncio.to_thread(
        _rows_for_member_award_matrix,
        date_from=date_from,
        date_to=date_to,
        member=member,
        category_filters=category_filters,
        meeting_no=meeting_no,
    )
    groups = _build_award_groups(rows, group_by=group_by, include_meetings=include_meetings)
    groups = _sort_award_groups(groups, sort_by=sort_by, sort_order=sort_order)
    capped = groups[:limit]

    return {
        "value": {
            "groups": capped,
            "total_rows": len(rows),
            "total_groups": len(groups),
            "limit": limit,
            "references": _award_references(rows),
            "reference_total": len(rows),
            "reference_limit": _REFERENCE_LIMIT,
            "unresolved_winners": _unresolved_winner_summary(rows),
            "standard_category_mapping": _standard_award_category_mapping(),
            "observed_categories": observed_categories,
        },
        "scope": {
            "date_from": date_from,
            "date_to": date_to,
            "member": member,
            "category_filters": category_filters,
            "resolved_category_filters": (
                sorted(resolved_category_filters) if resolved_category_filters is not None else None
            ),
            "meeting_no": meeting_no,
            "group_by": group_by,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_meetings": include_meetings,
        },
        "coverage": _coverage(
            source="dashboard_member_award_matrix",
            total_matches=len(groups),
            returned_count=len(capped),
        ),
        "scanned_count": len(rows),
    }
