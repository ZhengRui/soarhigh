from app.agents.meeting.models import Agenda, Meta, Segment
from app.agents.meeting.timing import recompute_start_times
from app.agents.meeting.validators import run_validators


def make(start="19:15", end="21:30", segs=()):
    """Build an Agenda from a list of (id, type, duration, buffer_before) tuples.

    Calls recompute_start_times so segment start_times reflect what production
    agendas always carry (every mutating tool runs the same recompute). Tests
    that need a deliberately stale layout can construct the Agenda directly."""
    agenda = Agenda(
        meta=Meta(start_time=start, end_time=end),
        segments=[
            Segment(
                id=sid,
                type=typ,
                start_time="00:00",
                duration=dur,
                buffer_before=buf,
            )
            for sid, typ, dur, buf in segs
        ],
    )
    recompute_start_times(agenda)
    return agenda


# --- empty / clean ---------------------------------------------------------


def test_empty_agenda_no_issues():
    agenda = make(start="19:15", end="19:15", segs=[])
    # empty + zero-window = no overflow, zero slack = no underflow
    issues = run_validators(agenda)
    assert issues == []


def test_clean_agenda_no_issues():
    # 135-min window, filled exactly (5 + 30 + 100 = 135)
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "Table Topic Session", 30, 0),
            ("s3", "Table Topic Evaluation", 100, 0),
        ],
    )
    issues = run_validators(agenda)
    assert issues == []


# --- TTE_ORDER -------------------------------------------------------------


def test_tte_before_tts_is_hard_issue():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "Table Topic Evaluation", 7, 0),
            ("s2", "Table Topic Session", 20, 0),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "TTE_ORDER" in codes
    tte = next(i for i in issues if i.code == "TTE_ORDER")
    assert tte.severity == "hard"
    assert tte.segment_ids == ["s1"]


def test_tte_after_tts_is_clean():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "Table Topic Session", 30, 0),
            ("s2", "Table Topic Evaluation", 105, 0),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "TTE_ORDER" not in codes


def test_no_tts_at_all_means_no_tte_order_issue():
    # TTE present but no TTS — can't enforce order against nothing
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "Table Topic Evaluation", 130, 0),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "TTE_ORDER" not in codes


def test_multiple_offending_ttes_all_reported():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "Table Topic Evaluation", 10, 0),
            ("s2", "SAA", 5, 0),
            ("s3", "Table Topic Evaluation", 10, 0),
            ("s4", "Table Topic Session", 110, 0),
        ],
    )
    issues = run_validators(agenda)
    tte_issues = [i for i in issues if i.code == "TTE_ORDER"]
    assert len(tte_issues) == 1
    assert set(tte_issues[0].segment_ids) == {"s1", "s3"}
    assert tte_issues[0].severity == "hard"


# --- BUFFER_SEGMENT_ANTIPATTERN --------------------------------------------


def test_buffer_segment_english_is_hard_issue():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "Buffer", 5, 0),
            ("s3", "TOM", 125, 0),
        ],
    )
    issues = run_validators(agenda)
    buf = [i for i in issues if i.code == "BUFFER_SEGMENT_ANTIPATTERN"]
    assert len(buf) == 1
    assert buf[0].severity == "hard"
    assert buf[0].segment_ids == ["s2"]


def test_buffer_segment_cjk_is_hard_issue():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "间隔", 5, 0),
            ("s3", "TOM", 125, 0),
        ],
    )
    issues = run_validators(agenda)
    buf = [i for i in issues if i.code == "BUFFER_SEGMENT_ANTIPATTERN"]
    assert len(buf) == 1
    assert buf[0].severity == "hard"
    assert buf[0].segment_ids == ["s2"]


def test_buffer_segment_gap_word_is_hard_issue():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "5min gap", 5, 0),
            ("s3", "TOM", 125, 0),
        ],
    )
    issues = run_validators(agenda)
    buf = [i for i in issues if i.code == "BUFFER_SEGMENT_ANTIPATTERN"]
    assert len(buf) == 1
    assert buf[0].severity == "hard"
    assert buf[0].segment_ids == ["s2"]


def test_buffer_segment_case_insensitive():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "BUFFER", 5, 0),
            ("s3", "TOM", 125, 0),
        ],
    )
    issues = run_validators(agenda)
    buf = [i for i in issues if i.code == "BUFFER_SEGMENT_ANTIPATTERN"]
    assert len(buf) == 1
    assert buf[0].segment_ids == ["s2"]


def test_multiple_buffer_segments_each_reported_separately():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 5, 0),
            ("s2", "Buffer", 5, 0),
            ("s3", "TOM", 5, 0),
            ("s4", "间隔", 5, 0),
            ("s5", "Gap", 5, 0),
            ("s6", "Closing", 110, 0),
        ],
    )
    issues = run_validators(agenda)
    buf = [i for i in issues if i.code == "BUFFER_SEGMENT_ANTIPATTERN"]
    assert len(buf) == 3
    assert [i.segment_ids for i in buf] == [["s2"], ["s4"], ["s5"]]
    assert all(i.severity == "hard" for i in buf)


