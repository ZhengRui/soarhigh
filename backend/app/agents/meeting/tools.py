"""Tool implementations. Separated from Pydantic AI @agent.tool registration
so they can be unit-tested with a plain dataclass context."""

import asyncio
import re
import uuid
from typing import Any

from pydantic_ai import ModelRetry

from app.agents.meeting.models import Agenda, Segment
from app.agents.meeting.normalize import meeting_to_agenda
from app.agents.meeting.save_gate import (
    classify_save,
    now_shanghai,
)
from app.agents.meeting.segment_ids import resolve as _resolve_segment_id
from app.agents.meeting.segment_ids import shorten as _shorten_id
from app.agents.meeting.timing import recompute_start_times
from app.agents.meeting.validators import run_validators
from app.db.core import (
    create_meeting,
    get_meeting_by_id,
    get_meeting_id_by_no,
    update_meeting,
)
from app.models.meeting import Attendee, Meeting
from app.models.meeting import Segment as MeetingSegment
from app.services import meeting_lookup
from app.utils.meeting import parse_meeting_agenda_image, plan_meeting_from_text


def _resolve_role_taker(
    agenda: Agenda,
    members_directory: list[dict],
    role_name: str,
) -> Attendee | None:
    """Resolve a bare-name role_taker arg into a structured Attendee.

    Tools like `set_role` / `add_segment` keep a string signature so the LLM
    contract stays simple. Internally Phase B requires the structured form
    so the route addendum can render the (member)/(guest) badge from the
    authoritative `member_id`. Resolution order:

      1. Empty / blank → None (segment has no role taker).
      2. Full-name match against an existing role_taker in the same agenda
         (case-insensitive) → reuse that Attendee, inheriting the DB-resolved
         `member_id` from the frontend snapshot. Common case: "Joyce 也来做
         Timer 吧" when Joyce is already TOM in this agenda.
      3. Full-name match in `members_directory` (the live members list eager-
         fetched by the route at turn boundary) → Attendee carrying the real
         DB `member_id`.
      4. **Unique first-name match in `members_directory`** ("Libra" →
         "Libra Lee" when only one club member has that first name). Mirrors
         the frontend's `resolveAttendee` heuristic so the chat addendum
         badge agrees with the form's badge. Without this, a model that
         passes a first name despite the prompt's "use full name" rule
         (observed on Chinese turns like "设置成Libra吧") would render
         `(guest)` here while the form renders `(member)`. The Attendee
         stores the directory's full name, not the model's first-name input
         — so subsequent turns see the canonical name.
      5. No match anywhere → guest Attendee with empty member_id. The
         frontend's `applyAgendaSnapshot` still runs `resolveAttendee` as a
         final defense.
    """
    name = (role_name or "").strip()
    if not name:
        return None
    lower = name.lower()
    for seg in agenda.segments:
        rt = seg.role_taker
        if rt is not None and rt.name.lower() == lower:
            return rt.model_copy()
    for member in members_directory or ():
        full_name = (member.get("full_name") or "").strip()
        if full_name.lower() == lower:
            uid = member.get("id") or ""
            return Attendee(id=uid or None, name=full_name, member_id=uid)
    first_name_matches = [
        m for m in (members_directory or ()) if (m.get("full_name") or "").strip().split(" ", 1)[0].lower() == lower
    ]
    if len(first_name_matches) == 1:
        m = first_name_matches[0]
        uid = m.get("id") or ""
        full_name = (m.get("full_name") or "").strip()
        return Attendee(id=uid or None, name=full_name, member_id=uid)
    return Attendee(id=None, name=name, member_id="")


