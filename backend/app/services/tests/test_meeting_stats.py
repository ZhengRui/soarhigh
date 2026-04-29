"""Data-gate tests for the shared statistics service.

These tests pin behaviors that the dashboard route AND the statistics
agent both depend on. If a refactor breaks any of these, both surfaces
diverge from the single source of truth.

Specifically:
  - `_batch_in` chunks correctly (regression for URL-length cap).
  - `resolve_member` resolves canonical / ambiguous / missing cleanly,
    and DB is the only source of truth (no static-list fallback).
  - `compute_meeting_attendance` produces the same merged attendance
    set for the dashboard and the stats agent — the load-bearing
    invariant for "dashboard parity".
  - Aggregation primitives (count / group / time_bucket / role
    distribution / attendance summary) match expected shapes for
    fixture data.
"""

from __future__ import annotations

from unittest.mock import patch

from app.services import meeting_stats

# ---------- _batch_in ----------


def test_batch_in_chunks_at_the_specified_size():
    """The whole point of _batch_in: never let a single .in_(...) call
    grow past PostgREST's URL-length cap. Verify chunk boundaries by
    counting per-call sizes."""
    seen_chunks: list[list[str]] = []

    def fake_fetch(chunk: list[str]) -> list[dict]:
        seen_chunks.append(chunk)
        return [{"id": x} for x in chunk]

    ids = [f"id-{i}" for i in range(125)]
    out = meeting_stats._batch_in(fake_fetch, ids, chunk_size=50)
    assert len(out) == 125
    assert [len(c) for c in seen_chunks] == [50, 50, 25]


def test_batch_in_skips_empty_inputs():
    calls = []

    def fake_fetch(chunk: list[str]) -> list[dict]:
        calls.append(chunk)
        return []

    assert meeting_stats._batch_in(fake_fetch, []) == []
    assert meeting_stats._batch_in(fake_fetch, [None, "", None]) == []  # type: ignore[list-item]
    assert calls == []


def test_execute_all_pages_fetches_until_short_page():
    rows = [{"id": f"row-{i}"} for i in range(2005)]
    seen_ranges: list[tuple[int, int]] = []

    class _Query:
        def __init__(self):
            self._range = (0, 999)

        def range(self, start: int, end: int):
            self._range = (start, end)
            seen_ranges.append((start, end))
            return self

        def execute(self):
            start, end = self._range

            class _Result:
                def __init__(self, d):
                    self.data = d

            return _Result(rows[start : end + 1])

    out = meeting_stats._execute_all_pages(_Query, page_size=1000)

    assert len(out) == 2005
    assert seen_ranges == [(0, 999), (1000, 1999), (2000, 2999)]


# ---------- resolve_member ----------


def _stub_supabase_members(rows: list[dict]):
    """Patch the supabase singleton inside meeting_stats so resolver
    tests don't require a live DB connection."""

    class _StubSelect:
        def __init__(self, data):
            self._data = data

        def execute(self):
            class _Result:
                def __init__(self, d):
                    self.data = d

            return _Result(self._data)

    class _StubTable:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_args, **_kwargs):
            return _StubSelect(self._rows)

    class _StubClient:
        def __init__(self, rows):
            self._rows = rows

        def table(self, _name):
            return _StubTable(self._rows)

    return patch("app.services.meeting_stats.supabase", _StubClient(rows))


def test_resolve_member_blank_returns_none():
    assert meeting_stats.resolve_member("") is None
    assert meeting_stats.resolve_member("   ") is None


def test_resolve_member_exact_full_name_match():
    rows = [
        {"id": "m1", "full_name": "Joyce Feng", "username": "joyce"},
        {"id": "m2", "full_name": "Frank Zeng", "username": "frank"},
    ]
    with _stub_supabase_members(rows):
        result = meeting_stats.resolve_member("Joyce Feng")
    assert isinstance(result, meeting_stats.Member)
    assert result.id == "m1"


def test_resolve_member_case_insensitive():
    rows = [{"id": "m1", "full_name": "Joyce Feng", "username": "joyce"}]
    with _stub_supabase_members(rows):
        result = meeting_stats.resolve_member("joyce feng")
    assert isinstance(result, meeting_stats.Member)
    assert result.id == "m1"


def test_resolve_member_username_fallback():
    """Exact full_name miss → fall through to exact username match."""
    rows = [{"id": "m1", "full_name": "Joyce Feng", "username": "jfeng"}]
    with _stub_supabase_members(rows):
        result = meeting_stats.resolve_member("jfeng")
    assert isinstance(result, meeting_stats.Member)
    assert result.id == "m1"


