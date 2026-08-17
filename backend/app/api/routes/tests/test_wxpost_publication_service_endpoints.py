"""HTTP-level tests for the async publication service endpoints.

Covers the `POST .../publication/assets/ensure` and
`POST .../publication/finalize` routes added for the async publication
pipeline: service-token auth, the OSS-copy asset materialization path, and
the finalize tail's version-drift guard + up-to-date short-circuit.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.api.routes.wxpost as wxpost_route
import app.services.wxpost_publication as wxpost_publication
from app.api.serv import app
from app.services.wxpost_oss_ops import OssOpsError

WXPOST_ID = UUID("00000000-0000-4000-8000-000000000abc")


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)


@pytest.fixture(autouse=True)
def _service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "controller-secret")


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer controller-secret"}


def _ensure_item(**overrides: Any) -> dict[str, Any]:
    payload = {
        "sourceId": "M01",
        "kind": "image",
        "filename": "round-table.jpg",
        "mimeType": "image/jpeg",
        "sizeBytes": 1024,
        "contentSha256": hashlib.sha256(b"public image bytes").hexdigest(),
        "meetingFileKey": "public/meetings/2026/M01.jpg",
        "needsWechatVariant": False,
    }
    payload.update(overrides)
    return payload


def test_ensure_asset_requires_service_token(client: TestClient) -> None:
    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/assets/ensure",
        json={"wxpostId": str(WXPOST_ID), "item": _ensure_item()},
    )

    assert response.status_code == 401


def test_finalize_requires_service_token(client: TestClient) -> None:
    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/finalize",
        json={
            "wxpostId": str(WXPOST_ID),
            "expectedManifestVersion": 1,
            "expectedDraftVersion": 1,
            "bundleSha256": "a" * 64,
        },
    )

    assert response.status_code == 401


def test_ensure_asset_copies_a_new_original_and_returns_its_public_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied: list[tuple[str, str, int]] = []
    created: list[dict] = []
    marked_ready: list[tuple[UUID, str]] = []

    monkeypatch.setattr(wxpost_publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)

    def fake_copy(source_key: str, target_key: str, *, expected_size: int) -> str:
        copied.append((source_key, target_key, expected_size))
        return "AB" * 16

    monkeypatch.setattr(wxpost_publication, "copy_public_object", fake_copy)

    def fake_create(values: dict) -> dict:
        created.append(values)
        return {**values, "status": "pending"}

    monkeypatch.setattr(wxpost_publication, "create_pending_wxpost_asset", fake_create)

    def fake_mark_ready(asset_id: UUID, *, etag: str) -> dict:
        marked_ready.append((asset_id, etag))
        return {**created[0], "status": "ready"}

    monkeypatch.setattr(wxpost_publication, "mark_wxpost_asset_ready", fake_mark_ready)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/assets/ensure",
        json={"wxpostId": str(WXPOST_ID), "item": _ensure_item()},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sourceId"] == "M01"
    assert body["variantReady"] is False
    assert body["publicUrl"] == wxpost_publication.public_asset_url(created[0]["object_key"])

    assert copied == [("public/meetings/2026/M01.jpg", created[0]["object_key"], 1024)]
    assert created[0]["content_md5"] == base64.b64encode(bytes.fromhex("AB" * 16)).decode()
    assert marked_ready == [(UUID(created[0]["id"]), "AB" * 16)]


def test_ensure_asset_reuses_an_existing_ready_asset_without_copying(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_asset = {
        "id": "00000000-0000-4000-8000-000000000999",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/existing/original.jpg",
    }
    monkeypatch.setattr(wxpost_publication, "get_ready_wxpost_asset", lambda *args, **kwargs: ready_asset)
    monkeypatch.setattr(
        wxpost_publication,
        "copy_public_object",
        lambda *args, **kwargs: pytest.fail("reuse path attempted a copy"),
    )

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/assets/ensure",
        json={"wxpostId": str(WXPOST_ID), "item": _ensure_item()},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["publicUrl"] == wxpost_publication.public_asset_url(ready_asset["object_key"])
    assert body["variantReady"] is False


def test_ensure_asset_maps_oss_ops_errors_to_publication_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_publication, "get_ready_wxpost_asset", lambda *args, **kwargs: None)

    def fake_copy(*args, **kwargs):
        raise OssOpsError("asset_changed", "Source object size mismatch")

    monkeypatch.setattr(wxpost_publication, "copy_public_object", fake_copy)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/assets/ensure",
        json={"wxpostId": str(WXPOST_ID), "item": _ensure_item()},
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "asset_changed"


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
                    "contentSha256": hashlib.sha256(b"public image bytes").hexdigest(),
                    "origin": {"type": "meeting-library", "fileKey": "public/meetings/2026/M01.jpg"},
                }
            ],
        },
        "draft": {"draftVersion": draft_version, "document": _document()},
    }


def _owner_row(*, draft_version: int = 2, draft_sha256: str) -> dict:
    return {
        "id": str(WXPOST_ID),
        "slug": "a-public-field-note",
        "status": "ready",
        "is_public": True,
        "article_revision": 3,
        "source_workspace_id": "wxpost-abc",
        "source_draft_version": draft_version,
        "source_draft_sha256": draft_sha256,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _finalize_body(
    *,
    manifest_version: int = 4,
    draft_version: int = 2,
    bundle_sha256: str,
) -> dict:
    return {
        "wxpostId": str(WXPOST_ID),
        "expectedManifestVersion": manifest_version,
        "expectedDraftVersion": draft_version,
        "bundleSha256": bundle_sha256,
    }


def test_finalize_rejects_a_stale_workspace_before_reading_asset_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def load_context(workspace_id: str) -> dict:
        return _context(manifest_version=99)

    monkeypatch.setattr(wxpost_route, "_load_workspace_context", load_context)
    monkeypatch.setattr(
        wxpost_publication,
        "get_ready_wxpost_assets",
        lambda *args, **kwargs: pytest.fail("version-drift finalize read asset state"),
    )

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/finalize",
        json=_finalize_body(bundle_sha256="a" * 64),
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


def test_finalize_happy_path_short_circuits_to_up_to_date_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def load_context(workspace_id: str) -> dict:
        assert workspace_id == "wxpost-abc"
        return _context()

    bundle_sha256 = "c" * 64
    owner = _owner_row(draft_sha256=bundle_sha256)
    ready_asset = {
        "id": "00000000-0000-4000-8000-000000000999",
        "object_key": f"public/wxposts/{WXPOST_ID}/assets/M01/original.jpg",
        "content_sha256": hashlib.sha256(b"public image bytes").hexdigest(),
    }

    monkeypatch.setattr(wxpost_route, "_load_workspace_context", load_context)
    monkeypatch.setattr(wxpost_publication, "get_wxpost_by_id", lambda wxpost_id: owner)
    monkeypatch.setattr(wxpost_publication, "get_wxpost_by_workspace_id", lambda workspace_id: owner)
    monkeypatch.setattr(wxpost_publication, "get_ready_wxpost_assets", lambda wxpost_id: [ready_asset])
    monkeypatch.setattr(
        wxpost_publication,
        "finalize_workspace_publication",
        lambda *args, **kwargs: pytest.fail("up-to-date finalize re-finalized the row"),
    )
    monkeypatch.setattr(
        wxpost_publication,
        "_remove_unreferenced_assets",
        lambda *args, **kwargs: None,
    )

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/finalize",
        json=_finalize_body(bundle_sha256=bundle_sha256),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "up-to-date"
    assert body["publicRevision"] == 3


def test_finalize_rejects_when_an_included_item_has_no_ready_asset(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def load_context(workspace_id: str) -> dict:
        return _context()

    monkeypatch.setattr(wxpost_route, "_load_workspace_context", load_context)
    monkeypatch.setattr(wxpost_publication, "get_wxpost_by_id", lambda wxpost_id: _owner_row(draft_sha256="z" * 64))
    monkeypatch.setattr(wxpost_publication, "get_wxpost_by_workspace_id", lambda workspace_id: None)
    monkeypatch.setattr(wxpost_publication, "get_ready_wxpost_assets", lambda wxpost_id: [])

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/finalize",
        json=_finalize_body(bundle_sha256="a" * 64),
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "missing_publication_media"
