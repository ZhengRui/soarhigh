from typing import Any

from app.meeting_agent.normalize import meeting_to_agenda
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


def test_segment_legacy_fields_dropped():
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
    assert seg.role_taker == "Joyce Feng"
    assert not hasattr(seg, "title")
    assert not hasattr(seg, "content")
    assert not hasattr(seg, "end_time")


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


def test_role_taker_extracted_from_attendee():
    agenda = meeting_to_agenda(
        _meeting(segments=[_segment(role_taker=Attendee(id=None, name="Frank Zeng", member_id="m1"))])
    )
    assert agenda.segments[0].role_taker == "Frank Zeng"


def test_role_taker_empty_when_attendee_none():
    agenda = meeting_to_agenda(_meeting(segments=[_segment(role_taker=None)]))
    assert agenda.segments[0].role_taker == ""


def test_segments_get_fresh_sequential_ids():
    agenda = meeting_to_agenda(
        _meeting(
            segments=[
                _segment(id="legacy_99", type="A", start_time="19:30", duration="3", end_time="19:33"),
                _segment(id="legacy_42", type="B", start_time="19:34", duration="2", end_time="19:36"),
            ],
        )
    )
    assert [s.id for s in agenda.segments] == ["s1", "s2"]
    assert "legacy_99" not in {s.id for s in agenda.segments}
    assert "legacy_42" not in {s.id for s in agenda.segments}
