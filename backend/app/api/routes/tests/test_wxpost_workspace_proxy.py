import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

import app.api.routes.wxpost as wxpost_route
import app.services.wxpost_publication as wxpost_publication
from app.api.serv import app
from app.models.users import User
from app.models.wxpost import WxPostPublicationStatus, WxPostWechatDraftResult

WXPOST_FIXTURE = Path(__file__).parent / "fixtures" / "wxpost-meeting-recap-v1.json"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[wxpost_route.get_current_user] = lambda: User(
        uid="member-123",
        username="test-member",
        full_name="Test Member",
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(wxpost_route.get_current_user, None)


def _configure_controller(
    monkeypatch: pytest.MonkeyPatch,
    handler,
) -> None:
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client_factory(*, timeout: int, trust_env: bool) -> httpx.AsyncClient:
        assert timeout in {30, 100, 330}
        assert trust_env is False
        return real_client(transport=transport)

    monkeypatch.setattr(wxpost_route, "WXPOST_CONTROLLER_URL", "http://controller")
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "controller-secret")
    monkeypatch.setattr(wxpost_route.httpx, "AsyncClient", client_factory)


def _public_row(article: dict, *, revision: int = 3) -> dict:
    return {
        "id": "00000000-0000-4000-8000-000000000236",
        "slug": article["slug"],
        "title": article["title"],
        "content": article["bodyMarkdown"],
        "schema_version": article["schemaVersion"],
        "article_type": article["articleType"],
        "custom_article_type": article.get("customArticleType"),
        "source_meeting_id": article.get("sourceMeetingId"),
        "excerpt": article.get("excerpt"),
        "byline": article.get("byline"),
        "media_manifest": article["media"],
        "cover_media_id": article["coverMediaId"],
        "default_presentation": article["presentation"],
        "render_version": 1,
        "article_revision": revision,
        "source_workspace_id": "wxpost-abc",
        "status": "ready",
        "is_public": True,
    }


def test_service_can_issue_and_read_a_version_bound_private_draft_preview(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/context"):
            return httpx.Response(
                200,
                json={
                    "workspaceId": "wxpost-abc",
                    "manifest": {
                        "manifestVersion": 7,
                        "sources": [{"id": "M01", "contentSha256": "a" * 64}],
                    },
                    "draft": {"draftVersion": 4, "document": article},
                },
            )
        if request.url.path.endswith("/sources/M01/content"):
            assert request.url.params["v"] == "a" * 64
            return httpx.Response(
                200,
                content=b"draft-image",
                headers={"Content-Type": "image/jpeg"},
            )
        return httpx.Response(404)

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(wxpost_route, "WXPOST_PUBLIC_BASE_URL", "https://soarhigh.example")
    monkeypatch.setattr(wxpost_route.time, "time", lambda: 1_800_000_000)

    issued = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/draft-preview?draft_version=4",
        headers={"Authorization": "Bearer controller-secret"},
    )

    assert issued.status_code == 200
    payload = issued.json()
    assert payload["draftVersion"] == 4
    assert payload["expiresAt"] == 1_800_086_400
    assert payload["previewUrl"].startswith("https://soarhigh.example/posts/wxposts/draft-preview/")
    assert payload["editorUrl"] == ("https://soarhigh.example/posts/wxposts/edit/abc?view=edit")
    token = payload["previewUrl"].rsplit("/", 1)[-1]

    preview = client.get(f"/posts/wxposts/draft-previews/{token}")

    assert preview.status_code == 200
    render_document = preview.json()["renderDocument"]
    assert preview.json()["draftVersion"] == 4
    assert render_document["title"] == article["title"]
    assert render_document["media"][0]["sourceUrl"].endswith(f"/draft-previews/{token}/media/M01")

    media = client.get(f"/posts/wxposts/draft-previews/{token}/media/M01")
    assert media.status_code == 200
    assert media.content == b"draft-image"
    assert media.headers["content-type"] == "image/jpeg"
    assert all(request.headers["Authorization"] == "Bearer controller-secret" for request in requests)


