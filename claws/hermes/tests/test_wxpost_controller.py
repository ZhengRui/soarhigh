from __future__ import annotations

import base64
import copy
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Generator, Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_ROOT = REPO_ROOT / "claws" / "hermes"
BACKEND_ROOT = REPO_ROOT / "backend"
FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "contract-token"
GROUP_PHOTO_ID = "M01"
SPEAKER_ID = "M02"
WEB_IMAGE_ID = "M03"
FEISHU_VIDEO_ID = "M04"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from wxpost_controller.core import (  # noqa: E402
    InvalidRequest,
    InvalidWorkspace,
    ValidationUnavailable,
    VersionConflict,
    WorkspaceController,
)
from wxpost_controller.errors import DraftStoreUnavailable  # noqa: E402
from wxpost_controller.http_server import build_server  # noqa: E402

from app.models.wxpost import (  # noqa: E402
    ArticleDocument,
    WxPostDraftEditRequest,
)
from app.services.wxpost_editing import apply_draft_edits  # noqa: E402
from app.services.wxpost_document import (  # noqa: E402
    ArticleDocumentValidationError,
    pydantic_validation_issues,
    validate_and_parse,
)


def _manifest_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "source-manifest-v5.json").read_text())


def _seed_workspace(root: Path, workspace_id: str) -> None:
    workspace = root / "inbox" / workspace_id
    workspace.mkdir(parents=True)
    manifest = _manifest_fixture()
    manifest["workspaceId"] = workspace_id
    for index, source in enumerate(manifest["sources"], start=1):
        if not source["workspaceReady"]:
            continue
        path = (
            workspace / "sources" / f"{source['id']}{Path(source['filename']).suffix}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([index]) * source["sizeBytes"])
    (workspace / "source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _article_document(*, title: str = "One Shared Workspace") -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "title": title,
        "articleType": "meeting-recap",
        "sourceMeetingId": "1cf40bec-f94d-45f4-b5df-18e3a9bffac8",
        "bodyMarkdown": (
            "The meeting began with a warm welcome.\n\n:::image\nmedia: M03\n:::"
        ),
        "media": [
            {
                "id": "M03",
                "kind": "image",
                "sourceUrl": "https://soarhigh.example/M03.jpg",
                "description": "Members welcome guests before the meeting.",
                "include": True,
                "order": 2,
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
        "presentation": {
            "layout": "brand-default",
            "palette": "paper-neutral",
            "appearance": "light",
            "typeface": "editorial-serif",
        },
    }


def _draft_proposal(
    *,
    media_ids: tuple[str, ...] = (WEB_IMAGE_ID,),
) -> dict[str, Any]:
    descriptions = {
        SPEAKER_ID: "A speaker shares a prepared story with the room.",
        WEB_IMAGE_ID: "Members welcome guests before the meeting.",
        FEISHU_VIDEO_ID: "A guest tries Table Topics for the first time.",
    }
    block_by_id = {
        SPEAKER_ID: {"type": "image", "media": SPEAKER_ID},
        WEB_IMAGE_ID: {"type": "image", "media": WEB_IMAGE_ID},
        FEISHU_VIDEO_ID: {"type": "video", "media": FEISHU_VIDEO_ID},
    }
    return {
        "schemaVersion": 2,
        "title": "One Shared Workspace",
        "excerpt": None,
        "byline": None,
        "blocks": [
            {
                "type": "markdown",
                "markdown": "The meeting began with a warm welcome.",
            },
            *(block_by_id[source_id] for source_id in media_ids),
        ],
        "media": [
            {
                "id": source_id,
                "description": descriptions[source_id],
                "credit": None,
                "people": [],
            }
            for source_id in media_ids
        ],
        "coverMediaId": next(
            (
                source_id
                for source_id in media_ids
                if source_id in {SPEAKER_ID, WEB_IMAGE_ID}
            ),
            None,
        ),
    }


def _backend_validate(document: Mapping[str, Any]) -> dict[str, Any]:
    parsed = ArticleDocument.model_validate(document)
    try:
        validate_and_parse(parsed)
    except ArticleDocumentValidationError as exc:
        issue = exc.errors[0]
        path = ".".join(str(part) for part in issue.path)
        raise InvalidRequest(
            f"ArticleDocument is invalid at {path or 'root'}: {issue.message}"
        ) from exc
    return parsed.model_dump(by_alias=True, mode="json")


def _backend_edit(
    document: Mapping[str, Any],
    available_media: list[Mapping[str, Any]],
    edits: list[Mapping[str, Any]],
) -> dict[str, Any]:
    request = WxPostDraftEditRequest.model_validate(
        {
            "document": document,
            "availableMedia": available_media,
            "edits": edits,
        }
    )
    return apply_draft_edits(request).model_dump(by_alias=True, mode="json")


def _canonical_document(document: Mapping[str, Any]) -> dict[str, Any]:
    return ArticleDocument.model_validate(document).model_dump(
        by_alias=True,
        mode="json",
    )


def _controller(root: Path) -> WorkspaceController:
    return WorkspaceController(
        root,
        article_validator=_backend_validate,
        article_editor=_backend_edit,
    )


@pytest.fixture
def seeded_workspace(tmp_path: Path) -> tuple[Path, str]:
    workspace_id = "wxpost-contract-workspace"
    _seed_workspace(tmp_path, workspace_id)
    return tmp_path, workspace_id


class _ValidationHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/meetings/") and not self.path.endswith("/media"):
            self._send(
                HTTPStatus.OK,
                {
                    "id": self.path.rsplit("/", 1)[-1],
                    "no": 462,
                    "type": "Regular",
                    "theme": "Culture in Every Voice",
                    "manager": {"name": "Test Member"},
                    "date": "2026-07-15",
                    "start_time": "19:15",
                    "end_time": "21:15",
                    "location": "SoarHigh Club",
                    "introduction": "A meeting about voice and belonging.",
                    "segments": [],
                    "awards": [],
                },
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path not in {"/posts/wxposts/validate", "/posts/wxposts/edit"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request_payload = json.loads(self.rfile.read(length))
        try:
            if self.path == "/posts/wxposts/edit":
                edit_request = WxPostDraftEditRequest.model_validate(request_payload)
                parsed = apply_draft_edits(edit_request)
            else:
                parsed = ArticleDocument.model_validate(request_payload)
            parsed_article = validate_and_parse(parsed)
        except ValidationError as exc:
            errors = [
                issue.model_dump(by_alias=True, mode="json")
                for issue in pydantic_validation_issues(exc)
            ]
            self._send(
                HTTPStatus.UNPROCESSABLE_ENTITY, {"valid": False, "errors": errors}
            )
        except ArticleDocumentValidationError as exc:
            errors = [
                issue.model_dump(by_alias=True, mode="json") for issue in exc.errors
            ]
            self._send(
                HTTPStatus.UNPROCESSABLE_ENTITY, {"valid": False, "errors": errors}
            )
        else:
            self._send(
                HTTPStatus.OK,
                {
                    "valid": True,
                    "document": parsed.model_dump(by_alias=True, mode="json"),
                    "renderDocument": parsed_article.render_document(parsed).model_dump(
                        by_alias=True,
                        mode="json",
                    ),
                },
            )

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def validation_url() -> Generator[str, None, None]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ValidationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str = TOKEN,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _upload_request(
    url: str,
    *,
    filename: str,
    expected_manifest_version: int,
    data: bytes,
    mime_type: str,
) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode({'filename': filename})}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": mime_type,
            "X-Expected-Manifest-Version": str(expected_manifest_version),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _mcp_value(result) -> dict[str, Any]:
    assert not result.isError
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


def test_http_workspace_delete_requires_the_current_manifest_version(
    tmp_path: Path,
) -> None:
    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, created = _json_request(
            f"{base_url}/workspaces",
            method="POST",
            payload={
                "meetingId": None,
                "editorial": {
                    "articleType": "meeting-recap",
                    "customArticleType": None,
                    "voiceTone": {"presets": [], "customProfiles": []},
                },
                "createdBy": {"id": "member-123", "name": "Test Member"},
            },
        )
        assert status == 200
        workspace_id = created["workspaceId"]
        assert workspace_id.startswith("wxpost-")
        url = f"{base_url}/workspaces/{workspace_id}"

        status, missing = _json_request(url, method="DELETE")
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert missing["error"]["code"] == "invalid_request"

        status, stale = _json_request(
            url,
            method="DELETE",
            headers={"X-Expected-Manifest-Version": "2"},
        )
        assert status == HTTPStatus.CONFLICT
        assert stale["error"]["code"] == "version_conflict"

        status, deleted = _json_request(
            url,
            method="DELETE",
            headers={
                "X-Expected-Manifest-Version": str(
                    created["manifest"]["manifestVersion"]
                )
            },
        )
        assert status == 200
        assert deleted["deleted"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_draft_save_returns_the_complete_updated_context(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    server = build_server(
        workspace_root=str(root),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    server.controller = _controller(root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, context = _json_request(
            (
                f"http://127.0.0.1:{server.server_port}/workspaces/"
                f"{workspace_id}/draft/save"
            ),
            method="POST",
            payload={
                "expectedManifestVersion": 1,
                "expectedDraftVersion": 0,
                "document": _article_document(),
            },
        )

        assert status == 200
        assert context["workspaceId"] == workspace_id
        assert context["manifest"]["draft"]["version"] == 1
        assert context["draft"]["draftVersion"] == 1
        assert context["draft"]["document"]["title"] == "One Shared Workspace"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_draft_chat_streams_progress_before_the_complete_result(
    tmp_path: Path,
) -> None:
    class DraftService:
        def chat(self, workspace_id: str, *, on_progress, **kwargs):
            assert workspace_id == "wxpost-stream"
            on_progress(
                {
                    "stage": "activity_started",
                    "activityId": "context-1",
                    "label": "Reading the saved Draft and media",
                }
            )
            on_progress(
                {
                    "stage": "activity_completed",
                    "activityId": "context-1",
                    "label": "Reading the saved Draft and media",
                }
            )
            return {
                "workspaceId": workspace_id,
                "reply": "Saved.",
                "context": {"workspaceId": workspace_id},
                "draftChanged": True,
            }

    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    server.draft_service = DraftService()  # type: ignore[assignment]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        (f"http://127.0.0.1:{server.server_port}/workspaces/wxpost-stream/draft/chat"),
        data=json.dumps(
            {
                "expectedManifestVersion": 4,
                "expectedDraftVersion": 2,
                "operationId": "draft-0123456789abcdef0123456789abcdef",
                "message": "Tighten it.",
                "selectedText": None,
            }
        ).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode()

        assert response.headers["Content-Type"] == ("text/event-stream; charset=utf-8")
        assert body.index('"stage": "request_started"') < body.index(
            '"stage": "activity_started"'
        )
        assert body.index('"stage": "activity_started"') < body.index(
            '"stage": "activity_completed"'
        )
        assert body.index("event: progress") < body.index("event: complete")
        assert '"reply": "Saved."' in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_draft_chat_sends_heartbeats_while_hermes_is_quiet(
    tmp_path: Path,
) -> None:
    operation_started = threading.Event()
    release_operation = threading.Event()
    operation_finished = threading.Event()

    class DraftService:
        def chat(self, workspace_id: str, *, on_progress, **kwargs):
            operation_started.set()
            try:
                assert release_operation.wait(timeout=5)
                return {
                    "workspaceId": workspace_id,
                    "reply": "Saved.",
                    "context": {"workspaceId": workspace_id},
                    "draftChanged": True,
                }
            finally:
                operation_finished.set()

    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
        draft_heartbeat_seconds=0.01,
    )
    server.draft_service = DraftService()  # type: ignore[assignment]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/workspaces/wxpost-stream/draft/chat",
        data=json.dumps(
            {
                "expectedManifestVersion": 4,
                "expectedDraftVersion": 2,
                "operationId": "draft-fedcba9876543210fedcba9876543210",
                "message": "Tighten it.",
                "selectedText": None,
            }
        ).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.readline() == b"event: progress\n"
            assert b'"stage": "request_started"' in response.readline()
            assert response.readline() == b"\n"
            assert operation_started.wait(timeout=1)
            assert response.readline() == b": keep-alive\n"
            assert response.readline() == b"\n"
            assert not operation_finished.is_set()
            release_operation.set()
            body = response.read().decode()

        assert "event: complete" in body
        assert '"reply": "Saved."' in body
    finally:
        release_operation.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_exposes_non_cached_draft_operation_status(tmp_path: Path) -> None:
    operation_id = "draft-0123456789abcdef0123456789abcdef"

    class DraftService:
        def operation(self, workspace_id: str, requested_id: str):
            assert workspace_id == "wxpost-stream"
            assert requested_id == operation_id
            return {
                "workspaceId": workspace_id,
                "operationId": operation_id,
                "state": "running",
                "result": None,
                "error": None,
            }

    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    server.draft_service = DraftService()  # type: ignore[assignment]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/workspaces/"
        f"wxpost-stream/draft/operations/{operation_id}",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read())
            assert response.headers["Cache-Control"] == "private, no-store"
        assert payload["state"] == "running"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_voice_tone_suggestion_uses_tool_free_hermes_oneshot(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    requests: list[dict[str, Any]] = []

    def editorial_runner(**kwargs: Any) -> str:
        requests.append(kwargs)
        source = json.loads(kwargs["user_input"].split("\n", 1)[1])
        profile_name = source["profileName"]
        if profile_name == "Unavailable":
            raise RuntimeError("provider unavailable")
        if profile_name == "Invalid":
            return ""
        return "Use warm details and restrained wit."

    server = build_server(
        workspace_root=str(root),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
        editorial_runner=editorial_runner,
        editorial_runtime_resolver=lambda: {
            "provider": "openai-codex",
            "model": "gpt-5.6-luna",
            "api_key": "test-token",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, result = _json_request(
            (
                f"http://127.0.0.1:{server.server_port}/workspaces/"
                f"{workspace_id}/voice-tone/suggestion"
            ),
            method="POST",
            payload={"name": "  Warmly funny  "},
        )

        assert status == HTTPStatus.OK
        assert result == {"instruction": "Use warm details and restrained wit."}
        assert len(requests) == 1
        assert requests[0]["task"] == "title_generation"
        assert requests[0]["max_tokens"] == 256
        assert requests[0]["main_runtime"]["provider"] == "openai-codex"
        assert "model" not in requests[0]
        assert "tools" not in requests[0]
        source = json.loads(requests[0]["user_input"].split("\n", 1)[1])
        assert source["profileName"] == "Warmly funny"
        assert source["workspaceEditorialContext"]["articleType"] == "meeting-recap"

        missing, missing_body = _json_request(
            (
                f"http://127.0.0.1:{server.server_port}/workspaces/"
                "wxpost-missing/voice-tone/suggestion"
            ),
            method="POST",
            payload={"name": "Warm"},
        )
        assert missing == HTTPStatus.NOT_FOUND
        assert missing_body["error"]["code"] == "workspace_not_found"
        assert len(requests) == 1

        unavailable, unavailable_body = _json_request(
            (
                f"http://127.0.0.1:{server.server_port}/workspaces/"
                f"{workspace_id}/voice-tone/suggestion"
            ),
            method="POST",
            payload={"name": "Unavailable"},
        )
        invalid, invalid_body = _json_request(
            (
                f"http://127.0.0.1:{server.server_port}/workspaces/"
                f"{workspace_id}/voice-tone/suggestion"
            ),
            method="POST",
            payload={"name": "Invalid"},
        )

        assert unavailable == HTTPStatus.SERVICE_UNAVAILABLE
        assert unavailable_body["error"]["code"] == "hermes_unavailable"
        assert invalid == HTTPStatus.BAD_GATEWAY
        assert invalid_body["error"]["code"] == "hermes_turn_failed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_draft_conversation_delete_resets_only_the_assistant_history(
    tmp_path: Path,
) -> None:
    class DraftService:
        def __init__(self) -> None:
            self.workspace_ids: list[str] = []

        def reset(self, workspace_id: str) -> dict[str, Any]:
            self.workspace_ids.append(workspace_id)
            return {
                "workspaceId": workspace_id,
                "messages": [],
            }

    draft_service = DraftService()
    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    server.draft_service = draft_service  # type: ignore[assignment]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/workspaces/wxpost-reset/draft/conversation"
    try:
        unauthorized, _ = _json_request(url, method="DELETE", token="wrong")
        status, result = _json_request(url, method="DELETE")

        assert unauthorized == HTTPStatus.UNAUTHORIZED
        assert status == HTTPStatus.OK
        assert result == {
            "workspaceId": "wxpost-reset",
            "messages": [],
        }
        assert draft_service.workspace_ids == ["wxpost-reset"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_draft_conversation_reports_controller_store_unavailable(
    tmp_path: Path,
) -> None:
    class DraftService:
        @staticmethod
        def history(_workspace_id: str) -> dict[str, Any]:
            raise DraftStoreUnavailable("Draft Controller state is unavailable")

    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    server.draft_service = DraftService()  # type: ignore[assignment]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = (
        f"http://127.0.0.1:{server.server_port}/workspaces/"
        "wxpost-store-error/draft/conversation"
    )
    try:
        status, result = _json_request(url)

        assert status == HTTPStatus.SERVICE_UNAVAILABLE
        assert result["error"] == {
            "code": "draft_store_unavailable",
            "message": "Draft Controller state is unavailable",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_session_retirement_requires_auth_and_queues_cleanup(
    tmp_path: Path,
) -> None:
    class DraftService:
        def __init__(self) -> None:
            self.session_ids: list[str] = []

        def retire_session(self, session_id: str) -> dict[str, Any]:
            self.session_ids.append(session_id)
            return {"sessionId": session_id, "cleanupScheduled": True}

    draft_service = DraftService()
    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    server.draft_service = draft_service  # type: ignore[assignment]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/sessions/retire"
    try:
        unauthorized, _ = _json_request(
            url,
            method="POST",
            payload={"sessionId": "old-feishu-session"},
            token="wrong",
        )
        invalid, invalid_body = _json_request(
            url,
            method="POST",
            payload={"sessionId": "   "},
        )
        status, result = _json_request(
            url,
            method="POST",
            payload={"sessionId": "old-feishu-session"},
        )

        assert unauthorized == HTTPStatus.UNAUTHORIZED
        assert invalid == HTTPStatus.UNPROCESSABLE_ENTITY
        assert invalid_body["error"]["code"] == "invalid_request"
        assert status == HTTPStatus.OK
        assert result == {
            "sessionId": "old-feishu-session",
            "cleanupScheduled": True,
        }
        assert draft_service.session_ids == ["old-feishu-session"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _mcp_parameters(
    root: Path,
    validation_url: str,
    module: str = "wxpost_controller.mcp_server",
) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        cwd=str(root),
        env={
            **os.environ,
            "PYTHONPATH": str(HERMES_ROOT),
            "WXPOST_WORKSPACE_ROOT": str(root),
            "SOARHIGH_API_BASE_URL": validation_url,
        },
    )


@pytest.mark.asyncio
async def test_mcp_save_draft_exposes_only_strict_proposal_fields(
    tmp_path: Path,
    validation_url: str,
) -> None:
    async with stdio_client(_mcp_parameters(tmp_path, validation_url)) as (
        read,
        write,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()

    schema = next(
        tool.inputSchema for tool in tools.tools if tool.name == "wxpost_save_draft"
    )
    assert "proposal" in schema["properties"]
    assert "operation_id" in schema["properties"]
    assert "operation_id" in schema["required"]
    assert "refresh_from_materials" in schema["properties"]
    assert "refresh_from_materials" in schema["required"]
    assert "media_changes" in schema["properties"]
    assert "media_changes" not in schema["required"]
    assert "document" not in schema["properties"]
    proposal_schema = schema["$defs"]["DraftProposal"]
    media_schema = schema["$defs"]["DraftMediaProposal"]
    section_schema = schema["$defs"]["DraftSectionBlock"]
    changes_schema = schema["$defs"]["DraftMediaChanges"]
    assert proposal_schema["additionalProperties"] is False
    assert proposal_schema["properties"]["schemaVersion"]["const"] == 2
    assert media_schema["required"] == ["id", "description"]
    assert "blocks" in proposal_schema["properties"]
    assert "bodyMarkdown" not in proposal_schema["properties"]
    assert "body" in section_schema["properties"]
    assert "markdown" not in section_schema["properties"]
    assert (
        "separate sibling blocks"
        in (section_schema["properties"]["body"]["description"])
    )
    assert "presentation" not in proposal_schema["properties"]
    assert set(changes_schema["properties"]) == {
        "addedMediaIds",
        "removedMediaIds",
        "cover",
    }
    assert set(media_schema["properties"]) == {
        "id",
        "description",
        "credit",
        "people",
    }
    for controller_owned_field in (
        "kind",
        "sourceUrl",
        "include",
        "included",
        "order",
        "descriptionSource",
        "descriptionStatus",
    ):
        assert controller_owned_field not in media_schema["properties"]


@pytest.mark.asyncio
async def test_mcp_edit_draft_exposes_only_typed_edits(
    tmp_path: Path,
    validation_url: str,
) -> None:
    async with stdio_client(_mcp_parameters(tmp_path, validation_url)) as (
        read,
        write,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()

    schema = next(
        tool.inputSchema for tool in tools.tools if tool.name == "wxpost_edit_draft"
    )
    assert set(schema["properties"]) == {
        "workspace_id",
        "expected_manifest_version",
        "expected_draft_version",
        "operation_id",
        "edits",
    }
    assert set(schema["required"]) == set(schema["properties"])
    assert "document" not in schema["properties"]
    edit_types = {
        definition["properties"]["type"]["const"]
        for definition in schema["$defs"].values()
        if isinstance(definition, dict)
        and isinstance(definition.get("properties"), dict)
        and isinstance(definition["properties"].get("type"), dict)
        and "const" in definition["properties"]["type"]
    }
    assert {
        "replaceMetadata",
        "replaceDirectiveField",
        "setCover",
        "insertImage",
    } <= edit_types


@pytest.mark.asyncio
async def test_mcp_edit_draft_applies_one_version_bound_transaction(
    seeded_workspace: tuple[Path, str],
    validation_url: str,
) -> None:
    root, workspace_id = seeded_workspace
    _controller(root).save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )

    async with stdio_client(_mcp_parameters(root, validation_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = _mcp_value(
                await session.call_tool(
                    "wxpost_edit_draft",
                    {
                        "workspace_id": workspace_id,
                        "expected_manifest_version": 1,
                        "expected_draft_version": 1,
                        "operation_id": "draft-mcp-fine-edit",
                        "edits": [
                            {
                                "type": "replaceMetadata",
                                "field": "title",
                                "value": "Edited Through MCP",
                            },
                            {"type": "setCover", "sourceId": SPEAKER_ID},
                        ],
                    },
                )
            )

    assert result["draftVersion"] == 2
    assert result["document"]["title"] == "Edited Through MCP"
    assert result["document"]["coverMediaId"] == SPEAKER_ID
    persisted = _controller(root).get_context(workspace_id)
    assert persisted["manifest"]["draft"]["operationId"] == "draft-mcp-fine-edit"


def test_fine_grained_edit_sets_excluded_imported_cover_without_changing_materials(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )

    edited = controller.edit_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=saved["draftVersion"],
        operation_id="draft-fine-cover",
        edits=[
            {
                "type": "replaceMetadata",
                "field": "title",
                "value": "A Smaller Change",
            },
            {"type": "setCover", "sourceId": SPEAKER_ID},
        ],
    )

    assert edited["draftVersion"] == 2
    assert edited["document"]["title"] == "A Smaller Change"
    assert edited["document"]["coverMediaId"] == SPEAKER_ID
    assert SPEAKER_ID not in edited["document"]["bodyMarkdown"]
    assert {item["id"] for item in edited["document"]["media"]} == {
        SPEAKER_ID,
        WEB_IMAGE_ID,
    }
    context = controller.get_context(workspace_id)
    speaker = next(
        source
        for source in context["manifest"]["sources"]
        if source["id"] == SPEAKER_ID
    )
    assert speaker["included"] is False
    assert context["manifest"]["draft"]["operationId"] == "draft-fine-cover"


def test_fine_grained_edit_rejects_a_stale_draft_version_without_writing(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    first = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    second_document = copy.deepcopy(first["document"])
    second_document["title"] = "Newer Saved Version"
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=second_document,
    )

    with pytest.raises(VersionConflict, match="expected draft version 1"):
        controller.edit_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=1,
            operation_id="draft-stale-edit",
            edits=[
                {
                    "type": "replaceMetadata",
                    "field": "title",
                    "value": "Must Not Be Written",
                }
            ],
        )

    context = controller.get_context(workspace_id)
    assert context["draft"]["draftVersion"] == 2
    assert context["draft"]["document"]["title"] == "Newer Saved Version"


def test_fine_grained_edit_retries_are_idempotent(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    request = {
        "expected_manifest_version": 1,
        "expected_draft_version": 1,
        "operation_id": "draft-idempotent-edit",
        "edits": [
            {
                "type": "replaceMetadata",
                "field": "title",
                "value": "Saved Once",
            }
        ],
    }

    first = controller.edit_draft(workspace_id, **request)
    retried = controller.edit_draft(workspace_id, **request)

    assert first == retried
    assert retried["draftVersion"] == 2
    assert controller.get_context(workspace_id)["draft"]["draftVersion"] == 2


@pytest.mark.asyncio
async def test_mcp_rejects_manifest_media_fields_in_a_draft_proposal(
    seeded_workspace: tuple[Path, str],
    validation_url: str,
) -> None:
    root, workspace_id = seeded_workspace
    proposal = _draft_proposal()
    proposal["media"][0]["included"] = True

    async with stdio_client(_mcp_parameters(root, validation_url)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "wxpost_save_draft",
                {
                    "workspace_id": workspace_id,
                    "expected_manifest_version": 1,
                    "expected_draft_version": 0,
                    "operation_id": "draft-invalid-proposal",
                    "proposal": proposal,
                },
            )

    assert result.isError
    assert "included" in result.content[0].text
    assert _controller(root).get_context(workspace_id)["draft"] is None


def test_agent_context_adds_normalized_live_meeting_facts_without_persisting_them(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    calls: list[str] = []

    def load_meeting(meeting_id: str) -> dict[str, Any]:
        calls.append(meeting_id)
        return {
            "id": meeting_id,
            "no": 462,
            "type": "Regular",
            "theme": "Culture in Every Voice",
            "manager": {"name": "Rui Zheng"},
            "date": "2026-07-15",
            "start_time": "19:15",
            "end_time": "21:15",
            "location": "SoarHigh Club",
            "introduction": "An evening of stories and careful listening.",
            "segments": [
                {
                    "type": "Prepared Speech",
                    "start_time": "19:45",
                    "end_time": "20:00",
                    "role_taker": {"name": "Jessica Peng"},
                    "title": "Every Voice",
                    "content": "A personal story about finding confidence.",
                }
            ],
            "awards": [
                {
                    "category": "Best Prepared Speaker",
                    "winner": "Jessica Peng",
                }
            ],
        }

    controller = WorkspaceController(
        root,
        article_validator=_backend_validate,
        meeting_context_loader=load_meeting,
    )

    normal_context = controller.get_context(workspace_id)
    agent_context = controller.get_agent_context(workspace_id)

    assert "meetingContext" not in normal_context
    assert calls == ["1cf40bec-f94d-45f4-b5df-18e3a9bffac8"]
    assert agent_context["meetingContext"] == {
        "id": "1cf40bec-f94d-45f4-b5df-18e3a9bffac8",
        "no": 462,
        "type": "Regular",
        "theme": "Culture in Every Voice",
        "manager": "Rui Zheng",
        "date": "2026-07-15",
        "startTime": "19:15",
        "endTime": "21:15",
        "location": "SoarHigh Club",
        "introduction": "An evening of stories and careful listening.",
        "agenda": [
            {
                "type": "Prepared Speech",
                "startTime": "19:45",
                "endTime": "20:00",
                "roleTaker": "Jessica Peng",
                "title": "Every Voice",
                "content": "A personal story about finding confidence.",
            }
        ],
        "awards": [
            {
                "category": "Best Prepared Speaker",
                "winner": "Jessica Peng",
            }
        ],
    }
    persisted = json.loads(
        (root / "inbox" / workspace_id / "source-manifest.json").read_text()
    )
    assert "meetingContext" not in persisted


def test_agent_context_exposes_version_bound_body_nodes_for_typed_edits(
    seeded_workspace: tuple[Path, str],
    validation_url: str,
) -> None:
    root, workspace_id = seeded_workspace
    controller = WorkspaceController(root, soarhigh_api_base_url=validation_url)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )

    agent_context = controller.get_agent_context(workspace_id)

    assert agent_context["draft"]["draftVersion"] == 1
    assert agent_context["draft"]["editContext"]["body"] == [
        {
            "kind": "markdown",
            "source": "The meeting began with a warm welcome.\n",
            "line": 1,
        },
        {
            "kind": "directive",
            "name": "image",
            "payload": {"media": "M03"},
            "line": 3,
        },
    ]
    assert "editContext" not in controller.get_context(workspace_id)["draft"]


def test_manifest_and_draft_versions_advance_independently(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)

    context = controller.get_context(workspace_id)
    assert context["manifest"]["schemaVersion"] == 5
    assert context["manifest"]["manifestVersion"] == 1
    assert context["manifest"]["draft"] is None
    assert context["draft"] is None

    unchanged = controller.update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[{"sourceId": WEB_IMAGE_ID, "included": True}],
    )
    assert unchanged["manifestVersion"] == 1

    manifest = controller.update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[
            {
                "sourceId": FEISHU_VIDEO_ID,
                "description": "A confirmed Table Topics highlight.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )
    assert manifest["manifestVersion"] == 2

    draft = controller.save_draft(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        document=_article_document(),
    )
    assert draft["draftVersion"] == 1

    manifest = controller.update_sources(
        workspace_id,
        expected_manifest_version=2,
        updates=[{"sourceId": FEISHU_VIDEO_ID, "included": True}],
    )
    context = controller.get_context(workspace_id)
    assert manifest["manifestVersion"] == 3
    assert context["draft"]["draftVersion"] == 1
    assert context["draft"]["document"] == draft["document"]


def test_article_json_is_the_raw_backend_normalized_document(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document["title"] = "  Normalized title  "
    document["media"][0]["description"] = (
        "An editorial description derived from the confirmed source fact."
    )
    document["media"][0]["include"] = 1
    document["media"][0]["order"] = "2"

    saved = _controller(root).save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=document,
    )

    workspace = root / "inbox" / workspace_id
    stored = json.loads((workspace / "draft" / "article.json").read_text())
    manifest = json.loads((workspace / "source-manifest.json").read_text())
    assert saved["document"] == stored
    assert stored == _canonical_document(document)
    assert stored["title"] == "Normalized title"
    assert stored["media"][0]["include"] is True
    assert stored["media"][0]["order"] == 2
    assert "draftVersion" not in stored
    assert "document" not in stored
    assert manifest["draft"]["version"] == 1
    assert manifest["draft"]["sourceManifestVersion"] == 1


def test_direct_draft_save_clears_a_previous_hermes_operation_id(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    first = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
        operation_id="draft-hermes-turn",
    )
    assert (
        controller.get_context(workspace_id)["manifest"]["draft"]["operationId"]
        == "draft-hermes-turn"
    )

    revised = first["document"]
    revised["title"] = "Member saved this version"
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=revised,
    )

    assert (
        "operationId" not in controller.get_context(workspace_id)["manifest"]["draft"]
    )


def test_authoritative_backend_validation_rejects_invalid_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document.pop("presentation")

    with pytest.raises(InvalidRequest, match="presentation"):
        _controller(root).save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=document,
        )

    workspace = root / "inbox" / workspace_id
    assert not (workspace / "draft" / "article.json").exists()
    assert json.loads((workspace / "source-manifest.json").read_text())["draft"] is None


def test_remote_validator_is_required_when_no_test_validator_is_injected(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace

    with pytest.raises(ValidationUnavailable, match="SOARHIGH_API_BASE_URL"):
        WorkspaceController(root, soarhigh_api_base_url="").save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=_article_document(),
        )


def test_source_reorder_is_stored_in_canonical_array_order(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace

    manifest = _controller(root).update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[{"sourceId": SPEAKER_ID, "moveToIndex": 0}],
    )

    assert [source["id"] for source in manifest["sources"][:2]] == [
        SPEAKER_ID,
        GROUP_PHOTO_ID,
    ]
    assert all("order" not in source for source in manifest["sources"])


def test_invalid_source_transition_is_rejected_without_data_loss(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)

    with pytest.raises(InvalidRequest, match="workspace-ready"):
        controller.update_sources(
            workspace_id,
            expected_manifest_version=1,
            updates=[{"sourceId": GROUP_PHOTO_ID, "included": True}],
        )

    context = controller.get_context(workspace_id)
    assert context["manifest"]["manifestVersion"] == 1
    assert context["manifest"]["sources"][0]["included"] is False


def test_stale_manifest_and_draft_writes_report_correct_versions(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.update_sources(
        workspace_id,
        expected_manifest_version=1,
        updates=[
            {
                "sourceId": FEISHU_VIDEO_ID,
                "description": "Confirmed Table Topics highlight.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )

    with pytest.raises(VersionConflict) as manifest_conflict:
        controller.update_sources(
            workspace_id,
            expected_manifest_version=1,
            updates=[{"sourceId": FEISHU_VIDEO_ID, "included": True}],
        )
    assert manifest_conflict.value.resource == "manifest"
    assert manifest_conflict.value.actual == 2

    with pytest.raises(VersionConflict) as draft_manifest_conflict:
        controller.save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=_article_document(),
        )
    assert draft_manifest_conflict.value.resource == "manifest"
    assert draft_manifest_conflict.value.actual == 2

    controller.save_draft(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        document=_article_document(),
    )
    with pytest.raises(VersionConflict) as draft_conflict:
        controller.save_draft(
            workspace_id,
            expected_manifest_version=2,
            expected_draft_version=0,
            document=_article_document(title="Stale writer"),
        )
    assert draft_conflict.value.resource == "draft"
    assert draft_conflict.value.actual == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "M99", "saved source snapshot"),
        ("kind", "video", "saved source snapshot"),
        ("include", False, "saved source snapshot"),
    ],
)
def test_draft_media_must_match_the_manifest_snapshot(
    seeded_workspace: tuple[Path, str],
    field: str,
    value: object,
    message: str,
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document["media"][0][field] = value
    if field == "id":
        document["bodyMarkdown"] = document["bodyMarkdown"].replace("M03", "M99")
    elif field == "kind":
        document["bodyMarkdown"] = (
            "The meeting began with a warm welcome.\n\n:::video\nmedia: M03\n:::"
        )
    elif field == "include":
        document["bodyMarkdown"] = "The meeting began with a warm welcome."

    with pytest.raises(InvalidRequest, match=message):
        _controller(root).save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=document,
        )


def test_draft_media_description_provenance_is_independent_from_materials(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    document = _article_document()
    document["media"][0]["description"] = "A generated article caption."
    document["media"][0]["descriptionSource"] = "ai"
    document["media"][0]["descriptionStatus"] = "needs_confirmation"

    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=document,
    )

    assert saved["document"]["media"][0]["descriptionSource"] == "ai"
    material = next(
        source
        for source in controller.get_context(workspace_id)["manifest"]["sources"]
        if source["id"] == WEB_IMAGE_ID
    )
    assert material["descriptionSource"] == "user"
    assert material["descriptionStatus"] == "confirmed"


def test_draft_contains_every_included_manifest_media_source(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    document = _article_document()
    document["media"] = []
    document["bodyMarkdown"] = "The meeting began with a warm welcome."

    with pytest.raises(InvalidRequest, match="saved source snapshot"):
        _controller(root).save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=document,
        )


def test_direct_draft_edit_can_remove_media_from_its_saved_snapshot(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    edited = copy.deepcopy(saved["document"])
    edited["bodyMarkdown"] = "The meeting began with a warm welcome."
    edited["media"] = []
    edited["coverMediaId"] = None

    updated = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=edited,
    )

    assert updated["draftVersion"] == 2
    assert updated["document"]["media"] == []
    source = next(
        item
        for item in controller.get_context(workspace_id)["manifest"]["sources"]
        if item["id"] == WEB_IMAGE_ID
    )
    assert source["included"] is True


def test_direct_draft_edit_can_add_a_ready_image_as_cover_only(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    edited = copy.deepcopy(saved["document"])
    edited["media"].append(
        {
            "id": SPEAKER_ID,
            "kind": "image",
            "sourceUrl": "https://workspace.invalid/M02.jpg",
            "description": "A speaker addresses the room.",
            "include": True,
            "order": 3,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    )
    edited["coverMediaId"] = SPEAKER_ID

    updated = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=edited,
    )

    assert updated["document"]["coverMediaId"] == SPEAKER_ID
    assert updated["document"]["bodyMarkdown"] == saved["document"]["bodyMarkdown"]
    assert [item["id"] for item in updated["document"]["media"]] == [
        WEB_IMAGE_ID,
        SPEAKER_ID,
    ]


def test_focused_revision_preserves_an_excluded_cover_only_image(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    initial = copy.deepcopy(saved["document"])
    initial["media"].append(
        {
            "id": SPEAKER_ID,
            "kind": "image",
            "sourceUrl": "https://workspace.invalid/M02.jpg",
            "description": "A speaker addresses the room.",
            "include": True,
            "order": 3,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    )
    initial["coverMediaId"] = SPEAKER_ID
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=initial,
    )
    proposal = _draft_proposal()
    proposal["coverMediaId"] = None

    revised = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=2,
        proposal=proposal,
        refresh_from_materials=False,
        media_changes={
            "addedMediaIds": [],
            "removedMediaIds": [],
            "cover": {"action": "preserve"},
        },
    )

    assert revised["document"]["coverMediaId"] == SPEAKER_ID
    assert [item["id"] for item in revised["document"]["media"]] == [
        WEB_IMAGE_ID,
        SPEAKER_ID,
    ]
    source = next(
        item
        for item in controller.get_context(workspace_id)["manifest"]["sources"]
        if item["id"] == SPEAKER_ID
    )
    assert source["included"] is False


def test_focused_revision_moves_a_cover_only_image_into_the_body_without_adding_it(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    initial = copy.deepcopy(saved["document"])
    initial["media"].append(
        {
            "id": SPEAKER_ID,
            "kind": "image",
            "sourceUrl": "https://workspace.invalid/M02.jpg",
            "description": "A speaker addresses the room.",
            "include": True,
            "order": 3,
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
    )
    initial["coverMediaId"] = SPEAKER_ID
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=initial,
    )
    proposal = _draft_proposal(media_ids=(WEB_IMAGE_ID, SPEAKER_ID))
    proposal["coverMediaId"] = None

    revised = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=2,
        proposal=proposal,
        refresh_from_materials=False,
        media_changes={
            "addedMediaIds": [],
            "removedMediaIds": [],
            "cover": {"action": "preserve"},
        },
    )

    assert revised["document"]["coverMediaId"] == SPEAKER_ID
    assert '"media": "M02"' in revised["document"]["bodyMarkdown"]
    assert [item["id"] for item in revised["document"]["media"]] == [
        WEB_IMAGE_ID,
        SPEAKER_ID,
    ]


def test_focused_revision_can_add_and_remove_imported_media_without_materials_change(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    added_proposal = _draft_proposal(media_ids=(WEB_IMAGE_ID, SPEAKER_ID))
    added_proposal["coverMediaId"] = SPEAKER_ID

    added = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        proposal=added_proposal,
        refresh_from_materials=False,
        media_changes={
            "addedMediaIds": [SPEAKER_ID],
            "removedMediaIds": [],
            "cover": {"action": "set", "sourceId": SPEAKER_ID},
        },
    )

    assert [item["id"] for item in added["document"]["media"]] == [
        WEB_IMAGE_ID,
        SPEAKER_ID,
    ]
    assert added["document"]["coverMediaId"] == SPEAKER_ID
    speaker = next(
        item
        for item in controller.get_context(workspace_id)["manifest"]["sources"]
        if item["id"] == SPEAKER_ID
    )
    assert speaker["workspaceReady"] is True
    assert speaker["included"] is False

    removed_proposal = _draft_proposal(media_ids=(SPEAKER_ID,))
    removed_proposal["coverMediaId"] = None
    removed = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=2,
        proposal=removed_proposal,
        refresh_from_materials=False,
        media_changes={
            "addedMediaIds": [],
            "removedMediaIds": [WEB_IMAGE_ID],
            "cover": {"action": "preserve"},
        },
    )

    assert [item["id"] for item in removed["document"]["media"]] == [SPEAKER_ID]
    assert removed["document"]["coverMediaId"] == SPEAKER_ID
    included_source = next(
        item
        for item in controller.get_context(workspace_id)["manifest"]["sources"]
        if item["id"] == WEB_IMAGE_ID
    )
    assert included_source["included"] is True

    cleared_proposal = _draft_proposal(media_ids=())
    cleared_proposal["coverMediaId"] = None
    cleared = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=3,
        proposal=cleared_proposal,
        refresh_from_materials=False,
        media_changes={
            "addedMediaIds": [],
            "removedMediaIds": [SPEAKER_ID],
            "cover": {"action": "clear"},
        },
    )

    assert cleared["document"]["media"] == []
    assert cleared["document"]["coverMediaId"] is None


def test_focused_revision_rejects_an_unimported_media_addition(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    proposal = copy.deepcopy(_draft_proposal())
    proposal["blocks"].append({"type": "image", "media": GROUP_PHOTO_ID})
    proposal["media"].append(
        {
            "id": GROUP_PHOTO_ID,
            "description": "Members gather for a group photograph.",
            "credit": None,
            "people": [],
        }
    )
    proposal["coverMediaId"] = None

    with pytest.raises(InvalidRequest, match="must be imported workspace media"):
        controller.save_draft_proposal(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=1,
            proposal=proposal,
            refresh_from_materials=False,
            media_changes={
                "addedMediaIds": [GROUP_PHOTO_ID],
                "removedMediaIds": [],
                "cover": {"action": "preserve"},
            },
        )


def test_direct_draft_edit_cannot_add_media_outside_its_saved_snapshot(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    edited = copy.deepcopy(saved["document"])
    edited["media"][0]["id"] = "M99"
    edited["bodyMarkdown"] = edited["bodyMarkdown"].replace("M03", "M99")

    with pytest.raises(InvalidRequest, match="imported workspace media"):
        controller.save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=1,
            document=edited,
        )


def test_draft_proposal_is_assembled_from_manifest_in_editorial_media_order(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.set_source_included(
        workspace_id,
        expected_manifest_version=1,
        source_id=FEISHU_VIDEO_ID,
        included=True,
    )

    saved = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        proposal=_draft_proposal(
            media_ids=(FEISHU_VIDEO_ID, WEB_IMAGE_ID),
        ),
    )

    document = saved["document"]
    assert document["schemaVersion"] == 1
    assert [item["id"] for item in document["media"]] == [
        FEISHU_VIDEO_ID,
        WEB_IMAGE_ID,
    ]
    assert [item["order"] for item in document["media"]] == [0, 1]
    assert document["media"][0] == {
        "id": FEISHU_VIDEO_ID,
        "kind": "video",
        "sourceUrl": (
            f"https://workspace.invalid/{workspace_id}/materials/{FEISHU_VIDEO_ID}"
        ),
        "posterUrl": None,
        "description": "A guest tries Table Topics for the first time.",
        "credit": None,
        "people": [],
        "include": True,
        "order": 0,
        "descriptionSource": "ai",
        "descriptionStatus": "needs_confirmation",
    }
    assert document["media"][1]["descriptionSource"] == "ai"
    assert document["media"][1]["descriptionStatus"] == "needs_confirmation"
    assert document["articleType"] == "meeting-recap"
    assert document["customArticleType"] is None
    assert document["sourceMeetingId"] == ("1cf40bec-f94d-45f4-b5df-18e3a9bffac8")
    assert document["presentation"] == {
        "layout": "brand-default",
        "palette": "fresh-sage",
        "appearance": "light",
        "typeface": "editorial-serif",
    }


def test_independent_custom_workspace_generates_without_an_optional_label(
    tmp_path: Path,
) -> None:
    workspace_id = "independent-custom"
    controller = _controller(tmp_path)
    controller.bootstrap_workspace(
        workspace_id,
        meeting_id=None,
        editorial={
            "articleType": "custom",
            "customArticleType": None,
            "voiceTone": {"presets": [], "customProfiles": []},
        },
        created_by={"id": "member-123", "name": "Test Member"},
    )

    saved = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        proposal=_draft_proposal(media_ids=()),
    )

    assert saved["document"]["articleType"] == "custom"
    assert saved["document"]["customArticleType"] is None
    assert saved["document"]["sourceMeetingId"] is None


def test_draft_proposal_converts_a_missing_source_description_to_ai_caption(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.set_source_included(
        workspace_id,
        expected_manifest_version=1,
        source_id=SPEAKER_ID,
        included=True,
    )

    saved = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        proposal=_draft_proposal(media_ids=(SPEAKER_ID, WEB_IMAGE_ID)),
    )

    speaker = saved["document"]["media"][0]
    assert speaker["description"] == (
        "A speaker shares a prepared story with the room."
    )
    assert speaker["descriptionSource"] == "ai"
    assert speaker["descriptionStatus"] == "needs_confirmation"


def test_draft_proposal_preserves_unchanged_user_caption_provenance(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    generated = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        proposal=_draft_proposal(),
    )
    user_edited = generated["document"]
    user_edited["media"][0]["description"] = "A member-edited article caption."
    user_edited["media"][0]["descriptionSource"] = "user"
    user_edited["media"][0]["descriptionStatus"] = "confirmed"
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=user_edited,
    )

    unchanged = _draft_proposal()
    unchanged["media"][0]["description"] = "A member-edited article caption."
    preserved = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=2,
        proposal=unchanged,
    )
    assert preserved["document"]["media"][0]["descriptionSource"] == "user"
    assert preserved["document"]["media"][0]["descriptionStatus"] == "confirmed"

    changed = _draft_proposal()
    changed["media"][0]["description"] = "A newly revised AI article caption."
    revised = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=3,
        proposal=changed,
    )
    assert revised["document"]["media"][0]["descriptionSource"] == "ai"
    assert revised["document"]["media"][0]["descriptionStatus"] == (
        "needs_confirmation"
    )


def test_draft_proposal_preserves_member_selected_presentation(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    generated = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        proposal=_draft_proposal(),
    )
    selected = {
        "layout": "editorial-feature",
        "palette": "warm-terracotta",
        "appearance": "dark",
        "typeface": "humanist-mix",
    }
    edited = {**generated["document"], "presentation": selected}
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=1,
        document=edited,
    )
    regenerated_proposal = _draft_proposal()
    regenerated_proposal["title"] = "A Different Editorial Shape"

    regenerated = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=2,
        proposal=regenerated_proposal,
    )

    assert regenerated["document"]["title"] == "A Different Editorial Shape"
    assert regenerated["document"]["presentation"] == selected


def test_draft_proposal_can_use_an_image_only_as_the_cover(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    proposal = _draft_proposal()
    proposal["blocks"] = proposal["blocks"][:1]

    saved = _controller(root).save_draft_proposal(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        proposal=proposal,
    )

    assert saved["document"]["coverMediaId"] == WEB_IMAGE_ID
    assert [item["id"] for item in saved["document"]["media"]] == [WEB_IMAGE_ID]
    assert WEB_IMAGE_ID not in saved["document"]["bodyMarkdown"]


def test_draft_proposal_rejects_excluded_or_missing_media(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    proposal = _draft_proposal(media_ids=(SPEAKER_ID,))

    with pytest.raises(InvalidRequest, match="source snapshot: M02"):
        _controller(root).save_draft_proposal(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            proposal=proposal,
        )


def test_draft_proposal_rejects_manual_directive_fences(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    proposal = _draft_proposal()
    proposal["blocks"][0]["markdown"] = (
        "Welcome to the meeting.\n\n:::image\nmedia: M03\n:::"
    )

    with pytest.raises(InvalidRequest, match="cannot contain directive fences"):
        _controller(root).save_draft_proposal(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            proposal=proposal,
        )

    assert _controller(root).get_context(workspace_id)["draft"] is None


def test_draft_proposal_rejects_semantic_blocks_inside_section_body(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    proposal = _draft_proposal()
    proposal["blocks"][0] = {
        "type": "section",
        "kicker": "Opening",
        "heading": "The Room Opens",
        "body": "Welcome.\n\n:::image\nmedia: M03\n:::",
    }

    with pytest.raises(InvalidRequest, match="cannot contain directive fences"):
        _controller(root).save_draft_proposal(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            proposal=proposal,
        )

    assert _controller(root).get_context(workspace_id)["draft"] is None


@pytest.mark.parametrize(
    "body",
    [
        "Welcome.\n\n## An accidental nested section\n\nMore prose.",
        "Welcome.\n\nAn accidental nested section\n---\n\nMore prose.",
    ],
)
def test_draft_proposal_rejects_headings_inside_section_body(
    seeded_workspace: tuple[Path, str],
    body: str,
) -> None:
    root, workspace_id = seeded_workspace
    proposal = _draft_proposal()
    proposal["blocks"][0] = {
        "type": "section",
        "kicker": "Opening",
        "heading": "The Room Opens",
        "body": body,
    }

    with pytest.raises(InvalidRequest, match="cannot contain Markdown headings"):
        _controller(root).save_draft_proposal(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            proposal=proposal,
        )

    assert _controller(root).get_context(workspace_id)["draft"] is None


def test_draft_proposal_serializes_typed_blocks_without_yaml_guessing(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.set_source_included(
        workspace_id,
        expected_manifest_version=1,
        source_id=SPEAKER_ID,
        included=True,
    )
    proposal = _draft_proposal(media_ids=(SPEAKER_ID, WEB_IMAGE_ID))
    proposal["blocks"] = [
        {
            "type": "section",
            "kicker": "THE PROGRAM",
            "heading": "A Room Full of Possibility",
            "body": "Guests arrived: curious, generous, and ready to speak.",
        },
        {
            "type": "gallery",
            "items": [SPEAKER_ID, WEB_IMAGE_ID],
            "caption": "Two views: the speaker, then the welcome.",
        },
        {
            "type": "takeaway",
            "title": "Remember",
            "text": "Make room for the next voice: listen first.",
        },
    ]

    saved = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=0,
        proposal=proposal,
    )

    document = saved["document"]
    assert [item["id"] for item in document["media"]] == [
        SPEAKER_ID,
        WEB_IMAGE_ID,
    ]
    assert (
        '"caption": "Two views: the speaker, then the welcome."'
        in (document["bodyMarkdown"])
    )
    validated = _backend_validate(document)
    assert validated["bodyMarkdown"] == document["bodyMarkdown"]


def test_concurrent_manifest_updates_serialize_and_one_conflicts(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def update(source_id: str, included: bool) -> None:
        barrier.wait()
        try:
            _controller(root).update_sources(
                workspace_id,
                expected_manifest_version=1,
                updates=[{"sourceId": source_id, "included": included}],
            )
        except VersionConflict:
            outcomes.append("conflict")
        else:
            outcomes.append("updated")

    threads = [
        threading.Thread(target=update, args=(WEB_IMAGE_ID, False)),
        threading.Thread(target=update, args=(FEISHU_VIDEO_ID, True)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(outcomes) == ["conflict", "updated"]


@pytest.mark.parametrize("failure", ["missing", "size", "symlink", "sources-symlink"])
def test_workspace_ready_requires_the_real_declared_file(
    seeded_workspace: tuple[Path, str],
    tmp_path: Path,
    failure: str,
) -> None:
    root, workspace_id = seeded_workspace
    workspace = root / "inbox" / workspace_id
    source = _manifest_fixture()["sources"][2]
    path = workspace / "sources" / f"{source['id']}{Path(source['filename']).suffix}"
    if failure == "missing":
        path.unlink()
    elif failure == "size":
        path.write_bytes(b"wrong")
    elif failure == "symlink":
        target = tmp_path / "outside.jpg"
        target.write_bytes(b"x" * source["sizeBytes"])
        path.unlink()
        path.symlink_to(target)
    else:
        source_dir = path.parent
        target_dir = workspace / "real-sources"
        source_dir.rename(target_dir)
        source_dir.symlink_to(target_dir, target_is_directory=True)

    with pytest.raises(InvalidWorkspace, match="source"):
        _controller(root).get_context(workspace_id)


def test_draft_hash_detects_out_of_band_changes(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    path = root / "inbox" / workspace_id / "draft" / "article.json"
    changed = json.loads(path.read_text())
    changed["title"] = "Changed outside the controller"
    path.write_text(json.dumps(changed))

    with pytest.raises(InvalidWorkspace, match="manifest hash"):
        controller.get_context(workspace_id)


def test_interrupted_first_draft_save_is_rolled_back_on_next_read(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    draft_dir = root / "inbox" / workspace_id / "draft"
    draft_dir.mkdir()
    pending = draft_dir / ".article-save-pending.json"
    pending.write_text(json.dumps({"previousDocument": None}))
    (draft_dir / "article.json").write_text(
        json.dumps(_canonical_document(_article_document()))
    )

    context = _controller(root).get_context(workspace_id)

    assert context["draft"] is None
    assert not (draft_dir / "article.json").exists()
    assert not pending.exists()


def test_interrupted_draft_overwrite_restores_the_manifest_version(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    draft_dir = root / "inbox" / workspace_id / "draft"
    pending = draft_dir / ".article-save-pending.json"
    pending.write_text(json.dumps({"previousDocument": saved["document"]}))
    interrupted = _canonical_document(
        _article_document(title="Interrupted replacement")
    )
    (draft_dir / "article.json").write_text(json.dumps(interrupted))

    context = _controller(root).get_context(workspace_id)

    assert context["draft"] == saved
    assert json.loads((draft_dir / "article.json").read_text()) == saved["document"]
    assert not pending.exists()


def test_completed_draft_save_discards_a_stale_pending_record(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    saved = _controller(root).save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    pending = root / "inbox" / workspace_id / "draft" / ".article-save-pending.json"
    pending.write_text(json.dumps({"previousDocument": None}))

    context = _controller(root).get_context(workspace_id)

    assert context["draft"] == saved
    assert not pending.exists()


@pytest.mark.parametrize("manifest_replaced", [False, True])
def test_manifest_write_failure_keeps_disk_state_self_consistent(
    seeded_workspace: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    manifest_replaced: bool,
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    original_write = controller._atomic_write_json

    def fail_manifest_write(path: Path, value: Mapping[str, Any]) -> None:
        if path.name == "source-manifest.json":
            if manifest_replaced:
                original_write(path, value)
            raise InvalidWorkspace("simulated manifest fsync failure")
        original_write(path, value)

    monkeypatch.setattr(controller, "_atomic_write_json", fail_manifest_write)

    with pytest.raises(InvalidWorkspace, match="simulated"):
        controller.save_draft(
            workspace_id,
            expected_manifest_version=1,
            expected_draft_version=0,
            document=_article_document(),
        )

    context = _controller(root).get_context(workspace_id)
    if manifest_replaced:
        assert context["draft"]["draftVersion"] == 1
    else:
        assert context["draft"] is None
    assert not (
        root / "inbox" / workspace_id / "draft" / ".article-save-pending.json"
    ).exists()


def test_v1_manifest_is_rejected_without_runtime_compatibility(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    path = root / "inbox" / workspace_id / "source-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["schemaVersion"] = 1
    path.write_text(json.dumps(manifest))

    with pytest.raises(InvalidWorkspace, match="source-manifest v5"):
        _controller(root).get_context(workspace_id)


def test_workspace_identifier_and_symlink_escape_are_rejected(
    seeded_workspace: tuple[Path, str],
    tmp_path: Path,
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    with pytest.raises(InvalidRequest):
        controller.get_context("../outside")

    outside = tmp_path / "outside"
    outside.mkdir()
    symlink = root / "inbox" / "linked-workspace"
    symlink.symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidWorkspace):
        controller.get_context("linked-workspace")


def test_materials_update_preserves_a_saved_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    saved = controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    assert saved["draftVersion"] == 1

    current = controller.get_context(workspace_id)
    updated = controller.update_workspace(
        workspace_id,
        expected_manifest_version=current["manifest"]["manifestVersion"],
        meeting_id=current["manifest"]["meetingId"],
        editorial=current["manifest"]["editorial"],
        source_updates=[
            {
                "sourceId": WEB_IMAGE_ID,
                "included": False,
                "description": "Updated source fact.",
                "descriptionSource": "user",
                "descriptionStatus": "confirmed",
            }
        ],
    )

    assert updated["workspaceId"] == workspace_id
    assert updated["manifest"]["manifestVersion"] == 2
    assert updated["manifest"]["editorial"]["articleType"] == "meeting-recap"
    updated_source = next(
        source
        for source in updated["manifest"]["sources"]
        if source["id"] == WEB_IMAGE_ID
    )
    assert updated_source["included"] is False
    assert updated_source["description"] == "Updated source fact."
    assert updated["manifest"]["draft"] == current["manifest"]["draft"]
    assert updated["draft"] == saved
    raw = json.loads(
        (root / "inbox" / workspace_id / "draft" / "article.json").read_text()
    )
    assert raw == _canonical_document(_article_document())

    direct_edit = {**saved["document"], "title": "Edited old Draft"}
    edited = controller.save_draft(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=1,
        document=direct_edit,
    )
    assert edited["document"]["articleType"] == "meeting-recap"
    assert edited["document"]["media"][0]["id"] == WEB_IMAGE_ID
    assert (
        controller.get_context(workspace_id)["manifest"]["draft"][
            "sourceManifestVersion"
        ]
        == 1
    )

    revision_proposal = _draft_proposal()
    revision_proposal["coverMediaId"] = None
    revised = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=2,
        proposal=revision_proposal,
        refresh_from_materials=False,
        media_changes={
            "addedMediaIds": [],
            "removedMediaIds": [],
            "cover": {"action": "preserve"},
        },
    )
    assert revised["document"]["articleType"] == "meeting-recap"
    assert revised["document"]["media"][0]["id"] == WEB_IMAGE_ID
    assert (
        controller.get_context(workspace_id)["manifest"]["draft"][
            "sourceManifestVersion"
        ]
        == 1
    )

    regenerated = controller.save_draft_proposal(
        workspace_id,
        expected_manifest_version=2,
        expected_draft_version=3,
        proposal=_draft_proposal(media_ids=()),
        refresh_from_materials=True,
    )
    assert regenerated["document"]["articleType"] == "meeting-recap"
    assert regenerated["document"]["media"] == []
    assert (
        controller.get_context(workspace_id)["manifest"]["draft"][
            "sourceManifestVersion"
        ]
        == 2
    )


def test_meeting_source_change_is_rejected_without_touching_saved_draft(
    seeded_workspace: tuple[Path, str],
) -> None:
    root, workspace_id = seeded_workspace
    controller = _controller(root)
    controller.save_draft(
        workspace_id,
        expected_manifest_version=1,
        expected_draft_version=0,
        document=_article_document(),
    )
    current = controller.get_context(workspace_id)

    with pytest.raises(InvalidRequest, match="meeting/source is fixed"):
        controller.update_workspace(
            workspace_id,
            expected_manifest_version=current["manifest"]["manifestVersion"],
            meeting_id=None,
            editorial=current["manifest"]["editorial"],
        )
    unchanged = controller.get_context(workspace_id)
    assert unchanged == current
    assert (root / "inbox" / workspace_id / "draft" / "article.json").is_file()


@pytest.mark.asyncio
async def test_http_and_mcp_share_auth_contract_state_and_raw_draft(
    seeded_workspace: tuple[Path, str],
    validation_url: str,
) -> None:
    root, workspace_id = seeded_workspace
    server = build_server(
        workspace_root=str(root),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized, _ = _json_request(
            f"{base_url}/workspaces/{workspace_id}/context",
            token="wrong",
        )
        assert unauthorized == 401

        status, listing = _json_request(
            f"{base_url}/workspaces?page=1&page_size=1",
        )
        assert status == 200
        assert listing["page"] == 1
        assert listing["page_size"] == 1
        assert listing["total"] == 1
        assert listing["pages"] == 1
        assert [item["workspaceId"] for item in listing["items"]] == [workspace_id]

        status, invalid_pagination = _json_request(
            f"{base_url}/workspaces?page=one",
        )
        assert status == 422
        assert invalid_pagination["error"]["code"] == "invalid_request"

        status, invalid = _json_request(
            f"{base_url}/workspaces/{workspace_id}/sources",
            method="PATCH",
            payload={
                "expectedManifestVersion": 1,
                "updates": [{"sourceId": WEB_IMAGE_ID, "included": False}],
                "unexpected": True,
            },
        )
        assert status == 422
        assert invalid["error"]["code"] == "invalid_request"

        status, http_manifest = _json_request(
            f"{base_url}/workspaces/{workspace_id}/sources",
            method="PATCH",
            payload={
                "expectedManifestVersion": 1,
                "updates": [
                    {
                        "sourceId": WEB_IMAGE_ID,
                        "description": "Updated confirmed source fact.",
                        "descriptionSource": "user",
                        "descriptionStatus": "confirmed",
                    }
                ],
            },
        )
        assert status == 200

        async with stdio_client(_mcp_parameters(root, validation_url)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                context = _mcp_value(
                    await session.call_tool(
                        "wxpost_get_context",
                        {"workspace_id": workspace_id},
                    )
                )
                assert context["manifest"] == http_manifest
                assert context["meetingContext"]["theme"] == ("Culture in Every Voice")

                saved = _mcp_value(
                    await session.call_tool(
                        "wxpost_save_draft",
                        {
                            "workspace_id": workspace_id,
                            "expected_manifest_version": 2,
                            "expected_draft_version": 0,
                            "operation_id": "draft-http-mcp-shared-state",
                            "refresh_from_materials": True,
                            "proposal": _draft_proposal(),
                        },
                    )
                )
                assert saved["draftVersion"] == 1

        persisted = _controller(root).get_context(workspace_id)
        assert persisted["manifest"]["manifestVersion"] == 2
        assert (
            persisted["manifest"]["draft"]["operationId"]
            == "draft-http-mcp-shared-state"
        )
        assert persisted["draft"] == saved
        raw = json.loads(
            (root / "inbox" / workspace_id / "draft" / "article.json").read_text()
        )
        assert raw == saved["document"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_http_and_mcp_share_the_complete_material_operation_state(
    tmp_path: Path,
    validation_url: str,
) -> None:
    server = build_server(
        workspace_root=str(tmp_path),
        bearer_token=TOKEN,
        host="127.0.0.1",
        port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, created = _json_request(
            f"{base_url}/workspaces",
            method="POST",
            payload={
                "meetingId": None,
                "editorial": {
                    "articleType": "meeting-recap",
                    "customArticleType": None,
                    "voiceTone": {"presets": [], "customProfiles": []},
                },
                "createdBy": {
                    "id": "member-123",
                    "name": "Test Member",
                },
            },
        )
        assert status == 200
        workspace_id = created["workspaceId"]
        assert workspace_id.startswith("wxpost-")
        assert created["manifest"]["manifestVersion"] == 1
        assert created["manifest"]["sources"] == []

        status, uploaded = _upload_request(
            f"{base_url}/workspaces/{workspace_id}/uploads",
            filename="网页照片.jpg",
            expected_manifest_version=1,
            data=PNG_BYTES,
            mime_type="image/jpeg",
        )
        assert status == 200, uploaded
        assert uploaded["sources"][0]["id"] == "M01"
        assert uploaded["sources"][0]["origin"] == {"type": "web-upload"}

        request = urllib.request.Request(
            f"{base_url}/workspaces/{workspace_id}/sources/M01/content"
            f"?v={uploaded['sources'][0]['contentSha256']}",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.headers["Cache-Control"] == (
                "private, max-age=31536000, immutable"
            )
            assert response.headers["ETag"] == (
                f'"{uploaded["sources"][0]["contentSha256"]}"'
            )
            assert response.read() == PNG_BYTES

        status, saved = _json_request(
            f"{base_url}/workspaces/{workspace_id}",
            method="PATCH",
            payload={
                "expectedManifestVersion": uploaded["manifestVersion"],
                "meetingId": None,
                "editorial": created["manifest"]["editorial"],
                "sourceUpdates": [
                    {
                        "sourceId": "M01",
                        "included": False,
                        "description": "Saved through the real HTTP route.",
                        "descriptionSource": "user",
                        "descriptionStatus": "confirmed",
                    }
                ],
            },
        )
        assert status == 200
        assert saved["manifest"]["manifestVersion"] == 3
        assert saved["manifest"]["sources"][0] == {
            **uploaded["sources"][0],
            "description": "Saved through the real HTTP route.",
            "descriptionSource": "user",
            "descriptionStatus": "confirmed",
        }
        status, conflict = _json_request(
            f"{base_url}/workspaces/{workspace_id}",
            method="PATCH",
            payload={
                "expectedManifestVersion": uploaded["manifestVersion"],
                "meetingId": None,
                "editorial": created["manifest"]["editorial"],
                "sourceUpdates": [],
            },
        )
        assert status == 409
        assert conflict["error"]["code"] == "version_conflict"

        status, second_upload = _upload_request(
            f"{base_url}/workspaces/{workspace_id}/uploads",
            filename="clip.mp4",
            expected_manifest_version=3,
            data=b"web-video",
            mime_type="video/mp4",
        )
        assert status == 200
        assert second_upload["manifestVersion"] == 4
        assert second_upload["sources"][1]["id"] == "M02"

        async with stdio_client(_mcp_parameters(tmp_path, validation_url)) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert {
                    "wxpost_update_workspace",
                    "wxpost_import_source",
                    "wxpost_set_source_included",
                    "wxpost_delete_source_preflight",
                    "wxpost_delete_source",
                }.issubset(tools)
                assert "wxpost_upload_source" not in tools

                status, http_conflict = _json_request(
                    f"{base_url}/workspaces/{workspace_id}/sources/M01/inclusion",
                    method="PUT",
                    payload={
                        "expectedManifestVersion": 1,
                        "included": True,
                    },
                )
                assert status == 409
                mcp_conflict = await session.call_tool(
                    "wxpost_set_source_included",
                    {
                        "workspace_id": workspace_id,
                        "expected_manifest_version": 1,
                        "source_id": "M01",
                        "included": True,
                    },
                )
                assert mcp_conflict.isError
                mcp_error_text = mcp_conflict.content[0].text
                assert (
                    json.loads(mcp_error_text[mcp_error_text.index("{") :])
                    == http_conflict
                )
                assert http_conflict["error"] == {
                    "code": "version_conflict",
                    "message": (
                        "expected manifest version 1, current manifest version is 4"
                    ),
                    "versionKind": "manifest",
                    "expectedVersion": 1,
                    "actualVersion": 4,
                }

                status, included = _json_request(
                    f"{base_url}/workspaces/{workspace_id}/sources/M01/inclusion",
                    method="PUT",
                    payload={
                        "expectedManifestVersion": 4,
                        "included": True,
                    },
                )
                assert status == 200
                assert included["manifestVersion"] == 5
                assert included["sources"][0]["included"] is True

                status, preflight = _json_request(
                    f"{base_url}/workspaces/{workspace_id}/sources/M02/delete-preflight",
                    headers={"X-Expected-Manifest-Version": "5"},
                )
                assert status == 200
                assert preflight["blockedByDraft"] is False
                assert preflight["manifestVersion"] == 5

                deleted = _mcp_value(
                    await session.call_tool(
                        "wxpost_delete_source",
                        {
                            "workspace_id": workspace_id,
                            "expected_manifest_version": 5,
                            "source_id": "M02",
                        },
                    )
                )
                assert deleted["manifestVersion"] == 6
                assert [source["id"] for source in deleted["sources"]] == ["M01"]

        status, final_context = _json_request(
            f"{base_url}/workspaces/{workspace_id}/context"
        )
        assert status == 200
        assert final_context["manifest"] == deleted
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
