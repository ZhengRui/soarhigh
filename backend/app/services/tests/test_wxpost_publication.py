import base64
import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest

import app.services.wxpost_publication as publication
from app.services.wxpost_oss_ops import OssOpsError, VariantObject

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000777")
WORKSPACE_ID = "wxpost-abc"


def _document() -> dict:
    return {
        "schemaVersion": 1,
        "title": "A Public Field Note",
        "excerpt": "One saved Draft becomes one public revision.",
        "byline": "SoarHigh editorial team",
        "articleType": "custom",
        "customArticleType": "Field Note",
        "sourceMeetingId": None,
        "media": [
            {
                "id": "M01",
                "kind": "image",
                "sourceUrl": "https://workspace.invalid/wxpost-abc/materials/M01",
                "description": "Members sharing ideas around a table.",
                "include": True,
                "order": 0,
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
        "coverMediaId": "M01",
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
        "bodyMarkdown": ':::image\n{"media": "M01"}\n:::',
    }


def _row(
    *,
    status: str = "ready",
    revision: int = 3,
    draft_version: int = 2,
    draft_sha256: str = "a" * 64,
) -> dict:
    return {
        "id": str(WXPOST_ID),
        "slug": "a-public-field-note",
        "status": status,
        "is_public": status == "ready",
        "article_revision": revision,
        "source_workspace_id": "wxpost-abc",
        "source_draft_version": draft_version,
        "source_draft_sha256": draft_sha256,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def test_publication_status_is_derived_from_saved_draft_version(monkeypatch) -> None:
    monkeypatch.setattr(
        publication,
        "WXPOST_PUBLIC_BASE_URL",
        "https://soarhigh.example",
    )
    not_synced = publication.publication_status("wxpost-abc", current_draft_version=2, row=None)
    current = publication.publication_status("wxpost-abc", current_draft_version=2, row=_row())
    stale = publication.publication_status("wxpost-abc", current_draft_version=4, row=_row())

    assert not_synced.state == "not-synced"
    assert current.state == "up-to-date"
    assert current.public_url == ("https://soarhigh.example/posts/wxposts/a-public-field-note")
    assert stale.state == "update-available"


def test_unused_ready_assets_are_deleted_from_oss_and_database(
    monkeypatch,
) -> None:
    stale = [
        {
            "id": "asset-old",
            "object_key": "public/wxposts/old/original.jpg",
            "poster_object_key": None,
        }
    ]
    deleted_objects: list[list[str]] = []
    deleted_rows: list[str] = []

    monkeypatch.setattr(
        publication,
        "abandon_unreferenced_wxpost_assets",
        lambda *args, **kwargs: stale,
    )
    monkeypatch.setattr(
        publication,
        "_delete_asset_objects",
        lambda assets: deleted_objects.append([asset["object_key"] for asset in assets]),
    )
    monkeypatch.setattr(
        publication,
        "delete_wxpost_assets",
        lambda asset_ids: deleted_rows.extend(asset_ids),
    )

    publication._remove_unreferenced_assets(
        WXPOST_ID,
        keep_content_sha256={"current"},
    )

    assert deleted_objects == [["public/wxposts/old/original.jpg"]]
    assert deleted_rows == ["asset-old"]


def test_asset_object_cleanup_includes_variants_before_database_cascade(monkeypatch) -> None:
    deleted: list[list[str]] = []
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_variants",
        lambda *args, **kwargs: [
            {
                "asset_id": "asset-old",
                "object_key": "public/wxposts/post/assets/asset-old/variants/wechat-body-v1.jpg",
            }
        ],
    )
    monkeypatch.setattr(publication.oss2, "Auth", lambda *args: object())

    class Bucket:
        def batch_delete_objects(self, keys):
            deleted.append(keys)

    monkeypatch.setattr(publication.oss2, "Bucket", lambda *args: Bucket())

    publication._delete_asset_objects(
        [
            {
                "id": "asset-old",
                "object_key": "public/wxposts/post/assets/asset-old/original.jpg",
                "poster_object_key": None,
            }
        ]
    )

    assert deleted == [
        [
            "public/wxposts/post/assets/asset-old/original.jpg",
            "public/wxposts/post/assets/asset-old/variants/wechat-body-v1.jpg",
        ]
    ]


def test_asset_cleanup_failure_keeps_database_rows_for_retry(monkeypatch) -> None:
    stale = [{"id": "asset-old", "object_key": "old.jpg", "poster_object_key": None}]
    deleted_rows: list[str] = []
    monkeypatch.setattr(publication, "abandon_unreferenced_wxpost_assets", lambda *args, **kwargs: stale)
    monkeypatch.setattr(
        publication,
        "_delete_asset_objects",
        lambda assets: (_ for _ in ()).throw(OSError("OSS unavailable")),
    )
    monkeypatch.setattr(publication, "delete_wxpost_assets", lambda ids: deleted_rows.extend(ids))

    with pytest.raises(OSError, match="OSS unavailable"):
        publication._remove_unreferenced_assets(WXPOST_ID, keep_content_sha256=set())

    assert deleted_rows == []


def _rendered_variant(object_key: str) -> VariantObject:
    content = b"wechat-variant-bytes"
    return VariantObject(
        object_key=object_key,
        mime_type="image/jpeg",
        extension="jpg",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
    )


@pytest.mark.asyncio
async def test_backfill_creates_missing_variant_via_oss_server_side_ladder(monkeypatch) -> None:
    source_sha = hashlib.sha256(b"immutable-public-original").hexdigest()
    source_asset = {
        "id": "00000000-0000-4000-8000-000000000996",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/source/original.jpg",
        "original_filename": "poster.jpg",
        "mime_type": "image/jpeg",
        "content_sha256": source_sha,
        "size_bytes": 26,
        "source_metadata": {"sourceId": "M01"},
        "variants": [],
    }
    row = _row(revision=6)
    document = publication.ArticleDocument.model_validate(_document())
    generated: list[tuple[str, str, str]] = []
    created: list[dict] = []
    ready: list[tuple[UUID, str]] = []

    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: row)
    monkeypatch.setattr(publication, "article_document_from_row", lambda found: document)
    monkeypatch.setattr(publication, "get_ready_wxpost_assets", lambda wxpost_id: [source_asset])
    monkeypatch.setattr(publication, "get_wxpost_asset_variant", lambda *args, **kwargs: None)

    variant_object_key = f"public/wxposts/{WXPOST_ID}/assets/source/variants/wechat-body-v1.jpg"

    def generate(source_key, target_directory, *, mime_type):
        generated.append((source_key, target_directory, mime_type))
        return _rendered_variant(variant_object_key)

    monkeypatch.setattr(publication, "generate_wechat_variant", generate)

    def create(values):
        created.append(values)
        return {**values, "status": "pending"}

    monkeypatch.setattr(publication, "create_pending_wxpost_asset_variant", create)

    def mark_ready(variant_id, *, etag):
        ready.append((variant_id, etag))
        return {**created[0], "status": "ready"}

    monkeypatch.setattr(publication, "mark_wxpost_asset_variant_ready", mark_ready)

    report = await publication.reconcile_publication_wechat_variants(WXPOST_ID)

    assert report == {
        "wxpostId": str(WXPOST_ID),
        "revision": 6,
        "profile": "wechat-body-v1",
        "missing": ["M01"],
        "created": ["M01"],
        "dryRun": False,
    }
    assert generated == [(source_asset["object_key"], f"public/wxposts/{WXPOST_ID}/assets/source", "image/jpeg")]
    assert created[0]["object_key"] == variant_object_key
    assert ready == [(UUID(created[0]["id"]), hashlib.md5(b"wechat-variant-bytes").hexdigest().upper())]


@pytest.mark.asyncio
async def test_backfill_reuses_one_public_asset_for_multiple_media_ids(monkeypatch) -> None:
    source_sha = hashlib.sha256(b"shared-immutable-public-original").hexdigest()
    object_key = f"public/wxposts/{WXPOST_ID}/assets/shared/original.jpg"
    source_asset = {
        "id": "00000000-0000-4000-8000-000000000995",
        "object_key": object_key,
        "original_filename": "shared.jpg",
        "mime_type": "image/jpeg",
        "content_sha256": source_sha,
        "size_bytes": 33,
        "source_metadata": {"sourceId": "M01"},
        "variants": [],
    }
    public_url = publication.public_asset_url(object_key)
    document_values = _document()
    document_values["media"][0]["sourceUrl"] = public_url
    document_values["media"].append(
        {
            **document_values["media"][0],
            "id": "M02",
            "order": 1,
            "sourceUrl": public_url,
        }
    )
    document_values["bodyMarkdown"] += '\n\n:::image\n{"media": "M02"}\n:::'
    document = publication.ArticleDocument.model_validate(document_values)
    generated: list[str] = []

    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row(revision=6))
    monkeypatch.setattr(publication, "article_document_from_row", lambda found: document)
    monkeypatch.setattr(publication, "get_ready_wxpost_assets", lambda wxpost_id: [source_asset])
    monkeypatch.setattr(publication, "get_wxpost_asset_variant", lambda *args, **kwargs: None)

    def generate(source_key, target_directory, *, mime_type):
        generated.append(source_key)
        return _rendered_variant(f"{target_directory}/variants/wechat-body-v1.jpg")

    monkeypatch.setattr(publication, "generate_wechat_variant", generate)
    monkeypatch.setattr(
        publication,
        "create_pending_wxpost_asset_variant",
        lambda values: {**values, "status": "pending"},
    )
    monkeypatch.setattr(
        publication,
        "mark_wxpost_asset_variant_ready",
        lambda variant_id, *, etag: {"id": str(variant_id), "status": "ready"},
    )

    report = await publication.reconcile_publication_wechat_variants(WXPOST_ID)

    assert report["missing"] == ["M01", "M02"]
    assert report["created"] == ["M01", "M02"]
    # Both media ids resolve to the same ready asset, so the OSS ladder runs once.
    assert generated == [source_asset["object_key"]]


