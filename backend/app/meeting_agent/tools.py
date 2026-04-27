"""Tool implementations. Separated from Pydantic AI @agent.tool registration
so they can be unit-tested with a plain dataclass context."""

import asyncio
import re
import threading
import uuid
from typing import Any

from pydantic_ai import ModelRetry

from app.db.core import get_meeting_by_id, get_meeting_id_by_no, get_meetings
from app.meeting_agent.models import Agenda, Segment
from app.meeting_agent.normalize import meeting_to_agenda
from app.meeting_agent.prompts import CLUB_MEMBERS
from app.meeting_agent.timing import recompute_start_times
from app.meeting_agent.validators import run_validators
from app.models.meeting import Meeting
from app.utils.meeting import parse_meeting_agenda_image, plan_meeting_from_text

_ALLOWED_META_FIELDS = {
    "type",
    "theme",
    "location",
    "date",
    "start_time",
    "no",
    "manager",
    "introduction",
}

# The frontend's <select> for Meeting Type only renders these three options.
# Any other value sets the form state but the dropdown silently falls back to
# Regular, giving a misleading success. Also the canonical `meetings.type`
# CHECK constraint rejects anything outside its own allow-list, so a
# mis-typed value here would fail at Save time anyway.
_ALLOWED_MEETING_TYPES = {"Regular", "Workshop", "Custom"}

_REQUIRED_MEETING_FIELDS: tuple[tuple[str, str], ...] = (
    ("no", "Meeting No."),
    ("theme", "Theme"),
    ("manager", "Meeting Manager"),
    ("date", "Date"),
    ("start_time", "Start Time"),
    ("end_time", "End Time"),
    ("location", "Location"),
)

_TEXT_REQUIRED_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "no": (
        # Explicit: "Meeting No: 451" / "no.451"
        r"(?i)\b(?:meeting\s*)?(?:no\.?|number)\s*[:\uFF1A]?\s*\d+",
        # "#451"
        r"#\s*\d+",
        # Club name + ordinal: "SOARHIGH 387th"
        r"(?i)\bsoarhigh\s+\d+(?:st|nd|rd|th)?\b",
        # Chinese: "第 451 期" / "第 451 次"
        r"第\s*\d+\s*[期次]",
        # Bare English ordinal: "451st" / "388th" — common in event headers
        # (e.g. "@ Allpeople Gather ~ 451st"). Permissive on purpose: better
        # to accept a planner-extracted value than to discard it.
        r"\b\d+\s*(?:st|nd|rd|th)\b",
    ),
    "theme": (
        r"(?i)(?:theme|主题)\s*[:\uFF1A\u4E3A]",
        r"✍",
        r"✈",
        r"(?i)\bsoarhigh\b[^\n:\uFF1A]{0,80}[:\uFF1A]\s*\S+",
    ),
    "manager": (
        r"(?i)(?:meeting\s*)?manager\s*[:\uFF1A]",
        r"(?im)(?:^|\n)\s*(?:👧\s*)?MM\s*[:\uFF1A]",
        r"(?:会议经理|主持人|主持)\s*[:\uFF1A]",
    ),
    "date": (
        r"(?i)(?:date|日期)\s*[:\uFF1A\u4E3A]",
        r"📅",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ),
    "start_time": (
        r"(?i)(?:time|时间)\s*[:\uFF1A\u4E3A]",
        r"⏰",
        r"\b\d{1,2}\s*:\s*\d{2}\s*(?:-|\u2013|\u2014|~|到|至)\s*\d{1,2}\s*:\s*\d{2}\b",
    ),
    "end_time": (
        r"(?i)(?:time|时间)\s*[:\uFF1A\u4E3A]",
        r"⏰",
        r"\b\d{1,2}\s*:\s*\d{2}\s*(?:-|\u2013|\u2014|~|到|至)\s*\d{1,2}\s*:\s*\d{2}\b",
    ),
    "location": (
        r"(?i)(?:location|地点|地址|venue)\s*[:\uFF1A\u4E3A]",
        r"📍",
    ),
}


# Matches a trailing "(member)" / "(guest)" / "(All)". Accepts ASCII and
# fullwidth parens because CJK keyboards routinely produce U+FF08 / U+FF09.
_MEMBERSHIP_SUFFIX_RE = re.compile(
    r"\s*[\(（]\s*(?:member|guest|all)\s*[\)）]\s*$",  # noqa: RUF001
    re.IGNORECASE,
)


def _strip_membership_suffix(name: str | None) -> str:
    """Remove a trailing "(member)" / "(guest)" / "(All)" annotation that the
    model may have copied verbatim from a previous turn's reply table.

    The chat replies render role takers with a parenthesized membership badge
    (e.g. "Lucas (guest)") so users can verify at a glance. The annotation
    must NEVER end up in the underlying `role_taker` field — that would
    corrupt the data for storage and confuse the form's own member/guest
    badge logic. This helper is the single chokepoint applied wherever a
    name comes in from a tool argument."""
    if not name:
        return name or ""
    return _MEMBERSHIP_SUFFIX_RE.sub("", name).strip()


def apply_set_role(ctx, segment_id: str, role_taker: str) -> dict:
    """Unilateral: set the role taker for ONE segment."""
    role_taker = _strip_membership_suffix(role_taker)
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.role_taker = role_taker
    return {"segment_id": segment_id, "role_taker": role_taker}


