import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest

import app.services.wxpost_publication as publication
from app.db.wxpost import WxPostRevisionConflictError
from app.models.wxpost import WxPostPublicationSyncRequest
from app.services.wxpost_image_variants import ImageVariant

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000777")
ENSURE_WECHAT_BODY_VARIANT = publication._ensure_wechat_body_variant


@pytest.fixture(autouse=True)
def _avoid_public_asset_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "abandon_unreferenced_wxpost_assets",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(publication, "delete_wxpost_assets", lambda asset_ids: None)
    monkeypatch.setattr(
        publication,
        "has_abandoned_wxpost_assets",
        lambda wxpost_id: False,
    )
    monkeypatch.setattr(publication, "get_wxpost_asset_variants", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        publication,
        "get_ready_wxpost_asset",
        lambda wxpost_id, **kwargs: {
            "id": "00000000-0000-4000-8000-000000000999",
            "object_key": f"public/wxposts/{wxpost_id}/assets/test/original.jpg",
        },
    )
    monkeypatch.setattr(
        publication,
        "_ensure_wechat_body_variant",
        lambda asset, media: {"status": "ready", "profile": "wechat-body-v1"},
    )


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


def _context(*, manifest_version: int = 4, draft_version: int = 2) -> dict:
    return {
        "workspaceId": "wxpost-abc",
        "manifest": {
            "manifestVersion": manifest_version,
            "sources": [
                {
                    "id": "M01",
                    "kind": "image",
                    "filename": "round-table.jpg",
                    "mimeType": "image/jpeg",
                    "workspaceReady": True,
                }
            ],
        },
        "draft": {"draftVersion": draft_version, "document": _document()},
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


def _request(
    *,
    manifest_version: int = 4,
    draft_version: int = 2,
    public_revision: int | None = None,
) -> WxPostPublicationSyncRequest:
    return WxPostPublicationSyncRequest(
        expected_manifest_version=manifest_version,
        expected_draft_version=draft_version,
        expected_public_revision=public_revision,
    )


async def _load_context(workspace_id: str) -> dict:
    assert workspace_id == "wxpost-abc"
    return _context()


async def _load_source(workspace_id: str, source_id: str) -> tuple[bytes, str]:
    assert (workspace_id, source_id) == ("wxpost-abc", "M01")
    return b"public image bytes", "image/jpeg"


async def _compile(render_document: dict) -> str:
    assert render_document["media"][0]["sourceUrl"].startswith("https://public.example/")
    return "<article>compiled</article>"


def _bundle_hash() -> str:
    document = publication.ArticleDocument.model_validate(_document())
    resolved = [
        publication.ResolvedMedia(
            source_id="M01",
            kind="image",
            filename="round-table.jpg",
            mime_type="image/jpeg",
            content_path=publication.Path("unused"),
            size_bytes=len(b"public image bytes"),
            sha256=publication.hashlib.sha256(b"public image bytes").hexdigest(),
            md5="unused",
        )
    ]
    return publication._bundle_sha256(document, resolved)


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


@pytest.mark.asyncio
async def test_sync_rejects_a_stale_workspace_before_upload(monkeypatch) -> None:
    uploaded = False

    def upload(*args, **kwargs):
        nonlocal uploaded
        uploaded = True

    monkeypatch.setattr(publication, "_upload_asset", upload)

    with pytest.raises(publication.PublicationError) as raised:
        await publication.synchronize_workspace_publication(
            "wxpost-abc",
            _request(manifest_version=3),
            load_context=_load_context,
            load_source=_load_source,
            compile_render=_compile,
        )

    assert raised.value.code == "version_conflict"
    assert raised.value.status == 409
    assert uploaded is False


@pytest.mark.asyncio
async def test_sync_rejects_missing_saved_material(monkeypatch) -> None:
    context = _context()
    context["manifest"]["sources"][0]["workspaceReady"] = False

    async def load(workspace_id: str) -> dict:
        return context

    monkeypatch.setattr(publication, "get_wxpost_by_workspace_id", lambda workspace_id: None)
    with pytest.raises(publication.PublicationError) as raised:
        await publication.synchronize_workspace_publication(
            "wxpost-abc",
            _request(),
            load_context=load,
            load_source=_load_source,
            compile_render=_compile,
        )

    assert raised.value.code == "missing_publication_media"
    assert raised.value.status == 422


@pytest.mark.asyncio
async def test_public_revision_conflict_stops_before_media_download(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(revision=4),
    )
    downloaded = False

    async def load_source(
        workspace_id: str,
        source_id: str,
    ) -> tuple[bytes, str]:
        nonlocal downloaded
        downloaded = True
        return b"unused", "image/jpeg"

    with pytest.raises(publication.PublicationError) as raised:
        await publication.synchronize_workspace_publication(
            "wxpost-abc",
            _request(public_revision=3),
            load_context=_load_context,
            load_source=load_source,
            compile_render=_compile,
        )

    assert raised.value.code == "version_conflict"
    assert downloaded is False


@pytest.mark.asyncio
async def test_first_sync_rewrites_media_and_finalizes_once(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(publication, "get_wxpost_by_workspace_id", lambda workspace_id: None)
    monkeypatch.setattr(
        publication,
        "create_publication_shell",
        lambda **kwargs: _row(
            status="assembling",
            revision=1,
            draft_version=kwargs["draft_version"],
            draft_sha256=kwargs["draft_sha256"],
        ),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda wxpost_id, workspace_id, media: ("https://public.example/public/wxposts/asset.jpg"),
    )

    def finalize(wxpost_id, **kwargs):
        captured.update(kwargs)
        return _row(
            status="ready",
            revision=1,
            draft_sha256=kwargs["draft_sha256"],
        )

    monkeypatch.setattr(publication, "finalize_workspace_publication", finalize)

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.state == "up-to-date"
    assert result.public_revision == 1
    assert captured["expected_status"] == "assembling"
    assert captured["next_revision"] == 1
    assert captured["expected_revision"] == 1
    assert str(captured["document"].media[0].source_url) == ("https://public.example/public/wxposts/asset.jpg")
    assert len(captured["draft_sha256"]) == 64


@pytest.mark.asyncio
async def test_sync_spools_media_without_retaining_all_source_bytes(
    monkeypatch,
) -> None:
    context = _context()
    context["manifest"]["sources"].append(
        {
            "id": "M02",
            "kind": "image",
            "filename": "second.jpg",
            "mimeType": "image/jpeg",
            "workspaceReady": True,
        }
    )
    context["draft"]["document"]["media"].append(
        {
            "id": "M02",
            "kind": "image",
            "sourceUrl": "https://workspace.invalid/wxpost-abc/materials/M02",
            "description": "A second public image.",
            "include": True,
            "order": 1,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    )
    context["draft"]["document"]["bodyMarkdown"] += '\n\n:::image\n{"media": "M02"}\n:::'

    async def load_context(workspace_id: str) -> dict:
        return context

    source_bytes = {"M01": b"first image", "M02": b"second image"}

    async def load_source(workspace_id: str, source_id: str) -> tuple[bytes, str]:
        return source_bytes[source_id], "image/jpeg"

    spooled_paths: list[publication.Path] = []

    def upload(wxpost_id, workspace_id, media):
        assert not hasattr(media, "content")
        assert media.content_path.read_bytes() == source_bytes[media.source_id]
        spooled_paths.append(media.content_path)
        return f"https://public.example/{media.source_id}.jpg"

    monkeypatch.setattr(publication, "get_wxpost_by_workspace_id", lambda workspace_id: None)
    monkeypatch.setattr(
        publication,
        "create_publication_shell",
        lambda **kwargs: _row(
            status="assembling",
            revision=1,
            draft_version=kwargs["draft_version"],
            draft_sha256=kwargs["draft_sha256"],
        ),
    )
    monkeypatch.setattr(publication, "_upload_asset", upload)
    monkeypatch.setattr(
        publication,
        "finalize_workspace_publication",
        lambda *args, **kwargs: _row(
            revision=1,
            draft_version=kwargs["draft_version"],
            draft_sha256=kwargs["draft_sha256"],
        ),
    )

    await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(),
        load_context=load_context,
        load_source=load_source,
        compile_render=_compile,
    )

    assert len(spooled_paths) == 2
    assert all(not path.exists() for path in spooled_paths)


@pytest.mark.asyncio
async def test_sync_can_recover_a_publication_hidden_by_failed_deletion(monkeypatch) -> None:
    captured: dict = {}
    hidden = _row(status="assembling", revision=3, draft_sha256="b" * 64)
    hidden["finalize_request_hash"] = "previous-public-bundle"
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: hidden,
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: "https://public.example/public/wxposts/asset.jpg",
    )

    def finalize(wxpost_id, **kwargs):
        captured.update(kwargs)
        return _row(
            status="ready",
            revision=kwargs["next_revision"],
            draft_sha256=kwargs["draft_sha256"],
        )

    monkeypatch.setattr(publication, "finalize_workspace_publication", finalize)

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.state == "up-to-date"
    assert result.public_revision == 4
    assert captured["expected_status"] == "assembling"
    assert captured["next_revision"] == 4


@pytest.mark.asyncio
async def test_retry_of_same_publication_is_idempotent(monkeypatch) -> None:
    bundle_hash = _bundle_hash()
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(draft_sha256=bundle_hash),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: pytest.fail("idempotent retry uploaded an asset"),
    )

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(public_revision=3),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.state == "up-to-date"
    assert result.public_revision == 3