@pytest.mark.asyncio
async def test_backfill_variant_generation_failure_maps_to_publication_error(monkeypatch) -> None:
    source_sha = hashlib.sha256(b"immutable-public-original").hexdigest()
    source_asset = {
        "id": "00000000-0000-4000-8000-000000000994",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/source/original.jpg",
        "original_filename": "poster.jpg",
        "mime_type": "image/jpeg",
        "content_sha256": source_sha,
        "size_bytes": 26,
        "source_metadata": {"sourceId": "M01"},
        "variants": [],
    }
    document = publication.ArticleDocument.model_validate(_document())

    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row(revision=6))
    monkeypatch.setattr(publication, "article_document_from_row", lambda found: document)
    monkeypatch.setattr(publication, "get_ready_wxpost_assets", lambda wxpost_id: [source_asset])
    monkeypatch.setattr(publication, "get_wxpost_asset_variant", lambda *args, **kwargs: None)

    def generate(source_key, target_directory, *, mime_type):
        raise OssOpsError("asset_unavailable", "OSS unavailable")

    monkeypatch.setattr(publication, "generate_wechat_variant", generate)

    with pytest.raises(publication.PublicationError) as raised:
        await publication.reconcile_publication_wechat_variants(WXPOST_ID)

    assert raised.value.code == "asset_unavailable"
    assert raised.value.status == 503


