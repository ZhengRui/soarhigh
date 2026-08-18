"""Tests for prepare_publication_uploads (presign step for upload-origin items)."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from uuid import UUID

import pytest

import app.services.wxpost_publication as publication
from app.db.wxpost import WxPostAssetConflictError
from app.models.wxpost import WxPostPublicationExpectedVersions
from app.services.wxpost_oss_ops import OssOpsError

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000001")


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


def _request() -> WxPostPublicationExpectedVersions:
    return WxPostPublicationExpectedVersions(
        expected_manifest_version=4,
        expected_draft_version=2,
        expected_public_revision=None,
    )


def _mixed_context() -> dict:
    return _context(
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


MD5_HEX = hashlib.md5(b"second image bytes").hexdigest()
CONTENT_MD5 = base64.b64encode(bytes.fromhex(MD5_HEX)).decode()


async def _fetch_checksums(workspace_id: str, source_ids: list[str]) -> dict[str, str]:
    assert workspace_id == "wxpost-abc"
    assert source_ids == ["M02"]
    return {"M02": MD5_HEX}


@pytest.mark.asyncio
async def test_mixed_plan_signs_only_upload_items(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict] = []

    def create_pending(values: dict) -> dict:
        created.append(values)
        return values

    signed: list[tuple[str, str, str]] = []

    def sign(key: str, *, content_md5: str, content_type: str) -> str:
        signed.append((key, content_md5, content_type))
        return f"https://signed.invalid/{key}"

    monkeypatch.setattr(publication, "create_pending_wxpost_asset", create_pending)
    monkeypatch.setattr(publication, "sign_public_put_url", sign)

    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    result = await publication.prepare_publication_uploads(
        "wxpost-abc",
        _request(),
        load_context=load_context,
        fetch_checksums=_fetch_checksums,
    )

    assert len(result.uploads) == 1
    upload = result.uploads[0]
    assert upload.source_id == "M02"
    assert upload.content_sha256 == hashlib.sha256(b"second image bytes").hexdigest()
    assert upload.headers == {"Content-MD5": CONTENT_MD5, "Content-Type": "image/jpeg"}
    assert upload.put_url.startswith("https://signed.invalid/public/wxposts/")

    assert len(created) == 1
    row = created[0]
    assert row["content_md5"] == CONTENT_MD5
    assert row["source_type"] == "workspace"
    assert row["source_metadata"] == {"workspaceId": "wxpost-abc", "sourceId": "M02"}
    idempotency = f"wxpost-abc:M02:{upload.content_sha256}"
    assert row["upload_idempotency_key_hash"] == hashlib.sha256(idempotency.encode()).hexdigest()
    row_key = row["object_key"]
    assert row_key.startswith(f"public/wxposts/{WXPOST_ID}/assets/")
    assert row_key.endswith("/original.jpg")
    assert signed == [(row_key, CONTENT_MD5, "image/jpeg")]
    assert row["kind"] == "image"
    assert row["original_filename"] == "round-table.jpg"
    assert row["mime_type"] == "image/jpeg"
    assert row["size_bytes"] == 19
    assert row["content_sha256"] == upload.content_sha256
    assert row["wxpost_id"] == str(WXPOST_ID)
    assert row["upload_request_hash"] == publication._request_hash(
        filename="round-table.jpg",
        kind="image",
        mime_type="image/jpeg",
        sha256=upload.content_sha256,
        size_bytes=19,
    )


@pytest.mark.asyncio
async def test_all_library_plan_returns_empty_without_checksum_call() -> None:
    async def load_context(workspace_id: str) -> dict:
        return _context()

    async def must_not_call(workspace_id: str, source_ids: list[str]) -> dict[str, str]:
        raise AssertionError("fetch_checksums must not be called")

    result = await publication.prepare_publication_uploads(
        "wxpost-abc",
        _request(),
        load_context=load_context,
        fetch_checksums=must_not_call,
    )
    assert result.uploads == []


@pytest.mark.asyncio
async def test_ready_row_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "create_pending_wxpost_asset",
        lambda values: {**values, "status": "ready"},
    )
    monkeypatch.setattr(
        publication,
        "sign_public_put_url",
        lambda *a, **k: pytest.fail("must not sign for ready rows"),
    )

    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    result = await publication.prepare_publication_uploads(
        "wxpost-abc",
        _request(),
        load_context=load_context,
        fetch_checksums=_fetch_checksums,
    )
    assert result.uploads == []


@pytest.mark.asyncio
async def test_inactive_row_is_retried_then_signed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "create_pending_wxpost_asset",
        lambda values: {**values, "id": "11111111-1111-4111-8111-111111111111", "status": "failed"},
    )
    retried: list[str] = []

    def retry(asset_id: UUID) -> dict:
        retried.append(str(asset_id))
        return {
            "id": str(asset_id),
            "status": "pending",
            "object_key": "public/wxposts/x/assets/y/original.jpg",
            "content_md5": CONTENT_MD5,
        }

    monkeypatch.setattr(publication, "retry_inactive_wxpost_asset", retry)
    monkeypatch.setattr(
        publication,
        "sign_public_put_url",
        lambda key, *, content_md5, content_type: f"https://signed.invalid/{key}",
    )

    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    result = await publication.prepare_publication_uploads(
        "wxpost-abc",
        _request(),
        load_context=load_context,
        fetch_checksums=_fetch_checksums,
    )
    assert retried == ["11111111-1111-4111-8111-111111111111"]
    assert len(result.uploads) == 1
    assert result.uploads[0].put_url.endswith("public/wxposts/x/assets/y/original.jpg")


@pytest.mark.asyncio
async def test_recovered_row_md5_mismatch_is_asset_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "create_pending_wxpost_asset",
        lambda values: {**values, "status": "pending", "content_md5": "ZGlmZmVyZW50IG1kNQ=="},
    )

    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_uploads(
            "wxpost-abc",
            _request(),
            load_context=load_context,
            fetch_checksums=_fetch_checksums,
        )
    assert raised.value.code == "asset_changed"
    assert raised.value.status == 409


@pytest.mark.asyncio
async def test_invalid_checksum_payload_is_asset_unavailable() -> None:
    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    async def bad_checksums(workspace_id: str, source_ids: list[str]) -> dict[str, str]:
        return {"M02": "not-hex"}

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_uploads(
            "wxpost-abc",
            _request(),
            load_context=load_context,
            fetch_checksums=bad_checksums,
        )
    assert raised.value.code == "asset_unavailable"
    assert raised.value.status == 503


@pytest.mark.asyncio
async def test_sign_failure_is_mapped_to_publication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publication,
        "create_pending_wxpost_asset",
        lambda values: {**values, "status": "pending"},
    )

    def sign(key: str, *, content_md5: str, content_type: str) -> str:
        raise OssOpsError("asset_unavailable", "boom")

    monkeypatch.setattr(publication, "sign_public_put_url", sign)

    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_uploads(
            "wxpost-abc",
            _request(),
            load_context=load_context,
            fetch_checksums=_fetch_checksums,
        )
    assert raised.value.code == "asset_unavailable"
    assert raised.value.status == 503


@pytest.mark.asyncio
async def test_asset_row_creation_conflict_is_asset_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    def create_pending(values: dict) -> dict:
        raise WxPostAssetConflictError()

    monkeypatch.setattr(publication, "create_pending_wxpost_asset", create_pending)

    async def load_context(workspace_id: str) -> dict:
        return _mixed_context()

    with pytest.raises(publication.PublicationError) as raised:
        await publication.prepare_publication_uploads(
            "wxpost-abc",
            _request(),
            load_context=load_context,
            fetch_checksums=_fetch_checksums,
        )
    assert raised.value.code == "asset_changed"
    assert raised.value.status == 409
