from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.meeting.models import Agenda, Meta
from app.agents.meeting.save_gate import (
    SaveClassification,
    classify_save,
    parse_meeting_datetime,
)

SH = ZoneInfo("Asia/Shanghai")


def _agenda(no=None, date="2026-05-10", start="19:30", end="21:30") -> Agenda:
    return Agenda(meta=Meta(no=no, date=date, start_time=start, end_time=end, theme="T", manager="M"))


def test_parse_meeting_datetime_combines_date_and_time_in_shanghai():
    dt = parse_meeting_datetime("2026-05-10", "19:30")
    assert dt == datetime(2026, 5, 10, 19, 30, tzinfo=SH)


def test_parse_meeting_datetime_returns_none_when_either_field_missing():
    assert parse_meeting_datetime(None, "19:30") is None
    assert parse_meeting_datetime("2026-05-10", None) is None
    assert parse_meeting_datetime("", "") is None


def test_classify_save_create_when_no_not_in_db_and_future():
    now = datetime(2026, 5, 1, 10, 0, tzinfo=SH)
    result = classify_save(_agenda(no=999), db_meeting=None, now=now)
    assert result == SaveClassification(mode="create")


def test_classify_save_refuses_create_when_start_time_past():
    now = datetime(2026, 5, 10, 19, 31, tzinfo=SH)
    result = classify_save(_agenda(no=999, date="2026-05-10", start="19:30"), db_meeting=None, now=now)
    assert result.mode == "refuse"
    assert result.reason == "create_past"


def test_classify_save_update_when_no_in_db_and_within_grace():
    now = datetime(2026, 5, 10, 22, 29, tzinfo=SH)  # 59 min after end_time
    db = {"id": "abc", "no": 451, "date": "2026-05-10", "end_time": "21:30"}
    result = classify_save(_agenda(no=451), db_meeting=db, now=now)
    assert result.mode == "update"
    assert result.meeting_id == "abc"


def test_classify_save_refuses_edit_after_grace_window():
    now = datetime(2026, 5, 10, 22, 31, tzinfo=SH)  # 61 min after end_time
    db = {"id": "abc", "no": 451, "date": "2026-05-10", "end_time": "21:30"}
    result = classify_save(_agenda(no=451), db_meeting=db, now=now)
    assert result.mode == "refuse"
    assert result.reason == "edit_past"


def test_classify_save_refuses_when_no_missing():
    now = datetime(2026, 5, 1, 10, 0, tzinfo=SH)
    result = classify_save(_agenda(no=None), db_meeting=None, now=now)
    assert result.mode == "refuse"
    assert result.reason == "missing_no"


def test_classify_save_refuses_when_create_missing_start_time():
    now = datetime(2026, 5, 1, 10, 0, tzinfo=SH)
    result = classify_save(_agenda(no=999, start=None), db_meeting=None, now=now)
    assert result.mode == "refuse"
    assert result.reason == "missing_schedule"