def test_service_can_get_authenticated_workspace_editor_links(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/workspaces/wxpost-abc/context")
        return httpx.Response(
            200,
            json={
                "workspaceId": "wxpost-abc",
                "manifest": {"manifestVersion": 1},
                "draft": None,
            },
        )

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(wxpost_route, "WXPOST_PUBLIC_BASE_URL", "https://soarhigh.example")

    response = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/editor-links",
        headers={"Authorization": "Bearer controller-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "workspaceId": "wxpost-abc",
        "materialsUrl": "https://soarhigh.example/posts/wxposts/edit/abc",
        "draftUrl": "https://soarhigh.example/posts/wxposts/edit/abc?view=edit",
    }


def test_private_draft_preview_rejects_stale_versions_and_unreferenced_media(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    current_version = 4

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "workspaceId": "wxpost-abc",
                "manifest": {"manifestVersion": 7},
                "draft": {
                    "draftVersion": current_version,
                    "document": article,
                },
            },
        )

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(wxpost_route.time, "time", lambda: 1_800_000_000)
    token = wxpost_route._encode_draft_preview_token("wxpost-abc", 4, 1_800_086_400)

    missing = client.get(f"/posts/wxposts/draft-previews/{token}/media/M99")
    assert missing.status_code == 404

    current_version = 5
    stale = client.get(f"/posts/wxposts/draft-previews/{token}")
    assert stale.status_code == 410
    assert "no longer current" in stale.json()["detail"]


def test_authenticated_workspace_creation_hides_controller_credential(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"workspaceId": "wxpost-abc", "manifest": {}, "draft": None},
        )

    _configure_controller(monkeypatch, handler)
    response = client.post(
        "/posts/wxposts/workspaces",
        headers={"Authorization": "Bearer member-token"},
        json={
            "meetingId": None,
            "editorial": {"articleType": "meeting-recap"},
            "createdBy": {"id": "spoofed", "name": "Spoofed member"},
        },
    )

    assert response.status_code == 200
    assert response.json()["workspaceId"] == "wxpost-abc"
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert str(request.url) == "http://controller/workspaces"
    assert request.headers["Authorization"] == "Bearer controller-secret"
    assert json.loads(request.content) == {
        "meetingId": None,
        "editorial": {"articleType": "meeting-recap"},
        "createdBy": {"id": "member-123", "name": "Test Member"},
    }


def test_authenticated_workspace_update_is_proxied_in_place(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"workspaceId": "wxpost-abc", "manifest": {}, "draft": None},
        )

    _configure_controller(monkeypatch, handler)
    payload = {
        "expectedManifestVersion": 7,
        "meetingId": "meeting-461",
        "editorial": {"articleType": "member-story"},
        "sourceUpdates": [
            {
                "sourceId": "M03",
                "included": False,
                "description": "Updated source fact.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    }
    response = client.patch(
        "/posts/wxposts/workspaces/wxpost-abc",
        headers={"Authorization": "Bearer member-token"},
        json=payload,
    )

    assert response.status_code == 200
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "PATCH"
    assert str(request.url) == "http://controller/workspaces/wxpost-abc"
    assert request.headers["Authorization"] == "Bearer controller-secret"
    assert json.loads(request.content) == payload


def test_image_description_suggestion_uses_the_long_running_controller_proxy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []
    real_client = httpx.AsyncClient

    def handle_request(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "workspaceId": "wxpost-abc",
                "sourceId": "M01",
                "description": "Members gather around a meeting table.",
            },
        )

    transport = httpx.MockTransport(handle_request)

    def client_factory(*, timeout: int, trust_env: bool) -> httpx.AsyncClient:
        assert timeout == 330
        assert trust_env is False
        return real_client(transport=transport)

    monkeypatch.setattr(wxpost_route, "WXPOST_CONTROLLER_URL", "http://controller")
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "controller-secret")
    monkeypatch.setattr(wxpost_route.httpx, "AsyncClient", client_factory)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/sources/M01/description-suggestion",
        headers={"Authorization": "Bearer member-token"},
        json={
            "expectedManifestVersion": 7,
            "currentDescription": "会员们围坐交流。",
        },
    )

    assert response.status_code == 200
    assert response.json()["sourceId"] == "M01"
    assert len(captured) == 1
    assert captured[0].headers["Authorization"] == "Bearer controller-secret"
    assert captured[0].url.path == ("/workspaces/wxpost-abc/sources/M01/description-suggestion")