def apply_set_type(ctx, segment_id: str, type: str) -> dict:
    """Unilateral: rename ONE segment's type. Does not affect timing."""
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.type = type
    return {"segment_id": segment_id, "type": type}


def apply_set_duration(ctx, segment_id: str, duration_min: int) -> dict:
    """Unilateral: set ONE segment's duration, then cascade downstream times."""
    if duration_min <= 0:
        raise ModelRetry(f"duration must be positive; got {duration_min}")
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.duration = duration_min
    recompute_start_times(ctx.deps.agenda)
    return {"segment_id": segment_id, "duration_min": duration_min}


def apply_set_buffer(ctx, segment_id: str, buffer_min: int) -> dict:
    """Unilateral: set the buffer_before for ONE segment, then cascade."""
    if buffer_min < 0:
        raise ModelRetry(f"buffer_min must be >= 0; got {buffer_min}")
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.buffer_before = buffer_min
    recompute_start_times(ctx.deps.agenda)
    return {"segment_id": segment_id, "buffer_min": buffer_min}


def apply_set_meta(ctx, field: str, value: str) -> dict:
    """Set one meeting-level meta field. Cascades times if start_time changes."""
    if field not in _ALLOWED_META_FIELDS:
        raise ModelRetry(
            f"Unknown meta field: {field}. Allowed: type, theme, location, date, "
            f"start_time, no, manager, introduction"
        )
    if field == "manager":
        # Same chokepoint as role_taker: strip any "(member)/(guest)" annotation
        # the model may have copied verbatim from an earlier table.
        value = _strip_membership_suffix(value)

    meta = ctx.deps.agenda.meta

    if field == "no":
        if value == "" or value is None:
            meta.no = None
        else:
            try:
                meta.no = int(value)
            except (TypeError, ValueError):
                raise ModelRetry(f"Meeting number must be an integer; got '{value}'") from None
    elif field == "type":
        if value not in _ALLOWED_MEETING_TYPES:
            raise ModelRetry(
                f"Meeting type must be one of: {', '.join(sorted(_ALLOWED_MEETING_TYPES))}. " f"Got: '{value}'."
            )
        meta.type = value
    else:
        setattr(meta, field, value if value else None)

    if field == "start_time":
        recompute_start_times(ctx.deps.agenda)

    return {"field": field, "value": value}


def apply_add_segment(
    ctx,
    type: str,
    duration_min: int,
    after_id: str | None = None,
    before_id: str | None = None,
    role_taker: str = "",
) -> dict:
    """Insert a new segment relative to an anchor. Exactly one of
    after_id or before_id must be provided. Downstream times recompute."""
    role_taker = _strip_membership_suffix(role_taker)
    if (after_id is None) == (before_id is None):
        raise ModelRetry("provide exactly one of after_id or before_id")
    if duration_min <= 0:
        raise ModelRetry(f"duration_min must be positive; got {duration_min}")
    if type.strip() == "":
        raise ModelRetry("type must be a non-empty string")

    anchor_id = after_id if after_id is not None else before_id
    agenda = ctx.deps.agenda

    anchor_idx = None
    for i, seg in enumerate(agenda.segments):
        if seg.id == anchor_id:
            anchor_idx = i
            break
    if anchor_idx is None:
        raise ModelRetry(f"unknown anchor segment: {anchor_id}")

    new_id = uuid.uuid4().hex[:5]
    new_seg = Segment(
        id=new_id,
        type=type,
        start_time="00:00",
        duration=duration_min,
        role_taker=role_taker,
        buffer_before=0,
    )

    insertion_index = anchor_idx + 1 if after_id is not None else anchor_idx
    agenda.segments.insert(insertion_index, new_seg)
    recompute_start_times(agenda)

    return {
        "new_segment_id": new_id,
        "type": type,
        "duration_min": duration_min,
        "role_taker": role_taker,
        "inserted_at_index": insertion_index,
    }


def apply_remove_segment(ctx, segment_id: str) -> dict:
    """Remove a segment by id. Downstream times recompute."""
    agenda = ctx.deps.agenda
    target_idx = None
    for i, seg in enumerate(agenda.segments):
        if seg.id == segment_id:
            target_idx = i
            break
    if target_idx is None:
        raise ModelRetry(f"unknown segment: {segment_id}")

    agenda.segments.pop(target_idx)
    recompute_start_times(agenda)
    return {"removed_segment_id": segment_id}


def apply_move_segment(
    ctx,
    segment_id: str,
    after_id: str | None = None,
    before_id: str | None = None,
) -> dict:
    """Relocate a segment to a new position relative to an anchor. Exactly one
    of after_id or before_id must be provided. Downstream times recompute."""
    if (after_id is None) == (before_id is None):
        raise ModelRetry("provide exactly one of after_id or before_id")

    anchor_id = after_id if after_id is not None else before_id
    if segment_id == anchor_id:
        raise ModelRetry("cannot move a segment relative to itself")

    agenda = ctx.deps.agenda

    seg_idx = None
    for i, seg in enumerate(agenda.segments):
        if seg.id == segment_id:
            seg_idx = i
            break
    if seg_idx is None:
        raise ModelRetry(f"unknown segment: {segment_id}")

    anchor_idx = None
    for i, seg in enumerate(agenda.segments):
        if seg.id == anchor_id:
            anchor_idx = i
            break
    if anchor_idx is None:
        raise ModelRetry(f"unknown anchor segment: {anchor_id}")

    moving = agenda.segments.pop(seg_idx)

    # Re-find the anchor index since popping may have shifted it. Anchor is
    # guaranteed to still exist here: we established segment_id != anchor_id
    # above, so the pop removed a different segment.
    new_anchor_idx = next(i for i, seg in enumerate(agenda.segments) if seg.id == anchor_id)

    new_idx = new_anchor_idx + 1 if after_id is not None else new_anchor_idx
    agenda.segments.insert(new_idx, moving)
    recompute_start_times(agenda)

    return {"segment_id": segment_id, "new_index": new_idx}