@pytest.mark.asyncio
async def test_retry_after_post_finalize_cleanup_failure_finishes_cleanup(
    monkeypatch,
) -> None:
    bundle_hash = _bundle_hash()
    cleanup_calls: list[set[str]] = []
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(revision=4, draft_sha256=bundle_hash),
    )
    monkeypatch.setattr(
        publication,
        "has_abandoned_wxpost_assets",
        lambda wxpost_id: True,
    )
    monkeypatch.setattr(
        publication,
        "_remove_unreferenced_assets",
        lambda wxpost_id, *, keep_content_sha256: cleanup_calls.append(keep_content_sha256),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: pytest.fail("cleanup retry uploaded an asset"),
    )

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(public_revision=3),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.state == "up-to-date"
    assert result.public_revision == 4
    assert cleanup_calls == [{hashlib.sha256(b"public image bytes").hexdigest()}]


@pytest.mark.asyncio
async def test_concurrent_first_sync_reuses_completed_publication(
    monkeypatch,
) -> None:
    bundle_hash = _bundle_hash()
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: None,
    )
    monkeypatch.setattr(
        publication,
        "create_publication_shell",
        lambda **kwargs: _row(
            status="ready",
            revision=1,
            draft_sha256=bundle_hash,
        ),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: pytest.fail("concurrent retry uploaded an asset"),
    )
    monkeypatch.setattr(
        publication,
        "finalize_workspace_publication",
        lambda *args, **kwargs: pytest.fail("concurrent retry finalized twice"),
    )

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.state == "up-to-date"
    assert result.public_revision == 1