def test_resolve_member_substring_unique():
    rows = [
        {"id": "m1", "full_name": "Joyce Feng", "username": "jfeng"},
        {"id": "m2", "full_name": "Frank Zeng", "username": "frank"},
    ]
    with _stub_supabase_members(rows):
        result = meeting_stats.resolve_member("Frank")
    assert isinstance(result, meeting_stats.Member)
    assert result.id == "m2"


def test_resolve_member_substring_ambiguous():
    """When multiple rows match a substring, return AmbiguousMember
    instead of guessing — the tool surfaces candidates and the user
    disambiguates. Use a substring that matches partially in both
    rows (no exact full_name or username match) so the resolver
    falls through to the substring step."""
    rows = [
        {"id": "m1", "full_name": "Joyce Feng", "username": "jfeng"},
        {"id": "m2", "full_name": "Joyce Anderson", "username": "janderson"},
    ]
    with _stub_supabase_members(rows):
        result = meeting_stats.resolve_member("Joyce")
    assert isinstance(result, meeting_stats.AmbiguousMember)
    assert {c.id for c in result.candidates} == {"m1", "m2"}


def test_resolve_member_unknown_returns_none():
    rows = [{"id": "m1", "full_name": "Joyce Feng", "username": "joyce"}]
    with _stub_supabase_members(rows):
        assert meeting_stats.resolve_member("Steve Jobs") is None


def test_resolve_member_does_not_consult_club_members_static_list():
    """Pin: resolver never touches CLUB_MEMBERS. DB is the only source
    of truth — the static prompt list can drift behind the DB and
    pre-validation against it would refuse new members the DB
    actually contains."""
    rows: list[dict] = []  # empty DB
    with _stub_supabase_members(rows):
        # CLUB_MEMBERS has names like "Joyce Feng" — resolver MUST NOT
        # find them when the DB is empty.
        assert meeting_stats.resolve_member("Joyce Feng") is None


# ---------- compute_meeting_attendance ----------


def _stub_supabase_with_tables(table_data: dict[str, list[dict]]):
    """A more general supabase stub for compute_meeting_attendance.
    Each table call returns the rows registered for that table; .in_()
    filters within those rows by the indicated column."""

    class _Query:
        def __init__(self, rows):
            self._rows = list(rows)
            self._predicates: list = []
            self._range: tuple[int, int] | None = None

        def select(self, *_args, **_kwargs):
            return self

        def range(self, start, end):
            self._range = (start, end)
            return self

        def in_(self, column, values):
            self._predicates.append(("in", column, list(values)))
            return self

        @property
        def not_(self):
            # supabase-py exposes `not_` as a chainable property, not a
            # method — `.not_.is_("attendee_id", "null")` is a filter
            # for IS NOT NULL on that column.
            return _NotQuery(self)

        def eq(self, column, value):
            self._predicates.append(("eq", column, value))
            return self

        def gte(self, column, value):
            self._predicates.append(("gte", column, value))
            return self

        def lte(self, column, value):
            self._predicates.append(("lte", column, value))
            return self

        def order(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def execute(self):
            rows = list(self._rows)
            for op, col, val in self._predicates:
                if op == "in":
                    rows = [r for r in rows if r.get(col) in val]
                elif op == "eq":
                    rows = [r for r in rows if r.get(col) == val]
                elif op == "is_not_null":
                    rows = [r for r in rows if r.get(col) is not None]
                elif op == "gte":
                    rows = [r for r in rows if (r.get(col) or "") >= val]
                elif op == "lte":
                    rows = [r for r in rows if (r.get(col) or "") <= val]

            if self._range is None:
                rows = rows[:1000]
            else:
                start, end = self._range
                rows = rows[start : end + 1]

            class _Result:
                def __init__(self, d):
                    self.data = d

            return _Result(rows)

    class _NotQuery:
        def __init__(self, parent):
            self._parent = parent

        def is_(self, column, value):
            if value == "null":
                self._parent._predicates.append(("is_not_null", column, None))
            return self._parent

    class _Table:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_args, **_kwargs):
            return _Query(self._rows)

    class _Client:
        def __init__(self, data):
            self._data = data

        def table(self, name):
            return _Table(self._data.get(name, []))

    return patch("app.services.meeting_stats.supabase", _Client(table_data))