@pytest.mark.asyncio
async def test_backfill_dry_run_reports_missing_without_generating(monkeypatch) -> None:
    source_sha = hashlib.sha256(b"immutable-public-original").hexdigest()
    source_asset = {
        "id": "00000000-0000-4000-8000-000000000993",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/source/original.jpg",
        "original_filename": "poster.jpg",
        "mime_type": "image/jpeg",
        "content_sha256": source_sha,
        "size_bytes": 26,
        "source_metadata": {"sourceId": "M01"},
        "variants": [],
    }
    document = publication.ArticleDocument.model_validate(_document())

    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row(revision=6))
    monkeypatch.setattr(publication, "article_document_from_row", lambda found: document)
    monkeypatch.setattr(publication, "get_ready_wxpost_assets", lambda wxpost_id: [source_asset])
    monkeypatch.setattr(
        publication,
        "generate_wechat_variant",
        lambda *args, **kwargs: pytest.fail("dry run generated a variant"),
    )

    report = await publication.reconcile_publication_wechat_variants(WXPOST_ID, dry_run=True)

    assert report["missing"] == ["M01"]
    assert report["created"] == []
    assert report["dryRun"] is True


@pytest.mark.asyncio
async def test_public_delete_hides_row_before_removing_assets(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def begin_deletion(*args, **kwargs) -> dict[str, str]:
        calls.append("hide")
        return {
            "id": str(WXPOST_ID),
            "source_workspace_id": "wxpost-abc",
        }

    monkeypatch.setattr(
        publication,
        "begin_wxpost_deletion",
        begin_deletion,
    )
    monkeypatch.setattr(
        publication,
        "_remove_unreferenced_assets",
        lambda *args, **kwargs: calls.append("assets"),
    )
    monkeypatch.setattr(
        publication,
        "delete_hidden_wxpost",
        lambda *args, **kwargs: calls.append("row"),
    )

    workspace_id = await publication.delete_public_wxpost(
        WXPOST_ID,
        expected_revision=3,
    )

    assert workspace_id == "wxpost-abc"
    assert calls == ["hide", "assets", "row"]


UPLOAD_ITEM = publication.WxPostPublicationSubmitItem(
    source_id="M02",
    kind="image",
    filename="second.jpg",
    mime_type="image/jpeg",
    size_bytes=19,
    content_sha256=hashlib.sha256(b"second image bytes").hexdigest(),
    origin="upload",
    meeting_file_key=None,
    needs_wechat_variant=False,
)
UPLOAD_MD5_HEX = hashlib.md5(b"second image bytes").hexdigest()
UPLOAD_CONTENT_MD5 = base64.b64encode(bytes.fromhex(UPLOAD_MD5_HEX)).decode()


def _pending_upload_row() -> dict:
    return {
        "id": "22222222-2222-4222-8222-222222222222",
        "status": "pending",
        "object_key": "public/wxposts/x/assets/y/original.jpg",
        "content_md5": UPLOAD_CONTENT_MD5,
    }


def _expected_idempotency_hash() -> str:
    idempotency_source = f"{WORKSPACE_ID}:{UPLOAD_ITEM.source_id}:{UPLOAD_ITEM.content_sha256}"
    return hashlib.sha256(idempotency_source.encode()).hexdigest()


@pytest.mark.asyncio
async def test_upload_item_verifies_and_marks_ready(monkeypatch) -> None:
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)

    lookups: list[tuple[UUID, str]] = []

    def fake_lookup(wxpost_id: UUID, idempotency_key_hash: str) -> dict:
        lookups.append((wxpost_id, idempotency_key_hash))
        return _pending_upload_row()

    monkeypatch.setattr(publication, "get_wxpost_asset_by_idempotency_hash", fake_lookup)
    monkeypatch.setattr(publication, "head_public_object", lambda key: (19, UPLOAD_MD5_HEX.upper()))

    marked_ready: list[tuple[UUID, str]] = []

    def fake_mark_ready(asset_id: UUID, *, etag: str) -> dict:
        marked_ready.append((asset_id, etag))
        return {**_pending_upload_row(), "status": "ready"}

    monkeypatch.setattr(publication, "mark_wxpost_asset_ready", fake_mark_ready)

    result = await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert result["public_url"] == publication.public_asset_url(_pending_upload_row()["object_key"])
    assert marked_ready == [(UUID(_pending_upload_row()["id"]), UPLOAD_MD5_HEX.upper())]
    assert lookups == [(WXPOST_ID, _expected_idempotency_hash())]


