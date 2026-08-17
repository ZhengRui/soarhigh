import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest

import app.services.wxpost_publication as publication
from app.models.wxpost import WxPostPublicationSyncRequest

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000777")


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
            },
            {
                "id": "M02",
                "kind": "image",
                "sourceUrl": "https://workspace.invalid/wxpost-abc/materials/M02",
                "description": "A second image, referenced in the body.",
                "include": True,
                "order": 1,
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            },
        ],
        "coverMediaId": "M01",
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
        "bodyMarkdown": ':::image\n{"media": "M02"}\n:::',
    }


def _source(
    *,
    source_id: str = "M01",
    filename: str = "round-table.jpg",
    content: bytes = b"public image bytes",
    size_bytes: int = 19,
    origin: dict | None = None,
) -> dict:
    return {
        "id": source_id,
        "kind": "image",
        "filename": filename,
        "mimeType": "image/jpeg",
        "sizeBytes": size_bytes,
        "workspaceReady": True,
        "contentSha256": hashlib.sha256(content).hexdigest(),
        "origin": (
            origin
            if origin is not None
            else {"type": "meeting-library", "fileKey": f"public/meetings/2026/{source_id}.jpg"}
        ),
    }


def _context(
    *,
    manifest_version: int = 4,
    draft_version: int = 2,
    sources: list[dict] | None = None,
    document: dict | None = None,
) -> dict:
    return {
        "workspaceId": "wxpost-abc",
        "manifest": {
            "manifestVersion": manifest_version,
            "sources": sources
            if sources is not None
            else [
                _source(source_id="M01", content=b"public image bytes", size_bytes=19),
                _source(source_id="M02", content=b"second image bytes", size_bytes=19),
            ],
        },
        "draft": {"draftVersion": draft_version, "document": document or _document()},
    }


def _request(
    *,
    manifest_version: int = 4,
    draft_version: int = 2,
    public_revision: int | None = None,
) -> WxPostPublicationSyncRequest:
    return WxPostPublicationSyncRequest(
        operation_id="publish-" + "0" * 32,
        expected_manifest_version=manifest_version,
        expected_draft_version=draft_version,
        expected_public_revision=public_revision,
    )


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


@pytest.fixture(autouse=True)
def _stub_shell_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publication, "get_wxpost_by_workspace_id", lambda workspace_id: None)
    monkeypatch.setattr(
        publication,
        "has_abandoned_wxpost_assets",
        lambda wxpost_id: False,
    )
    monkeypatch.setattr(
        publication,
        "create_publication_shell",
        lambda **kwargs: {
            "id": str(WXPOST_ID),
            "status": "assembling",
            "is_public": False,
            "article_revision": 1,
            "source_workspace_id": kwargs["workspace_id"],
            "source_draft_version": kwargs["draft_version"],
            "source_draft_sha256": kwargs["draft_sha256"],
        },
    )


async def _load_context(workspace_id: str) -> dict:
    assert workspace_id == "wxpost-abc"
    return _context()


@pytest.mark.asyncio
async def test_happy_path_returns_ordered_items_with_variant_flags_and_shell() -> None:
    plan = await publication.prepare_publication_submit(
        "wxpost-abc",
        _request(),
        load_context=_load_context,
    )

    assert plan.wxpost_id == str(WXPOST_ID)
    assert plan.draft_version == 2
    assert plan.manifest_version == 4
    assert len(plan.bundle_sha256) == 64
    assert [item.source_id for item in plan.items] == ["M01", "M02"]

    m01, m02 = plan.items
    # M01 is only the cover, and its size stays under the hard-max threshold.
    assert m01.needs_wechat_variant is False
    assert m01.meeting_file_key == "public/meetings/2026/M01.jpg"
    assert m01.kind == "image"
    assert m01.mime_type == "image/jpeg"
    assert m01.content_sha256 == hashlib.sha256(b"public image bytes").hexdigest()

    # M02 is referenced by a body directive, so it needs a WeChat body variant.
    assert m02.needs_wechat_variant is True
    assert m02.meeting_file_key == "public/meetings/2026/M02.jpg"


@pytest.mark.asyncio
async def test_oversized_cover_needs_wechat_variant_even_without_body_reference() -> None:
    oversized = publication.WECHAT_COVER_HARD_MAX_BYTES + 1
    context = _context(
        sources=[
            _source(source_id="M01", content=b"public image bytes", size_bytes=oversized),
            _source(source_id="M02", content=b"second image bytes", size_bytes=19),
        ]
    )

    async def load_context(workspace_id: str) -> dict:
        return context

    plan = await publication.prepare_publication_submit(
        "wxpost-abc",
        _request(),
        load_context=load_context,
    )

    m01 = next(item for item in plan.items if item.source_id == "M01")
    assert m01.needs_wechat_variant is True


@pytest.mark.asyncio
async def test_upload_origin_source_is_rejected() -> None:
    context = _context(
        sources=[
            _source(source_id="M01", content=b"public image bytes", size_bytes=19),
            _source(
                source_id="M02",
                content=b"second image bytes",
                size_bytes=19,
                origin={"type": "web-upload"},
            ),
        ]
    )

    async def load_context(workspace_id: str) -> dict:
        return context

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_submit(
            "wxpost-abc",
            _request(),
            load_context=load_context,
        )

    assert raised.value.code == "upload_origin_unsupported"
    assert raised.value.status == 422
    assert "M02" in str(raised.value)


@pytest.mark.asyncio
async def test_version_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: _row(revision=4),
    )

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_submit(
            "wxpost-abc",
            _request(public_revision=3),
            load_context=_load_context,
        )

    assert raised.value.code == "version_conflict"
    assert raised.value.status == 409


@pytest.mark.asyncio
async def test_missing_draft_is_rejected() -> None:
    async def load_context(workspace_id: str) -> dict:
        return {"workspaceId": workspace_id, "manifest": {"manifestVersion": 4, "sources": []}}

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_submit(
            "wxpost-abc",
            _request(),
            load_context=load_context,
        )

    assert raised.value.code == "draft_required"
    assert raised.value.status == 422