def test_authenticated_members_can_list_and_delete_all_workspaces(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "items": [],
                    "total": 0,
                    "page": 2,
                    "page_size": 5,
                    "pages": 1,
                },
            )
        return httpx.Response(
            200,
            json={"workspaceId": "wxpost-abc", "deleted": True},
        )

    _configure_controller(monkeypatch, handler)
    listed = client.get(
        "/posts/wxposts/workspaces",
        params={"page": 2, "page_size": 5},
        headers={"Authorization": "Bearer member-token"},
    )
    deleted = client.delete(
        "/posts/wxposts/workspaces/wxpost-abc",
        headers={
            "Authorization": "Bearer member-token",
            "X-Expected-Manifest-Version": "4",
        },
    )

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [],
        "total": 0,
        "page": 2,
        "page_size": 5,
        "pages": 1,
    }
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/workspaces"),
        ("DELETE", "/workspaces/wxpost-abc"),
    ]
    assert dict(captured[0].url.params) == {"page": "2", "page_size": "5"}
    assert captured[1].headers["X-Expected-Manifest-Version"] == "4"


def test_workspace_list_is_enriched_with_batch_publication_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "workspaceId": "wxpost-abc",
                        "draftVersion": 4,
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 10,
                "pages": 1,
            },
        )

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(
        wxpost_route,
        "get_wxposts_by_workspace_ids",
        lambda workspace_ids: [
            {
                "slug": "public-note",
                "status": "ready",
                "is_public": True,
                "article_revision": 2,
                "source_workspace_id": "wxpost-abc",
                "source_draft_version": 3,
                "source_draft_sha256": "a" * 64,
                "updated_at": "2026-08-01T08:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        wxpost_publication,
        "WXPOST_PUBLIC_BASE_URL",
        "https://soarhigh.example",
    )

    response = client.get("/posts/wxposts/workspaces")

    assert response.status_code == 200
    status = response.json()["items"][0]["publication"]
    assert status["state"] == "update-available"
    assert status["publicRevision"] == 2
    assert status["currentDraftVersion"] == 4


def test_workspace_list_survives_unavailable_publication_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [{"workspaceId": "wxpost-abc", "draftVersion": 4}],
                "total": 1,
                "page": 1,
                "page_size": 10,
                "pages": 1,
            },
        )

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(
        wxpost_route,
        "get_wxposts_by_workspace_ids",
        lambda workspace_ids: (_ for _ in ()).throw(
            APIError(
                {
                    "message": "database unavailable",
                    "code": "503",
                    "hint": "",
                    "details": "",
                }
            )
        ),
    )

    response = client.get("/posts/wxposts/workspaces")

    assert response.status_code == 200
    assert response.json()["items"][0]["publication"] == {
        "state": "unavailable",
        "workspaceId": "wxpost-abc",
        "slug": None,
        "publicRevision": None,
        "sourceDraftVersion": None,
        "currentDraftVersion": 4,
        "publishedAt": None,
        "publicUrl": None,
    }