@pytest.mark.asyncio
async def test_upload_item_without_row_is_upload_not_prepared(monkeypatch) -> None:
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(publication, "get_wxpost_asset_by_idempotency_hash", lambda *args, **kwargs: None)

    with pytest.raises(publication.PublicationError) as raised:
        await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert raised.value.code == "upload_not_prepared"
    assert raised.value.status == 422


@pytest.mark.asyncio
async def test_upload_item_missing_object_is_upload_missing(monkeypatch) -> None:
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_by_idempotency_hash",
        lambda *args, **kwargs: _pending_upload_row(),
    )

    def fake_head(key: str) -> tuple[int, str]:
        raise OssOpsError("asset_missing", "gone")

    monkeypatch.setattr(publication, "head_public_object", fake_head)
    monkeypatch.setattr(
        publication,
        "mark_wxpost_asset_failed",
        lambda *args, **kwargs: pytest.fail("upload_missing still marked the asset failed"),
    )

    with pytest.raises(publication.PublicationError) as raised:
        await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert raised.value.code == "upload_missing"
    assert raised.value.status == 422


@pytest.mark.asyncio
async def test_upload_item_etag_mismatch_is_asset_changed(monkeypatch) -> None:
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_by_idempotency_hash",
        lambda *args, **kwargs: _pending_upload_row(),
    )
    monkeypatch.setattr(publication, "head_public_object", lambda key: (19, "AB" * 16))

    failed: list[UUID] = []
    monkeypatch.setattr(publication, "mark_wxpost_asset_failed", lambda asset_id: failed.append(asset_id))

    with pytest.raises(publication.PublicationError) as raised:
        await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert raised.value.code == "asset_changed"
    assert raised.value.status == 409
    assert failed == [UUID(_pending_upload_row()["id"])]


@pytest.mark.asyncio
async def test_upload_item_size_mismatch_is_asset_changed(monkeypatch) -> None:
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_by_idempotency_hash",
        lambda *args, **kwargs: _pending_upload_row(),
    )
    monkeypatch.setattr(publication, "head_public_object", lambda key: (20, UPLOAD_MD5_HEX.upper()))

    failed: list[UUID] = []
    monkeypatch.setattr(publication, "mark_wxpost_asset_failed", lambda asset_id: failed.append(asset_id))

    with pytest.raises(publication.PublicationError) as raised:
        await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert raised.value.code == "asset_changed"
    assert raised.value.status == 409
    assert failed == [UUID(_pending_upload_row()["id"])]