def test_compute_meeting_attendance_merges_segments_and_checkins():
    """Member who appears via segment role AND check-in counts ONCE.
    Pinning the smart-merge invariant — same logic the dashboard has
    used in production, now extracted into a shared function."""
    table_data = {
        "segments": [
            {"meeting_id": "mtg-1", "attendee_id": "att-joyce"},
        ],
        "attendees": [
            {"id": "att-joyce", "name": "Joyce Feng", "wxid": "wx-joyce", "member_id": "mem-joyce"},
        ],
        "checkins": [
            # Same person showing up via wxid in checkins.
            {"meeting_id": "mtg-1", "wxid": "wx-joyce", "name": "Joyce Feng", "is_member": True},
        ],
        "members": [{"id": "mem-joyce", "full_name": "Joyce Feng"}],
    }
    with _stub_supabase_with_tables(table_data):
        out = meeting_stats.compute_meeting_attendance(["mtg-1"])
    record = out["mtg-1"]
    # ONE member, ZERO guests (Joyce isn't a guest — she's a member who
    # also checked in, dedupe must drop the duplicate).
    assert record.member_ids == {"mem-joyce"}
    assert record.guest_names == set()


def test_compute_meeting_attendance_dedupes_guest_against_member_full_name():
    """A guest entry whose name substring-matches a member's full_name
    is dropped — same person showing up in two channels under different
    spellings ('Joyce' guest entry vs 'Joyce Feng' member entry)."""
    table_data = {
        "segments": [
            # Member via segment role
            {"meeting_id": "mtg-1", "attendee_id": "att-joyce-mem"},
            # Same person re-entered as a guest in a different segment
            {"meeting_id": "mtg-1", "attendee_id": "att-joyce-guest"},
        ],
        "attendees": [
            {"id": "att-joyce-mem", "name": "Joyce", "wxid": None, "member_id": "mem-joyce"},
            {"id": "att-joyce-guest", "name": "Joyce", "wxid": None, "member_id": None},
        ],
        "checkins": [],
        "members": [{"id": "mem-joyce", "full_name": "Joyce Feng"}],
    }
    with _stub_supabase_with_tables(table_data):
        out = meeting_stats.compute_meeting_attendance(["mtg-1"])
    record = out["mtg-1"]
    assert record.member_ids == {"mem-joyce"}
    assert record.guest_names == set()


def test_compute_meeting_attendance_filters_placeholder_guest_names():
    """Names like 'TBD', 'all', '-' are placeholders, not real guests."""
    table_data = {
        "segments": [
            {"meeting_id": "mtg-1", "attendee_id": "att-tbd"},
            {"meeting_id": "mtg-1", "attendee_id": "att-real"},
        ],
        "attendees": [
            {"id": "att-tbd", "name": "TBD", "wxid": None, "member_id": None},
            {"id": "att-real", "name": "Lucas", "wxid": None, "member_id": None},
        ],
        "checkins": [],
        "members": [],
    }
    with _stub_supabase_with_tables(table_data):
        out = meeting_stats.compute_meeting_attendance(["mtg-1"])
    record = out["mtg-1"]
    assert record.guest_names == {"Lucas"}


def test_compute_meeting_attendance_pages_more_than_1000_segment_rows():
    """Regression: batching by meeting id is not enough when one batch
    still returns more rows than PostgREST's default cap."""
    segment_rows = [{"meeting_id": "mtg-1", "attendee_id": f"att-{i}"} for i in range(1001)]
    attendee_rows = [
        {
            "id": f"att-{i}",
            "name": f"Guest {i}",
            "wxid": None,
            "member_id": None,
        }
        for i in range(1001)
    ]
    table_data = {
        "segments": segment_rows,
        "attendees": attendee_rows,
        "checkins": [],
        "members": [],
    }

    with _stub_supabase_with_tables(table_data):
        out = meeting_stats.compute_meeting_attendance(["mtg-1"])

    assert len(out["mtg-1"].guest_names) == 1001


def test_compute_meeting_attendance_empty_meeting_ids():
    assert meeting_stats.compute_meeting_attendance([]) == {}


# ---------- count_meetings / group ----------


def test_count_meetings_uses_loader():
    fake_meetings = [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]
    with patch(
        "app.services.meeting_stats.load_meetings_in_range",
        return_value=fake_meetings,
    ):
        out = meeting_stats.count_meetings("2025-01-01", "2025-12-31")
    assert out["value"] == 3
    assert out["scanned_count"] == 3


def test_group_meetings_by_type_aggregates():
    fake = [
        {"id": "m1", "type": "Workshop"},
        {"id": "m2", "type": "Regular"},
        {"id": "m3", "type": "Workshop"},
        {"id": "m4", "type": "Custom"},
    ]
    with patch(
        "app.services.meeting_stats.load_meetings_in_range",
        return_value=fake,
    ):
        groups = meeting_stats.group_meetings_by_type(None, None)
    assert {g["type"]: g["count"] for g in groups} == {
        "Workshop": 2,
        "Regular": 1,
        "Custom": 1,
    }