def test_member_can_read_and_sync_workspace_publication(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = {
        "workspaceId": "wxpost-abc",
        "manifest": {"manifestVersion": 5, "sources": []},
        "draft": {"draftVersion": 3, "document": {}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=context)

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(
        wxpost_route,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: None,
    )
    calls: list[dict] = []

    async def sync(workspace_id, request, **kwargs):
        calls.append(
            {
                "workspace_id": workspace_id,
                "request": request.model_dump(by_alias=True),
            }
        )
        return WxPostPublicationStatus(
            state="up-to-date",
            workspaceId=workspace_id,
            slug="public-note",
            publicRevision=1,
            sourceDraftVersion=3,
            currentDraftVersion=3,
            publishedAt="2026-08-01T08:00:00Z",
            publicUrl="https://soarhigh.example/posts/wxposts/public-note",
        )

    monkeypatch.setattr(
        wxpost_route,
        "synchronize_workspace_publication",
        sync,
    )

    status_response = client.get("/posts/wxposts/workspaces/wxpost-abc/publication")
    sync_response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/publication/sync",
        json={
            "expectedManifestVersion": 5,
            "expectedDraftVersion": 3,
            "expectedPublicRevision": None,
        },
    )

    assert status_response.status_code == 200
    assert status_response.json()["state"] == "not-synced"
    assert sync_response.status_code == 200
    assert sync_response.json()["state"] == "up-to-date"
    assert calls == [
        {
            "workspace_id": "wxpost-abc",
            "request": {
                "expectedManifestVersion": 5,
                "expectedDraftVersion": 3,
                "expectedPublicRevision": None,
            },
        }
    ]


def test_controller_service_can_read_publication_without_a_callback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "service-secret")
    monkeypatch.setattr(
        wxpost_route,
        "get_wxpost_by_workspace_id",
        lambda workspace_id: {
            "slug": "public-note",
            "status": "ready",
            "is_public": True,
            "article_revision": 3,
            "source_workspace_id": workspace_id,
            "source_draft_version": 4,
            "source_draft_sha256": "a" * 64,
            "updated_at": "2026-08-01T08:00:00Z",
        },
    )
    monkeypatch.setattr(
        wxpost_publication,
        "WXPOST_PUBLIC_BASE_URL",
        "https://soarhigh.example",
    )

    unauthorized = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/publication/service",
        params={"current_draft_version": 5},
    )
    authorized = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/publication/service",
        params={"current_draft_version": 5},
        headers={"Authorization": "Bearer service-secret"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json() == {
        "state": "update-available",
        "workspaceId": "wxpost-abc",
        "slug": "public-note",
        "publicRevision": 3,
        "sourceDraftVersion": 4,
        "currentDraftVersion": 5,
        "publishedAt": "2026-08-01T08:00:00Z",
        "publicUrl": "https://soarhigh.example/posts/wxposts/public-note",
    }


def test_member_can_delete_a_public_wxpost_revision(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[UUID, int]] = []

    async def delete(wxpost_id: UUID, *, expected_revision: int) -> str:
        calls.append((wxpost_id, expected_revision))
        return "wxpost-abc"

    monkeypatch.setattr(wxpost_route, "delete_public_wxpost", delete)
    wxpost_id = UUID("00000000-0000-4000-8000-000000000777")

    response = client.request(
        "DELETE",
        f"/posts/wxposts/{wxpost_id}/publication",
        json={"expectedPublicRevision": 3},
    )

    assert response.status_code == 200
    assert response.json() == {
        "deleted": True,
        "workspaceId": "wxpost-abc",
    }
    assert calls == [(wxpost_id, 3)]


def test_voice_tone_suggestion_uses_the_controller_boundary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"instruction": "Use lively details and restrained wit."},
        )

    _configure_controller(monkeypatch, handler)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/voice-tone/suggestion",
        headers={"Authorization": "Bearer member-token"},
        json={"name": "  Dry humour  "},
    )

    assert response.status_code == 200
    assert response.json() == {"instruction": "Use lively details and restrained wit."}
    assert [(request.method, request.url.path) for request in captured] == [
        ("POST", "/workspaces/wxpost-abc/voice-tone/suggestion")
    ]
    assert json.loads(captured[0].content) == {"name": "Dry humour"}


