from __future__ import annotations

import base64
import hashlib
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Generator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from wxpost_controller.core import (
    InvalidRequest,
    InvalidWorkspace,
    SourceReferencedByDraft,
    UpstreamUnavailable,
    VersionConflict,
    WorkspaceAlreadyExists,
    WorkspaceController,
)
from wxpost_controller.http_server import build_server

MEETING_ID = "meeting-462"
SECOND_MEETING_ID = "meeting-461"
EDITORIAL = {
    "articleType": "meeting-recap",
    "customArticleType": None,
    "writingApproach": "chronological",
    "transcript": "",
    "extraNotes": "",
    "writingGuidance": "",
    "voiceTone": {"presets": [], "customProfiles": []},
}
CREATOR = {"id": "member-123", "name": "Test Member"}
RED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAADElEQVR4nGP8zwACAAYIAQFazwZIAAAAAElFTkSuQmCC"
)


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
                            "sizeBytes": len(RED_PNG),
                        }
                    ]
                }
            )
            return
        if self.path == "/assets/photo.jpg":
            body = RED_PNG
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


def test_workspace_report_and_display_media_use_one_canonical_catalog(
    tmp_path: Path,
) -> None:
    media = [
        _media(
            "meetings/462/first.jpg",
            "first.jpg",
            size=len(RED_PNG),
            uploaded_at="2026-07-20T09:00:00Z",
        ),
        _media(
            "meetings/462/second.mp4",
            "second.mp4",
            size=5,
            uploaded_at="2026-07-20T10:00:00Z",
            mime_type="video/mp4",
        ),
    ]
    files = {
        "https://assets.example/first.jpg": RED_PNG,
        "https://assets.example/second.mp4": b"video",
    }
    controller = WorkspaceController(
        tmp_path,
        article_validator=lambda document: document,
        meeting_media_loader=lambda meeting_id: (
            list(media) if meeting_id == MEETING_ID else []
        ),
        meeting_context_loader=lambda meeting_id: {
            "id": meeting_id,
            "no": 462,
            "theme": "Belonging",
        },
        source_loader=lambda url: files[url],
    )
    created = _bootstrap(controller)
    imported = controller.import_source(
        "material-workspace",
        expected_manifest_version=created["manifest"]["manifestVersion"],
        source_id="M01",
    )
    included = controller.set_source_included(
        "material-workspace",
        expected_manifest_version=imported["manifestVersion"],
        source_id="M01",
        included=True,
    )
    controller.save_draft(
        "material-workspace",
        expected_manifest_version=included["manifestVersion"],
        expected_draft_version=0,
        document=_draft("M01"),
        refresh_source_snapshot=True,
    )

    report = controller.get_workspace_report("material-workspace")
    displayed = controller.read_materials_for_display("material-workspace")

    assert report["source"]["kind"] == "meeting"
    assert report["source"]["meetingId"] == MEETING_ID
    assert report["source"]["meeting"]["id"] == MEETING_ID
    assert report["source"]["meeting"]["no"] == 462
    assert report["source"]["meeting"]["theme"] == "Belonging"
    assert report["counts"] == {
        "total": 2,
        "candidates": 1,
        "imported": 1,
        "included": 1,
        "draftMedia": 1,
    }
    assert [
        (
            item["id"],
            item["candidate"],
            item["imported"],
            item["usedInDraft"],
            item["usedAsCover"],
        )
        for item in report["materials"]
    ] == [
        ("M01", False, True, True, True),
        ("M02", True, False, False, False),
    ]
    assert report["draft"] == {
        "version": 1,
        "mediaIds": ["M01"],
        "coverMediaId": "M01",
    }
    assert report["publication"]["state"] == "unavailable"
    assert [item["source"]["id"] for item in displayed] == ["M01", "M02"]
    assert [item["data"] for item in displayed] == [RED_PNG, b"video"]


def _bootstrap(
    controller: WorkspaceController,
    workspace_id: str = "material-workspace",
) -> dict[str, Any]:
    return controller.bootstrap_workspace(
        workspace_id,
        meeting_id=MEETING_ID,
        editorial=EDITORIAL,
        created_by=CREATOR,
    )


