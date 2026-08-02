import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.api.routes.post as post_route
import app.api.routes.wxpost as wxpost_route
from app.api.serv import app
from app.db.wxpost import WxPostRevisionConflictError
from app.models.wxpost import ArticleDocument, WxPostPublicDetail
from app.services.wxpost_document import validate_and_parse

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wxpost-meeting-recap-v1.json"
WXPOST_ID = UUID("00000000-0000-4000-8000-000000000236")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def article() -> dict:
    payload = json.loads(FIXTURE_PATH.read_text())
    payload["sourceMeetingId"] = None
    return payload


def _row(
    article: dict,
    *,
    revision: int = 1,
    workspace_id: str | None = None,
) -> dict:
    return {
        "id": str(WXPOST_ID),
        "slug": "the-courage-to-try-the-next-sentence",
        "article_revision": revision,
        "default_presentation": article["presentation"],
        "source_workspace_id": workspace_id,
    }


def _authorize(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "test-service-token")
    return {"Authorization": "Bearer test-service-token"}


def test_create_requires_the_scoped_service_credential(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "test-service-token")

    response = client.post("/posts/wxposts", json={"document": article})

    assert response.status_code == 401


def test_create_is_disabled_until_the_service_credential_is_configured(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_route, "WXPOST_SERVICE_TOKEN", "")

    response = client.post("/posts/wxposts", json={"document": article})

    assert response.status_code == 503


def test_create_validates_and_returns_the_stable_preview_link(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[ArticleDocument] = []
    monkeypatch.setattr(wxpost_route, "WXPOST_PUBLIC_BASE_URL", "https://soarhigh.example")

    def create(document: ArticleDocument) -> dict:
        captured.append(document)
        return _row(article)

    monkeypatch.setattr(wxpost_route, "create_wxpost", create)

    response = client.post(
        "/posts/wxposts",
        headers=_authorize(monkeypatch),
        json={"document": article},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(WXPOST_ID),
        "slug": "the-courage-to-try-the-next-sentence",
        "article_revision": 1,
        "preview_url": ("https://soarhigh.example/posts/wxposts/" "the-courage-to-try-the-next-sentence"),
    }
    assert captured[0].body_markdown == article["bodyMarkdown"]


def test_create_rejects_a_non_uuid_meeting_association(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    article["sourceMeetingId"] = "meeting-236"

    response = client.post(
        "/posts/wxposts",
        headers=_authorize(monkeypatch),
        json={"document": article},
    )

    assert response.status_code == 422
    assert "meeting UUID" in response.json()["detail"]


def test_update_retains_the_stored_presentation_when_omitted(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_document = copy.deepcopy(article)
    update_document.pop("presentation")
    update_document["title"] = "A Revised Title"
    captured: list[ArticleDocument] = []

    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: _row(article, revision=4))

    def update(wxpost_id, expected_revision, document: ArticleDocument) -> dict:
        captured.append(document)
        return _row(article, revision=5)

    monkeypatch.setattr(wxpost_route, "update_wxpost", update)

    response = client.patch(
        f"/posts/wxposts/{WXPOST_ID}",
        headers=_authorize(monkeypatch),
        json={"expected_revision": 4, "document": update_document},
    )

    assert response.status_code == 200
    assert response.json()["article_revision"] == 5
    assert captured[0].presentation.model_dump(by_alias=True) == article["presentation"]
    assert captured[0].title == "A Revised Title"


def test_update_maps_a_stale_revision_to_conflict(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_route, "get_wxpost_by_id", lambda wxpost_id: _row(article, revision=5))

    def conflict(*args, **kwargs):
        raise WxPostRevisionConflictError

    monkeypatch.setattr(wxpost_route, "update_wxpost", conflict)

    response = client.patch(
        f"/posts/wxposts/{WXPOST_ID}",
        headers=_authorize(monkeypatch),
        json={"expected_revision": 4, "document": article},
    )

    assert response.status_code == 409


def test_update_rejects_a_workspace_managed_public_projection(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wxpost_route,
        "get_wxpost_by_id",
        lambda wxpost_id: _row(article, revision=5, workspace_id="wxpost-abc"),
    )

    response = client.patch(
        f"/posts/wxposts/{WXPOST_ID}",
        headers=_authorize(monkeypatch),
        json={"expected_revision": 5, "document": article},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == ("Workspace-linked WxPosts must be updated through publication sync.")


def test_public_read_returns_the_backend_render_document(
    client: TestClient,
    article: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = ArticleDocument.model_validate(article)
    now = datetime.now(timezone.utc)
    detail = WxPostPublicDetail(
        id=WXPOST_ID,
        slug="the-courage-to-try-the-next-sentence",
        is_public=True,
        article_revision=3,
        context_label="Meeting Recap",
        created_at=now,
        updated_at=now,
        render_document=validate_and_parse(document).render_document(document),
    )
    monkeypatch.setattr(wxpost_route, "get_public_wxpost_by_slug", lambda slug: detail)

    response = client.get("/posts/wxposts/the-courage-to-try-the-next-sentence")

    assert response.status_code == 200
    assert response.json()["article_revision"] == 3
    assert response.json()["context_label"] == "Meeting Recap"
    assert response.json()["render_document"]["renderVersion"] == 1
    assert response.json()["render_document"]["title"] == article["title"]


def test_public_read_hides_missing_or_non_public_rows(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wxpost_route, "get_public_wxpost_by_slug", lambda slug: None)

    response = client.get("/posts/wxposts/not-public")

    assert response.status_code == 404


def test_posts_index_forwards_the_content_source_filter(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict] = []

    def list_content(**kwargs) -> dict:
        captured.append(kwargs)
        return {
            "items": [],
            "total": 0,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "pages": 0,
        }

    monkeypatch.setattr(post_route, "get_content_items", list_content)
    app.dependency_overrides[post_route.get_optional_user] = lambda: None
    try:
        response = client.get("/posts?kind=wxpost&page=2&page_size=5")
    finally:
        app.dependency_overrides.pop(post_route.get_optional_user, None)

    assert response.status_code == 200
    assert captured == [
        {
            "kind": "wxpost",
            "user_id": None,
            "page": 2,
            "page_size": 5,
        }
    ]