def apply_swap_roles(ctx, segment_id_a: str, segment_id_b: str) -> dict:
    """Bilateral: atomically exchange the role_taker between TWO segments.
    Positions, durations, buffers, and start_times are unchanged."""
    if segment_id_a == segment_id_b:
        raise ModelRetry("cannot swap a segment with itself")

    agenda = ctx.deps.agenda

    seg_a = None
    seg_b = None
    for seg in agenda.segments:
        if seg.id == segment_id_a:
            seg_a = seg
        elif seg.id == segment_id_b:
            seg_b = seg
    if seg_a is None:
        raise ModelRetry(f"unknown segment: {segment_id_a}")
    if seg_b is None:
        raise ModelRetry(f"unknown segment: {segment_id_b}")

    seg_a.role_taker, seg_b.role_taker = seg_b.role_taker, seg_a.role_taker

    return {
        "segment_id_a": segment_id_a,
        "segment_id_b": segment_id_b,
        "role_taker_a": seg_a.role_taker,
        "role_taker_b": seg_b.role_taker,
    }


def apply_swap_time(ctx, segment_id_a: str, segment_id_b: str) -> dict:
    """Bilateral: exchange the sequence positions of TWO segments. Also swaps
    buffer_before values because a buffer is a gap at a POSITION — it belongs
    to the slot, not the segment. Downstream times recompute."""
    if segment_id_a == segment_id_b:
        raise ModelRetry("cannot swap a segment with itself")

    agenda = ctx.deps.agenda

    idx_a = None
    idx_b = None
    for i, seg in enumerate(agenda.segments):
        if seg.id == segment_id_a:
            idx_a = i
        elif seg.id == segment_id_b:
            idx_b = i
    if idx_a is None:
        raise ModelRetry(f"unknown segment: {segment_id_a}")
    if idx_b is None:
        raise ModelRetry(f"unknown segment: {segment_id_b}")

    seg_a = agenda.segments[idx_a]
    seg_b = agenda.segments[idx_b]

    # Swap array positions.
    agenda.segments[idx_a], agenda.segments[idx_b] = seg_b, seg_a
    # Swap buffer_before so gaps stay anchored to their positions, not segments.
    buf_a = seg_a.buffer_before or 0
    seg_a.buffer_before = seg_b.buffer_before or 0
    seg_b.buffer_before = buf_a

    recompute_start_times(agenda)

    # After swap: a is at idx_b, b is at idx_a.
    return {
        "segment_id_a": segment_id_a,
        "segment_id_b": segment_id_b,
        "new_index_a": idx_b,
        "new_index_b": idx_a,
    }


def apply_shift_segment_time(ctx, segment_id: str, delta_min: int) -> dict:
    """Shift ONE segment earlier/later by signed minutes via buffer_before.
    Positive delta increases the gap (pushes later). Negative delta consumes
    the existing gap (pulls earlier) — refuses if gap is insufficient or
    segment is first."""
    agenda = ctx.deps.agenda

    seg_idx = None
    for i, seg in enumerate(agenda.segments):
        if seg.id == segment_id:
            seg_idx = i
            break
    if seg_idx is None:
        raise ModelRetry(f"unknown segment: {segment_id}")

    if delta_min == 0:
        return {"segment_id": segment_id, "delta_min": 0}

    seg = agenda.segments[seg_idx]

    if delta_min < 0:
        if seg_idx == 0:
            raise ModelRetry(
                "cannot shift the first segment earlier; move meeting start_time earlier via set_meta instead"
            )
        available = seg.buffer_before or 0
        if abs(delta_min) > available:
            raise ModelRetry(
                f"only {available} min gap available before segment {segment_id}; "
                f"cannot pull back {abs(delta_min)} min"
            )

    seg.buffer_before = (seg.buffer_before or 0) + delta_min
    recompute_start_times(agenda)

    direction = "later" if delta_min > 0 else "earlier"
    return {
        "segment_id": segment_id,
        "delta_min": delta_min,
        "new_buffer_before": seg.buffer_before,
        "direction": direction,
    }


def _validation_issues(agenda: Agenda) -> list[dict]:
    return [issue.model_dump() for issue in run_validators(agenda)]


def _is_blank_meta_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _meeting_summary(agenda: Agenda) -> dict:
    meta = agenda.meta
    return {
        "no": meta.no,
        "type": meta.type,
        "theme": meta.theme,
        "manager": meta.manager,
        "date": meta.date,
        "start_time": meta.start_time,
        "end_time": meta.end_time,
        "location": meta.location,
        "segment_count": len(agenda.segments),
    }


