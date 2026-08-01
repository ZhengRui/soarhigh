import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

import app.api.routes.wxpost as wxpost_route
from app.api.serv import app
from app.models.users import User


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
        ("POST", "/workspaces/wxpost-abc/draft/save"),
        ("POST", "/workspaces/wxpost-abc/draft/generate"),
        ("POST", "/workspaces/wxpost-abc/draft/chat"),
    ]
