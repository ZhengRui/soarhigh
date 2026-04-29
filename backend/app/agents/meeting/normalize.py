"""Convert legacy Meeting models into the meeting agent's lean Agenda shape."""

import uuid
from datetime import datetime, timedelta

from app.agents.meeting.models import Agenda, Meta, Segment
from app.models.meeting import Attendee, Meeting


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

    for src in meeting.segments:
        start_dt = _parse_hhmm(src.start_time)
        buffer_before = _gap_minutes(prev_end_dt, start_dt)
        try:
            duration = int(src.duration) if src.duration else 0
        except (TypeError, ValueError):
            duration = 0

        # Preserve the structured Attendee (id + member_id) so render-time
        # member/guest classification is DB-authoritative. Previously this
        # flattened to just `.name`, which forced the route addendum to guess
        # membership against the static `CLUB_MEMBERS` list — the bug Phase A
        # fixed for the preview path; Phase B closes the same gap on the
        # current-draft path.
        if src.role_taker:
            role_taker = Attendee(
                id=src.role_taker.id,
                name=src.role_taker.name,
                member_id=src.role_taker.member_id or "",
            )
        else:
            role_taker = None

        out_segments.append(
            Segment(
                # Allocate a fresh real UUID for every segment in the agent's
                # internal representation. The LLM-facing prompt JSON is
                # later shortened to the first 5 chars via
                # `segment_ids.shorten_agenda_dump`. Pre-Phase-4 this
                # allocated `s{i+1}` which made aliases position-coupled and
                # let history bias delete the wrong segment after a
                # delete-and-renumber turn (see segment_ids.py module
                # docstring for the bug class).
                id=str(uuid.uuid4()),
                type=src.type or "",
                start_time=src.start_time or "",
                duration=duration,
                role_taker=role_taker,
                buffer_before=buffer_before,
                # Phase 3: preserve segment details so a clone / preview /
                # create-from-* path doesn't silently drop a prepared speech's
                # title or workshop content.
                title=src.title or "",
                content=src.content or "",
                related_segment_ids=src.related_segment_ids or "",
            )
        )

        if start_dt is not None and duration > 0:
            prev_end_dt = start_dt + timedelta(minutes=duration)

    return Agenda(meta=meta, segments=out_segments)
