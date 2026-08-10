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
        self.deleted = False

    def update(self, values: dict):
        self.updated = values
        return self

    def select(self, *args, **kwargs):
        return self

    def delete(self):
        self.deleted = True
        return self

    def eq(self, field: str, value: object):
        self.filters.append((field, value))
        return self

    def in_(self, field: str, value: object):
        self.filters.append((field, value))
        return self

    def is_(self, field: str, value: object):
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


class FakeAnyTableSupabase(FakeSupabase):
    def table(self, name: str):
        assert name in {"wxposts", "wxpost_assets", "wxpost_asset_variants"}
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


def test_custom_article_without_a_label_uses_the_database_default() -> None:
    payload = _document().model_copy(update={"custom_article_type": None})

    values = wxpost_db._document_values(payload)

    assert values["article_type"] == "custom"
    assert values["custom_article_type"] == "Custom"


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
    assert collision.inserted["status"] == "ready"
    assert retry.inserted is not None
    assert retry.inserted["slug"] == "the-courage-to-try-abcdef"
    assert retry.inserted["status"] == "ready"


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
        ("source_workspace_id", "null"),
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


def test_finalize_publication_is_one_guarded_visibility_swap(monkeypatch) -> None:
    updated = {
        "id": str(WXPOST_ID),
        "slug": "the-courage-to-try",
        "article_revision": 4,
        "status": "ready",
        "is_public": True,
    }
    query = FakeQuery(data=[updated])
    monkeypatch.setattr(wxpost_db, "supabase", FakeSupabase([query]))

    result = wxpost_db.finalize_workspace_publication(
        WXPOST_ID,
        workspace_id="wxpost-abc",
        expected_revision=3,
        expected_status="ready",
        next_revision=4,
        draft_version=6,
        draft_sha256="a" * 64,
        document=_document(),
    )

    assert result == updated
    assert query.filters == [
        ("id", str(WXPOST_ID)),
        ("source_workspace_id", "wxpost-abc"),
        ("article_revision", 3),
        ("status", "ready"),
    ]
    assert query.updated is not None
    assert query.updated["article_revision"] == 4
    assert query.updated["source_draft_version"] == 6
    assert query.updated["source_draft_sha256"] == "a" * 64
    assert query.updated["status"] == "ready"
    assert query.updated["is_public"] is True


def test_abandoned_public_assets_are_detected_for_cleanup_retry(monkeypatch) -> None:
    query = FakeQuery(data=[{"id": "asset-old"}])
    monkeypatch.setattr(wxpost_db, "supabase", FakeAnyTableSupabase([query]))

    assert wxpost_db.has_abandoned_wxpost_assets(WXPOST_ID) is True
    assert query.filters == [
        ("wxpost_id", str(WXPOST_ID)),
        ("status", "abandoned"),
    ]


def test_publication_deletion_hides_then_deletes_one_guarded_row(monkeypatch) -> None:
    hidden = {
        "id": str(WXPOST_ID),
        "article_revision": 4,
        "status": "assembling",
        "is_public": False,
    }
    hide_query = FakeQuery(data=[hidden])
    delete_query = FakeQuery(data=[hidden])
    monkeypatch.setattr(
        wxpost_db,
        "supabase",
        FakeSupabase([hide_query, delete_query]),
    )

    result = wxpost_db.begin_wxpost_deletion(
        WXPOST_ID,
        expected_revision=4,
    )
    wxpost_db.delete_hidden_wxpost(
        WXPOST_ID,
        expected_revision=4,
    )

    assert result == hidden
    assert hide_query.filters == [
        ("id", str(WXPOST_ID)),
        ("article_revision", 4),
        ("status", "ready"),
    ]
    assert hide_query.updated is not None
    assert hide_query.updated["status"] == "assembling"
    assert hide_query.updated["is_public"] is False
    assert delete_query.deleted is True
    assert delete_query.filters == [
        ("id", str(WXPOST_ID)),
        ("article_revision", 4),
        ("status", "assembling"),
    ]


def test_unreferenced_ready_assets_are_abandoned_and_deletable(monkeypatch) -> None:
    select_query = FakeQuery(
        data=[
            {
                "id": "asset-current",
                "content_sha256": "current",
                "status": "ready",
                "object_key": "current.jpg",
                "poster_object_key": None,
            },
            {
                "id": "asset-old",
                "content_sha256": "old",
                "status": "ready",
                "object_key": "old.jpg",
                "poster_object_key": None,
            },
        ]
    )
    abandon_query = FakeQuery(data=[])
    delete_query = FakeQuery(data=[{"id": "asset-old"}])
    monkeypatch.setattr(
        wxpost_db,
        "supabase",
        FakeAnyTableSupabase([select_query, abandon_query, delete_query]),
    )

    stale = wxpost_db.abandon_unreferenced_wxpost_assets(
        WXPOST_ID,
        keep_content_sha256={"current"},
    )
    wxpost_db.delete_wxpost_assets(["asset-old"])

    assert [asset["id"] for asset in stale] == ["asset-old"]
    assert ("status", ["pending", "ready", "failed", "abandoned"]) in select_query.filters
    assert abandon_query.updated is not None
    assert abandon_query.updated["status"] == "abandoned"
    assert abandon_query.filters == [("id", ["asset-old"])]
    assert delete_query.deleted is True
    assert delete_query.filters == [("id", ["asset-old"])]


def test_ready_asset_descriptor_lookup_is_scoped_to_one_public_wxpost(monkeypatch) -> None:
    rows = [
        {
            "id": "asset-image",
            "object_key": "public/wxposts/post/assets/image/original.jpg",
            "content_sha256": "a" * 64,
            "size_bytes": 123,
            "kind": "image",
        }
    ]
    query = FakeQuery(data=rows)
    variants_query = FakeQuery(data=[])
    monkeypatch.setattr(wxpost_db, "supabase", FakeAnyTableSupabase([query, variants_query]))

    assert wxpost_db.get_ready_wxpost_assets(WXPOST_ID) == [{**rows[0], "variants": []}]
    assert query.filters == [
        ("wxpost_id", str(WXPOST_ID)),
        ("status", "ready"),
    ]
    assert variants_query.filters == [
        ("asset_id", ["asset-image"]),
        ("status", ["ready"]),
    ]


def test_variant_retry_recovers_a_concurrent_pending_transition(monkeypatch) -> None:
    variant_id = UUID("00000000-0000-4000-8000-000000000998")
    update_query = FakeQuery(data=[])
    pending = {"id": str(variant_id), "status": "pending"}
    current_query = FakeQuery(data=[pending])
    monkeypatch.setattr(wxpost_db, "supabase", FakeAnyTableSupabase([update_query, current_query]))

    assert wxpost_db.retry_failed_wxpost_asset_variant(variant_id) == pending
    assert update_query.filters == [
        ("id", str(variant_id)),
        ("status", "failed"),
    ]
    assert current_query.filters == [("id", str(variant_id))]


def test_batch_publication_lookup_uses_one_query(monkeypatch) -> None:
    rows = [{"source_workspace_id": "wxpost-a"}]
    query = FakeQuery(data=rows)
    monkeypatch.setattr(wxpost_db, "supabase", FakeSupabase([query]))

    result = wxpost_db.get_wxposts_by_workspace_ids(["wxpost-a", "wxpost-b"])

    assert result == rows
    assert query.filters == [("source_workspace_id", ["wxpost-a", "wxpost-b"])]


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