@pytest.mark.asyncio
async def test_new_draft_version_with_same_bundle_still_completes_update(
    monkeypatch,
) -> None:
    bundle_hash = _bundle_hash()
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(draft_sha256=bundle_hash),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: "https://public.example/asset.jpg",
    )
    captured: dict = {}

    def finalize(wxpost_id, **kwargs):
        captured.update(kwargs)
        return _row(
            revision=4,
            draft_version=3,
            draft_sha256=kwargs["draft_sha256"],
        )

    monkeypatch.setattr(publication, "finalize_workspace_publication", finalize)

    async def load_newer_context(workspace_id: str) -> dict:
        return _context(draft_version=3)

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(draft_version=3, public_revision=3),
        load_context=load_newer_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert captured["draft_version"] == 3
    assert captured["expected_revision"] == 3
    assert result.state == "up-to-date"
    assert result.public_revision == 4


@pytest.mark.asyncio
async def test_finalize_conflict_is_reported_without_replacing_public_row(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(draft_sha256="b" * 64),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: "https://public.example/asset.jpg",
    )
    monkeypatch.setattr(
        publication,
        "finalize_workspace_publication",
        lambda *args, **kwargs: (_ for _ in ()).throw(WxPostRevisionConflictError()),
    )

    with pytest.raises(publication.PublicationError) as raised:
        await publication.synchronize_workspace_publication(
            "wxpost-abc",
            _request(public_revision=3),
            load_context=_load_context,
            load_source=_load_source,
            compile_render=_compile,
        )

    assert raised.value.code == "version_conflict"
    assert raised.value.status == 409


