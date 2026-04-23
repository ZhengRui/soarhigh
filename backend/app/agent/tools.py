"""Tool implementations. Separated from Pydantic AI @agent.tool registration
so they can be unit-tested with a plain dataclass context."""

from pydantic_ai import ModelRetry

from app.agent.timing import recompute_start_times

_ALLOWED_META_FIELDS = {
    "theme",
    "location",
    "date",
    "start_time",
    "no",
    "manager",
    "introduction",
}


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
            f"Unknown meta field: {field}. Allowed: theme, location, date, " f"start_time, no, manager, introduction"
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
    else:
        setattr(meta, field, value if value else None)

    if field == "start_time":
        recompute_start_times(ctx.deps.agenda)

    return {"field": field, "value": value}


def _find_segment(agenda, segment_id: str):
    for seg in agenda.segments:
        if seg.id == segment_id:
            return seg
    raise ValueError(f"unknown segment_id: {segment_id}")
