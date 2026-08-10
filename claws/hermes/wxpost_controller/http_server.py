from __future__ import annotations

import argparse
import hmac
import json
import os
import queue
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from .core import (
    MAX_SOURCE_BYTES,
    InvalidRequest,
    InvalidWorkspace,
    SourceReferencedByDraft,
    UpstreamUnavailable,
    ValidationUnavailable,
    VersionConflict,
    WorkspaceController,
    WorkspaceError,
    WorkspaceAlreadyExists,
    WorkspaceNotFound,
    error_response,
)
from .errors import DraftOperationNotFound, HermesTurnFailed, HermesUnavailable
from .hermes_editorial import (
    HermesEditorialClient,
    MainRuntimeResolver,
    OneShotRunner,
)
from .hermes_session import (
    HermesDescriptionService,
    HermesDraftService,
    HermesSessionClient,
)

WORKSPACE_PATH = re.compile(r"^/workspaces/([^/]+)$")
WORKSPACES_PATH = "/workspaces"
CONTEXT_PATH = re.compile(r"^/workspaces/([^/]+)/context$")
SOURCES_PATH = re.compile(r"^/workspaces/([^/]+)/sources$")
SOURCE_IMPORT_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)/import$")
SOURCE_INCLUSION_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)/inclusion$")
SOURCE_DELETE_PREFLIGHT_PATH = re.compile(
    r"^/workspaces/([^/]+)/sources/([^/]+)/delete-preflight$"
)
SOURCE_CONTENT_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)/content$")
SOURCE_DESCRIPTION_PATH = re.compile(
    r"^/workspaces/([^/]+)/sources/([^/]+)/description-suggestion$"
)
SOURCE_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)$")
UPLOADS_PATH = re.compile(r"^/workspaces/([^/]+)/uploads$")
DRAFT_SESSION_PATH = re.compile(r"^/workspaces/([^/]+)/draft/session$")
DRAFT_OPERATION_PATH = re.compile(
    r"^/workspaces/([^/]+)/draft/operations/([^/]+)$"
)
DRAFT_SAVE_PATH = re.compile(r"^/workspaces/([^/]+)/draft/save$")
DRAFT_GENERATE_PATH = re.compile(r"^/workspaces/([^/]+)/draft/generate$")
DRAFT_CHAT_PATH = re.compile(r"^/workspaces/([^/]+)/draft/chat$")
VOICE_TONE_SUGGESTION_PATH = re.compile(r"^/workspaces/([^/]+)/voice-tone/suggestion$")
SESSION_RETIRE_PATH = "/sessions/retire"
MAX_REQUEST_BYTES = 1_000_000


class ControllerHTTPServer(ThreadingHTTPServer):
    controller: WorkspaceController
    description_service: HermesDescriptionService
    draft_service: HermesDraftService
    editorial_client: HermesEditorialClient
    bearer_token: str
    draft_heartbeat_seconds: float


