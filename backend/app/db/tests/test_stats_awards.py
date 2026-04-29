from __future__ import annotations

from unittest.mock import patch

from app.db import stats as db_stats


def _stub_supabase_tables(table_data: dict[str, list[dict]]):
    class _Query:
        def __init__(self, rows):
            self._rows = list(rows)
            self._predicates: list[tuple[str, str, list[str]]] = []
            self._range: tuple[int, int] | None = None

        def select(self, *_args, **_kwargs):
            return self

        def in_(self, column, values):
            self._predicates.append(("in", column, list(values)))
            return self

        def range(self, start, end):
            self._range = (start, end)
            return self

        def execute(self):
            rows = list(self._rows)
            for op, column, values in self._predicates:
                if op == "in":
                    rows = [row for row in rows if row.get(column) in values]
            if self._range is None:
                rows = rows[:1000]
            else:
                start, end = self._range
                rows = rows[start : end + 1]

            class _Result:
                def __init__(self, data):
                    self.data = data

            return _Result(rows)

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

    return patch("app.db.stats.supabase", _Client(table_data))


def test_get_member_award_stats_keeps_unresolved_and_ambiguous_winners():
    meetings = [
        {"id": "m1", "date": "2026-01-07", "theme": "A", "no": 451},
        {"id": "m2", "date": "2026-01-14", "theme": "B", "no": 452},
    ]
    table_data = {
        "awards": [
            {
                "id": "a1",
                "meeting_id": "m1",
                "category": "Best Prepared Speaker",
                "winner": "Joyce Feng",
            },
            {
                "id": "a2",
                "meeting_id": "m1",
                "category": "Best Evaluator",
                "winner": "Frank",
            },
            {
                "id": "a3",
                "meeting_id": "m2",
                "category": "Best Joke",
                "winner": "Guest A",
            },
        ],
        "members": [
            {"id": "mem-joyce", "username": "joyce", "full_name": "Joyce Feng"},
            {"id": "mem-frank-1", "username": "frank1", "full_name": "Frank Zeng"},
            {"id": "mem-frank-2", "username": "frank2", "full_name": "Frank Wang"},
        ],
    }

    with (
        patch("app.services.meeting_stats.load_meetings_in_range", return_value=meetings),
        _stub_supabase_tables(table_data),
    ):
        rows = db_stats.get_member_award_stats("2026-01-01", "2026-12-31")

    assert len(rows) == 3
    assert rows[0] == {
        "award_id": "a1",
        "meeting_id": "m1",
        "meeting_date": "2026-01-07",
        "meeting_theme": "A",
        "meeting_no": 451,
        "category": "Best Prepared Speaker",
        "winner_name": "Joyce Feng",
        "member_id": "mem-joyce",
        "username": "joyce",
        "full_name": "Joyce Feng",
        "winner_resolved": True,
    }
    assert rows[1]["winner_name"] == "Frank"
    assert rows[1]["winner_resolved"] is False
    assert rows[1]["member_id"] is None
    assert rows[2]["winner_name"] == "Guest A"
    assert rows[2]["winner_resolved"] is False