# ---------- time_bucket ----------


def test_bucket_key_month_quarter_year():
    assert meeting_stats._bucket_key("2025-10-15", "month") == "2025-10"
    assert meeting_stats._bucket_key("2025-10-15", "quarter") == "2025-Q4"
    assert meeting_stats._bucket_key("2025-10-15", "year") == "2025"
    assert meeting_stats._bucket_key("2025-01-01", "quarter") == "2025-Q1"
    assert meeting_stats._bucket_key("2025-04-01", "quarter") == "2025-Q2"
    assert meeting_stats._bucket_key("2025-07-01", "quarter") == "2025-Q3"
    assert meeting_stats._bucket_key("2025-10-01", "quarter") == "2025-Q4"


def test_time_bucket_meetings_count_metric():
    fake = [
        {"id": "m1", "date": "2025-01-15"},
        {"id": "m2", "date": "2025-01-22"},
        {"id": "m3", "date": "2025-02-05"},
    ]
    with patch(
        "app.services.meeting_stats.load_meetings_in_range",
        return_value=fake,
    ):
        series = meeting_stats.time_bucket_meetings("count", "month")
    assert series == [
        {"bucket": "2025-01", "value": 2, "meeting_count": 2},
        {"bucket": "2025-02", "value": 1, "meeting_count": 1},
    ]


# ---------- member_role_distribution ----------


def test_member_role_distribution_counts_by_segment_type():
    def _hist_row(meeting_id, no, date, segment_type):
        return {
            "meeting_id": meeting_id,
            "no": no,
            "date": date,
            "theme": "T",
            "segment_type": segment_type,
            "start_time": "19:30",
        }

    fake_history = [
        _hist_row("m1", 1, "2025-01-15", "Timer"),
        _hist_row("m2", 2, "2025-02-15", "Timer"),
        _hist_row("m3", 3, "2025-03-15", "Hark Master"),
    ]
    with patch(
        "app.services.meeting_stats.member_segment_history",
        return_value=fake_history,
    ):
        dist = meeting_stats.member_role_distribution("mem-1", date_from=None, date_to=None, include_manager=False)
    assert dist == {"Timer": 2, "Hark Master": 1}


def test_member_role_distribution_include_manager_adds_synthetic_entry():
    """Default excludes manager (matches dashboard). When include_manager
    is True, add a synthetic 'Meeting Manager' entry alongside segment
    counts so the user sees it separately."""
    fake_history = [
        {
            "meeting_id": "m1",
            "no": 1,
            "date": "2025-01-15",
            "theme": "T1",
            "segment_type": "Timer",
            "start_time": "19:30",
        },
    ]
    fake_managed = [{"meeting_id": "m9", "no": 9, "date": "2025-04-01", "theme": "M"}]
    with (
        patch(
            "app.services.meeting_stats.member_segment_history",
            return_value=fake_history,
        ),
        patch(
            "app.services.meeting_stats.meetings_managed_by",
            return_value=fake_managed,
        ),
    ):
        dist = meeting_stats.member_role_distribution("mem-1", include_manager=True)
    assert dist == {"Timer": 1, "Meeting Manager": 1}


# ---------- member_attendance_summary ----------


def test_member_attendance_summary_uses_smart_merge_definition():
    """Numerator = meetings where the member appeared in the merged
    attendance set (member_ids). Critical correctness pin: 'attended'
    must use the same definition the dashboard uses, not just
    'had a segment role'."""
    fake_meetings = [
        {"id": "m1", "no": 1, "date": "2025-01-15"},
        {"id": "m2", "no": 2, "date": "2025-02-15"},
        {"id": "m3", "no": 3, "date": "2025-03-15"},
    ]
    fake_attendance = {
        "m1": meeting_stats.MeetingAttendance("m1", member_ids={"mem-target"}, guest_names=set()),
        # m2: member-target NOT present (skipped that meeting).
        "m2": meeting_stats.MeetingAttendance("m2", member_ids={"mem-other"}, guest_names=set()),
        "m3": meeting_stats.MeetingAttendance("m3", member_ids={"mem-target"}, guest_names=set()),
    }
    with (
        patch(
            "app.services.meeting_stats.load_meetings_in_range",
            return_value=fake_meetings,
        ),
        patch(
            "app.services.meeting_stats.compute_meeting_attendance",
            return_value=fake_attendance,
        ),
    ):
        summary = meeting_stats.member_attendance_summary("mem-target")
    assert summary == {"attended": 2, "total": 3, "rate": round(2 / 3, 4)}