@pytest.mark.asyncio
async def test_identical_concurrent_finalize_returns_completed_revision(
    monkeypatch,
) -> None:
    bundle_hash = _bundle_hash()
    rows = iter(
        [
            _row(status="assembling", revision=1, draft_sha256=bundle_hash),
            _row(status="ready", revision=1, draft_sha256=bundle_hash),
        ]
    )
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: next(rows),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: "https://public.example/asset.jpg",
    )
    monkeypatch.setattr(
        publication,
        "finalize_workspace_publication",
        lambda *args, **kwargs: (_ for _ in ()).throw(WxPostRevisionConflictError()),
    )

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.state == "up-to-date"
    assert result.public_revision == 1


@pytest.mark.asyncio
async def test_same_public_revision_reconciles_variant_without_new_revision_or_original_upload(
    monkeypatch,
) -> None:
    bundle_hash = _bundle_hash()
    reconciled: list[str] = []
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(revision=6, draft_sha256=bundle_hash),
    )
    monkeypatch.setattr(
        publication,
        "_upload_asset",
        lambda *args, **kwargs: pytest.fail("same revision uploaded its original again"),
    )
    monkeypatch.setattr(
        publication,
        "_ensure_wechat_body_variant",
        lambda asset, media: reconciled.append(media.source_id),
    )

    result = await publication.synchronize_workspace_publication(
        "wxpost-abc",
        _request(public_revision=6),
        load_context=_load_context,
        load_source=_load_source,
        compile_render=_compile,
    )

    assert result.public_revision == 6
    assert reconciled == ["M01"]