def _membership_label(role_taker: str) -> str | None:
    """Resolve a role_taker string to "member" / "guest" / None.

    None for "All" / empty (group roles like Table Topic Session). Exact
    full-name match against CLUB_MEMBERS (case-insensitive) → "member";
    any other non-empty name → "guest". Centralizing this here keeps the
    chat reply consistent with the form's badge logic without relying on
    the model to scan the CLUB_MEMBERS section of its system prompt for
    every row in the segment table — a check that has been observed to
    misfire (e.g. labeling Lucas as a member when he is a guest)."""
    name = (role_taker or "").strip()
    if not name or name.lower() == "all":
        return None
    name_lower = name.lower()
    for member in CLUB_MEMBERS:
        if member.lower() == name_lower:
            return "member"
    return "guest"


def _format_role_display(role_taker: str) -> str:
    """Pre-baked display string for the segment table's Role taker column.

    Contains the membership annotation so the model can emit it verbatim
    instead of recomputing per row. Empty / falsy roles render as a dash
    so the column never goes blank."""
    membership = _membership_label(role_taker)
    if membership is None:
        return role_taker if role_taker else "—"
    return f"{role_taker} ({membership})"


def _segments_summary(agenda: Agenda) -> list[dict]:
    """Compact list of every segment, in order — for the model's reply table.

    The router prompt's snapshot reflects pre-tool state (built once at turn
    start). Without surfacing segments in the tool result, after wholesale
    creation the model has no way to count segments accurately and might
    fabricate from raw_text.

    Intentionally omits any (member)/(guest) annotation. Membership is a pure
    render-layer concern — the route addendum (`_render_segment_table`) and
    the frontend form compute it deterministically from CLUB_MEMBERS. Keeping
    it out of the tool result means the model never sees the annotated form
    and therefore can never copy it back into a tool argument."""
    return [
        {
            "id": seg.id,
            "start_time": seg.start_time,
            "type": seg.type,
            "duration": seg.duration,
            "role_taker": seg.role_taker,
            "buffer_before": seg.buffer_before,
        }
        for seg in agenda.segments
    ]


def _missing_required_fields(agenda: Agenda) -> list[dict]:
    missing: list[dict] = []
    for field, label in _REQUIRED_MEETING_FIELDS:
        value = getattr(agenda.meta, field)
        if _is_blank_meta_value(value):
            missing.append({"field": field, "label": label})
    return missing


def _text_mentions_required_field(raw_text: str, field: str) -> bool:
    patterns = _TEXT_REQUIRED_FIELD_PATTERNS[field]
    return any(re.search(pattern, raw_text) for pattern in patterns)


def _clear_required_fields_absent_from_text(agenda: Agenda, raw_text: str) -> None:
    """Prevent the text planner from silently hallucinating required fields.

    The planner may infer a plausible manager/location/date when the source
    text is incomplete. For create-from-text, the user needs to confirm missing
    essentials explicitly, so fields without source evidence are cleared and
    surfaced in `missing_required_fields`.
    """
    for field, _label in _REQUIRED_MEETING_FIELDS:
        if not _text_mentions_required_field(raw_text, field):
            setattr(agenda.meta, field, None)


async def apply_create_from_text(ctx, raw_text: str) -> dict:
    """Wholesale replace the agenda by parsing a pasted registration message."""
    if not raw_text or not raw_text.strip():
        raise ModelRetry("raw_text must not be empty")
    try:
        meeting = await asyncio.to_thread(plan_meeting_from_text, raw_text)
    except ValueError as e:
        raise ModelRetry(f"create_from_text failed: {e}") from e

    new_agenda = meeting_to_agenda(meeting)
    _clear_required_fields_absent_from_text(new_agenda, raw_text)
    # Trust the planner's start_times. The developer prompt enforces the
    # invariants we care about (Note 2: no buffer between segments; Note 8:
    # 19:15 "Members and Guest Registration, Warm Up" as the first segment
    # for Regular / Workshop). Calling recompute_start_times here would
    # re-anchor on meta.start_time (e.g. 19:30 from the source registration
    # text) and overwrite the planner's 19:15 warmup positioning.
    ctx.deps.agenda.meta = new_agenda.meta
    ctx.deps.agenda.segments = new_agenda.segments
    return {
        "created": True,
        "segment_count": len(new_agenda.segments),
        "meeting_summary": _meeting_summary(ctx.deps.agenda),
        "segments": _segments_summary(ctx.deps.agenda),
        "missing_required_fields": _missing_required_fields(ctx.deps.agenda),
        "validation_issues": _validation_issues(ctx.deps.agenda),
    }


# Soarhigh Regular meeting standard structure — 22 segments, 2 prepared
# speeches, 19:15 warmup → 21:15 closing. President defaults follow the
# planner prompt convention (Amy Fang for Opening Remarks / Awards /
# Closing Remarks); user re-assigns via subsequent chat edits.
_REGULAR_2PS_SEGMENTS: tuple[tuple[str, str, int, str], ...] = (
    # (type, start_time, duration_min, role_taker)
    ("Members and Guests Registration, Warm Up", "19:15", 15, "All"),
    ("Meeting Rules Introduction (SAA)", "19:30", 2, ""),
    ("Opening Remarks", "19:32", 2, "Amy Fang"),
    ("TOM (Toastmaster of Meeting) Introduction", "19:34", 2, ""),
    ("Timer", "19:36", 2, ""),
    ("Hark Master", "19:38", 1, ""),
    ("Guests Self Introduction (30s per guest)", "19:39", 8, "All"),
    ("TTM (Table Topic Master) Opening", "19:47", 3, ""),
    ("Table Topic Session", "19:50", 20, "All"),
    ("Prepared Speech", "20:10", 7, ""),
    ("Prepared Speech", "20:17", 7, ""),
    ("Tea Break & Group Photos", "20:24", 10, "All"),
    ("Table Topic Evaluation", "20:34", 7, ""),
    ("Prepared Speech Evaluation", "20:41", 3, ""),
    ("Prepared Speech Evaluation", "20:44", 3, ""),
    ("Timer's Report", "20:47", 2, ""),
    ("Hark Master Pop Quiz", "20:49", 5, ""),
    ("General Evaluation", "20:54", 8, ""),
    ("Voting Section", "21:02", 2, ""),
    ("Moment of Truth", "21:04", 7, ""),
    ("Awards", "21:11", 3, "Amy Fang"),
    ("Closing Remarks", "21:14", 1, "Amy Fang"),
)


