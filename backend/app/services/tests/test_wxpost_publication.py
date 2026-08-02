import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest

import app.services.wxpost_publication as publication
from app.db.wxpost import WxPostRevisionConflictError
from app.models.wxpost import WxPostPublicationSyncRequest

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000777")


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
