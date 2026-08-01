from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.routes.meeting as meeting_route
from app.api.serv import app

MEETING_ID = "0facf243-38cb-41dc-b65a-321fad1f6b16"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_meeting_media_exposes_import_metadata_to_the_scoped_service(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    prefix = f"public/meetings/{MEETING_ID}/media/"
    monkeypatch.setattr(meeting_route, "WXPOST_SERVICE_TOKEN", "service-token")

    def get_meeting(meeting_id: str, user_id: str | None = None):
        captured.update(meeting_id=meeting_id, user_id=user_id)
        return {"id": meeting_id}

    monkeypatch.setattr(meeting_route, "get_meeting_by_id", get_meeting)
    monkeypatch.setattr(meeting_route.oss2, "Auth", lambda key, secret: object())
    monkeypatch.setattr(
        meeting_route.oss2,
        "Bucket",
        lambda auth, endpoint, bucket: object(),
    )
    monkeypatch.setattr(
        meeting_route.oss2,
        "ObjectIterator",
        lambda bucket, *, prefix: [
            SimpleNamespace(
                key=f"{prefix}group photo.jpg",
                last_modified=1_753_000_000,
                size=12_345,
            )
        ],
    )

    response = client.get(
        f"/meetings/{MEETING_ID}/media",
        headers={"Authorization": "Bearer service-token"},
    )

    assert response.status_code == 200
    assert captured == {
        "meeting_id": MEETING_ID,
        "user_id": "wxpost-service",
    }
    assert response.json()["items"] == [
        {
            "filename": "group photo.jpg",
            "url": (
                f"https://{meeting_route.ALICLOUD_OSS_BUCKET}."
                f"{meeting_route.ALICLOUD_OSS_ENDPOINT}/{prefix}group%20photo.jpg"
            ),
            "fileKey": f"{prefix}group photo.jpg",
            "uploadedAt": "2025-07-20T08:26:40Z",
            "mimeType": "image/jpeg",
            "sizeBytes": 12_345,
        }
    ]


def test_meeting_detail_is_available_to_the_scoped_wxpost_service(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}
    monkeypatch.setattr(meeting_route, "WXPOST_SERVICE_TOKEN", "service-token")

    def get_meeting(meeting_id: str, user_id: str | None = None):
        captured.update(meeting_id=meeting_id, user_id=user_id)
        return {
            "id": meeting_id,
            "no": 462,
            "type": "Regular",
            "theme": "Culture in Every Voice",
            "manager": {"id": None, "name": "Rui Zheng", "member_id": ""},
            "date": "2026-07-15",
            "start_time": "19:15",
            "end_time": "21:15",
            "location": "SoarHigh Club",
            "introduction": "An evening of stories and careful listening.",
            "segments": [],
            "status": "draft",
            "awards": [],
        }

    monkeypatch.setattr(meeting_route, "get_meeting_by_id", get_meeting)

    response = client.get(
        f"/meetings/{MEETING_ID}",
        headers={"Authorization": "Bearer service-token"},
    )

    assert response.status_code == 200
    assert captured == {
        "meeting_id": MEETING_ID,
        "user_id": "wxpost-service",
    }
    assert response.json()["theme"] == "Culture in Every Voice"


def test_meeting_media_preserves_not_found_instead_of_returning_500(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        meeting_route,
        "get_meeting_by_id",
        lambda meeting_id, user_id=None: None,
    )

    response = client.get(f"/meetings/{MEETING_ID}/media")

    assert response.status_code == 404
    assert response.json() == {"detail": "Meeting not found"}
