"""Tool implementations. Separated from Pydantic AI @agent.tool registration
so they can be unit-tested with a plain dataclass context."""

import uuid

from pydantic_ai import ModelRetry

from app.agent.models import Segment
from app.agent.timing import recompute_start_times

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


def apply_set_role(ctx, segment_id: str, new_role_taker: str) -> dict:
    """Unilateral: set the role taker for ONE segment."""
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.role_taker = new_role_taker
    return {"segment_id": segment_id, "new_role_taker": new_role_taker}


def apply_set_type(ctx, segment_id: str, new_type: str) -> dict:
    """Unilateral: rename ONE segment's type. Does not affect timing."""
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.type = new_type
    return {"segment_id": segment_id, "new_type": new_type}


def apply_set_duration(ctx, segment_id: str, new_duration_min: int) -> dict:
    """Unilateral: set ONE segment's duration, then cascade downstream times."""
    if new_duration_min <= 0:
        raise ModelRetry(f"duration must be positive; got {new_duration_min}")
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.duration = new_duration_min
    recompute_start_times(ctx.deps.agenda)
    return {"segment_id": segment_id, "new_duration_min": new_duration_min}


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


def _find_segment(agenda, segment_id: str):
    for seg in agenda.segments:
        if seg.id == segment_id:
            return seg
    raise ValueError(f"unknown segment_id: {segment_id}")