def test_voice_tone_suggestion_preserves_the_missing_workspace_response(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "error": {
                    "code": "workspace_not_found",
                    "message": "workspace not found",
                }
            },
        )

    _configure_controller(monkeypatch, handler)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-missing/voice-tone/suggestion",
        headers={"Authorization": "Bearer member-token"},
        json={"name": "Warm"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "workspace_not_found"


def test_material_proxy_preserves_version_and_binary_contracts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"manifestVersion": 2})
        if request.url.path.endswith("/delete-preflight"):
            return httpx.Response(
                200,
                json={
                    "sourceId": "M01",
                    "manifestVersion": 2,
                    "referenced": False,
                },
            )
        return httpx.Response(
            200,
            content=b"photo",
            headers={
                "Content-Type": "image/jpeg",
                "Cache-Control": "private, max-age=31536000, immutable",
                "ETag": f'"{"a" * 64}"',
                "Vary": "Authorization",
            },
        )

    _configure_controller(monkeypatch, handler)
    uploaded = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/uploads",
        params={"filename": "group photo.jpg"},
        headers={
            "Authorization": "Bearer member-token",
            "Content-Type": "image/jpeg",
            "X-Expected-Manifest-Version": "1",
        },
        content=b"photo",
    )
    content = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/sources/M01/content",
        params={"v": "a" * 64},
        headers={"Authorization": "Bearer member-token"},
    )
    missing_version = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/sources/M01/content",
        headers={"Authorization": "Bearer member-token"},
    )
    preflight = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/sources/M01/delete-preflight",
        headers={
            "Authorization": "Bearer member-token",
            "X-Expected-Manifest-Version": "2",
        },
    )

    assert uploaded.status_code == 200
    assert captured[0].url.params["filename"] == "group photo.jpg"
    assert captured[0].headers["X-Expected-Manifest-Version"] == "1"
    assert captured[0].content == b"photo"
    assert content.status_code == 200
    assert content.content == b"photo"
    assert content.headers["Content-Type"] == "image/jpeg"
    assert content.headers["Cache-Control"] == ("private, max-age=31536000, immutable")
    assert content.headers["ETag"] == f'"{"a" * 64}"'
    assert content.headers["Vary"] == "Authorization"
    assert captured[1].url.params["v"] == "a" * 64
    assert missing_version.status_code == 422
    assert preflight.status_code == 200
    assert preflight.json()["manifestVersion"] == 2
    assert captured[2].headers["X-Expected-Manifest-Version"] == "2"


