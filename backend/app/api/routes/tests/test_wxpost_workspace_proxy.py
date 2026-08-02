import json
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

import app.api.routes.wxpost as wxpost_route
from app.api.serv import app
from app.models.users import User
from app.models.wxpost import WxPostPublicationStatus


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
        assert timeout in {30, 330}
        assert trust_env is False
        return real_client(transport=transport)

    monkeypatch.setattr(wxpost_route, "WXPOST_CONTROLLER_URL", "http://controller")
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "controller-secret")
    monkeypatch.setattr(wxpost_route.httpx, "AsyncClient", client_factory)


def test_authenticated_workspace_bootstrap_hides_controller_credential(
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
    response = client.put(
        "/posts/wxposts/workspaces/wxpost-abc",
        headers={"Authorization": "Bearer member-token"},
        json={"meetingId": None, "editorial": {"articleType": "meeting-recap"}},
    )

    assert response.status_code == 200
    assert response.json()["workspaceId"] == "wxpost-abc"
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "PUT"
    assert str(request.url) == "http://controller/workspaces/wxpost-abc"
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
        wxpost_route,
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


def test_voice_tone_suggestion_uses_workspace_context_and_existing_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []
    hermes_calls: list[dict] = []
    workspace_context = {
        "workspaceId": "wxpost-abc",
        "manifest": {
            "editorial": {
                "articleType": "meeting-recap",
                "customArticleType": None,
                "writingGuidance": "Keep it vivid.",
                "voiceTone": {
                    "presets": ["reflective"],
                    "customProfiles": [],
                },
            }
        },
        "draft": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=workspace_context)

    async def suggest(**kwargs) -> str:
        hermes_calls.append(kwargs)
        return "Use lively details and restrained wit."

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(wxpost_route, "WXPOST_HERMES_URL", "http://hermes")
    monkeypatch.setattr(wxpost_route, "suggest_voice_tone_instruction", suggest)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/voice-tone/suggestion",
        headers={"Authorization": "Bearer member-token"},
        json={"name": "  Dry humour  "},
    )

    assert response.status_code == 200
    assert response.json() == {"instruction": "Use lively details and restrained wit."}
    assert [(request.method, request.url.path) for request in captured] == [("GET", "/workspaces/wxpost-abc/context")]
    assert hermes_calls == [
        {
            "hermes_url": "http://hermes",
            "service_token": "controller-secret",
            "profile_name": "Dry humour",
            "workspace_context": workspace_context,
        }
    ]


def test_voice_tone_suggestion_does_not_run_when_workspace_is_missing(
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

    async def should_not_run(**kwargs) -> str:
        raise AssertionError("Hermes should not run for an unknown workspace")

    _configure_controller(monkeypatch, handler)
    monkeypatch.setattr(
        wxpost_route,
        "suggest_voice_tone_instruction",
        should_not_run,
    )

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
                "Cache-Control": "private, no-store",
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
    assert content.headers["Cache-Control"] == "private, no-store"
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
        ("GET", "/draft/session", None),
        ("DELETE", "/draft/session", None),
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
        ("GET", "/workspaces/wxpost-abc/draft/session"),
        ("DELETE", "/workspaces/wxpost-abc/draft/session"),
        ("POST", "/workspaces/wxpost-abc/draft/save"),
        ("POST", "/workspaces/wxpost-abc/draft/generate"),
        ("POST", "/workspaces/wxpost-abc/draft/chat"),
    ]


def test_workspace_draft_chat_preserves_the_controller_event_stream(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = (
        'event: progress\ndata: {"stage":"request_started"}\n\n'
        'event: progress\ndata: {"stage":"activity_started",'
        '"activityId":"context-1","label":"Reading the saved Draft"}\n\n'
        'event: complete\ndata: {"reply":"Done."}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/workspaces/wxpost-abc/draft/chat"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream; charset=utf-8"},
            content=stream.encode(),
        )

    _configure_controller(monkeypatch, handler)

    response = client.post(
        "/posts/wxposts/workspaces/wxpost-abc/draft/chat",
        headers={"Authorization": "Bearer member-token"},
        json={
            "expectedManifestVersion": 3,
            "expectedDraftVersion": 1,
            "message": "How many sections are there?",
            "selectedText": None,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == stream