class ControllerRequestHandler(BaseHTTPRequestHandler):
    server: ControllerHTTPServer

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if not self._authorized():
            return
        if path == WORKSPACES_PATH:
            query = parse_qs(parsed.query, keep_blank_values=True)
            if set(query) - {"page", "page_size"} or any(
                len(values) != 1 for values in query.values()
            ):
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "workspace list accepts one page and page_size value",
                )
                return
            try:
                page = int(query.get("page", ["1"])[0])
                page_size = int(query.get("page_size", ["10"])[0])
            except ValueError:
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "workspace page and page_size must be integers",
                )
                return
            self._run_controller(
                lambda: self.server.controller.list_workspaces(
                    page=page,
                    page_size=page_size,
                )
            )
            return
        context_match = CONTEXT_PATH.fullmatch(path)
        if context_match is not None:
            self._run_controller(
                lambda: self.server.controller.get_context(context_match.group(1))
            )
            return
        draft_session_match = DRAFT_SESSION_PATH.fullmatch(path)
        if draft_session_match is not None:
            self._run_controller(
                lambda: self.server.draft_service.history(draft_session_match.group(1))
            )
            return
        draft_operation_match = DRAFT_OPERATION_PATH.fullmatch(path)
        if draft_operation_match is not None:
            self._run_controller(
                lambda: self.server.draft_service.operation(
                    draft_operation_match.group(1),
                    draft_operation_match.group(2),
                ),
                cache_control="private, no-store",
            )
            return
        content_match = SOURCE_CONTENT_PATH.fullmatch(path)
        if content_match is not None:
            self._run_source_read(
                lambda: self.server.controller.read_source(
                    content_match.group(1),
                    source_id=content_match.group(2),
                )
            )
            return
        preflight_match = SOURCE_DELETE_PREFLIGHT_PATH.fullmatch(path)
        if preflight_match is not None:
            expected_version = self._read_expected_manifest_version()
            if expected_version is None:
                return
            self._run_controller(
                lambda: self.server.controller.delete_source_preflight(
                    preflight_match.group(1),
                    expected_manifest_version=expected_version,
                    source_id=preflight_match.group(2),
                )
            )
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_PATCH(self) -> None:
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        workspace_match = WORKSPACE_PATH.fullmatch(path)
        if workspace_match is not None:
            payload = self._read_json_body()
            required_fields = {
                "expectedManifestVersion",
                "meetingId",
                "editorial",
            }
            accepted_fields = required_fields | {"sourceUpdates"}
            if payload is None or not self._accept_fields(
                payload,
                accepted_fields,
                "workspace update",
            ):
                return
            missing_fields = required_fields - set(payload)
            if missing_fields:
                self._send_json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    error_response(
                        InvalidRequest(
                            "missing workspace update fields: "
                            + ", ".join(sorted(missing_fields))
                        )
                    ),
                )
                return
            self._run_controller(
                lambda: self.server.controller.update_workspace(
                    workspace_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    meeting_id=cast(str | None, payload.get("meetingId")),
                    editorial=cast(
                        dict[str, Any],
                        payload.get("editorial"),
                    ),
                    source_updates=cast(
                        list[dict[str, Any]],
                        payload.get("sourceUpdates", []),
                    ),
                )
            )
            return

        match = SOURCES_PATH.fullmatch(path)
        if match is None:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        payload = self._read_json_body()
        if payload is None:
            return
        unknown_fields = set(payload) - {
            "expectedManifestVersion",
            "updates",
        }
        if unknown_fields:
            self._send_json(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                error_response(
                    InvalidRequest(
                        "unsupported source update fields: "
                        + ", ".join(sorted(unknown_fields))
                    )
                ),
            )
            return
        self._run_controller(
            lambda: self.server.controller.update_sources(
                match.group(1),
                expected_manifest_version=cast(
                    int,
                    payload.get("expectedManifestVersion"),
                ),
                updates=cast(
                    list[dict[str, Any]],
                    payload.get("updates"),
                ),
            )
        )

    def do_PUT(self) -> None:
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        inclusion_match = SOURCE_INCLUSION_PATH.fullmatch(path)
        if inclusion_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"expectedManifestVersion", "included"},
                "source inclusion",
            ):
                return
            self._run_controller(
                lambda: self.server.controller.set_source_included(
                    inclusion_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    source_id=inclusion_match.group(2),
                    included=cast(bool, payload.get("included")),
                )
            )
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_POST(self) -> None:
        if not self._authorized():
            return
        parsed = urlsplit(self.path)
        if parsed.path == SESSION_RETIRE_PATH:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"sessionId"},
                "session retirement",
            ):
                return
            session_id = payload.get("sessionId")
            if not isinstance(session_id, str) or not session_id.strip():
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "sessionId must be a non-empty string",
                )
                return
            self._run_controller(
                lambda: self.server.draft_service.retire_session(session_id.strip())
            )
            return
        if parsed.path == WORKSPACES_PATH:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"meetingId", "editorial", "createdBy"},
                "workspace creation",
            ):
                return
            self._run_controller(
                lambda: self.server.controller.create_workspace(
                    meeting_id=cast(str | None, payload.get("meetingId")),
                    editorial=cast(dict[str, Any], payload.get("editorial")),
                    created_by=cast(dict[str, Any], payload.get("createdBy")),
                )
            )
            return
        description_match = SOURCE_DESCRIPTION_PATH.fullmatch(parsed.path)
        if description_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"expectedManifestVersion", "currentDescription"},
                "source description suggestion",
            ):
                return
            self._run_controller(
                lambda: self.server.description_service.suggest(
                    description_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    source_id=description_match.group(2),
                    current_description=cast(
                        str,
                        payload.get("currentDescription"),
                    ),
                )
            )
            return

        draft_save_match = DRAFT_SAVE_PATH.fullmatch(parsed.path)
        if draft_save_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {
                    "expectedManifestVersion",
                    "expectedDraftVersion",
                    "document",
                },
                "draft save",
            ):
                return
            self._run_controller(
                lambda: self._save_draft(
                    draft_save_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    expected_draft_version=cast(
                        int,
                        payload.get("expectedDraftVersion"),
                    ),
                    document=cast(
                        dict[str, Any],
                        payload.get("document"),
                    ),
                )
            )
            return

        draft_generate_match = DRAFT_GENERATE_PATH.fullmatch(parsed.path)
        if draft_generate_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {
                    "expectedManifestVersion",
                    "expectedDraftVersion",
                },
                "draft generation",
            ):
                return
            self._run_controller(
                lambda: self.server.draft_service.generate(
                    draft_generate_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    expected_draft_version=cast(
                        int,
                        payload.get("expectedDraftVersion"),
                    ),
                )
            )
            return

        draft_chat_match = DRAFT_CHAT_PATH.fullmatch(parsed.path)
        if draft_chat_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {
                    "expectedManifestVersion",
                    "expectedDraftVersion",
                    "operationId",
                    "message",
                    "selectedText",
                },
                "draft revision",
            ):
                return
            self._run_draft_stream(
                lambda on_progress: self.server.draft_service.chat(
                    draft_chat_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    expected_draft_version=cast(
                        int,
                        payload.get("expectedDraftVersion"),
                    ),
                    operation_id=cast(str, payload.get("operationId")),
                    message=cast(str, payload.get("message")),
                    selected_text=cast(
                        str | None,
                        payload.get("selectedText"),
                    ),
                    on_progress=on_progress,
                )
            )
            return

        voice_tone_match = VOICE_TONE_SUGGESTION_PATH.fullmatch(parsed.path)
        if voice_tone_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"name"},
                "voice and tone suggestion",
            ):
                return
            name = payload.get("name")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 64:
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "voice and tone name must contain 1 to 64 characters",
                )
                return
            self._run_controller(
                lambda: {
                    "instruction": self.server.editorial_client.suggest_voice_tone_instruction(
                        profile_name=name.strip(),
                        workspace_context=self.server.controller.get_context(
                            voice_tone_match.group(1)
                        ),
                    )
                }
            )
            return

        import_match = SOURCE_IMPORT_PATH.fullmatch(parsed.path)
        if import_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"expectedManifestVersion"},
                "source import",
            ):
                return
            self._run_controller(
                lambda: self.server.controller.import_source(
                    import_match.group(1),
                    expected_manifest_version=cast(
                        int,
                        payload.get("expectedManifestVersion"),
                    ),
                    source_id=import_match.group(2),
                )
            )
            return

        upload_match = UPLOADS_PATH.fullmatch(parsed.path)
        if upload_match is not None:
            query = parse_qs(parsed.query, keep_blank_values=True)
            if set(query) != {"filename"} or len(query["filename"]) != 1:
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "one filename query parameter is required",
                )
                return
            expected_version = self._read_expected_manifest_version()
            if expected_version is None:
                return
            data = self._read_body(MAX_SOURCE_BYTES)
            if data is None:
                return
            self._run_controller(
                lambda: self.server.controller.upload_source(
                    upload_match.group(1),
                    expected_manifest_version=expected_version,
                    origin="web-upload",
                    filename=query["filename"][0],
                    mime_type=self.headers.get(
                        "Content-Type",
                        "application/octet-stream",
                    ),
                    data=data,
                )
            )
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def _save_draft(
        self,
        workspace_id: str,
        *,
        expected_manifest_version: int,
        expected_draft_version: int,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        self.server.controller.save_draft(
            workspace_id,
            expected_manifest_version=expected_manifest_version,
            expected_draft_version=expected_draft_version,
            document=document,
        )
        return self.server.controller.get_context(workspace_id)

    def do_DELETE(self) -> None:
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        draft_session_match = DRAFT_SESSION_PATH.fullmatch(path)
        if draft_session_match is not None:
            self._run_controller(
                lambda: self.server.draft_service.reset(draft_session_match.group(1))
            )
            return
        workspace_match = WORKSPACE_PATH.fullmatch(path)
        if workspace_match is not None:
            expected_version = self._read_expected_manifest_version()
            if expected_version is None:
                return
            self._run_controller(
                lambda: self.server.draft_service.delete_workspace(
                    workspace_match.group(1),
                    expected_manifest_version=expected_version,
                )
            )
            return
        match = SOURCE_PATH.fullmatch(path)
        if match is None:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        payload = self._read_json_body()
        if payload is None or not self._accept_fields(
            payload,
            {"expectedManifestVersion"},
            "source delete",
        ):
            return
        self._run_controller(
            lambda: self.server.controller.delete_source(
                match.group(1),
                expected_manifest_version=cast(
                    int,
                    payload.get("expectedManifestVersion"),
                ),
                source_id=match.group(2),
            )
        )

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.bearer_token}"
        actual = self.headers.get("Authorization", "")
        if not hmac.compare_digest(actual, expected):
            self._send_error(
                HTTPStatus.UNAUTHORIZED,
                "unauthorized",
                "valid bearer token required",
            )
            return False
        return True

    def _read_json_body(self) -> dict[str, Any] | None:
        body = self._read_body(MAX_REQUEST_BYTES)
        if body is None:
            return None
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "request body must be JSON",
            )
            return None
        if not isinstance(payload, dict):
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "JSON object required",
            )
            return None
        return payload

    def _read_expected_manifest_version(self) -> int | None:
        raw_version = self.headers.get("X-Expected-Manifest-Version")
        try:
            return int(raw_version or "")
        except ValueError:
            self._send_error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "invalid_request",
                "X-Expected-Manifest-Version must be an integer",
            )
            return None

    def _read_body(self, maximum: int) -> bytes | None:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "")
        except ValueError:
            self._send_error(
                HTTPStatus.BAD_REQUEST, "invalid_request", "Content-Length required"
            )
            return None
        if length <= 0 or length > maximum:
            self._send_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "invalid_request",
                "request body size is invalid",
            )
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "request body ended before Content-Length",
            )
            return None
        return body

    def _accept_fields(
        self,
        payload: dict[str, Any],
        allowed: set[str],
        label: str,
    ) -> bool:
        unknown = set(payload) - allowed
        if not unknown:
            return True
        self._send_json(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            error_response(
                InvalidRequest(
                    f"unsupported {label} fields: " + ", ".join(sorted(unknown))
                )
            ),
        )
        return False

    def _run_controller(self, operation, *, cache_control: str | None = None) -> None:
        try:
            result = operation()
        except WorkspaceError as exc:
            if isinstance(
                exc,
                (
                    VersionConflict,
                    SourceReferencedByDraft,
                    WorkspaceAlreadyExists,
                ),
            ):
                status = HTTPStatus.CONFLICT
            elif isinstance(exc, (WorkspaceNotFound, DraftOperationNotFound)):
                status = HTTPStatus.NOT_FOUND
            elif isinstance(
                exc,
                (
                    ValidationUnavailable,
                    UpstreamUnavailable,
                    HermesUnavailable,
                ),
            ):
                status = HTTPStatus.SERVICE_UNAVAILABLE
            elif isinstance(exc, HermesTurnFailed):
                status = HTTPStatus.BAD_GATEWAY
            elif isinstance(exc, (InvalidRequest, InvalidWorkspace)):
                status = HTTPStatus.UNPROCESSABLE_ENTITY
            else:
                status = HTTPStatus.BAD_REQUEST
            self._send_json(status, error_response(exc))
        except Exception:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "internal_error",
                "controller operation failed",
            )
        else:
            self._send_json(HTTPStatus.OK, result, cache_control=cache_control)

    def _run_draft_stream(self, operation) -> None:
        connected = True

        def send_event(event: str, payload: Any) -> None:
            nonlocal connected
            if not connected:
                return
            body = (
                f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            ).encode("utf-8")
            try:
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                connected = False

        def send_heartbeat() -> None:
            nonlocal connected
            if not connected:
                return
            try:
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                connected = False

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "private, no-store, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        send_event("progress", {"stage": "request_started"})
        outcomes: queue.Queue[tuple[str, Any]] = queue.Queue()

        def run_operation() -> None:
            try:
                result = operation(
                    lambda progress: outcomes.put(("progress", progress))
                )
            except WorkspaceError as exc:
                outcomes.put(("error", error_response(exc)["error"]))
            except Exception:
                outcomes.put(
                    (
                        "error",
                        {
                            "code": "internal_error",
                            "message": "controller operation failed",
                        },
                    )
                )
            else:
                outcomes.put(("complete", result))

        threading.Thread(
            target=run_operation,
            name="wxpost-draft-stream",
            daemon=True,
        ).start()
        while True:
            try:
                event, payload = outcomes.get(
                    timeout=self.server.draft_heartbeat_seconds
                )
            except queue.Empty:
                send_heartbeat()
                continue
            send_event(event, payload)
            if event in {"complete", "error"}:
                return

    def _run_source_read(self, operation) -> None:
        try:
            data, mime_type = operation()
        except WorkspaceError as exc:
            if isinstance(exc, WorkspaceNotFound):
                status = HTTPStatus.NOT_FOUND
            elif isinstance(exc, (InvalidRequest, InvalidWorkspace)):
                status = HTTPStatus.UNPROCESSABLE_ENTITY
            else:
                status = HTTPStatus.BAD_REQUEST
            self._send_json(status, error_response(exc))
        except Exception:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "internal_error",
                "controller operation failed",
            )
        else:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, no-store")
            self.end_headers()
            self.wfile.write(data)

    def _send_error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    def _send_json(
        self,
        status: HTTPStatus,
        payload: Any,
        *,
        cache_control: str | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def build_server(
    *,
    workspace_root: str,
    bearer_token: str,
    host: str = "127.0.0.1",
    port: int = 8787,
    hermes_serve_url: str = "ws://127.0.0.1:9119/api/ws",
    editorial_runner: OneShotRunner | None = None,
    editorial_runtime_resolver: MainRuntimeResolver | None = None,
    draft_heartbeat_seconds: float = 15,
) -> ControllerHTTPServer:
    if not bearer_token:
        raise ValueError("controller bearer token must not be empty")
    if draft_heartbeat_seconds <= 0:
        raise ValueError("Draft heartbeat interval must be positive")
    server = ControllerHTTPServer((host, port), ControllerRequestHandler)
    server.controller = WorkspaceController(workspace_root)
    session_client = HermesSessionClient(
        serve_url=hermes_serve_url,
        token=bearer_token,
    )
    server.draft_service = HermesDraftService(
        controller=server.controller,
        session_client=session_client,
    )
    server.description_service = HermesDescriptionService(
        controller=server.controller,
        session_client=session_client,
        retire_session=server.draft_service.retire_session,
    )
    server.editorial_client = HermesEditorialClient(
        runner=editorial_runner,
        runtime_resolver=editorial_runtime_resolver,
    )
    server.bearer_token = bearer_token
    server.draft_heartbeat_seconds = draft_heartbeat_seconds
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the WxPost workspace API")
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace"),
    )
    parser.add_argument("--token", default=os.environ.get("WXPOST_SERVICE_TOKEN", ""))
    parser.add_argument(
        "--hermes-serve-url",
        default=os.environ.get(
            "HERMES_SERVE_URL",
            "ws://127.0.0.1:9119/api/ws",
        ),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = build_server(
        workspace_root=args.workspace_root,
        bearer_token=args.token,
        host=args.host,
        port=args.port,
        hermes_serve_url=args.hermes_serve_url,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