def test_upload_rejects_oversized_bodies_before_proxying(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(wxpost_route, "WXPOST_MAX_SOURCE_BYTES", 4)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/uploads",
        params={"filename": "large.jpg"},
        headers={
            "Authorization": "Bearer member-token",
            "Content-Type": "image/jpeg",
            "X-Expected-Manifest-Version": "1",
        },
        content=b"12345",
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Upload exceeds 50 MiB."
    assert captured == []


def test_workspace_proxy_reports_missing_or_unavailable_controller(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_route, "WXPOST_CONTROLLER_URL", "")
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "")
    response = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/context",
        headers={"Authorization": "Bearer member-token"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == ("WxPost workspace controller is not configured.")

    async def fail_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    _configure_controller(monkeypatch, fail_request)
    response = client.get(
        "/posts/wxposts/workspaces/wxpost-abc/context",
        headers={"Authorization": "Bearer member-token"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == ("WxPost workspace controller is unavailable.")


def test_workspace_proxy_exposes_private_draft_operation_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = "draft-0123456789abcdef0123456789abcdef"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/draft/operations/{operation_id}")
        return httpx.Response(
            200,
            headers={"Cache-Control": "private, no-store"},
            json={
                "workspaceId": "wxpost-abc",
                "operationId": operation_id,
                "state": "running",
                "result": None,
                "error": None,
            },
        )

    _configure_controller(monkeypatch, handler)
    response = client.get(
        f"/posts/wxposts/workspaces/wxpost-abc/draft/operations/{operation_id}",
        headers={"Authorization": "Bearer member-token"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["state"] == "running"


def test_workspace_proxy_allows_draft_operation_interrupt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_id = "draft-0123456789abcdef0123456789abcdef"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith(f"/draft/operations/{operation_id}/interrupt")
        return httpx.Response(
            200,
            json={
                "workspaceId": "wxpost-abc",
                "operationId": operation_id,
                "interrupted": True,
            },
        )

    _configure_controller(monkeypatch, handler)
    response = client.post(
        f"/posts/wxposts/workspaces/wxpost-abc/draft/operations/{operation_id}/interrupt",
        headers={"Authorization": "Bearer member-token"},
    )

    assert response.status_code == 200
    assert response.json()["interrupted"] is True


def test_workspace_proxy_rejects_operations_outside_the_materials_slice(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    _configure_controller(monkeypatch, handler)
    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/draft",
        headers={"Authorization": "Bearer member-token"},
        json={"document": {}},
    )

    assert response.status_code == 404
    assert captured == []


def test_workspace_proxy_allows_only_the_scoped_draft_routes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    _configure_controller(monkeypatch, handler)

    requests = [
        ("GET", "/draft/conversation", None),
        ("DELETE", "/draft/conversation", None),
        (
            "POST",
            "/draft/save",
            {
                "expectedManifestVersion": 3,
                "expectedDraftVersion": 1,
                "document": {"schemaVersion": 1},
            },
        ),
        (
            "POST",
            "/draft/generate",
            {"expectedManifestVersion": 3, "expectedDraftVersion": 1},
        ),
        (
            "POST",
            "/draft/chat",
            {
                "expectedManifestVersion": 3,
                "expectedDraftVersion": 1,
                "message": "Tighten the opening.",
                "selectedText": "The meeting began.",
            },
        ),
    ]
    for method, suffix, payload in requests:
        response = client.request(
            method,
            f"/posts/wxposts/workspaces/wxpost-abc{suffix}",
            headers={"Authorization": "Bearer member-token"},
            json=payload,
        )
        assert response.status_code == 200

    rejected = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/draft/arbitrary",
        headers={"Authorization": "Bearer member-token"},
        json={},
    )

    assert rejected.status_code == 404
    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/workspaces/wxpost-abc/draft/conversation"),
        ("DELETE", "/workspaces/wxpost-abc/draft/conversation"),
        ("POST", "/workspaces/wxpost-abc/draft/save"),
        ("POST", "/workspaces/wxpost-abc/draft/generate"),
        ("POST", "/workspaces/wxpost-abc/draft/chat"),
    ]


def test_workspace_draft_chat_proxies_the_async_submit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """draft/chat is a short JSON submit: the Controller answers immediately
    with the running operation and the browser polls it — no held-open
    stream crosses this backend."""

    submit_payload = {
        "workspaceId": "wxpost-abc",
        "operationId": "draft-0123456789abcdef0123456789abcdef",
        "state": "running",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/workspaces/wxpost-abc/draft/chat"
        body = json.loads(request.content)
        assert body["operationId"] == submit_payload["operationId"]
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json; charset=utf-8"},
            json=submit_payload,
        )

    _configure_controller(monkeypatch, handler)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/draft/chat",
        headers={"Authorization": "Bearer member-token"},
        json={
            "expectedManifestVersion": 3,
            "expectedDraftVersion": 1,
            "operationId": submit_payload["operationId"],
            "message": "How many sections are there?",
            "selectedText": None,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == submit_payload


def test_member_reads_the_wechat_projection_status_from_the_public_revision(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    row = _public_row(article)
    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: row)
    monkeypatch.setattr(
        wxpost_route.wxpost_wechat_store,
        "get_projection",
        lambda workspace_id: {
            "state": "ready",
            "wechat_media_id": "linked-draft-id",
            "source_public_revision": 2,
            "presentation": article["presentation"],
            "readback_changed": True,
            "last_error": None,
        },
    )

    response = client.get(f"/posts/wxposts/{row['id']}/wechat-draft")

    assert response.status_code == 200
    assert response.json()["state"] == "ready"
    assert response.json()["sourcePublicRevision"] == 2
    assert response.json()["needsUpdate"] is True


def test_member_publishes_server_compiled_revision_with_selected_presentation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    row = _public_row(article)
    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: row)
    compiled: list[tuple[dict, dict]] = []
    published: list[dict] = []

    async def compile_render(render_document: dict, presentation: dict) -> str:
        compiled.append((render_document, presentation))
        return "<p>trusted canonical HTML</p>"

    async def publish(**values) -> WxPostWechatDraftResult:
        published.append(values)
        return WxPostWechatDraftResult.model_validate(
            {
                "state": "ready",
                "action": "created",
                "sourcePublicRevision": 3,
                "presentation": values["presentation"],
                "readbackChanged": False,
                "needsUpdate": False,
                "message": None,
                "previewUrl": "https://mp.weixin.qq.com/s/test-preview",
            }
        )

    monkeypatch.setattr(wxpost_route, "_compile_trusted_render", compile_render)
    monkeypatch.setattr(wxpost_route, "publish_wechat_draft", publish)
    selected = {
        "layout": "brand-default",
        "palette": "paper-neutral",
        "appearance": "dark",
        "typeface": "modern-sans",
    }

    response = client.post(
        f"/posts/wxposts/{row['id']}/wechat-draft",
        json={"expectedPublicRevision": 3, "presentation": selected, "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["action"] == "created"
    assert compiled[0][1] == selected
    assert published[0]["canonical_html"] == "<p>trusted canonical HTML</p>"
    assert published[0]["row"] is row


def test_wechat_publish_requires_literal_user_confirmation(
    client: TestClient,
) -> None:
    response = client.post(
        "/posts/wxposts/00000000-0000-4000-8000-000000000236/wechat-draft",
        json={
            "expectedPublicRevision": 3,
            "presentation": {
                "layout": "brand-default",
                "palette": "paper-neutral",
                "appearance": "light",
                "typeface": "modern-sans",
            },
            "confirmed": False,
        },
    )

    assert response.status_code == 422


def test_wechat_publish_rejects_a_stale_public_revision_before_rendering(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    row = _public_row(article, revision=4)
    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: row)

    response = client.post(
        f"/posts/wxposts/{row['id']}/wechat-draft",
        json={"expectedPublicRevision": 3, "presentation": article["presentation"], "confirmed": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "The Public Revision changed before WeChat publishing started."


def test_member_can_reset_an_uncertain_wechat_projection_after_explicit_confirmation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    row = _public_row(article)
    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: row)
    reset_workspaces: list[str] = []

    def reset(workspace_id: str) -> dict:
        reset_workspaces.append(workspace_id)
        return {
            "state": "idle",
            "source_public_revision": None,
            "presentation": None,
            "readback_changed": None,
            "last_error": None,
        }

    monkeypatch.setattr(wxpost_route.wxpost_wechat_store, "reset_uncertain_projection", reset)

    response = client.post(
        f"/posts/wxposts/{row['id']}/wechat-draft/reset-uncertain",
        json={"expectedPublicRevision": 3, "confirmedNoDraft": True},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "not-created"
    assert reset_workspaces == ["wxpost-abc"]


def test_wechat_uncertain_reset_requires_literal_confirmation(client: TestClient) -> None:
    response = client.post(
        "/posts/wxposts/00000000-0000-4000-8000-000000000236/wechat-draft/reset-uncertain",
        json={"expectedPublicRevision": 3, "confirmedNoDraft": False},
    )

    assert response.status_code == 422


def test_member_opens_the_link_refetched_from_the_linked_wechat_draft(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article = json.loads(WXPOST_FIXTURE.read_text())
    row = _public_row(article)
    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: row)

    async def preview_url(workspace_id: str) -> str:
        assert workspace_id == "wxpost-abc"
        return "https://mp.weixin.qq.com/s/test-preview"

    monkeypatch.setattr(wxpost_route, "get_preview_url", preview_url)

    response = client.post(f"/posts/wxposts/{row['id']}/wechat-draft/preview")

    assert response.status_code == 200
    assert response.json() == {"previewUrl": "https://mp.weixin.qq.com/s/test-preview"}