# --- DURATION_OVERFLOW -----------------------------------------------------


def test_overflow_reports_soft_issue():
    # window 135 min, agenda 200 min  → 65 min overflow
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 100, 0),
            ("s2", "TOM", 100, 0),
        ],
    )
    issues = run_validators(agenda)
    over = [i for i in issues if i.code == "DURATION_OVERFLOW"]
    assert len(over) == 1
    assert over[0].severity == "soft"
    assert "65 min" in over[0].message


def test_no_overflow_no_issue():
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 60, 0),
            ("s2", "TOM", 75, 0),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "DURATION_OVERFLOW" not in codes


def test_overflow_does_not_double_count_pre_meeting_warmup():
    """Regression: club agendas put a 15-min Guests Registration warmup at
    19:15 even though meta.start_time is 19:30 (the official meeting start).
    The validator must anchor on the LAST segment's end, not on
    `meta.start_time + sum(durations)` — otherwise the 15-min pre-meeting
    window double-counts and produces a false-positive overflow."""
    agenda = Agenda(
        meta=Meta(start_time="19:30", end_time="21:30"),
        segments=[
            Segment(id="s1", type="Guests Registration", start_time="19:15", duration=15),
            Segment(id="s2", type="SAA", start_time="19:30", duration=2),
            Segment(id="s3", type="Closing Remarks", start_time="21:29", duration=1),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "DURATION_OVERFLOW" not in codes


# --- DURATION_UNDERFLOW ----------------------------------------------------


def test_underflow_slack_over_10_is_soft_issue():
    # 135-min window, 30-min agenda = 105 min of slack
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 10, 0),
            ("s2", "TOM", 20, 0),
        ],
    )
    issues = run_validators(agenda)
    under = [i for i in issues if i.code == "DURATION_UNDERFLOW"]
    assert len(under) == 1
    assert under[0].severity == "soft"
    assert "105 min" in under[0].message


def test_underflow_slack_under_threshold_no_issue():
    # 135-min window, 130-min agenda = 5 min of slack (≤ 10 threshold)
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 60, 0),
            ("s2", "TOM", 70, 0),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "DURATION_UNDERFLOW" not in codes


def test_underflow_slack_exactly_10_no_issue():
    # 135-min window, 125-min agenda = 10 min of slack (> 10 is threshold, 10 itself is OK)
    agenda = make(
        start="19:15",
        end="21:30",
        segs=[
            ("s1", "SAA", 60, 0),
            ("s2", "TOM", 65, 0),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "DURATION_UNDERFLOW" not in codes


def test_invalid_meta_times_skip_time_checks_silently():
    # Missing end_time → overflow/underflow both skipped
    agenda1 = Agenda(
        meta=Meta(start_time="19:15", end_time=None),
        segments=[
            Segment(id="s1", type="SAA", start_time="00:00", duration=5, buffer_before=0),
        ],
    )
    issues1 = run_validators(agenda1)
    codes1 = {i.code for i in issues1}
    assert "DURATION_OVERFLOW" not in codes1
    assert "DURATION_UNDERFLOW" not in codes1

    # Missing start_time → also skipped
    agenda2 = Agenda(
        meta=Meta(start_time=None, end_time="21:30"),
        segments=[
            Segment(id="s1", type="SAA", start_time="00:00", duration=5, buffer_before=0),
        ],
    )
    issues2 = run_validators(agenda2)
    codes2 = {i.code for i in issues2}
    assert "DURATION_OVERFLOW" not in codes2
    assert "DURATION_UNDERFLOW" not in codes2

    # Garbage start_time → also skipped
    agenda3 = Agenda(
        meta=Meta(start_time="not-a-time", end_time="21:30"),
        segments=[
            Segment(id="s1", type="SAA", start_time="00:00", duration=5, buffer_before=0),
        ],
    )
    issues3 = run_validators(agenda3)
    codes3 = {i.code for i in issues3}
    assert "DURATION_OVERFLOW" not in codes3
    assert "DURATION_UNDERFLOW" not in codes3


# --- buffer_before counted in totals --------------------------------------


def test_buffer_before_counted_in_overflow():
    # window 10 min, segments 3 + 3 = 6, plus 5-min buffer_before on s2 = 11 total → overflow
    agenda = make(
        start="19:00",
        end="19:10",
        segs=[
            ("s1", "SAA", 3, 0),
            ("s2", "TOM", 3, 5),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    assert "DURATION_OVERFLOW" in codes


def test_first_segment_buffer_before_ignored_in_totals():
    # s1 has buffer_before=100 but that's ignored for the first segment;
    # window 10 min, agenda effectively 3 min → underflow
    agenda = make(
        start="19:00",
        end="19:10",
        segs=[
            ("s1", "SAA", 3, 100),
        ],
    )
    issues = run_validators(agenda)
    codes = {i.code for i in issues}
    # Should NOT overflow (first seg's buffer_before is ignored)
    assert "DURATION_OVERFLOW" not in codes
    # Should underflow (3 min agenda in 10 min window = 7 min slack, below 10 threshold)
    assert "DURATION_UNDERFLOW" not in codes