def test_variant_upload_is_idempotent_and_records_actual_descriptor(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    rendered = ImageVariant(
        content=b"encoded",
        mime_type="image/jpeg",
        extension="jpg",
        size_bytes=7,
        sha256=hashlib.sha256(b"encoded").hexdigest(),
    )
    created: list[dict] = []
    uploaded: list[tuple[str, bytes, dict]] = []
    ready: list[tuple[UUID, str]] = []
    stored: list[dict] = []
    monkeypatch.setattr(
        publication,
        "get_wxpost_asset_variant",
        lambda *args, **kwargs: stored[0] if stored else None,
    )
    monkeypatch.setattr(publication, "render_wechat_body_variant", lambda *args, **kwargs: rendered)

    def create(values):
        created.append(values)
        return {**values, "status": "pending"}

    monkeypatch.setattr(publication, "create_pending_wxpost_asset_variant", create)
    monkeypatch.setattr(publication.oss2, "Auth", lambda *args: object())

    class Bucket:
        def put_object(self, key, content, headers):
            uploaded.append((key, content, headers))
            return type("Result", (), {"etag": "variant-etag"})()

    monkeypatch.setattr(publication.oss2, "Bucket", lambda *args: Bucket())

    def mark_ready(variant_id, *, etag):
        ready.append((variant_id, etag))
        result = {**created[0], "status": "ready", "etag": etag}
        stored.append(result)
        return result

    monkeypatch.setattr(publication, "mark_wxpost_asset_variant_ready", mark_ready)
    asset_id = UUID("00000000-0000-4000-8000-000000000998")
    asset = {
        "id": str(asset_id),
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/{asset_id}/original.jpg",
    }
    media = publication.ResolvedMedia(
        source_id="M01",
        kind="image",
        filename="poster.jpg",
        mime_type="image/jpeg",
        content_path=source,
        size_bytes=6,
        sha256=hashlib.sha256(b"source").hexdigest(),
        md5="unused",
    )

    first = ENSURE_WECHAT_BODY_VARIANT(asset, media)
    second = ENSURE_WECHAT_BODY_VARIANT(asset, media)

    assert first == second
    assert first["status"] == "ready"
    assert created[0]["content_sha256"] == rendered.sha256
    assert created[0]["object_key"].endswith("/variants/wechat-body-v1.jpg")
    assert uploaded == [
        (
            created[0]["object_key"],
            b"encoded",
            {"Content-Type": "image/jpeg"},
        )
    ]
    assert ready == [(UUID(created[0]["id"]), "variant-etag")]


def test_variant_upload_failure_is_recorded_for_safe_retry(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    rendered = ImageVariant(
        content=b"encoded",
        mime_type="image/jpeg",
        extension="jpg",
        size_bytes=7,
        sha256=hashlib.sha256(b"encoded").hexdigest(),
    )
    variant_id = UUID("00000000-0000-4000-8000-000000000997")
    failed: list[UUID] = []
    monkeypatch.setattr(publication, "get_wxpost_asset_variant", lambda *args, **kwargs: None)
    monkeypatch.setattr(publication, "render_wechat_body_variant", lambda *args, **kwargs: rendered)
    monkeypatch.setattr(
        publication,
        "create_pending_wxpost_asset_variant",
        lambda values: {**values, "id": str(variant_id), "status": "pending"},
    )
    monkeypatch.setattr(publication, "mark_wxpost_asset_variant_failed", failed.append)
    monkeypatch.setattr(publication.oss2, "Auth", lambda *args: object())

    class Bucket:
        def put_object(self, *args, **kwargs):
            raise OSError("OSS unavailable")

    monkeypatch.setattr(publication.oss2, "Bucket", lambda *args: Bucket())
    asset = {
        "id": "00000000-0000-4000-8000-000000000998",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/source/original.jpg",
    }
    media = publication.ResolvedMedia(
        source_id="M01",
        kind="image",
        filename="poster.jpg",
        mime_type="image/jpeg",
        content_path=source,
        size_bytes=6,
        sha256=hashlib.sha256(b"source").hexdigest(),
        md5="unused",
    )

    with pytest.raises(publication.PublicationError) as raised:
        ENSURE_WECHAT_BODY_VARIANT(asset, media)

    assert raised.value.code == "asset_variant_upload_failed"
    assert failed == [variant_id]


def test_variant_retry_returns_concurrent_ready_result_without_reupload(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    variant_id = UUID("00000000-0000-4000-8000-000000000996")
    failed = {"id": str(variant_id), "status": "failed"}
    ready = {"id": str(variant_id), "status": "ready"}
    monkeypatch.setattr(publication, "get_wxpost_asset_variant", lambda *args, **kwargs: failed)
    monkeypatch.setattr(
        publication,
        "render_wechat_body_variant",
        lambda *args, **kwargs: ImageVariant(
            content=b"encoded",
            mime_type="image/jpeg",
            extension="jpg",
            size_bytes=7,
            sha256=hashlib.sha256(b"encoded").hexdigest(),
        ),
    )
    monkeypatch.setattr(publication, "create_pending_wxpost_asset_variant", lambda values: failed)
    monkeypatch.setattr(publication, "retry_failed_wxpost_asset_variant", lambda found_id: ready)
    monkeypatch.setattr(
        publication.oss2,
        "Auth",
        lambda *args: pytest.fail("ready variant was uploaded again"),
    )

    result = ENSURE_WECHAT_BODY_VARIANT(
        {
            "id": "00000000-0000-4000-8000-000000000998",
            "object_key": f"public/wxposts/{WXPOST_ID}/assets/source/original.jpg",
        },
        publication.ResolvedMedia(
            source_id="M01",
            kind="image",
            filename="poster.jpg",
            mime_type="image/jpeg",
            content_path=source,
            size_bytes=6,
            sha256=hashlib.sha256(b"source").hexdigest(),
            md5="unused",
        ),
    )

    assert result == ready


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


def test_backfill_creates_missing_variant_without_changing_public_revision(monkeypatch, tmp_path) -> None:
    source_content = b"immutable-public-original"
    source_sha = hashlib.sha256(source_content).hexdigest()
    source_asset = {
        "id": "00000000-0000-4000-8000-000000000996",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/source/original.jpg",
        "original_filename": "poster.jpg",
        "mime_type": "image/jpeg",
        "content_sha256": source_sha,
        "size_bytes": len(source_content),
        "source_metadata": {"sourceId": "M01"},
        "variants": [],
    }
    row = _row(revision=6)
    document = publication.ArticleDocument.model_validate(_document())
    ensured: list[tuple[dict, publication.ResolvedMedia]] = []
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: row)
    monkeypatch.setattr(publication, "article_document_from_row", lambda found: document)
    monkeypatch.setattr(publication, "get_ready_wxpost_assets", lambda wxpost_id: [source_asset])
    monkeypatch.setattr(publication.oss2, "Auth", lambda *args: object())

    class Bucket:
        def get_object_to_file(self, key, path):
            assert key == source_asset["object_key"]
            publication.Path(path).write_bytes(source_content)

    monkeypatch.setattr(publication.oss2, "Bucket", lambda *args: Bucket())
    monkeypatch.setattr(
        publication,
        "_ensure_wechat_body_variant",
        lambda asset, media: ensured.append((asset, media)),
    )

    report = publication.reconcile_publication_wechat_variants(WXPOST_ID)

    assert report == {
        "wxpostId": str(WXPOST_ID),
        "revision": 6,
        "profile": "wechat-body-v1",
        "missing": ["M01"],
        "created": ["M01"],
        "dryRun": False,
    }
    assert ensured[0][0] == source_asset
    assert ensured[0][1].sha256 == source_sha
    assert row["article_revision"] == 6


def test_backfill_reuses_one_public_asset_for_multiple_media_ids(monkeypatch) -> None:
    source_content = b"shared-immutable-public-original"
    source_sha = hashlib.sha256(source_content).hexdigest()
    object_key = f"public/wxposts/{WXPOST_ID}/assets/shared/original.jpg"
    source_asset = {
        "id": "00000000-0000-4000-8000-000000000995",
        "object_key": object_key,
        "original_filename": "shared.jpg",
        "mime_type": "image/jpeg",
        "content_sha256": source_sha,
        "size_bytes": len(source_content),
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
    downloads: list[str] = []
    ensured: list[str] = []
    monkeypatch.setattr(publication, "get_wxpost_by_id", lambda wxpost_id: _row(revision=6))
    monkeypatch.setattr(publication, "article_document_from_row", lambda found: document)
    monkeypatch.setattr(publication, "get_ready_wxpost_assets", lambda wxpost_id: [source_asset])
    monkeypatch.setattr(publication.oss2, "Auth", lambda *args: object())

    class Bucket:
        def get_object_to_file(self, key, path):
            downloads.append(key)
            publication.Path(path).write_bytes(source_content)

    monkeypatch.setattr(publication.oss2, "Bucket", lambda *args: Bucket())
    monkeypatch.setattr(
        publication,
        "_ensure_wechat_body_variant",
        lambda asset, media: ensured.append(media.source_id),
    )

    report = publication.reconcile_publication_wechat_variants(WXPOST_ID)

    assert report["missing"] == ["M01", "M02"]
    assert report["created"] == ["M01", "M02"]
    assert downloads == [source_asset["object_key"]]
    assert ensured == ["M01"]


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
