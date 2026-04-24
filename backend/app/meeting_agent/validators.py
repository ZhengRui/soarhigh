"""Global invariant checkers for the agenda.

Each validator is a pure function: it inspects the Agenda and returns a list of
Issue objects. Nothing mutates the agenda.

Two severity levels:
- "hard": must be fixed before the agent replies. The router prompt tells the
  model to correct these with other tools and call validate_agenda again.
- "soft": should be surfaced to the user in the final reply, not silently
  corrected.
"""

from typing import Literal

from pydantic import BaseModel

from app.meeting_agent.models import Agenda
from app.meeting_agent.timing import _format_hhmm


class Issue(BaseModel):
    code: str
    severity: Literal["soft", "hard"]
    message: str
    segment_ids: list[str] = []


def run_validators(agenda: Agenda) -> list[Issue]:
    """Run all global invariant checks, returning a flat list of issues.

    HARD issues must be fixed before the agent replies (per router prompt).
    SOFT issues should be surfaced to the user in the final sentence.
    """
    issues: list[Issue] = []
    issues.extend(_check_tte_order(agenda))
    issues.extend(_check_buffer_segment_antipattern(agenda))
    issues.extend(_check_duration_overflow(agenda))
    issues.extend(_check_duration_underflow(agenda))
    return issues


def _check_tte_order(agenda: Agenda) -> list[Issue]:
    """Every Table Topic Evaluation segment must appear AFTER the last Table
    Topic Session segment. If no TTS exists at all, no issue is raised."""
    last_tts_idx: int | None = None
    tte_indices: list[int] = []

    for i, seg in enumerate(agenda.segments):
        type_lower = (seg.type or "").lower()
        if "table topic session" in type_lower:
            last_tts_idx = i
        if "table topic evaluation" in type_lower:
            tte_indices.append(i)

    if last_tts_idx is None:
        return []

    offending = [agenda.segments[idx].id for idx in tte_indices if idx < last_tts_idx]
    if not offending:
        return []

    return [
        Issue(
            code="TTE_ORDER",
            severity="hard",
            message=("Table Topic Evaluation must appear after the Table Topic " "Session, not before it."),
            segment_ids=offending,
        )
    ]


def _check_buffer_segment_antipattern(agenda: Agenda) -> list[Issue]:
    """No segment's type may look like a buffer. Buffers are time gaps
    expressed via buffer_before, not real segments."""
    issues: list[Issue] = []
    for seg in agenda.segments:
        type_str = seg.type or ""
        type_lower = type_str.lower()
        is_buffer = "buffer" in type_lower or "gap" in type_lower or "间隔" in type_str
        if is_buffer:
            issues.append(
                Issue(
                    code="BUFFER_SEGMENT_ANTIPATTERN",
                    severity="hard",
                    message=(
                        f"Segment '{seg.type}' looks like a buffer — buffers "
                        "are time gaps expressed via buffer_before, not "
                        "segments. Remove it and use set_buffer on the next "
                        "segment instead."
                    ),
                    segment_ids=[seg.id],
                )
            )
    return issues


def _agenda_total_minutes(agenda: Agenda) -> int:
    """Total elapsed minutes from first segment start to last segment end,
    including buffer_before on every segment AFTER the first."""
    total = 0
    for i, seg in enumerate(agenda.segments):
        if i > 0:
            total += max(seg.buffer_before or 0, 0)
        total += max(seg.duration or 0, 0)
    return total


def _try_parse_hhmm(hhmm: str | None) -> int | None:
    """Return minutes-since-midnight or None if hhmm is missing/invalid.

    Unlike _parse_hhmm (which returns 0 on failure), this distinguishes
    missing/invalid from a legitimate 00:00 anchor.
    """
    if not hhmm:
        return None
    try:
        parts = hhmm.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None
    if h < 0 or m < 0:
        return None
    return h * 60 + m


def _check_duration_overflow(agenda: Agenda) -> list[Issue]:
    """Agenda computed end must not exceed meta.end_time."""
    meta = agenda.meta
    start_min = _try_parse_hhmm(meta.start_time)
    end_min = _try_parse_hhmm(meta.end_time)
    if start_min is None or end_min is None:
        return []

    agenda_min = _agenda_total_minutes(agenda)
    computed_end = start_min + agenda_min

    if computed_end > end_min:
        overflow_min = computed_end - end_min
        return [
            Issue(
                code="DURATION_OVERFLOW",
                severity="soft",
                message=(
                    f"Agenda runs {overflow_min} min past the meeting "
                    f"end_time ({meta.end_time}). Total: "
                    f"{_format_hhmm(computed_end)}."
                ),
                segment_ids=[],
            )
        ]
    return []


def _check_duration_underflow(agenda: Agenda) -> list[Issue]:
    """Agenda total must not leave more than 10 min of slack at the end."""
    meta = agenda.meta
    start_min = _try_parse_hhmm(meta.start_time)
    end_min = _try_parse_hhmm(meta.end_time)
    if start_min is None or end_min is None:
        return []

    window_min = end_min - start_min
    agenda_min = _agenda_total_minutes(agenda)
    slack_min = window_min - agenda_min

    if slack_min > 10:
        return [
            Issue(
                code="DURATION_UNDERFLOW",
                severity="soft",
                message=(
                    f"Agenda ends {slack_min} min before the meeting "
                    f"end_time ({meta.end_time}). Current total: "
                    f"{agenda_min} min."
                ),
                segment_ids=[],
            )
        ]
    return []
