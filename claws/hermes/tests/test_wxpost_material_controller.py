from __future__ import annotations

import json
import threading
from collections.abc import Generator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from wxpost_controller.core import (
    ConfirmationRequired,
    InvalidRequest,
    UpstreamUnavailable,
    VersionConflict,
    WorkspaceController,
)

MEETING_ID = "meeting-462"
EDITORIAL = {
    "articleType": "meeting-recap",
    "customArticleType": None,
    "writingApproach": "chronological",
    "transcript": "",
    "extraNotes": "",
    "writingGuidance": "",
}


class _MeetingMediaHandler(BaseHTTPRequestHandler):
    authorizations: list[tuple[str, str | None]] = []

    def do_GET(self) -> None:
        self.authorizations.append((self.path, self.headers.get("Authorization")))
        if self.path == f"/meetings/{MEETING_ID}/media":
            self._send_json(
                {
                    "items": [
                        {
                            "filename": "photo.jpg",
                            "url": (
                                f"http://127.0.0.1:{self.server.server_port}"
                                "/assets/photo.jpg"
                            ),
                            "fileKey": "meetings/462/photo.jpg",
                            "uploadedAt": "2026-07-20T09:00:00Z",
                            "mimeType": "image/jpeg",
                            "sizeBytes": 5,
                        }
                    ]
                }
            )
            return
        if self.path == "/assets/photo.jpg":
            body = b"photo"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def meeting_api() -> Generator[str, None, None]:
    _MeetingMediaHandler.authorizations = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MeetingMediaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _media(
    file_key: str,
    filename: str,
    *,
    size: int,
    uploaded_at: str,
    mime_type: str = "image/jpeg",
) -> dict[str, Any]:
    return {
        "filename": filename,
        "url": f"https://assets.example/{filename}",
        "fileKey": file_key,
        "uploadedAt": uploaded_at,
        "mimeType": mime_type,
        "sizeBytes": size,
    }


def _controller(
    root: Path,
    media: list[dict[str, Any]],
    files: dict[str, bytes],
) -> WorkspaceController:
    return WorkspaceController(
        root,
        article_validator=lambda document: document,
        meeting_media_loader=lambda meeting_id: (
            list(media) if meeting_id == MEETING_ID else []
        ),
        source_loader=lambda url: files[url],
    )


def _bootstrap(
    controller: WorkspaceController,
    workspace_id: str = "material-workspace",
) -> dict[str, Any]:
    return controller.bootstrap_workspace(
        workspace_id,
        meeting_id=MEETING_ID,
        editorial=EDITORIAL,
    )


