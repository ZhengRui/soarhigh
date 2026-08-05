import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import app.api.routes.meeting as meeting_route
import app.db.core as meeting_db
from app.api.serv import app


class _QueryResult:
    def __init__(self, *, data=None, count=None):
        self.data = data
        self.count = count


class _MeetingOptionsQuery:
    def __init__(self, owner):
        self.owner = owner
        self.is_count = False

    def select(self, columns, count=None):
        self.owner.selects.append((columns, count))
        self.is_count = count == "exact"
        return self

    def eq(self, column, value):
        self.owner.filters.append((column, value))
        return self

    def in_(self, column, values):
        self.owner.in_filters.append((column, values))
        return self

    def order(self, column, desc=False):
        self.owner.orders.append((column, desc))
        return self

    def range(self, start, end):
        self.owner.ranges.append((start, end))
        return self

    def execute(self):
        if self.is_count:
            return _QueryResult(count=len(self.owner.rows))
        return _QueryResult(data=self.owner.rows)


class _MeetingOptionsSupabase:
    def __init__(self, rows):
        self.rows = rows
        self.selects = []
        self.filters = []
        self.in_filters = []
        self.orders = []
        self.ranges = []

    def table(self, table_name):
        assert table_name == "meetings"
        return _MeetingOptionsQuery(self)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_auth_override():
    yield
    app.dependency_overrides.pop(meeting_route.get_meeting_reader_user_id, None)


def test_meeting_options_returns_only_selector_fields_for_an_authenticated_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def get_options(**kwargs):
        captured.update(kwargs)
        return {
            "items": [
                {
                    "id": "meeting-462",
                    "no": 462,
                    "type": "Regular",
                    "theme": "Cultural sharing and exchange",
                    "date": "2026-07-15",
                    "introduction": "This full-detail field must not leak into the compact response.",
                }
            ],
            "total": 11,
            "page": 2,
            "page_size": 10,
            "pages": 2,
        }

    monkeypatch.setattr(meeting_route, "get_meeting_options", get_options)
    app.dependency_overrides[meeting_route.get_meeting_reader_user_id] = lambda: "member-1"

    response = client.get("/meetings/options?page=2&page_size=10&status=draft")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "meeting-462",
                "no": 462,
                "type": "Regular",
                "theme": "Cultural sharing and exchange",
                "date": "2026-07-15",
            }
        ],
        "total": 11,
        "page": 2,
        "page_size": 10,
        "pages": 2,
    }
    assert captured == {
        "user_id": "member-1",
        "status": "draft",
        "page": 2,
        "page_size": 10,
    }


def test_meeting_options_uses_the_anonymous_visibility_scope(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def get_options(**kwargs):
        captured.update(kwargs)
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 50,
            "pages": 1,
        }

    monkeypatch.setattr(meeting_route, "get_meeting_options", get_options)
    app.dependency_overrides[meeting_route.get_meeting_reader_user_id] = lambda: None

    response = client.get("/meetings/options")

    assert response.status_code == 200
    assert captured == {
        "user_id": None,
        "status": None,
        "page": 1,
        "page_size": 50,
    }


def test_meeting_options_query_is_lightweight_and_reuses_visibility_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "id": "meeting-462",
            "no": 462,
            "type": "Regular",
            "theme": "Cultural sharing and exchange",
            "date": "2026-07-15",
        }
    ]
    fake_supabase = _MeetingOptionsSupabase(rows)
    monkeypatch.setattr(meeting_db, "supabase", fake_supabase)

    result = meeting_db.get_meeting_options(
        user_id=None,
        status=None,
        page=2,
        page_size=10,
    )

    assert result == {
        "items": rows,
        "total": 1,
        "page": 2,
        "page_size": 10,
        "pages": 1,
    }
    assert fake_supabase.selects == [
        ("id", "exact"),
        ("id,no,type,theme,date", None),
    ]
    assert fake_supabase.filters == [
        ("status", "published"),
        ("status", "published"),
    ]
    assert fake_supabase.orders == [("date", True)]
    assert fake_supabase.ranges == [(10, 19)]


def test_meeting_options_batch_returns_requested_records_in_request_order(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def get_options(ids, **kwargs):
        captured.update({"ids": ids, **kwargs})
        return [
            {
                "id": "meeting-462",
                "no": 462,
                "type": "Regular",
                "theme": "Culture in Every Voice",
                "date": "2026-07-15",
            }
        ]

    monkeypatch.setattr(meeting_route, "get_meeting_options_by_ids", get_options)
    app.dependency_overrides[meeting_route.get_meeting_reader_user_id] = lambda: "member-1"

    response = client.post(
        "/meetings/options/batch",
        json={"ids": ["meeting-462", "meeting-461", "meeting-462"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "meeting-462",
                "no": 462,
                "type": "Regular",
                "theme": "Culture in Every Voice",
                "date": "2026-07-15",
            }
        ]
    }
    assert captured == {
        "ids": ["meeting-462", "meeting-461", "meeting-462"],
        "user_id": "member-1",
    }


def test_meeting_options_batch_rejects_more_than_one_hundred_ids(
    client: TestClient,
) -> None:
    response = client.post(
        "/meetings/options/batch",
        json={"ids": [f"meeting-{index}" for index in range(101)]},
    )

    assert response.status_code == 422


def test_meeting_reader_accepts_only_the_scoped_wxpost_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meeting_route, "WXPOST_SERVICE_TOKEN", "service-secret")

    assert (
        meeting_route.get_meeting_reader_user_id(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="service-secret")
        )
        == "wxpost-service"
    )


def test_meeting_options_batch_query_is_compact_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "id": "meeting-462",
            "no": 462,
            "type": "Regular",
            "theme": "Culture in Every Voice",
            "date": "2026-07-15",
        },
        {
            "id": "meeting-461",
            "no": 461,
            "type": "Regular",
            "theme": "Workshop night",
            "date": "2026-07-08",
        },
    ]
    fake_supabase = _MeetingOptionsSupabase(rows)
    monkeypatch.setattr(meeting_db, "supabase", fake_supabase)

    result = meeting_db.get_meeting_options_by_ids(
        ["meeting-461", "meeting-462", "meeting-461"],
        user_id="member-1",
    )

    assert result == [rows[1], rows[0]]
    assert fake_supabase.selects == [("id,no,type,theme,date", None)]
    assert fake_supabase.in_filters == [("id", ["meeting-461", "meeting-462"])]
    assert fake_supabase.filters == []