def _build_template_regular_2ps() -> Agenda:
    """Hardcoded Regular meeting with 2 prepared speeches.

    Segments are back-to-back from 19:15 (warmup) to 21:15 (closing).
    meta.start_time is 19:30 (the official meeting start, after warmup);
    meta.end_time is intentionally None so the validator skips overflow /
    underflow checks until the user fills it in (the agenda's actual end
    is 21:15, but typical SoarHigh slots end at 21:30 — let the user
    decide rather than picking one for them)."""
    from app.meeting_agent.models import Meta as _Meta

    meta = _Meta(
        type="Regular",
        start_time="19:30",
    )
    segments = [
        Segment(
            id=f"s{i + 1}",
            type=seg_type,
            start_time=start,
            duration=duration,
            role_taker=role,
            buffer_before=0,
        )
        for i, (seg_type, start, duration, role) in enumerate(_REGULAR_2PS_SEGMENTS)
    ]
    return Agenda(meta=meta, segments=segments)


def _build_template_custom() -> Agenda:
    """Minimal single-segment Custom meeting starter.

    Custom meetings have no fixed structural convention — no required
    canonical segment list. The template gives the user a blank slate with
    ONE placeholder segment so the form has something to render; they build
    it up segment-by-segment via subsequent chat edits (set_type, add_segment,
    set_role, etc.). The placeholder is positioned at 19:15 with a 15-min
    duration so it aligns with the standard pre-meeting warmup window — the
    user can rename / resize / re-anchor as needed. meta.start_time is set to
    the typical 19:30 club slot; everything else is left blank."""
    from app.meeting_agent.models import Meta as _Meta

    meta = _Meta(
        type="Custom",
        start_time="19:30",
    )
    segments = [
        Segment(
            id="s1",
            type="Segment 1",
            start_time="19:15",
            duration=15,
            role_taker="",
            buffer_before=0,
        )
    ]
    return Agenda(meta=meta, segments=segments)


_TEMPLATE_BUILDERS = {
    "regular_2ps": _build_template_regular_2ps,
    # Aliases — the model has been observed to reach for whatever name the user
    # said; mapping common variants here keeps the contract forgiving without
    # opening the door to free-form creation.
    "regular": _build_template_regular_2ps,
    "regular 2 ps": _build_template_regular_2ps,
    "regular_2_ps": _build_template_regular_2ps,
    "2ps": _build_template_regular_2ps,
    "custom": _build_template_custom,
    "custom_blank": _build_template_custom,
    "blank": _build_template_custom,
}


async def apply_create_from_template(ctx, template: str) -> dict:
    """Wholesale replace the agenda with a stock template — deterministic, no
    planner / LLM call.

    Use when the user wants a meeting from scratch with no source material
    (registration text, image, or historical meeting number). Currently
    supports "regular_2ps" (canonical 22-segment Regular with 2 prepared
    speeches). The user fills theme / manager / date / location and any
    role_takers via subsequent chat edits."""
    key = (template or "").strip().lower()
    builder = _TEMPLATE_BUILDERS.get(key)
    if builder is None:
        raise ModelRetry(
            f"Unknown template: {template!r}. Supported names: " f"{', '.join(sorted(_TEMPLATE_BUILDERS.keys()))}"
        )
    new_agenda = builder()
    ctx.deps.agenda.meta = new_agenda.meta
    ctx.deps.agenda.segments = new_agenda.segments
    return {
        "created": True,
        "segment_count": len(new_agenda.segments),
        "meeting_summary": _meeting_summary(ctx.deps.agenda),
        "segments": _segments_summary(ctx.deps.agenda),
        "missing_required_fields": _missing_required_fields(ctx.deps.agenda),
        "validation_issues": _validation_issues(ctx.deps.agenda),
    }


# Supabase's Python client wraps a SYNC httpx client which is NOT thread-safe;
# concurrent calls from worker threads (e.g. several `preview_meeting` tools
# firing in parallel via `asyncio.to_thread`) corrupt the HTTP/2 stream state
# and surface as `httpx.RemoteProtocolError: Server disconnected`. Serialize
# every agent-side DB query through this lock so parallel tool calls fall back
# to sequential — adds ~few hundred ms per extra call but is fully reliable.
_DB_LOCK = threading.Lock()


def _db_meetings_recent(limit: int = 50) -> list[dict]:
    """Thin sync wrapper so tests can patch the DB fetch."""
    with _DB_LOCK:
        page = get_meetings(user_id=None, status=None, page=1, page_size=limit)
    return page.get("items", [])


