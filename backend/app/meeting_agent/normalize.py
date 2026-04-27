"""Convert legacy Meeting models into the meeting agent's lean Agenda shape."""

from datetime import datetime, timedelta

from app.meeting_agent.models import Agenda, Meta, Segment
from app.models.meeting import Meeting


def _parse_hhmm(t: str | None) -> datetime | None:
    if not t:
        return None
    parts = t.split(":")
    if len(parts) < 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return datetime(2000, 1, 1, hour, minute)


def _gap_minutes(prev_end: datetime | None, this_start: datetime | None) -> int:
    if prev_end is None or this_start is None:
        return 0
    delta = (this_start - prev_end).total_seconds() / 60
    return max(0, int(round(delta)))


def meeting_to_agenda(meeting: Meeting) -> Agenda:
    """Drop legacy fields and derive buffer_before from clock-time gaps."""
    meta = Meta(
        no=meeting.no,
        type=meeting.type,
        theme=meeting.theme,
        manager=meeting.manager.name if meeting.manager else None,
        date=meeting.date,
        start_time=meeting.start_time,
        end_time=meeting.end_time,
        location=meeting.location,
        introduction=meeting.introduction,
    )

    out_segments: list[Segment] = []
    prev_end_dt = _parse_hhmm(meeting.start_time)

    for i, src in enumerate(meeting.segments):
        start_dt = _parse_hhmm(src.start_time)
        buffer_before = _gap_minutes(prev_end_dt, start_dt)
        try:
            duration = int(src.duration) if src.duration else 0
        except (TypeError, ValueError):
            duration = 0

        out_segments.append(
            Segment(
                id=f"s{i + 1}",
                type=src.type or "",
                start_time=src.start_time or "",
                duration=duration,
                role_taker=src.role_taker.name if src.role_taker else "",
                buffer_before=buffer_before,
            )
        )

        if start_dt is not None and duration > 0:
            prev_end_dt = start_dt + timedelta(minutes=duration)

    return Agenda(meta=meta, segments=out_segments)
