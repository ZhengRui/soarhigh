"""Time-computation helpers shared by every mutating tool.

Segments have a stable ordering in the `segments` list. After any structural
change (reorder, add, remove, set_duration, set_buffer, shift_segment_time,
set_meta start_time), we recompute every segment's start_time so the chain
stays consistent. Buffers are gaps BETWEEN adjacent segments — they live as
`buffer_before` on the following segment.
"""

from app.meeting_agent.models import Agenda


def recompute_start_times(agenda: Agenda) -> None:
    """Rewrite every segment.start_time from meta.start_time anchor +
    cumulative (prev.duration + cur.buffer_before). Mutates in place.
    """
    if not agenda.segments:
        return

    anchor = agenda.meta.start_time or "19:15"
    minutes = _parse_hhmm(anchor)

    for i, seg in enumerate(agenda.segments):
        if i > 0:
            minutes += max(seg.buffer_before or 0, 0)
        seg.start_time = _format_hhmm(minutes)
        minutes += max(seg.duration or 0, 0)


def _parse_hhmm(hhmm: str) -> int:
    """'19:15' → 1155. Accepts 'H:M' or 'HH:MM'. Invalid input returns 0."""
    try:
        parts = hhmm.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h * 60 + m
    except (ValueError, IndexError):
        return 0


def _format_hhmm(minutes: int) -> str:
    """1155 → '19:15'. Wraps past 24h using modulo for safety."""
    total = max(minutes, 0) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"
