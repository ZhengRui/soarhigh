from typing import Any

from app.agents.meeting.normalize import meeting_to_agenda
from app.models.meeting import Attendee, Meeting
from app.models.meeting import Segment as MeetingSegment


def _segment(**overrides: Any) -> MeetingSegment:
    base: dict[str, Any] = {
        "id": "legacy",
        "type": "SAA",
        "start_time": "19:30",
        "end_time": "19:33",
        "duration": "3",
        "role_taker": Attendee(id=None, name="", member_id=""),
        "title": "",
        "content": "",
        "related_segment_ids": "",
    }
    base.update(overrides)
    return MeetingSegment(**base)


def _meeting(**overrides: Any) -> Meeting:
    base: dict[str, Any] = {
        "id": None,
        "no": 387,
        "type": "Regular",
        "theme": "Test",
        "manager": Attendee(id=None, name="Rui Zheng", member_id=""),
        "date": "2024-11-05",
        "start_time": "19:15",
        "end_time": "21:30",
        "location": "Loc",
        "introduction": "intro",
        "status": "draft",
        "awards": [],
        "segments": [],
    }
    base.update(overrides)
    return Meeting(**base)


def test_basic_meta_fields_carry_over():
    agenda = meeting_to_agenda(_meeting())
    assert agenda.meta.no == 387
    assert agenda.meta.type == "Regular"
    assert agenda.meta.theme == "Test"
    assert agenda.meta.manager == "Rui Zheng"
    assert agenda.meta.date == "2024-11-05"
    assert agenda.meta.start_time == "19:15"
    assert agenda.meta.end_time == "21:30"
    assert agenda.meta.location == "Loc"
    assert agenda.meta.introduction == "intro"


def test_segment_preserves_phase3_detail_fields():
    """Phase 3: title / content / related_segment_ids round-trip through
    `meeting_to_agenda` so a clone / preview / create-from-* path doesn't
    silently drop a prepared speech's title or workshop content. Pre-Phase-3
    these were dropped on the way into the agent's lean `Segment` model;
    that meant any agent edit (e.g. set_role) would erase them when the
    agenda_after came back to the frontend.

    `end_time` remains intentionally absent — the agent derives it from
    `start_time + duration` and doesn't need to store it."""
    agenda = meeting_to_agenda(
        _meeting(
            segments=[
                _segment(
                    id="1",
                    role_taker=Attendee(id=None, name="Joyce Feng", member_id="m1"),
                    title="legacy_title",
                    content="legacy_content",
                    related_segment_ids="2,3",
                )
            ]
        )
    )
    seg = agenda.segments[0]
    assert seg.type == "SAA"
    assert seg.duration == 3
    assert seg.role_taker is not None
    assert seg.role_taker.name == "Joyce Feng"
    assert seg.role_taker.member_id == "m1"
    # Detail fields preserved (Phase 3).
    assert seg.title == "legacy_title"
    assert seg.content == "legacy_content"
    assert seg.related_segment_ids == "2,3"
    assert not hasattr(seg, "end_time")


def test_segment_detail_fields_default_to_empty_when_source_missing():
    """When the source segment doesn't carry a title/content, the agent's
    Segment defaults to empty string — keeps the field present so downstream
    consumers can rely on the shape without None-checks, and matches the
    frontend `BaseSegment` default."""
    agenda = meeting_to_agenda(_meeting(segments=[_segment(id="1", title="", content="", related_segment_ids="")]))
    seg = agenda.segments[0]
    assert seg.title == ""
    assert seg.content == ""
    assert seg.related_segment_ids == ""


def test_buffer_before_derived_from_start_time_gap():
    agenda = meeting_to_agenda(
        _meeting(
            start_time="19:15",
            segments=[
                _segment(id="1", type="A", start_time="19:30", duration="3", end_time="19:33"),
                _segment(id="2", type="B", start_time="19:34", duration="2", end_time="19:36"),
            ],
        )
    )
    assert agenda.segments[0].buffer_before == 15
    assert agenda.segments[1].buffer_before == 1


def test_first_segment_buffer_from_meta_start_time_gap():
    agenda = meeting_to_agenda(
        _meeting(
            start_time="19:15",
            segments=[_segment(id="1", type="A", start_time="19:20", duration="3", end_time="19:23")],
        )
    )
    assert agenda.segments[0].buffer_before == 5


def test_role_taker_preserves_structured_attendee():
    """Phase B: meeting_to_agenda preserves the DB-authoritative member_id
    on the structured Attendee so the route addendum can decide member/guest
    without falling back to the static CLUB_MEMBERS list."""
    agenda = meeting_to_agenda(
        _meeting(segments=[_segment(role_taker=Attendee(id="att-1", name="Frank Zeng", member_id="m1"))])
    )
    rt = agenda.segments[0].role_taker
    assert rt is not None
    assert rt.name == "Frank Zeng"
    assert rt.member_id == "m1"


def test_role_taker_none_when_attendee_missing():
    agenda = meeting_to_agenda(_meeting(segments=[_segment(role_taker=None)]))
    assert agenda.segments[0].role_taker is None


def test_segments_get_fresh_uuid_ids():
    """Phase 4: meeting_to_agenda allocates a fresh real UUID per segment.
    Source ids are dropped — the agent's segment ids are independent of the
    DB / planner output (which often has incomplete or unstable ids), and
    the LLM-facing prompt JSON shortens these UUIDs to 5-char prefixes via
    `segment_ids.shorten_agenda_dump`. The pure-derivation prefix scheme
    closes the alias-reuse bug class the prior `s{i+1}` allocator caused
    (see segment_ids.py module docstring)."""
    import uuid

    agenda = meeting_to_agenda(
        _meeting(
            segments=[
                _segment(id="legacy_99", type="A", start_time="19:30", duration="3", end_time="19:33"),
                _segment(id="legacy_42", type="B", start_time="19:34", duration="2", end_time="19:36"),
            ],
        )
    )
    ids = [s.id for s in agenda.segments]
    assert len(ids) == 2
    assert ids[0] != ids[1]
    # Each id parses as a real UUID — not the legacy `s{i+1}` shape.
    for sid in ids:
        uuid.UUID(sid)
    assert "legacy_99" not in ids
    assert "legacy_42" not in ids