@pytest.mark.asyncio
async def test_upload_item_malformed_content_md5_is_asset_changed(monkeypatch) -> None:
    """A row whose stored content_md5 is not valid base64 (which should never
    happen, but the OSS-returned etag is untrusted input to decode against)
    must fail closed exactly like an etag mismatch, not raise an unhandled
    binascii/ValueError out of the publication pipeline."""

    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_by_idempotency_hash",
        lambda *args, **kwargs: {**_pending_upload_row(), "content_md5": "AB!"},
    )
    monkeypatch.setattr(publication, "head_public_object", lambda key: (19, UPLOAD_MD5_HEX.upper()))

    failed: list[UUID] = []
    monkeypatch.setattr(publication, "mark_wxpost_asset_failed", lambda asset_id: failed.append(asset_id))

    with pytest.raises(publication.PublicationError) as raised:
        await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert raised.value.code == "asset_changed"
    assert raised.value.status == 409
    assert failed == [UUID(_pending_upload_row()["id"])]


@pytest.mark.asyncio
async def test_upload_item_ready_row_short_circuits(monkeypatch) -> None:
    ready_row = {**_pending_upload_row(), "status": "ready"}
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(publication, "get_wxpost_asset_by_idempotency_hash", lambda *args, **kwargs: ready_row)
    monkeypatch.setattr(
        publication,
        "head_public_object",
        lambda *args, **kwargs: pytest.fail("ready row short-circuit still called head"),
    )

    result = await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert result["public_url"] == publication.public_asset_url(ready_row["object_key"])


@pytest.mark.asyncio
async def test_upload_item_inactive_row_is_retried(monkeypatch) -> None:
    failed_row = {**_pending_upload_row(), "status": "failed"}
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)
    monkeypatch.setattr(publication, "get_wxpost_asset_by_idempotency_hash", lambda *args, **kwargs: failed_row)

    retried: list[UUID] = []

    def fake_retry(asset_id: UUID) -> dict:
        retried.append(asset_id)
        return _pending_upload_row()

    monkeypatch.setattr(publication, "retry_inactive_wxpost_asset", fake_retry)
    monkeypatch.setattr(publication, "head_public_object", lambda key: (19, UPLOAD_MD5_HEX.upper()))

    marked_ready: list[tuple[UUID, str]] = []

    def fake_mark_ready(asset_id: UUID, *, etag: str) -> dict:
        marked_ready.append((asset_id, etag))
        return {**_pending_upload_row(), "status": "ready"}

    monkeypatch.setattr(publication, "mark_wxpost_asset_ready", fake_mark_ready)

    result = await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert retried == [UUID(failed_row["id"])]
    assert marked_ready == [(UUID(_pending_upload_row()["id"]), UPLOAD_MD5_HEX.upper())]
    assert result["public_url"] == publication.public_asset_url(_pending_upload_row()["object_key"])


@pytest.mark.asyncio
async def test_upload_item_does_not_use_the_ready_by_sha_shortcut_for_a_pending_row(monkeypatch) -> None:
    """An upload item's own presign-created row may still be pending even
    though another asset with the same content sha is already ready (two
    materials sharing identical bytes). The ready-by-sha shortcut must never
    be consulted for upload items -- it would return the other asset and
    strand this item's own pending row forever, and finalize blocks while
    pending rows exist. Verify the full head-then-ready path runs instead."""

    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row())
    monkeypatch.setattr(
        publication,
        "get_ready_wxpost_asset",
        lambda *args, **kwargs: pytest.fail("upload item dispatch consulted the ready-by-sha shortcut"),
    )
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_by_idempotency_hash",
        lambda *args, **kwargs: _pending_upload_row(),
    )

    headed: list[str] = []

    def fake_head(key: str) -> tuple[int, str]:
        headed.append(key)
        return 19, UPLOAD_MD5_HEX.upper()

    monkeypatch.setattr(publication, "head_public_object", fake_head)

    marked_ready: list[tuple[UUID, str]] = []

    def fake_mark_ready(asset_id: UUID, *, etag: str) -> dict:
        marked_ready.append((asset_id, etag))
        return {**_pending_upload_row(), "status": "ready"}

    monkeypatch.setattr(publication, "mark_wxpost_asset_ready", fake_mark_ready)

    result = await publication.ensure_publication_asset(WORKSPACE_ID, WXPOST_ID, UPLOAD_ITEM)

    assert headed == [_pending_upload_row()["object_key"]]
    assert marked_ready == [(UUID(_pending_upload_row()["id"]), UPLOAD_MD5_HEX.upper())]
    assert result["public_url"] == publication.public_asset_url(_pending_upload_row()["object_key"])