_ALLOWED_META_FIELDS = {
    "type",
    "theme",
    "location",
    "date",
    "start_time",
    "end_time",
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
    real_id = _resolve_segment_id(ctx.deps.agenda, segment_id)
    seg = _find_segment(ctx.deps.agenda, real_id)
    seg.role_taker = _resolve_role_taker(ctx.deps.agenda, ctx.deps.members_directory, role_taker)
    # Surface the CANONICAL name to the model. When `_resolve_role_taker`
    # canonicalizes a first-name slip ("Libra" → "Libra Lee"), the LLM-
    # facing tool result must reflect that — otherwise the model's reply
    # text quotes the non-canonical input ("Updated to Libra"), drifting
    # from the prompt's "use full name" rule and from what subsequent
    # turns will see in the live agenda snapshot.
    canonical = seg.role_taker.name if seg.role_taker else ""
    return {"segment_id": _shorten_id(real_id), "role_taker": canonical}


def apply_set_type(ctx, segment_id: str, type: str) -> dict:
    """Unilateral: rename ONE segment's type. Does not affect timing."""
    real_id = _resolve_segment_id(ctx.deps.agenda, segment_id)
    seg = _find_segment(ctx.deps.agenda, real_id)
    seg.type = type
    return {"segment_id": _shorten_id(real_id), "type": type}


# Mirrors the FE's `*_config.editable` flags in
# `frontend/src/utils/defaultSegments.ts`. Fixed standard types do NOT carry
# per-segment title/content — the on-screen heading IS the type label, and
# the form has no inputs for those fields. Editing them via the agent would
# write data the user can't see or modify.
_FIXED_STANDARD_TYPES = frozenset(
    {
        "Members and Guests Registration, Warm up",
        "Meeting Rules Introduction (SAA)",
        "Opening Remarks (President)",
        "TOM (Toastmaster of Meeting) Introduction",
        "Timer",
        "Hark Master",
        "Grammarian",
        "Guests Self Introduction (30s per guest)",
        "TTM (Table Topic Master) Opening",
        "Table Topic Session",
        "Tea Break & Group Photos",
        "Table Topic Evaluation",
        "Timer's Report",
        "Grammarian's Report",
        "Hark Master Pop Quiz Time",
        "General Evaluation",
        "Voting Section (TOM)",
        "Voting Section",
        "Awards (President)",
        "Awards",
        "Moment of Truth",
        "Closing Remarks (President)",
    }
)


def _is_prepared_speech(t: str) -> bool:
    return t.startswith("Prepared Speech") and "Evaluation" not in t


def _is_prepared_speech_eval(t: str) -> bool:
    return t.startswith("Prepared Speech") and "Evaluation" in t


def _can_edit_title(t: str) -> bool:
    """Title editable on Prepared Speech (any number) and any non-fixed
    custom-style type (Workshop / Ice Breaker / etc.). Locked on every fixed
    standard type and on Prepared Speech Evaluation rows."""
    if _is_prepared_speech_eval(t):
        return False
    return _is_prepared_speech(t) or t not in _FIXED_STANDARD_TYPES


def _can_edit_content(t: str) -> bool:
    """Content editable on Prepared Speech (pathway notes), Table Topic
    Session (WOT), and any non-fixed custom-style type. Locked on every
    other fixed standard type and on Prepared Speech Evaluation rows."""
    if _is_prepared_speech_eval(t):
        return False
    if t == "Table Topic Session":
        return True
    if _is_prepared_speech(t):
        return True
    return t not in _FIXED_STANDARD_TYPES


def apply_set_title(ctx, segment_id: str, title: str) -> dict:
    """Unilateral: set the title (e.g. speech title) of ONE segment.

    Distinct from `set_type` which renames the segment's category label.
    Title is editable for Prepared Speech and Custom-style segments;
    refused for fixed standard types and Prepared Speech Evaluation."""
    real_id = _resolve_segment_id(ctx.deps.agenda, segment_id)
    seg = _find_segment(ctx.deps.agenda, real_id)
    if not _can_edit_title(seg.type):
        raise ModelRetry(
            f"Title is not editable for a '{seg.type}' segment. Title applies "
            f"to Prepared Speech and Custom-style segments only. To rename the "
            f"segment's category label use set_type; this tool is for the "
            f"per-segment title (e.g. a speech title)."
        )
    seg.title = title
    return {"segment_id": _shorten_id(real_id), "title": title}


def apply_set_content(ctx, segment_id: str, content: str) -> dict:
    """Unilateral: set the content / notes / WOT of ONE segment.

    Per-type meaning: Table Topic Session → WOT (Word of Today);
    Prepared Speech → pathway notes; Custom-style segments → freeform notes.
    Refused for fixed standard types and Prepared Speech Evaluation rows."""
    real_id = _resolve_segment_id(ctx.deps.agenda, segment_id)
    seg = _find_segment(ctx.deps.agenda, real_id)
    if not _can_edit_content(seg.type):
        raise ModelRetry(
            f"Content is not editable for a '{seg.type}' segment. Content "
            f"applies to Table Topic Session (WOT), Prepared Speech (pathway), "
            f"and Custom-style segments only."
        )
    seg.content = content
    return {"segment_id": _shorten_id(real_id), "content": content}


def apply_set_duration(ctx, segment_id: str, duration_min: int) -> dict:
    """Unilateral: set ONE segment's duration, then cascade downstream times."""
    if duration_min <= 0:
        raise ModelRetry(f"duration must be positive; got {duration_min}")
    real_id = _resolve_segment_id(ctx.deps.agenda, segment_id)
    seg = _find_segment(ctx.deps.agenda, real_id)
    seg.duration = duration_min
    recompute_start_times(ctx.deps.agenda)
    return {"segment_id": _shorten_id(real_id), "duration_min": duration_min}


def apply_set_buffer(ctx, segment_id: str, buffer_min: int) -> dict:
    """Unilateral: set the buffer_before for ONE segment, then cascade."""
    if buffer_min < 0:
        raise ModelRetry(f"buffer_min must be >= 0; got {buffer_min}")
    real_id = _resolve_segment_id(ctx.deps.agenda, segment_id)
    seg = _find_segment(ctx.deps.agenda, real_id)
    seg.buffer_before = buffer_min
    recompute_start_times(ctx.deps.agenda)
    return {"segment_id": _shorten_id(real_id), "buffer_min": buffer_min}


def apply_set_meta(ctx, field: str, value: str) -> dict:
    """Set one meeting-level meta field. Cascades times if start_time changes."""
    if field not in _ALLOWED_META_FIELDS:
        raise ModelRetry(
            f"Unknown meta field: {field}. Allowed: type, theme, location, date, "
            f"start_time, end_time, no, manager, introduction"
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

    agenda = ctx.deps.agenda
    # Exactly one of after_id / before_id is non-None per the check above.
    raw_anchor: str = after_id if after_id is not None else before_id  # type: ignore[assignment]
    real_anchor = _resolve_segment_id(agenda, raw_anchor)

    anchor_idx = next(
        (i for i, seg in enumerate(agenda.segments) if seg.id == real_anchor),
        None,
    )
    if anchor_idx is None:  # pragma: no cover — resolver already raised
        raise ModelRetry(f"unknown anchor segment: {raw_anchor}")

    # Allocate a full UUID; the LLM-facing tool result is shortened below
    # via `_shorten_id`. Pre-Phase-4 this used a 5-char hex slice which
    # was *not* a real UUID, just a short random hex — workable in
    # isolation but inconsistent with every other segment id in the
    # agenda once we switched to UUIDs everywhere.
    new_id = str(uuid.uuid4())
    new_seg = Segment(
        id=new_id,
        type=type,
        start_time="00:00",
        duration=duration_min,
        role_taker=_resolve_role_taker(agenda, ctx.deps.members_directory, role_taker),
        buffer_before=0,
    )

    insertion_index = anchor_idx + 1 if after_id is not None else anchor_idx
    agenda.segments.insert(insertion_index, new_seg)
    recompute_start_times(agenda)

    # Surface canonical name (see apply_set_role for rationale).
    canonical = new_seg.role_taker.name if new_seg.role_taker else ""
    return {
        "new_segment_id": _shorten_id(new_id),
        "type": type,
        "duration_min": duration_min,
        "role_taker": canonical,
        "inserted_at_index": insertion_index,
    }


def apply_remove_segment(ctx, segment_id: str) -> dict:
    """Remove a segment by id. Downstream times recompute."""
    agenda = ctx.deps.agenda
    real_id = _resolve_segment_id(agenda, segment_id)
    target_idx = next(
        (i for i, seg in enumerate(agenda.segments) if seg.id == real_id),
        None,
    )
    if target_idx is None:  # pragma: no cover — resolver already raised
        raise ModelRetry(f"unknown segment: {segment_id}")

    agenda.segments.pop(target_idx)
    recompute_start_times(agenda)
    return {"removed_segment_id": _shorten_id(real_id)}


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

    agenda = ctx.deps.agenda
    real_seg_id = _resolve_segment_id(agenda, segment_id)
    # Exactly one of after_id / before_id is non-None per the check above.
    raw_anchor: str = after_id if after_id is not None else before_id  # type: ignore[assignment]
    real_anchor = _resolve_segment_id(agenda, raw_anchor)
    if real_seg_id == real_anchor:
        raise ModelRetry("cannot move a segment relative to itself")

    seg_idx = next(
        (i for i, seg in enumerate(agenda.segments) if seg.id == real_seg_id),
        None,
    )
    if seg_idx is None:  # pragma: no cover
        raise ModelRetry(f"unknown segment: {segment_id}")

    anchor_idx = next(
        (i for i, seg in enumerate(agenda.segments) if seg.id == real_anchor),
        None,
    )
    if anchor_idx is None:  # pragma: no cover
        raise ModelRetry(f"unknown anchor segment: {raw_anchor}")

    moving = agenda.segments.pop(seg_idx)

    # Re-find the anchor index since popping may have shifted it. Anchor is
    # guaranteed to still exist here: we established segment_id != anchor_id
    # above, so the pop removed a different segment.
    new_anchor_idx = next(i for i, seg in enumerate(agenda.segments) if seg.id == real_anchor)

    new_idx = new_anchor_idx + 1 if after_id is not None else new_anchor_idx
    agenda.segments.insert(new_idx, moving)
    recompute_start_times(agenda)

    return {"segment_id": _shorten_id(real_seg_id), "new_index": new_idx}


def apply_swap_roles(ctx, segment_id_a: str, segment_id_b: str) -> dict:
    """Bilateral: atomically exchange the role_taker between TWO segments.
    Positions, durations, buffers, and start_times are unchanged."""
    agenda = ctx.deps.agenda
    real_a = _resolve_segment_id(agenda, segment_id_a)
    real_b = _resolve_segment_id(agenda, segment_id_b)
    if real_a == real_b:
        raise ModelRetry("cannot swap a segment with itself")

    seg_a = next(seg for seg in agenda.segments if seg.id == real_a)
    seg_b = next(seg for seg in agenda.segments if seg.id == real_b)

    seg_a.role_taker, seg_b.role_taker = seg_b.role_taker, seg_a.role_taker

    # Tool result emits bare-name strings — keeping the model-facing contract
    # uniform across set_role / swap_roles / preview / show_current_agenda.
    # The structured Attendee survives in `agenda.segments[*].role_taker`
    # for render-time membership lookup.
    return {
        "segment_id_a": _shorten_id(real_a),
        "segment_id_b": _shorten_id(real_b),
        "role_taker_a": seg_a.role_taker.name if seg_a.role_taker else "",
        "role_taker_b": seg_b.role_taker.name if seg_b.role_taker else "",
    }


def apply_swap_time(ctx, segment_id_a: str, segment_id_b: str) -> dict:
    """Bilateral: exchange the sequence positions of TWO segments. Also swaps
    buffer_before values because a buffer is a gap at a POSITION — it belongs
    to the slot, not the segment. Downstream times recompute."""
    agenda = ctx.deps.agenda
    real_a = _resolve_segment_id(agenda, segment_id_a)
    real_b = _resolve_segment_id(agenda, segment_id_b)
    if real_a == real_b:
        raise ModelRetry("cannot swap a segment with itself")

    idx_a = next(i for i, seg in enumerate(agenda.segments) if seg.id == real_a)
    idx_b = next(i for i, seg in enumerate(agenda.segments) if seg.id == real_b)

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
        "segment_id_a": _shorten_id(real_a),
        "segment_id_b": _shorten_id(real_b),
        "new_index_a": idx_b,
        "new_index_b": idx_a,
    }


def apply_shift_segment_time(ctx, segment_id: str, delta_min: int) -> dict:
    """Shift ONE segment earlier/later by signed minutes via buffer_before.
    Positive delta increases the gap (pushes later). Negative delta consumes
    the existing gap (pulls earlier) — refuses if gap is insufficient or
    segment is first."""
    agenda = ctx.deps.agenda
    real_id = _resolve_segment_id(agenda, segment_id)
    short = _shorten_id(real_id)
    seg_idx = next(
        (i for i, seg in enumerate(agenda.segments) if seg.id == real_id),
        None,
    )
    if seg_idx is None:  # pragma: no cover
        raise ModelRetry(f"unknown segment: {segment_id}")

    if delta_min == 0:
        return {"segment_id": short, "delta_min": 0}

    seg = agenda.segments[seg_idx]

    if delta_min < 0:
        if seg_idx == 0:
            raise ModelRetry(
                "cannot shift the first segment earlier; move meeting start_time earlier via set_meta instead"
            )
        available = seg.buffer_before or 0
        if abs(delta_min) > available:
            raise ModelRetry(
                f"only {available} min gap available before segment {short}; " f"cannot pull back {abs(delta_min)} min"
            )

    seg.buffer_before = (seg.buffer_before or 0) + delta_min
    recompute_start_times(agenda)

    direction = "later" if delta_min > 0 else "earlier"
    return {
        "segment_id": short,
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


def _segments_summary(agenda: Agenda) -> list[dict]:
    """Compact list of every segment, in order — for the model's reply table.

    The router prompt's snapshot reflects pre-tool state (built once at turn
    start). Without surfacing segments in the tool result, after wholesale
    creation the model has no way to count segments accurately and might
    fabricate from raw_text.

    Intentionally omits any (member)/(guest) annotation. Membership is a pure
    render-layer concern — the route addendum (`_render_segment_table`) and
    the frontend form compute it deterministically from `member_id`. Keeping
    it out of the tool result means the model never sees the annotated form
    and therefore can never copy it back into a tool argument.

    `role_taker` stays a bare-name string for LLM contract uniformity. The
    structured Attendee's `member_id` rides as a `role_taker_member_id`
    sidecar — same shape Phase A introduced for preview projections."""
    out: list[dict] = []
    real_ids = [seg.id for seg in agenda.segments]
    # Disambiguate prefixes against the full agenda so the model-facing
    # `id` is unique even in the rare case two real UUIDs share `[:5]`.
    from app.agents.meeting.segment_ids import shorten_unique

    short_map = shorten_unique(real_ids)
    for seg in agenda.segments:
        rt = seg.role_taker
        out.append(
            {
                "id": short_map.get(seg.id, _shorten_id(seg.id)),
                "start_time": seg.start_time,
                "type": seg.type,
                "duration": seg.duration,
                "role_taker": rt.name if rt else "",
                "role_taker_member_id": rt.member_id if rt else "",
                "buffer_before": seg.buffer_before,
            }
        )
    return out


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
    # 19:15 "Members and Guests Registration, Warm up" as the first segment
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
    # Type strings must match the canonical labels emitted by the frontend's
    # `DEFAULT_SEGMENTS_REGULAR_MEETING` (frontend/src/utils/defaultSegments.ts);
    # otherwise `instantiateSegmentByType` falls back to CustomSegment and the
    # form renders these rows as generic custom cards instead of the proper
    # specialized segments.
    ("Members and Guests Registration, Warm up", "19:15", 15, "All"),
    ("Meeting Rules Introduction (SAA)", "19:30", 2, ""),
    ("Opening Remarks (President)", "19:32", 2, ""),
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
    ("Hark Master Pop Quiz Time", "20:49", 5, ""),
    ("General Evaluation", "20:54", 8, ""),
    ("Voting Section (TOM)", "21:02", 2, ""),
    ("Moment of Truth", "21:04", 7, ""),
    ("Awards (President)", "21:11", 3, ""),
    ("Closing Remarks (President)", "21:14", 1, "Amy Fang"),
)


def _build_template_regular_2ps(members_directory: list[dict]) -> Agenda:
    """Hardcoded Regular meeting with 2 prepared speeches.

    Segments are back-to-back from 19:15 (warmup) to 21:15 (closing).
    meta.start_time is 19:15 — same as the first segment — so a later
    structural edit (set_duration / set_buffer / add_segment / etc.)
    that triggers `recompute_start_times` re-anchors at 19:15 and
    preserves the warmup position. Treating "official meeting starts
    at 19:30" as a separate concept from meta.start_time was a footgun:
    the recompute helper only knows one anchor.
    meta.end_time is intentionally None so the validator skips overflow /
    underflow checks until the user fills it in (the agenda's actual end
    is 21:15, but typical SoarHigh slots end at 21:30 — let the user
    decide rather than picking one for them).

    `members_directory` is the live members list eager-fetched at turn
    boundary by the route. Static defaults like "Amy Fang" (the current
    president) are resolved through `_resolve_role_taker` so they carry a
    real DB `member_id` — without this, the chat addendum would render
    those default-presider rows as `(guest)` until the frontend re-resolved
    on the next snapshot."""
    from app.agents.meeting.models import Meta as _Meta

    meta = _Meta(
        type="Regular",
        start_time="19:15",
    )
    empty_agenda = Agenda(meta=_Meta(), segments=[])
    segments = [
        Segment(
            # Real UUID per segment — see normalize.py for why we no longer
            # use positional `s{i+1}` ids.
            id=str(uuid.uuid4()),
            type=seg_type,
            start_time=start,
            duration=duration,
            role_taker=_resolve_role_taker(empty_agenda, members_directory, role),
            buffer_before=0,
        )
        for _i, (seg_type, start, duration, role) in enumerate(_REGULAR_2PS_SEGMENTS)
    ]
    return Agenda(meta=meta, segments=segments)


def _build_template_custom(members_directory: list[dict]) -> Agenda:
    """Minimal single-segment Custom meeting starter.

    Custom meetings have no fixed structural convention — no required
    canonical segment list. The template gives the user a blank slate with
    ONE placeholder segment so the form has something to render; they build
    it up segment-by-segment via subsequent chat edits (set_type, add_segment,
    set_role, etc.). The placeholder is positioned at 19:15 with a 15-min
    duration so it aligns with the standard pre-meeting warmup window — the
    user can rename / resize / re-anchor as needed. meta.start_time matches
    the first segment (19:15) so `recompute_start_times` preserves the
    placeholder's clock position after subsequent structural edits.

    `members_directory` is unused by this template (the only segment has no
    role taker) but is accepted so both template builders share one signature
    in `_TEMPLATE_BUILDERS`."""
    del members_directory
    from app.agents.meeting.models import Meta as _Meta

    meta = _Meta(
        type="Custom",
        start_time="19:15",
    )
    segments = [
        Segment(
            id=str(uuid.uuid4()),
            type="Segment 1",
            start_time="19:15",
            duration=15,
            role_taker=None,
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
    new_agenda = builder(ctx.deps.members_directory)
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


# Re-export the shared agent-tool wrappers so existing meeting-agent
# imports (`from app.agents.meeting.tools import apply_lookup_meeting`)
# keep working without churning callers. The actual logic lives in
# `app.services.meeting_lookup` so the statistics agent (and any future
# specialist) shares one validation path, one envelope shape, one
# pool-cache definition. See feedback_mirror_existing_patterns.md.
apply_lookup_meeting = meeting_lookup.apply_lookup_meeting
apply_preview_meeting = meeting_lookup.apply_preview_meeting


_CLONE_LOOKUP_LOOKBACK_TURNS = 3


def _tool_result_cards(result: Any) -> list[dict]:
    """Extract the lookup_meeting cards from a stored tool_trace result.
    Accepts both the current envelope shape ({cards, total_matches, ...})
    and the legacy bare-list shape from older turns persisted before the
    envelope rollout — the clone gate looks back 3 turns and may see
    either across a session that spans the change."""
    if isinstance(result, dict):
        cards = result.get("cards")
        if isinstance(cards, list):
            return [c for c in cards if isinstance(c, dict)]
        return []
    if isinstance(result, list):
        return [c for c in result if isinstance(c, dict)]
    return []


async def _recent_lookup_includes_no(session_id: str, no: int, user_id: str | None) -> bool:
    from app.agents.runtime.store import agent_turn_store

    tail_seq, _ = await agent_turn_store.load(session_id, user_id=user_id)
    if tail_seq <= 0:
        return False
    for seq in range(tail_seq, max(0, tail_seq - _CLONE_LOOKUP_LOOKBACK_TURNS), -1):
        turn = await agent_turn_store.load_turn(session_id, seq, user_id=user_id)
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
    if not await _recent_lookup_includes_no(ctx.deps.session_id, no, ctx.deps.user_id):
        raise ModelRetry(
            f"clone_from_meeting refused: no recent lookup_meeting surfaced #{no}. "
            "Call lookup_meeting first, present the result, then wait for explicit confirmation."
        )
    if not _is_explicit_clone_confirmation(ctx.deps.current_user_message):
        raise ModelRetry(
            "clone_from_meeting refused: the current user message is not an explicit confirmation. "
            "Ask the user to confirm the looked-up meeting before cloning."
        )

    meeting_dict = await asyncio.to_thread(meeting_lookup.fetch_meeting_full, no)
    if meeting_dict is None:
        raise ModelRetry(f"Meeting #{no} not found in recent history.")

    cloned = meeting_to_agenda(Meeting(**meeting_dict))
    cloned.meta.no = None
    cloned.meta.theme = None
    cloned.meta.manager = None
    cloned.meta.date = None
    cloned.meta.introduction = None
    for seg in cloned.segments:
        seg.role_taker = None
        # Per-meeting user content does not transfer on clone — only the
        # structural skeleton (type / start_time / duration / buffer_before)
        # does. Speech titles, workshop notes, WOT, and eval-to-speech links
        # belong to the source meeting; carrying them over surfaces stale
        # data the user has to manually wipe before the new draft is usable.
        seg.title = ""
        seg.content = ""
        seg.related_segment_ids = ""

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


def _agenda_to_meeting_payload(agenda) -> dict:
    """Convert an Agenda (Meta + segments with structured Attendee role_takers)
    into the dict shape `create_meeting` / `update_meeting` expect (mirrors
    Meeting.dict(exclude={'id'}) from the REST routes). Manager string is
    coerced into an Attendee. Status defaults to draft."""
    meta = agenda.meta
    manager_name = (meta.manager or "").strip()
    manager = Attendee(id=None, name=manager_name, member_id="")
    segments_payload: list[dict] = []
    for seg in agenda.segments:
        rt = seg.role_taker
        role_attendee = (
            Attendee(id=None, name=rt.name, member_id=rt.member_id or "")
            if rt and (rt.name or "").strip()
            else Attendee(id=None, name="", member_id="")
        )
        segments_payload.append(
            MeetingSegment(
                id=seg.id,
                type=seg.type or "",
                start_time=seg.start_time or "",
                end_time="",  # backend recalculates from start + duration
                duration=str(seg.duration) if seg.duration is not None else "",
                role_taker=role_attendee,
                title=seg.title or "",
                content=seg.content or "",
                related_segment_ids=seg.related_segment_ids or "",
            ).dict()
        )
    payload = Meeting(
        id=None,
        no=meta.no,
        type=meta.type or "Regular",
        theme=meta.theme or "",
        manager=manager,
        date=meta.date or "",
        start_time=meta.start_time or "",
        end_time=meta.end_time or "",
        location=meta.location or "",
        introduction=meta.introduction or "",
        status="draft",
        segments=[],
    ).dict(exclude={"id", "segments"})
    payload["segments"] = segments_payload
    return payload


_SAVE_CONFIRM_NEGATIVES = ("不", "别", "不用", "不要", "算了", "取消", "不是", "no", "not", "wrong", "cancel")
# Generic yes-tokens that ratify a pending preview. Intentionally
# DISJOINT from `_SAVE_INTENT_TOKENS` — repeating a save verb like
# "保存" is treated as a fresh save request (re-initiate the preview),
# not as confirmation of an earlier preview. Only an explicit yes
# without a save verb counts as confirmation.
_SAVE_CONFIRM_POSITIVES = (
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


def _is_explicit_save_confirmation(text: str) -> bool:
    q = (text or "").strip().lower()
    if not q:
        return False
    if any(n in q for n in _SAVE_CONFIRM_NEGATIVES):
        return False
    return any(p in q for p in _SAVE_CONFIRM_POSITIVES)


# Strict subset of confirmation tokens — the user is unambiguously
# asking to save NOW. Used for the preview-turn gate to prevent the
# model from calling save_draft on its own initiative after unrelated
# edits. Intentionally excludes generic confirmation tokens like
# "yes" / "ok" / "好" / "确认" — those confirm a pending preview but
# do NOT initiate one.
_SAVE_INTENT_TOKENS = (
    "保存",
    "存盘",
    "存一下",
    "save",
)


def _is_explicit_save_request(text: str) -> bool:
    """True iff the user's current message explicitly asks to save.
    Distinct from `_is_explicit_save_confirmation`: that helper accepts
    a yes-token to ratify a pending preview; this one demands an
    actual save verb to *initiate* one."""
    q = (text or "").strip().lower()
    if not q:
        return False
    if any(n in q for n in _SAVE_CONFIRM_NEGATIVES):
        return False
    return any(t in q for t in _SAVE_INTENT_TOKENS)


async def _immediately_prior_turn_was_save_preview(session_id: str, user_id: str | None) -> bool:
    """True iff the immediately previous turn ran a successful
    `save_draft` with `pending_confirmation: True`. Strict check — any
    intervening turn (including read-only ones like show_current_agenda
    or any edit) invalidates the preview and forces a fresh one."""
    from app.agents.runtime.store import agent_turn_store

    tail_seq, _ = await agent_turn_store.load(session_id, user_id=user_id)
    if tail_seq <= 0:
        return False
    turn = await agent_turn_store.load_turn(session_id, tail_seq, user_id=user_id)
    if turn is None:
        return False
    for trace in turn.tool_trace or []:
        if trace.get("name") != "save_draft" or trace.get("status") != "ok":
            continue
        result = trace.get("result")
        if isinstance(result, dict) and result.get("pending_confirmation") is True:
            return True
    return False


async def apply_save_draft(ctx, *, confirmed: bool = False) -> dict:
    """Save the current agenda as a meeting draft.

    Two-turn protocol:
      1. First call (`confirmed=False`): classify create vs update vs
         refuse using the time gate. Return a preview without writing.
      2. Second call (`confirmed=True` AND explicit user confirmation
         in `current_user_message`): re-validate the gate, then persist
         via `create_meeting` or `update_meeting`.

    The tool re-checks the time gate on every call so the LLM cannot
    skip it by passing `confirmed=True` directly. Refusals raise
    ModelRetry — terminal for the turn (no retries).
    """
    agenda = ctx.deps.agenda

    # Preview-turn intent gate. Block the model from calling save_draft
    # on its own after unrelated edits (e.g. user says "Timer 是 Vicky"
    # and the model preemptively chains a save). The check is per-turn,
    # so a compound message like "Timer 是 Vicky, 然后保存" still
    # passes — "保存" satisfies the gate.
    if not confirmed and not _is_explicit_save_request(ctx.deps.current_user_message):
        raise ModelRetry(
            "save_draft refused: this turn's user message does not request a save. "
            "Don't call save_draft preemptively after edits — only call it when the "
            "user explicitly asks (e.g. '保存', 'save', 'save the draft'). "
            "Reply with the edit summary and stop."
        )

    no = agenda.meta.no

    db_meeting: dict | None = None
    meeting_id: str | None = None
    if no is not None:
        meeting_id = await asyncio.to_thread(get_meeting_id_by_no, no, ctx.deps.user_id)
        if meeting_id:
            db_meeting = await asyncio.to_thread(get_meeting_by_id, meeting_id, ctx.deps.user_id)

    classification = classify_save(agenda, db_meeting, now_shanghai())

    if classification.mode == "refuse":
        if classification.reason == "missing_no":
            raise ModelRetry(
                "save_draft refused: the agenda has no meeting number. "
                "Ask the user for the meeting #N before saving."
            )
        if classification.reason == "missing_schedule":
            raise ModelRetry(
                "save_draft refused: the agenda is missing date or start_time. "
                "Ask the user to fill them in before saving."
            )
        if classification.reason == "create_past":
            raise ModelRetry(
                "save_draft refused: cannot create a past meeting through chat. "
                "The agenda's start_time is already in the past."
            )
        if classification.reason == "edit_past":
            # Single refuse path covers both possible user intents,
            # since the tool can't tell which they meant:
            # (a) intended update on an existing meeting that already
            #     ended → directs them to the dashboard;
            # (b) intended create with a `no` that collides with a past
            #     meeting → directs them to pick a different number.
            past_date = (db_meeting or {}).get("date") if db_meeting else None
            date_clause = f"was held on {past_date}" if past_date else "already happened"
            raise ModelRetry(
                f"save_draft refused: meeting #{agenda.meta.no} {date_clause} — "
                "past meetings can't be modified from chat. "
                "If you wanted to create a new meeting, pick a different number; "
                "if you need to update this one, go to the dashboard."
            )

    preview = _meeting_summary(agenda)

    if not confirmed:
        return {
            "mode": classification.mode,
            "pending_confirmation": True,
            "meeting_id": classification.meeting_id,
            "preview": preview,
        }

    if not _is_explicit_save_confirmation(ctx.deps.current_user_message):
        raise ModelRetry(
            "save_draft refused: confirmed=True but the current user message is not "
            "an explicit confirmation. Show the preview and wait for the user's yes."
        )

    if not await _immediately_prior_turn_was_save_preview(ctx.deps.session_id, ctx.deps.user_id):
        raise ModelRetry(
            "save_draft refused: no fresh preview in the immediately prior turn. "
            "Any turn between preview and confirm — including edits or read-only "
            "tool calls — invalidates the preview. Call save_draft(confirmed=false) "
            "first to show a new preview, then wait for the user's yes."
        )

    payload = _agenda_to_meeting_payload(agenda)

    if classification.mode == "create":
        saved = await asyncio.to_thread(create_meeting, payload)
        return {
            "mode": "create",
            "pending_confirmation": False,
            "meeting_id": saved.get("id"),
            "no": saved.get("no"),
            "preview": preview,
        }

    # mode == "update"
    if not ctx.deps.user_id:
        raise ModelRetry("save_draft refused: missing user_id; cannot perform update.")
    # classification.meeting_id is non-None when mode == "update" (set by classify_save).
    assert classification.meeting_id is not None
    updated = await asyncio.to_thread(update_meeting, classification.meeting_id, payload, ctx.deps.user_id)
    return {
        "mode": "update",
        "pending_confirmation": False,
        "meeting_id": classification.meeting_id,
        "no": updated.get("no") if updated else agenda.meta.no,
        "preview": preview,
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


async def _walk_back_to_meaningful_turn(store, session_id: str, from_seq: int, user_id: str | None):
    """Walk backward from `from_seq`, skipping chit-chat turns. Return
    (seq, turn, kind, tool_names) for the first edit-or-revert turn found,
    or None if the session has no meaningful turns."""
    for seq in range(from_seq, 0, -1):
        t = await store.load_turn(session_id, seq, user_id=user_id)
        if t is None:
            continue
        names = {nm for nm in (x.get("name", "") for x in (t.tool_trace or [])) if nm}
        kind = _classify_turn(names)
        if kind != "chit-chat":
            return (seq, t, kind, names)
    return None


async def _load_recent_edit_turns_for_refusal(
    store, session_id: str, before_seq: int, user_id: str | None, limit: int = 5
) -> list[dict]:
    """Collect up to `limit` edit turns (skipping revert and chit-chat) to
    surface in the consecutive-revert refusal."""
    out: list[dict] = []
    seq = before_seq - 1
    while seq >= 1 and len(out) < limit:
        t = await store.load_turn(session_id, seq, user_id=user_id)
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
    from app.agents.runtime.store import agent_turn_store

    store = agent_turn_store
    session_id = ctx.deps.session_id
    user_id = ctx.deps.user_id
    tail_seq, _ = await store.load(session_id, user_id=user_id)
    if tail_seq == 0:
        raise ModelRetry("no prior turns in this session; nothing to revert")

    meaningful = await _walk_back_to_meaningful_turn(store, session_id, tail_seq, user_id)
    if meaningful is None:
        raise ModelRetry("no edits made in this session yet; nothing to revert")

    target_seq, target_turn, kind, names = meaningful

    if kind == "revert":
        recent = await _load_recent_edit_turns_for_refusal(store, session_id, before_seq=target_seq, user_id=user_id)
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

    from app.agents.runtime.store import agent_turn_store

    store = agent_turn_store
    session_id = ctx.deps.session_id
    user_id = ctx.deps.user_id

    if after_seq == 0:
        # Initial state = agenda_before of turn 1. If turn 1 doesn't exist,
        # there's nothing to revert — refuse.
        first = await store.load_turn(session_id, 1, user_id=user_id)
        if first is None:
            raise ModelRetry("session has no turns; already at initial state")
        state = first.agenda_before
    else:
        target = await store.load_turn(session_id, after_seq, user_id=user_id)
        if target is None:
            raise ModelRetry(f"turn {after_seq} not found in this session; cannot revert to it")
        state = target.agenda_after

    if state is None:
        # Stats and router-only turns have no agenda snapshots; you can't
        # revert TO a non-meeting turn. The model should pick an edit turn.
        raise ModelRetry(f"turn {after_seq} is not a meeting edit; cannot revert to it. Pick an edit turn instead.")

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