def _draft(source_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "title": "Meeting recap",
        "articleType": "meeting-recap",
        "customArticleType": None,
        "sourceMeetingId": MEETING_ID,
        "bodyMarkdown": (
            f"A short recap.\n\n:::gallery\nitems:\n  - {source_id}\n:::\n"
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


def test_bootstrap_registers_stable_references_and_is_create_only(
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

    media.append(dict(media[0]))
    with pytest.raises(WorkspaceAlreadyExists):
        _bootstrap(controller)


def test_workspace_list_and_delete_expose_collaboration_metadata(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    workspace_id = "shared-workspace"

    created = _bootstrap(controller, workspace_id)["manifest"]
    assert created["schemaVersion"] == 5
    assert created["createdBy"] == CREATOR
    assert created["createdAt"] == created["updatedAt"]

    listing = controller.list_workspaces()
    assert listing == {
        "items": [
            {
                "workspaceId": workspace_id,
                "createdBy": CREATOR,
                "createdAt": created["createdAt"],
                "updatedAt": created["updatedAt"],
                "meetingId": MEETING_ID,
                "articleType": "meeting-recap",
                "customArticleType": None,
                "manifestVersion": 1,
                "sourceCount": 0,
                "readySourceCount": 0,
                "includedSourceCount": 0,
                "draftVersion": None,
                "draftExcerpt": None,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 10,
        "pages": 1,
    }

    deleted = controller.delete_workspace(
        workspace_id,
        expected_manifest_version=created["manifestVersion"],
    )
    assert deleted["workspaceId"] == workspace_id
    assert deleted["deleted"] is True
    assert not (tmp_path / "inbox" / workspace_id).exists()
    assert controller.list_workspaces() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 10,
        "pages": 1,
    }


def test_workspace_list_includes_latest_draft_excerpt(tmp_path: Path) -> None:
    controller = _controller(tmp_path, [], {})
    workspace_id = "workspace-with-draft"
    created = _bootstrap(controller, workspace_id)["manifest"]
    controller.save_draft(
        workspace_id,
        expected_manifest_version=created["manifestVersion"],
        expected_draft_version=0,
        document={
            "excerpt": None,
            "articleType": "meeting-recap",
            "customArticleType": None,
            "sourceMeetingId": MEETING_ID,
            "bodyMarkdown": (
                "## A shared beginning\n\n"
                "Members arrived ready to listen and learn together.\n\n"
                ":::takeaway\nA semantic block is omitted from the preview.\n:::"
            ),
            "media": [],
            "coverMediaId": None,
        },
    )

    summary = controller.list_workspaces()["items"][0]

    assert summary["draftVersion"] == 1
    assert summary["draftExcerpt"] == (
        "A shared beginning Members arrived ready to listen and learn together."
    )

    controller.save_draft(
        workspace_id,
        expected_manifest_version=created["manifestVersion"],
        expected_draft_version=1,
        document={
            "excerpt": "A concise editorial summary.",
            "articleType": "meeting-recap",
            "customArticleType": None,
            "sourceMeetingId": MEETING_ID,
            "bodyMarkdown": "This body should not replace the explicit excerpt.",
            "media": [],
            "coverMediaId": None,
        },
    )

    updated_summary = controller.list_workspaces()["items"][0]
    assert updated_summary["draftVersion"] == 2
    assert updated_summary["draftExcerpt"] == "A concise editorial summary."


def test_workspace_list_is_paginated_by_latest_creation(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    for index in range(12):
        workspace_id = f"wxpost-{index:02d}"
        _bootstrap(controller, workspace_id)
        manifest_path = tmp_path / "inbox" / workspace_id / "source-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["createdAt"] = f"2026-01-01T00:00:{index:02d}Z"
        manifest["updatedAt"] = f"2026-01-02T00:00:{11 - index:02d}Z"
        manifest_path.write_text(json.dumps(manifest))

    listing = controller.list_workspaces(page=2, page_size=5)

    assert listing["total"] == 12
    assert listing["page"] == 2
    assert listing["page_size"] == 5
    assert listing["pages"] == 3
    assert [item["workspaceId"] for item in listing["items"]] == [
        "wxpost-06",
        "wxpost-05",
        "wxpost-04",
        "wxpost-03",
        "wxpost-02",
    ]

    with pytest.raises(InvalidRequest, match="workspace pagination"):
        controller.list_workspaces(page=0)
    with pytest.raises(InvalidRequest, match="workspace pagination"):
        controller.list_workspaces(page_size=101)


def test_workspace_list_skips_unreadable_entries_and_delete_rejects_stale_version(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    controller = _controller(tmp_path, [], {})
    workspace_id = "wxpost-readable"
    created = _bootstrap(controller, workspace_id)["manifest"]
    (tmp_path / "inbox" / "wxpost-incomplete").mkdir()

    assert [item["workspaceId"] for item in controller.list_workspaces()["items"]] == [
        workspace_id
    ]
    assert "Skipping unreadable WxPost workspace wxpost-incomplete" in caplog.text

    with pytest.raises(VersionConflict):
        controller.delete_workspace(
            workspace_id,
            expected_manifest_version=created["manifestVersion"] + 1,
        )
    assert (tmp_path / "inbox" / workspace_id).exists()


def test_bootstrap_rejects_bad_upstream_metadata(
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
    media.append(dict(media[0]))
    with pytest.raises(UpstreamUnavailable, match="duplicate fileKey"):
        controller.bootstrap_workspace(
            "another-workspace",
            meeting_id=MEETING_ID,
            editorial=EDITORIAL,
            created_by=CREATOR,
        )
    assert not (tmp_path / "inbox" / "another-workspace").exists()


def test_workspace_update_rejects_fixed_setup_changes_and_preserves_uploads(
    tmp_path: Path,
) -> None:
    media_by_meeting = {
        MEETING_ID: [
            _media(
                "meetings/462/photo.jpg",
                "photo.jpg",
                size=len(RED_PNG),
                uploaded_at="2026-07-20T09:00:00Z",
            )
        ],
        SECOND_MEETING_ID: [
            _media(
                "meetings/461/workshop.jpg",
                "workshop.jpg",
                size=8,
                uploaded_at="2026-07-13T09:00:00Z",
            )
        ],
    }
    controller = WorkspaceController(
        tmp_path,
        article_validator=lambda document: document,
        meeting_media_loader=lambda meeting_id: list(
            media_by_meeting.get(meeting_id, [])
        ),
        source_loader=lambda url: {"https://assets.example/photo.jpg": RED_PNG}[url],
    )
    created = _bootstrap(controller)["manifest"]
    assert created["workspaceId"] == "material-workspace"

    imported = controller.import_source(
        "material-workspace",
        expected_manifest_version=1,
        source_id="M01",
    )
    uploaded = controller.upload_source(
        "material-workspace",
        expected_manifest_version=imported["manifestVersion"],
        origin="web-upload",
        filename="member-note.png",
        mime_type="image/png",
        data=RED_PNG,
    )
    assert [source["id"] for source in uploaded["sources"]] == ["M01", "M02"]

    with pytest.raises(InvalidRequest, match="meeting/source is fixed"):
        controller.update_workspace(
            "material-workspace",
            expected_manifest_version=uploaded["manifestVersion"],
            meeting_id=SECOND_MEETING_ID,
            editorial=EDITORIAL,
        )
    with pytest.raises(InvalidRequest, match="article type is fixed"):
        controller.update_workspace(
            "material-workspace",
            expected_manifest_version=uploaded["manifestVersion"],
            meeting_id=MEETING_ID,
            editorial={**EDITORIAL, "articleType": "member-story"},
        )
    manifest = controller.get_context("material-workspace")["manifest"]
    assert manifest["meetingId"] == MEETING_ID
    assert manifest["editorial"]["articleType"] == "meeting-recap"
    assert manifest["manifestVersion"] == 3
    assert manifest["nextMaterialNumber"] == 3
    workspace = tmp_path / "inbox" / "material-workspace"
    assert (workspace / "sources" / "M01.jpg").read_bytes() == RED_PNG
    assert (workspace / "sources" / "M02.png").read_bytes() == RED_PNG


def test_workspace_update_is_version_checked_and_idempotent(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    created = _bootstrap(controller)

    unchanged = controller.update_workspace(
        "material-workspace",
        expected_manifest_version=1,
        meeting_id=MEETING_ID,
        editorial=EDITORIAL,
    )
    assert unchanged == created

    first = controller.update_workspace(
        "material-workspace",
        expected_manifest_version=1,
        meeting_id=MEETING_ID,
        editorial={**EDITORIAL, "extraNotes": "Saved notes."},
    )
    assert first["manifest"]["manifestVersion"] == 2
    with pytest.raises(VersionConflict):
        controller.update_workspace(
            "material-workspace",
            expected_manifest_version=1,
            meeting_id=MEETING_ID,
            editorial={**EDITORIAL, "extraNotes": "Stale notes."},
        )
    unchanged_again = controller.update_workspace(
        "material-workspace",
        expected_manifest_version=2,
        meeting_id=MEETING_ID,
        editorial={**EDITORIAL, "extraNotes": "Saved notes."},
    )
    assert unchanged_again == first


def test_stale_materials_save_conflicts_before_a_deleted_source_is_applied(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    uploaded = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="temporary.png",
        mime_type="image/png",
        data=RED_PNG,
    )
    source_id = uploaded["sources"][0]["id"]
    controller.delete_source(
        "material-workspace",
        expected_manifest_version=uploaded["manifestVersion"],
        source_id=source_id,
    )

    with pytest.raises(VersionConflict):
        controller.update_workspace(
            "material-workspace",
            expected_manifest_version=uploaded["manifestVersion"],
            meeting_id=MEETING_ID,
            editorial=EDITORIAL,
            source_updates=[
                {
                    "sourceId": source_id,
                    "included": False,
                    "description": "Stale description.",
                    "descriptionSource": "user",
                    "descriptionStatus": "confirmed",
                }
            ],
        )

    with pytest.raises(VersionConflict):
        controller.delete_source_preflight(
            "material-workspace",
            expected_manifest_version=uploaded["manifestVersion"],
            source_id=source_id,
        )


def test_import_and_include_materialize_exactly_once(
    tmp_path: Path,
) -> None:
    photo = RED_PNG
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


def test_source_description_context_exposes_one_ready_image_and_meeting_facts(
    tmp_path: Path,
) -> None:
    photo = RED_PNG
    controller = WorkspaceController(
        tmp_path,
        article_validator=lambda document: document,
        meeting_media_loader=lambda meeting_id: [
            _media(
                "meetings/462/photo.jpg",
                "photo.jpg",
                size=len(photo),
                uploaded_at="2026-07-20T09:00:00Z",
            )
        ],
        meeting_context_loader=lambda meeting_id: {
            "id": meeting_id,
            "theme": "Culture in Every Voice",
            "introduction": "A meeting about belonging.",
            "segments": [
                {
                    "type": "Table Topics",
                    "start_time": "20:00",
                    "end_time": "20:30",
                    "title": "Speak from experience",
                    "content": "",
                }
            ],
        },
        source_loader=lambda url: photo,
    )
    _bootstrap(controller)

    with pytest.raises(InvalidRequest, match="not available"):
        controller.get_source_description_context(
            "material-workspace",
            expected_manifest_version=1,
            source_id="M01",
        )

    controller.import_source(
        "material-workspace",
        expected_manifest_version=1,
        source_id="M01",
    )
    result = controller.get_source_description_context(
        "material-workspace",
        expected_manifest_version=2,
        source_id="M01",
    )

    assert result["source"] == {
        "id": "M01",
        "filename": "photo.jpg",
        "mimeType": "image/jpeg",
        "path": "sources/M01.jpg",
    }
    assert result["meetingContext"]["theme"] == "Culture in Every Voice"
    assert result["meetingContext"]["introduction"] == ("A meeting about belonging.")
    assert result["meetingContext"]["agenda"][0]["title"] == ("Speak from experience")
    controller.assert_source_description_target(
        "material-workspace",
        expected_manifest_version=2,
        source_id="M01",
        expected_source_revision=result["sourceRevision"],
    )

    controller.update_sources(
        "material-workspace",
        expected_manifest_version=2,
        updates=[
            {
                "sourceId": "M01",
                "description": "Changed elsewhere.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )
    with pytest.raises(VersionConflict, match="current manifest version is 3"):
        controller.assert_source_description_target(
            "material-workspace",
            expected_manifest_version=2,
            source_id="M01",
            expected_source_revision=result["sourceRevision"],
        )


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
    ).read_bytes() == RED_PNG
    assert _MeetingMediaHandler.authorizations == [
        (f"/meetings/{MEETING_ID}/media", "Bearer service-token"),
        (f"/meetings/{MEETING_ID}/media", "Bearer service-token"),
        ("/assets/photo.jpg", None),
    ]


def test_include_nonready_source_downloads_and_includes_in_one_version(
    tmp_path: Path,
) -> None:
    photo = RED_PNG
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    monkeypatch.setenv("WXPOST_UPLOAD_CACHE_ROOTS", str(incoming))
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
        "contentSha256": "ab5aa97074c454a0632057e704220d9a6678fbf773a0a5806fc09b8173b07309",
        "dimensions": None,
        "workspaceReady": True,
        "included": False,
        "description": "",
        "descriptionSource": None,
        "descriptionStatus": "missing",
    }
    assert (
        tmp_path / "inbox/material-workspace/sources/M01.txt"
    ).read_bytes() == b"notes"

    (incoming / "clip.mp4").write_bytes(b"video")
    feishu = controller.upload_sources_from_paths(
        "material-workspace",
        expected_manifest_version=2,
        message_id="om_upload",
        attachments=[{"sourcePath": str(incoming / "clip.mp4")}],
    )
    assert feishu["sourceIds"] == ["M02"]
    assert feishu["manifest"]["sources"][1]["kind"] == "video"
    assert feishu["manifest"]["nextMaterialNumber"] == 3
    assert (
        tmp_path / "inbox/material-workspace/sources/M02.mp4"
    ).read_bytes() == b"video"

    workspace_file = tmp_path / "inbox/material-workspace/sources/M01.txt"
    with pytest.raises(InvalidRequest, match="configured upload cache"):
        controller.upload_sources_from_paths(
            "material-workspace",
            expected_manifest_version=3,
            message_id="om_cross_workspace_path",
            attachments=[{"sourcePath": str(workspace_file)}],
        )

    outside = tmp_path.parent / "outside-upload.txt"
    outside.write_bytes(b"outside")
    try:
        with pytest.raises(InvalidRequest, match="configured upload cache"):
            controller.upload_sources_from_paths(
                "material-workspace",
                expected_manifest_version=3,
                message_id="om_outside",
                attachments=[{"sourcePath": str(outside)}],
            )
    finally:
        outside.unlink()


def test_workspace_ready_source_can_be_read_with_its_declared_mime_type(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    uploaded = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="cover.jpg",
        mime_type="image/jpeg",
        data=RED_PNG,
    )

    assert controller.read_source(
        "material-workspace",
        source_id="M01",
    ) == (RED_PNG, "image/jpeg", uploaded["sources"][0]["contentSha256"])

    manifest = json.loads(
        (tmp_path / "inbox/material-workspace/source-manifest.json").read_text()
    )
    manifest["sources"][0]["sizeBytes"] = 99
    (tmp_path / "inbox/material-workspace/source-manifest.json").write_text(
        json.dumps(manifest)
    )
    with pytest.raises(InvalidWorkspace, match="size"):
        controller.read_source("material-workspace", source_id="M01")


def test_nonready_meeting_reference_cannot_be_read_from_workspace(
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
    controller = _controller(tmp_path, media, {})
    _bootstrap(controller)

    with pytest.raises(InvalidRequest, match="not available"):
        controller.read_source("material-workspace", source_id="M01")


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
        data=RED_PNG,
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
        expected_manifest_version=3,
        source_id="M01",
    )
    assert preflight == {
        "sourceId": "M01",
        "manifestVersion": 3,
        "draftVersion": 1,
        "blockedByDraft": True,
        "references": ["media.0", "coverMediaId"],
    }
    with pytest.raises(SourceReferencedByDraft) as confirmation:
        controller.delete_source(
            "material-workspace",
            expected_manifest_version=3,
            source_id="M01",
        )
    assert confirmation.value.references == preflight["references"]

    with pytest.raises(SourceReferencedByDraft):
        controller.delete_source(
            "material-workspace",
            expected_manifest_version=3,
            source_id="M01",
        )
    assert (tmp_path / "inbox/material-workspace/sources/M01.jpg").exists()
    assert controller.get_context("material-workspace")["draft"] == saved


def test_delete_ignores_material_id_used_as_plain_article_text(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    manifest = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="source.jpg",
        mime_type="image/jpeg",
        data=RED_PNG,
        description="A confirmed photo.",
        description_source="user",
        description_status="confirmed",
    )
    document = _draft("M01")
    document["bodyMarkdown"] = "## Image sources\n\nM01 — public domain"
    document["media"] = []
    document["coverMediaId"] = None
    controller.save_draft(
        "material-workspace",
        expected_manifest_version=manifest["manifestVersion"],
        expected_draft_version=0,
        document=document,
    )

    preflight = controller.delete_source_preflight(
        "material-workspace",
        expected_manifest_version=manifest["manifestVersion"],
        source_id="M01",
    )

    assert preflight["blockedByDraft"] is False
    assert preflight["references"] == []
    controller.delete_source(
        "material-workspace",
        expected_manifest_version=manifest["manifestVersion"],
        source_id="M01",
    )
    assert controller.get_context("material-workspace")["manifest"]["sources"] == []


def test_meeting_source_delete_keeps_reference_and_can_reimport(
    tmp_path: Path,
) -> None:
    photo = RED_PNG
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
            data=RED_PNG,
        )

    context = _controller(tmp_path, [], {}).get_context("material-workspace")
    source_path = tmp_path / "inbox/material-workspace/sources/M01.jpg"
    if manifest_replaced:
        assert context["manifest"]["sources"][0]["id"] == "M01"
        assert source_path.read_bytes() == RED_PNG
    else:
        assert context["manifest"]["sources"] == []
        assert not source_path.exists()


def test_source_checksums_returns_md5_for_ready_sources(tmp_path: Path) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    data = b"public image bytes"
    uploaded = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="notes.txt",
        mime_type="text/plain",
        data=data,
    )
    source_id = uploaded["sources"][0]["id"]

    result = controller.source_checksums("material-workspace", source_ids=[source_id])

    assert result == {"checksums": {source_id: hashlib.md5(data).hexdigest()}}


def test_source_checksums_rejects_unknown_source(tmp_path: Path) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)

    with pytest.raises(InvalidRequest):
        controller.source_checksums("material-workspace", source_ids=["M99"])


def test_source_checksums_rejects_not_ready_source(tmp_path: Path) -> None:
    media = [
        _media(
            "meetings/462/photo.jpg",
            "photo.jpg",
            size=5,
            uploaded_at="2026-07-20T09:00:00Z",
        )
    ]
    controller = _controller(tmp_path, media, {})
    _bootstrap(controller)

    with pytest.raises(InvalidRequest):
        controller.source_checksums("material-workspace", source_ids=["M01"])


def test_source_checksums_rejects_corrupted_file(tmp_path: Path) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    uploaded = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="cover.jpg",
        mime_type="image/jpeg",
        data=RED_PNG,
    )
    source_id = uploaded["sources"][0]["id"]
    source_path = tmp_path / "inbox/material-workspace/sources/M01.jpg"
    source_path.write_bytes(b"tampered bytes!!!!")

    with pytest.raises(InvalidWorkspace):
        controller.source_checksums("material-workspace", source_ids=[source_id])


def test_source_checksums_bounds_id_count(tmp_path: Path) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)

    with pytest.raises(InvalidRequest):
        controller.source_checksums("material-workspace", source_ids=[])
    with pytest.raises(InvalidRequest):
        controller.source_checksums("material-workspace", source_ids=["M01"] * 65)


def _checksums_json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = "contract-token",
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_http_source_checksums_returns_md5_and_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path, [], {})
    _bootstrap(controller)
    data = b"public image bytes"
    uploaded = controller.upload_source(
        "material-workspace",
        expected_manifest_version=1,
        origin="web-upload",
        filename="notes.txt",
        mime_type="text/plain",
        data=data,
    )
    source_id = uploaded["sources"][0]["id"]

    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token="contract-token",
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    url = f"{base_url}/workspaces/material-workspace/sources/checksums"
    try:
        status, body = _checksums_json_request(
            url,
            method="POST",
            payload={"sourceIds": [source_id]},
        )
        assert status == 200
        assert body == {"checksums": {source_id: hashlib.md5(data).hexdigest()}}

        status, rejected = _checksums_json_request(
            url,
            method="POST",
            payload={"sourceIds": [source_id], "x": 1},
        )
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert rejected["error"]["code"] == "invalid_request"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
