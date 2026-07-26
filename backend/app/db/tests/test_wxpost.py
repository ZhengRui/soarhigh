from types import SimpleNamespace
from uuid import UUID

from postgrest.exceptions import APIError

import app.db.content as content_db
import app.db.wxpost as wxpost_db
from app.models.wxpost import ArticleDocument

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000236")


class FakeQuery:
    def __init__(self, *, data: list[dict] | None = None):
        self.data = data or []
        self.filters: list[tuple[str, object]] = []
        self.updated: dict | None = None

    def update(self, values: dict):
        self.updated = values
        return self

    def select(self, *args, **kwargs):
        return self

    def eq(self, field: str, value: object):
        self.filters.append((field, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class FakeSupabase:
    def __init__(self, queries: list[object]):
        self.queries = queries

    def table(self, name: str):
        assert name == "wxposts"
        return self.queries.pop(0)


class FakeInsertQuery:
    def __init__(self, outcome):
        self.outcome = outcome
        self.inserted: dict | None = None

    def insert(self, values: dict):
        self.inserted = values
        return self

    def execute(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SimpleNamespace(data=[self.outcome])


def _document() -> ArticleDocument:
    return ArticleDocument.model_validate(
        {
            "schemaVersion": 1,
            "title": "The Courage to Try",
            "articleType": "custom",
            "customArticleType": "Field Reflection",
            "bodyMarkdown": "A complete thought.",
            "media": [],
            "presentation": {
                "layout": "brand-default",
                "palette": "paper-neutral",
                "appearance": "light",
                "typeface": "editorial-serif",
            },
        }
    )


def test_slugify_is_stable_and_has_a_safe_fallback() -> None:
    assert wxpost_db.slugify_wxpost_title("  The Courage: Try Again!  ") == "the-courage-try-again"
    assert wxpost_db.slugify_wxpost_title("勇气") == "wxpost"


def test_create_suffixes_only_after_a_real_slug_collision(monkeypatch) -> None:
    collision = FakeInsertQuery(
        APIError(
            {
                "code": "23505",
                "message": "duplicate key",
                "hint": "",
                "details": "",
            }
        )
    )
    created = {
        "id": str(WXPOST_ID),
        "slug": "the-courage-to-try-abcdef",
        "article_revision": 1,
    }
    retry = FakeInsertQuery(created)
    monkeypatch.setattr(wxpost_db, "supabase", FakeSupabase([collision, retry]))
    monkeypatch.setattr(
        wxpost_db,
        "uuid4",
        lambda: SimpleNamespace(hex="abcdef1234567890"),
    )

    result = wxpost_db.create_wxpost(_document())

    assert result == created
    assert collision.inserted is not None
    assert collision.inserted["slug"] == "the-courage-to-try"
    assert retry.inserted is not None
    assert retry.inserted["slug"] == "the-courage-to-try-abcdef"


def test_update_is_a_single_compare_and_swap_write(
    monkeypatch,
) -> None:
    updated_row = {
        "id": str(WXPOST_ID),
        "slug": "the-courage-to-try",
        "article_revision": 5,
    }
    query = FakeQuery(data=[updated_row])
    monkeypatch.setattr(wxpost_db, "supabase", FakeSupabase([query]))

    result = wxpost_db.update_wxpost(
        WXPOST_ID,
        expected_revision=4,
        document=_document(),
    )

    assert result == updated_row
    assert query.filters == [
        ("id", str(WXPOST_ID)),
        ("article_revision", 4),
    ]
    assert query.updated is not None
    assert query.updated["article_revision"] == 5
    assert "slug" not in query.updated
    assert query.updated["content"] == "A complete thought."


def test_zero_row_update_distinguishes_missing_from_stale(
    monkeypatch,
) -> None:
    update_query = FakeQuery(data=[])
    lookup_query = FakeQuery(data=[{"id": str(WXPOST_ID), "article_revision": 5}])
    monkeypatch.setattr(
        wxpost_db,
        "supabase",
        FakeSupabase([update_query, lookup_query]),
    )

    try:
        wxpost_db.update_wxpost(
            WXPOST_ID,
            expected_revision=4,
            document=_document(),
        )
    except wxpost_db.WxPostRevisionConflictError:
        pass
    else:
        raise AssertionError("Expected a stale revision conflict.")


def test_combined_content_is_sorted_before_final_pagination(monkeypatch) -> None:
    monkeypatch.setattr(
        content_db,
        "_post_rows",
        lambda user_id, limit: (
            [
                {"id": "post-new", "created_at": "2026-07-25T12:00:00+00:00"},
                {"id": "post-old", "created_at": "2026-07-23T12:00:00+00:00"},
            ],
            2,
        ),
    )
    monkeypatch.setattr(
        content_db,
        "_wxpost_rows",
        lambda limit: (
            [
                {"id": "wx-new", "created_at": "2026-07-26T12:00:00+00:00"},
                {"id": "wx-old", "created_at": "2026-07-24T12:00:00+00:00"},
            ],
            2,
        ),
    )

    page = content_db.get_content_items(
        kind="all",
        user_id=None,
        page=2,
        page_size=2,
    )

    assert [item["id"] for item in page["items"]] == ["wx-old", "post-old"]
    assert page["total"] == 4
    assert page["pages"] == 2
