"""Tool implementations. Separated from Pydantic AI @agent.tool registration
so they can be unit-tested with a plain dataclass context."""


def apply_set_role(ctx, segment_id: str, new_role_taker: str) -> dict:
    """Unilateral: set the role taker for ONE segment."""
    seg = _find_segment(ctx.deps.agenda, segment_id)
    seg.role_taker = new_role_taker
    return {"segment_id": segment_id, "new_role_taker": new_role_taker}


def _find_segment(agenda, segment_id: str):
    for seg in agenda.segments:
        if seg.id == segment_id:
            return seg
    raise ValueError(f"unknown segment_id: {segment_id}")
