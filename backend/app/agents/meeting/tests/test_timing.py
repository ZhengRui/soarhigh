from app.agents.meeting.models import Agenda, Meta, Segment
from app.agents.meeting.timing import recompute_start_times


def make(start_time: str, segs: list[tuple[str, int, int]]) -> Agenda:
    """Helper: build an Agenda from (id, duration, buffer_before) tuples."""
    return Agenda(
        meta=Meta(start_time=start_time),
        segments=[
            Segment(
                id=sid,
                type="T",
                start_time="00:00",  # will be overwritten
                duration=dur,
                buffer_before=buf,
            )
            for sid, dur, buf in segs
        ],
    )


def test_empty_agenda_noop():
    agenda = Agenda(meta=Meta(start_time="19:15"), segments=[])
    recompute_start_times(agenda)
    assert agenda.segments == []


def test_single_segment_uses_meta_start():
    agenda = make("19:15", [("a", 10, 0)])
    recompute_start_times(agenda)
    assert agenda.segments[0].start_time == "19:15"


def test_chains_durations_without_buffers():
    agenda = make("19:15", [("a", 15, 0), ("b", 5, 0), ("c", 7, 0)])
    recompute_start_times(agenda)
    assert [s.start_time for s in agenda.segments] == ["19:15", "19:30", "19:35"]


def test_buffer_before_adds_gap():
    agenda = make("19:15", [("a", 15, 0), ("b", 3, 2), ("c", 2, 0)])
    recompute_start_times(agenda)
    assert [s.start_time for s in agenda.segments] == ["19:15", "19:32", "19:35"]


def test_first_segment_ignores_buffer_before():
    agenda = make("19:15", [("a", 10, 5), ("b", 5, 0)])
    recompute_start_times(agenda)
    assert agenda.segments[0].start_time == "19:15"
    assert agenda.segments[1].start_time == "19:25"


def test_changing_meta_start_time_cascades():
    agenda = make("19:15", [("a", 15, 0), ("b", 5, 0), ("c", 7, 0)])
    recompute_start_times(agenda)
    assert [s.start_time for s in agenda.segments] == ["19:15", "19:30", "19:35"]

    agenda.meta.start_time = "20:00"
    recompute_start_times(agenda)
    assert [s.start_time for s in agenda.segments] == ["20:00", "20:15", "20:20"]


def test_24h_overflow_wraps():
    agenda = make("23:50", [("a", 20, 0), ("b", 60, 0)])
    recompute_start_times(agenda)
    # 23:50 → 00:10 (wrap) → 01:10
    assert agenda.segments[0].start_time == "23:50"
    assert agenda.segments[1].start_time == "00:10"


def test_invalid_meta_start_time_falls_back_to_zero():
    agenda = make("garbage", [("a", 10, 0), ("b", 5, 0)])
    recompute_start_times(agenda)
    assert agenda.segments[0].start_time == "00:00"
    assert agenda.segments[1].start_time == "00:10"