def _lookup_to_card(meeting: dict) -> dict:
    manager = meeting.get("manager") or {}
    manager_name = manager.get("name") if isinstance(manager, dict) else (manager or "")
    return {
        "no": meeting.get("no"),
        "type": meeting.get("type", ""),
        "date": meeting.get("date", ""),
        "theme": meeting.get("theme", ""),
        "manager_name": manager_name or "",
        "segment_count": len(meeting.get("segments") or []),
    }


async def apply_show_current_agenda(ctx) -> dict:
    """Read-only echo of the current draft agenda. The tool itself returns the
    same `meeting_summary` + `segments` shape as the creation tools so the model
    has full data to acknowledge — but the meaningful artifact is server-side:
    the route detects this tool call and appends folded meta + agenda tables
    (with deterministic (member)/(guest) badges) below the model's reply, just
    like preview_meeting does for historical meetings."""
    return {
        "shown": True,
        "meeting_summary": _meeting_summary(ctx.deps.agenda),
        "segments": _segments_summary(ctx.deps.agenda),
    }


def _preview_segment(src: dict) -> dict:
    """Project a DB segment row into the agent's preview shape — same fields
    we surface for the current agenda's `segments` summary so the model can
    treat preview output and current-agenda output uniformly."""
    role = src.get("role_taker") or {}
    role_name = role.get("name") if isinstance(role, dict) else (role or "")
    try:
        duration = int(src.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    return {
        "type": src.get("type", ""),
        "start_time": src.get("start_time", ""),
        "duration": duration,
        "role_taker": role_name or "",
    }


async def apply_preview_meeting(ctx, no: int) -> dict:
    """Read-only fetch of a single historical meeting's full structure —
    meta + ordered segments — without modifying the current agenda.

    Bridges the gap between `lookup_meeting` (lightweight cards, no segments)
    and `clone_from_meeting` (destructive replace). Use this when the user
    wants to inspect what a meeting looks like before deciding whether to
    clone it. The route does NOT auto-render an agenda table for this tool,
    so present the segments yourself in a Markdown table if the user asked
    to see them — the data is unambiguously yours to read here."""
    meeting_dict = await asyncio.to_thread(_db_get_meeting_by_no, no)
    if meeting_dict is None:
        raise ModelRetry(f"Meeting #{no} not found in recent history.")

    manager = meeting_dict.get("manager") or {}
    manager_name = manager.get("name") if isinstance(manager, dict) else (manager or "")
    return {
        "no": meeting_dict.get("no"),
        "type": meeting_dict.get("type", ""),
        "theme": meeting_dict.get("theme", ""),
        "date": meeting_dict.get("date", ""),
        "manager": manager_name or "",
        "start_time": meeting_dict.get("start_time", ""),
        "end_time": meeting_dict.get("end_time", ""),
        "location": meeting_dict.get("location", ""),
        "segments": [_preview_segment(s) for s in (meeting_dict.get("segments") or [])],
    }


async def apply_lookup_meeting(ctx, query: str) -> list[dict]:
    """Find historical meetings by number or descriptor. Returns up to 5 cards."""
    q = (query or "").strip()
    if not q:
        return []

    digits = "".join(ch for ch in q if ch.isdigit())
    if digits and len(digits) <= 4:
        target = int(digits)
        items = await asyncio.to_thread(_db_meetings_recent, 200)
        return [_lookup_to_card(m) for m in items if m.get("no") == target][:1]

    items = await asyncio.to_thread(_db_meetings_recent, 50)
    type_filter = None
    ql = q.lower()
    if "workshop" in ql or "工作坊" in ql:
        type_filter = "Workshop"
    elif "regular" in ql or "常规" in ql:
        type_filter = "Regular"
    elif "custom" in ql:
        type_filter = "Custom"

    if type_filter:
        items = [m for m in items if m.get("type") == type_filter]

    return [_lookup_to_card(m) for m in items[:5]]


def _db_get_meeting_by_no(no: int) -> dict | None:
    """Resolve a meeting by its display number to a fully-hydrated dict.

    Two cheap targeted queries:
    1. `get_meeting_id_by_no(no)` — single-row lookup `meetings.eq("no", no)`.
    2. `get_meeting_by_id(id)` — per-meeting fetch with all segments.

    Avoids the bulk `_db_meetings_recent(500)` scan which uses
    `.in_(500 meeting_ids)`: that URL alone is ~18 KB and overflows
    PostgREST / cloudflare URL-length limits when several preview /
    clone calls fire concurrently in one turn (parallel tool calls
    have hit 400 'JSON could not be generated' / cloudflare bad-request
    pages in production). It also missed late-time segments via a
    PostgREST 1000-row cap — `get_meeting_by_id` is unaffected by both."""
    with _DB_LOCK:
        meeting_id = get_meeting_id_by_no(no)
        if meeting_id is None:
            return None
        return get_meeting_by_id(meeting_id, user_id=None)


_CLONE_LOOKUP_LOOKBACK_TURNS = 3


def _tool_result_cards(result: Any) -> list[dict]:
    if isinstance(result, list):
        return [c for c in result if isinstance(c, dict)]
    return []


async def _recent_lookup_includes_no(session_id: str, no: int) -> bool:
    from app.meeting_agent import store as _store_module

    tail_seq, _ = await _store_module.session_store.load(session_id)
    if tail_seq <= 0:
        return False
    for seq in range(tail_seq, max(0, tail_seq - _CLONE_LOOKUP_LOOKBACK_TURNS), -1):
        turn = await _store_module.session_store.load_turn(session_id, seq)
        if turn is None:
            continue
        for trace in turn.tool_trace or []:
            if trace.get("name") != "lookup_meeting" or trace.get("status") != "ok":
                continue
            if any(card.get("no") == no for card in _tool_result_cards(trace.get("result"))):
                return True
    return False


def _is_explicit_clone_confirmation(text: str) -> bool:
    q = (text or "").strip().lower()
    if not q:
        return False
    negatives = ("不", "别", "不用", "不要", "算了", "取消", "不是", "no", "not", "wrong", "cancel")
    if any(n in q for n in negatives):
        return False
    confirmations = (
        "确认",
        "对",
        "是",
        "好的",
        "好",
        "可以",
        "行",
        "没错",
        "yes",
        "yep",
        "ok",
        "okay",
        "sure",
        "confirm",
        "do it",
    )
    return any(c in q for c in confirmations)


async def apply_clone_from_meeting(ctx, no: int) -> dict:
    """Clone a meeting's structure into the current agenda after confirmation."""
    if not await _recent_lookup_includes_no(ctx.deps.session_id, no):
        raise ModelRetry(
            f"clone_from_meeting refused: no recent lookup_meeting surfaced #{no}. "
            "Call lookup_meeting first, present the result, then wait for explicit confirmation."
        )
    if not _is_explicit_clone_confirmation(ctx.deps.current_user_message):
        raise ModelRetry(
            "clone_from_meeting refused: the current user message is not an explicit confirmation. "
            "Ask the user to confirm the looked-up meeting before cloning."
        )

    meeting_dict = await asyncio.to_thread(_db_get_meeting_by_no, no)
    if meeting_dict is None:
        raise ModelRetry(f"Meeting #{no} not found in recent history.")

    cloned = meeting_to_agenda(Meeting(**meeting_dict))
    cloned.meta.no = None
    cloned.meta.theme = None
    cloned.meta.manager = None
    cloned.meta.date = None
    cloned.meta.introduction = None
    for seg in cloned.segments:
        seg.role_taker = ""

    ctx.deps.agenda.meta = cloned.meta
    ctx.deps.agenda.segments = cloned.segments
    return {
        "cloned_from_no": no,
        "segment_count": len(cloned.segments),
        "meeting_summary": _meeting_summary(ctx.deps.agenda),
        "segments": _segments_summary(ctx.deps.agenda),
        "missing_required_fields": _missing_required_fields(ctx.deps.agenda),
        "validation_issues": _validation_issues(ctx.deps.agenda),
    }


async def apply_create_from_image(ctx) -> dict:
    """Wholesale replace the agenda from an attached image."""
    if not ctx.deps.image_data:
        raise ModelRetry(
            "create_from_image: no image was attached in this turn. "
            "Ask the user to attach the agenda image and resend."
        )
    content_type = ctx.deps.image_content_type or "image/jpeg"
    try:
        meeting = await asyncio.to_thread(parse_meeting_agenda_image, ctx.deps.image_data, content_type)
    except ValueError as e:
        raise ModelRetry(f"create_from_image failed: {e}") from e

    new_agenda = meeting_to_agenda(meeting)
    ctx.deps.agenda.meta = new_agenda.meta
    ctx.deps.agenda.segments = new_agenda.segments
    ctx.deps.image_data = None
    ctx.deps.image_content_type = None
    return {
        "created": True,
        "segment_count": len(new_agenda.segments),
        "meeting_summary": _meeting_summary(ctx.deps.agenda),
        "segments": _segments_summary(ctx.deps.agenda),
        "missing_required_fields": _missing_required_fields(ctx.deps.agenda),
        "validation_issues": _validation_issues(ctx.deps.agenda),
    }


_REVERT_TOOL_NAMES = {"revert_last_turn", "revert_to_turn"}
_EDIT_TOOL_NAMES = {
    "set_role",
    "set_type",
    "set_duration",
    "set_buffer",
    "set_meta",
    "add_segment",
    "remove_segment",
    "move_segment",
    "swap_roles",
    "swap_time",
    "shift_segment_time",
    "create_from_text",
    "create_from_image",
    "clone_from_meeting",
}


def _classify_turn(tool_names: set[str]) -> str:
    """revert / edit / chit-chat. validate_agenda alone counts as chit-chat
    (no state mutation)."""
    if tool_names & _REVERT_TOOL_NAMES:
        return "revert"
    if tool_names & _EDIT_TOOL_NAMES:
        return "edit"
    return "chit-chat"


async def _walk_back_to_meaningful_turn(store, session_id: str, from_seq: int):
    """Walk backward from `from_seq`, skipping chit-chat turns. Return
    (seq, turn, kind, tool_names) for the first edit-or-revert turn found,
    or None if the session has no meaningful turns."""
    for seq in range(from_seq, 0, -1):
        t = await store.load_turn(session_id, seq)
        if t is None:
            continue
        names = {nm for nm in (x.get("name", "") for x in (t.tool_trace or [])) if nm}
        kind = _classify_turn(names)
        if kind != "chit-chat":
            return (seq, t, kind, names)
    return None


async def _load_recent_edit_turns_for_refusal(store, session_id: str, before_seq: int, limit: int = 5) -> list[dict]:
    """Collect up to `limit` edit turns (skipping revert and chit-chat) to
    surface in the consecutive-revert refusal."""
    out: list[dict] = []
    seq = before_seq - 1
    while seq >= 1 and len(out) < limit:
        t = await store.load_turn(session_id, seq)
        if t is not None:
            names = {nm for nm in (x.get("name", "") for x in (t.tool_trace or [])) if nm}
            if _classify_turn(names) == "edit":
                out.append({"seq": seq, "user_message": t.user_message, "tool_names": sorted(names)})
        seq -= 1
    return out


async def apply_revert_last_turn(ctx) -> dict:
    """Soft revert: undo the most recent edit turn. Walks backward past
    chit-chat turns (describe/question turns with no edit tools), so 'undo'
    always targets an actual state change. Chat history preserved — this
    call is itself a new turn.

    The restored state equals `agenda_after` of the turn *before* the undone
    edit (i.e., the state the user saw right before they typed the message
    that triggered the undone edit). In restore-point terms:
    `restored_after_seq = undone_seq - 1`; 0 means the initial state
    (no turns applied).

    Refuses if:
    - No meaningful turns yet (only chit-chat, or empty session)
    - The most recent meaningful turn was itself a revert (consecutive-revert
      guard; refusal surfaces restore points so agent can ask user to pick
      an explicit target via revert_to_turn)

    Return contract: `undone_user_message` is the INSTRUCTION for the
    now-undone turn, NOT a description of the current state. The current
    state is BEFORE that instruction ran."""
    from app.meeting_agent import store as _store_module

    store = _store_module.session_store
    session_id = ctx.deps.session_id
    tail_seq, _ = await store.load(session_id)
    if tail_seq == 0:
        raise ModelRetry("no prior turns in this session; nothing to revert")

    meaningful = await _walk_back_to_meaningful_turn(store, session_id, tail_seq)
    if meaningful is None:
        raise ModelRetry("no edits made in this session yet; nothing to revert")

    target_seq, target_turn, kind, names = meaningful

    if kind == "revert":
        recent = await _load_recent_edit_turns_for_refusal(store, session_id, before_seq=target_seq)
        # Present each edit turn as a named restore point. The user picks a
        # seq; the agent passes it VERBATIM to revert_to_turn(after_seq=N).
        # Include seq 0 (initial state) as an explicit option.
        lines = ["  - seq 0: initial state (no edits yet; blank agenda)"]
        for r in recent:
            lines.append(
                f"  - seq {r['seq']}: state AFTER {r['user_message']!r} was applied "
                f"(tools: {', '.join(r['tool_names'])})"
            )
        restore_points = "\n".join(lines)
        raise ModelRetry(
            "Consecutive revert blocked: the most recent meaningful turn was "
            "already a revert; calling revert_last_turn again would redo it "
            "(ping-pong). Ask the user which restore point they want, then "
            "call revert_to_turn(after_seq=N) with the seq number they "
            "picked — pass it VERBATIM, do NOT subtract or transform. The web "
            "UI also offers a direct ↺ icon on any earlier chat bubble.\n\n"
            "Available restore points (each restores the agenda to that "
            "state):\n"
            f"{restore_points}"
        )

    # Normal revert: apply agenda_before of the target edit turn (same as
    # agenda_after of target_seq - 1, i.e. restore_point = target_seq - 1).
    reverted = Agenda.model_validate(target_turn.agenda_before)
    ctx.deps.agenda.meta = reverted.meta
    ctx.deps.agenda.segments = reverted.segments

    return {
        "undone_seq": target_seq,
        "undone_user_message": target_turn.user_message,
        "undone_tool_names": sorted(n for n in names if n in _EDIT_TOOL_NAMES),
        "restored_after_seq": target_seq - 1,
        "n_segments": len(reverted.segments),
    }


async def apply_revert_to_turn(ctx, after_seq: int) -> dict:
    """Restore the agenda to a specific restore point. `after_seq` semantics:

      after_seq = 0 → initial state (before any turns)
      after_seq = N (N>=1) → state AFTER turn N completed

    This is the ONLY direction semantic we expose to the model. When user
    says 'revert to seq N', pass N directly as after_seq. Do not subtract
    or transform.

    Chat history is preserved (this call is itself a new turn)."""
    if after_seq < 0:
        raise ModelRetry(f"after_seq must be >= 0; got {after_seq}")

    from app.meeting_agent import store as _store_module

    store = _store_module.session_store
    session_id = ctx.deps.session_id

    if after_seq == 0:
        # Initial state = agenda_before of turn 1. If turn 1 doesn't exist,
        # there's nothing to revert — refuse.
        first = await store.load_turn(session_id, 1)
        if first is None:
            raise ModelRetry("session has no turns; already at initial state")
        state = first.agenda_before
    else:
        target = await store.load_turn(session_id, after_seq)
        if target is None:
            raise ModelRetry(f"turn {after_seq} not found in this session; cannot revert to it")
        state = target.agenda_after

    reverted = Agenda.model_validate(state)
    ctx.deps.agenda.meta = reverted.meta
    ctx.deps.agenda.segments = reverted.segments

    return {
        "restored_after_seq": after_seq,
        "n_segments": len(reverted.segments),
    }


def _find_segment(agenda, segment_id: str):
    for seg in agenda.segments:
        if seg.id == segment_id:
            return seg
    raise ValueError(f"unknown segment_id: {segment_id}")