def _draft(source_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "title": "Meeting recap",
        "articleType": "meeting-recap",
        "customArticleType": None,
        "sourceMeetingId": MEETING_ID,
        "bodyMarkdown": (
            "A short recap.\n\n:::gallery\nitems:\n" f"  - {source_id}\n:::\n"
        ),
        "media": [
            {
                "id": source_id,
                "kind": "image",
                "sourceUrl": f"https://assets.example/{source_id}.jpg",
                "description": "A confirmed photo.",
                "include": True,
                "order": 0,
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
        "coverMediaId": source_id,
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
    }


def test_bootstrap_registers_stable_references_and_resumes_idempotently(
    tmp_path: Path,
) -> None:
    media = [
        _media(
            "meetings/462/later.jpg",
            "later.jpg",
            size=5,
            uploaded_at="2026-07-20T10:00:00Z",
        ),
        _media(
            "meetings/462/first.jpg",
            "first.jpg",
            size=4,
            uploaded_at="2026-07-20T09:00:00Z",
        ),
    ]
    controller = _controller(tmp_path, media, {})

    created = _bootstrap(controller)
    manifest = created["manifest"]
    assert manifest["manifestVersion"] == 1
    assert manifest["nextMaterialNumber"] == 3
    assert [
        (source["id"], source["origin"]["fileKey"]) for source in manifest["sources"]
    ] == [
        ("M01", "meetings/462/first.jpg"),
        ("M02", "meetings/462/later.jpg"),
    ]
    assert all(
        not source["workspaceReady"] and not source["included"]
        for source in manifest["sources"]
    )
    assert not (tmp_path / "inbox" / "material-workspace" / "sources").exists()

    resumed = _bootstrap(controller)
    assert resumed == created

    media.pop(0)
    media.append(
        _media(
            "meetings/462/new-earliest.jpg",
            "new-earliest.jpg",
            size=3,
            uploaded_at="2026-07-20T08:00:00Z",
        )
    )
    refreshed = _bootstrap(controller)["manifest"]
    assert refreshed["manifestVersion"] == 2
    assert refreshed["nextMaterialNumber"] == 4
    assert [source["id"] for source in refreshed["sources"]] == [
        "M01",
        "M02",
        "M03",
    ]
    assert refreshed["sources"][1]["origin"]["fileKey"].endswith("later.jpg")
    assert refreshed["sources"][2]["origin"]["fileKey"].endswith("new-earliest.jpg")


def test_bootstrap_rejects_meeting_change_and_bad_upstream_metadata(
    tmp_path: Path,
) -> None:
    media = [
        _media(
            "meetings/462/photo.jpg",
            "photo.jpg",
            size=4,
            uploaded_at="2026-07-20T09:00:00Z",
        )
    ]
    controller = _controller(tmp_path, media, {})
    _bootstrap(controller)

    with pytest.raises(InvalidRequest, match="meetingId cannot change"):
        controller.bootstrap_workspace(
            "material-workspace",
            meeting_id=None,
            editorial=EDITORIAL,
        )

    media.append(dict(media[0]))
    with pytest.raises(UpstreamUnavailable, match="duplicate fileKey"):
        controller.bootstrap_workspace(
            "another-workspace",
            meeting_id=MEETING_ID,
            editorial=EDITORIAL,
        )
    assert not (tmp_path / "inbox" / "another-workspace").exists()


def test_import_and_include_materialize_exactly_once(
    tmp_path: Path,
) -> None:
    photo = b"photo"
    media = [
        _media(
            "meetings/462/photo.jpg",
            "photo.jpg",
            size=len(photo),
            uploaded_at="2026-07-20T09:00:00Z",
        )
    ]
    files = {"https://assets.example/photo.jpg": photo}
    controller = _controller(tmp_path, media, files)
    _bootstrap(controller)

    imported = controller.import_source(
        "material-workspace",
        expected_manifest_version=1,
        source_id="M01",
    )
    assert imported["manifestVersion"] == 2
    assert imported["sources"][0]["workspaceReady"] is True
    assert imported["sources"][0]["included"] is False
    source_path = tmp_path / "inbox/material-workspace/sources/M01.jpg"
    assert source_path.read_bytes() == photo

    unchanged = controller.import_source(
        "material-workspace",
        expected_manifest_version=2,
        source_id="M01",
    )
    assert unchanged["manifestVersion"] == 2

    included = controller.set_source_included(
        "material-workspace",
        expected_manifest_version=2,
        source_id="M01",
        included=True,
    )
    assert included["manifestVersion"] == 3
    assert included["sources"][0]["included"] is True

    excluded = controller.set_source_included(
        "material-workspace",
        expected_manifest_version=3,
        source_id="M01",
        included=False,
    )
    assert excluded["sources"][0]["workspaceReady"] is True
    assert excluded["sources"][0]["included"] is False
    assert source_path.exists()


def test_real_media_transport_scopes_service_token_to_the_backend(
    tmp_path: Path,
    meeting_api: str,
) -> None:
    controller = WorkspaceController(
        tmp_path,
        soarhigh_api_base_url=meeting_api,
        soarhigh_service_token="service-token",
    )
    _bootstrap(controller)
    imported = controller.import_source(
        "material-workspace",
        expected_manifest_version=1,
        source_id="M01",
    )

    assert imported["sources"][0]["workspaceReady"] is True
    assert (
        tmp_path / "inbox/material-workspace/sources/M01.jpg"
    ).read_bytes() == b"photo"
    assert _MeetingMediaHandler.authorizations == [
        (f"/meetings/{MEETING_ID}/media", "Bearer service-token"),
        (f"/meetings/{MEETING_ID}/media", "Bearer service-token"),
        ("/assets/photo.jpg", None),
    ]


def test_include_nonready_source_downloads_and_includes_in_one_version(
    tmp_path: Path,
) -> None:
    photo = b"photo"
    media = [
        _media(
            "meetings/462/photo.jpg",
            "photo.jpg",
            size=len(photo),
            uploaded_at="2026-07-20T09:00:00Z",
        )
    ]
    controller = _controller(
        tmp_path,
        media,
        {"https://assets.example/photo.jpg": photo},
    )
    _bootstrap(controller)

    manifest = controller.set_source_included(
        "material-workspace",
        expected_manifest_version=1,
        source_id="M01",
        included=True,
    )

    assert manifest["manifestVersion"] == 2
    assert manifest["sources"][0]["workspaceReady"] is True
    assert manifest["sources"][0]["included"] is True


def test_failed_import_and_stale_write_leave_state_unchanged(
    tmp_path: Path,
) -> None:
    media = [
        _media(
            "meetings/462/photo.jpg",
            "photo.jpg",
            size=5,
            uploaded_at="2026-07-20T09:00:00Z",
        )
    ]
    controller = _controller(
        tmp_path,
        media,
        {"https://assets.example/photo.jpg": b"bad"},
    )
    _bootstrap(controller)

    with pytest.raises(UpstreamUnavailable, match="size"):
        controller.import_source(
            "material-workspace",
            expected_manifest_version=1,
            source_id="M01",
        )
    context = controller.get_context("material-workspace")
    assert context["manifest"]["manifestVersion"] == 1
    assert context["manifest"]["sources"][0]["workspaceReady"] is False

    controller.update_sources(
        "material-workspace",
        expected_manifest_version=1,
        updates=[
            {
                "sourceId": "M01",
                "description": "The opening photo.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )
    with pytest.raises(VersionConflict) as conflict:
        controller.set_source_included(
            "material-workspace",
            expected_manifest_version=1,
            source_id="M01",
            included=False,
        )
    assert conflict.value.actual == 2


def test_web_and_feishu_uploads_use_high_water_ids_and_canonical_paths(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)

    web = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="notes.txt",
        mime_type="text/plain",
        data=b"notes",
    )
    assert web["sources"][0] == {
        "id": "M01",
        "kind": "transcript",
        "origin": {"type": "web-upload"},
        "filename": "notes.txt",
        "mimeType": "text/plain",
        "sizeBytes": 5,
        "workspaceReady": True,
        "included": False,
        "description": "",
        "descriptionSource": None,
        "descriptionStatus": "missing",
    }
    assert (
        tmp_path / "inbox/material-workspace/sources/M01.txt"
    ).read_bytes() == b"notes"

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "clip.mp4").write_bytes(b"video")
    feishu = controller.upload_source_from_path(
        "material-workspace",
        expected_manifest_version=2,
        source_path=str(incoming / "clip.mp4"),
        origin="feishu-upload",
        description="A short clip.",
        description_source="user",
        description_status="confirmed",
    )
    assert feishu["sources"][1]["id"] == "M02"
    assert feishu["sources"][1]["kind"] == "video"
    assert feishu["nextMaterialNumber"] == 3
    assert (
        tmp_path / "inbox/material-workspace/sources/M02.mp4"
    ).read_bytes() == b"video"

    outside = tmp_path.parent / "outside-upload.txt"
    outside.write_bytes(b"outside")
    try:
        with pytest.raises(InvalidRequest, match="WXPOST_WORKSPACE_ROOT"):
            controller.upload_source_from_path(
                "material-workspace",
                expected_manifest_version=3,
                source_path=str(outside),
                origin="feishu-upload",
            )
    finally:
        outside.unlink()


def test_delete_requires_confirmation_and_preserves_draft(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    manifest = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="cover.jpg",
        mime_type="image/jpeg",
        data=b"cover",
        description="A confirmed photo.",
        description_source="user",
        description_status="confirmed",
    )
    manifest = controller.set_source_included(
        "material-workspace",
        expected_manifest_version=manifest["manifestVersion"],
        source_id="M01",
        included=True,
    )
    saved = controller.save_draft(
        "material-workspace",
        expected_manifest_version=manifest["manifestVersion"],
        expected_draft_version=0,
        document=_draft("M01"),
    )

    preflight = controller.delete_source_preflight(
        "material-workspace",
        source_id="M01",
    )
    assert preflight == {
        "sourceId": "M01",
        "manifestVersion": 3,
        "draftVersion": 1,
        "referenced": True,
        "requiresConfirmation": True,
        "references": ["media.0", "coverMediaId", "bodyMarkdown"],
    }
    with pytest.raises(ConfirmationRequired) as confirmation:
        controller.delete_source(
            "material-workspace",
            expected_manifest_version=3,
            source_id="M01",
        )
    assert confirmation.value.references == preflight["references"]

    deleted = controller.delete_source(
        "material-workspace",
        expected_manifest_version=3,
        source_id="M01",
        confirm_referenced=True,
    )
    assert deleted["manifestVersion"] == 4
    assert deleted["nextMaterialNumber"] == 2
    assert deleted["sources"] == []
    assert not (tmp_path / "inbox/material-workspace/sources/M01.jpg").exists()
    assert controller.get_context("material-workspace")["draft"] == saved


def test_meeting_source_delete_keeps_reference_and_can_reimport(
    tmp_path: Path,
) -> None:
    photo = b"photo"
    media = [
        _media(
            "meetings/462/photo.jpg",
            "photo.jpg",
            size=len(photo),
            uploaded_at="2026-07-20T09:00:00Z",
        )
    ]
    controller = _controller(
        tmp_path,
        media,
        {"https://assets.example/photo.jpg": photo},
    )
    _bootstrap(controller)
    included = controller.set_source_included(
        "material-workspace",
        expected_manifest_version=1,
        source_id="M01",
        included=True,
    )
    deleted = controller.delete_source(
        "material-workspace",
        expected_manifest_version=included["manifestVersion"],
        source_id="M01",
    )

    source = deleted["sources"][0]
    assert source["id"] == "M01"
    assert source["origin"]["fileKey"] == "meetings/462/photo.jpg"
    assert source["workspaceReady"] is False
    assert source["included"] is False
    assert deleted["nextMaterialNumber"] == 2
    assert not (tmp_path / "inbox/material-workspace/sources/M01.jpg").exists()

    reimported = controller.import_source(
        "material-workspace",
        expected_manifest_version=deleted["manifestVersion"],
        source_id="M01",
    )
    assert reimported["sources"][0]["workspaceReady"] is True
    assert reimported["sources"][0]["id"] == "M01"


@pytest.mark.parametrize("manifest_replaced", [False, True])
def test_upload_manifest_failure_never_leaves_an_invalid_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_replaced: bool,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    original_write = controller._atomic_write_json

    def fail_manifest_write(path: Path, value: dict[str, Any]) -> None:
        if path.name == "source-manifest.json":
            if manifest_replaced:
                original_write(path, value)
            raise InvalidRequest("simulated manifest write failure")
        original_write(path, value)

    monkeypatch.setattr(controller, "_atomic_write_json", fail_manifest_write)
    with pytest.raises(InvalidRequest, match="simulated"):
        controller.upload_source(
            "material-workspace",
            expected_manifest_version=1,
            origin="web-upload",
            filename="photo.jpg",
            mime_type="image/jpeg",
            data=b"photo",
        )

    context = _controller(tmp_path, [], {}).get_context("material-workspace")
    source_path = tmp_path / "inbox/material-workspace/sources/M01.jpg"
    if manifest_replaced:
        assert context["manifest"]["sources"][0]["id"] == "M01"
        assert source_path.read_bytes() == b"photo"
    else:
        assert context["manifest"]["sources"] == []
        assert not source_path.exists()
