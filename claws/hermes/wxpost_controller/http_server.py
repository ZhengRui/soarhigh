from __future__ import annotations

import argparse
import hmac
import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from .core import (
    MAX_SOURCE_BYTES,
    ConfirmationRequired,
    InvalidRequest,
    InvalidWorkspace,
    UpstreamUnavailable,
    ValidationUnavailable,
    VersionConflict,
    WorkspaceController,
    WorkspaceError,
    WorkspaceNotFound,
    error_response,
)

WORKSPACE_PATH = re.compile(r"^/workspaces/([^/]+)$")
CONTEXT_PATH = re.compile(r"^/workspaces/([^/]+)/context$")
SOURCES_PATH = re.compile(r"^/workspaces/([^/]+)/sources$")
SOURCE_IMPORT_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)/import$")
SOURCE_INCLUSION_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)/inclusion$")
SOURCE_DELETE_PREFLIGHT_PATH = re.compile(
    r"^/workspaces/([^/]+)/sources/([^/]+)/delete-preflight$"
)
SOURCE_PATH = re.compile(r"^/workspaces/([^/]+)/sources/([^/]+)$")
UPLOADS_PATH = re.compile(r"^/workspaces/([^/]+)/uploads$")
MAX_REQUEST_BYTES = 1_000_000


class ControllerHTTPServer(ThreadingHTTPServer):
    controller: WorkspaceController
    bearer_token: str


class ControllerRequestHandler(BaseHTTPRequestHandler):
    server: ControllerHTTPServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if not self._authorized():
            return
        context_match = CONTEXT_PATH.fullmatch(path)
        if context_match is not None:
            self._run_controller(
                lambda: self.server.controller.get_context(context_match.group(1))
            )
            return
        preflight_match = SOURCE_DELETE_PREFLIGHT_PATH.fullmatch(path)
        if preflight_match is not None:
            self._run_controller(
                lambda: self.server.controller.delete_source_preflight(
                    preflight_match.group(1),
                    source_id=preflight_match.group(2),
                )
            )
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_PATCH(self) -> None:
        if not self._authorized():
            return
        match = SOURCES_PATH.fullmatch(urlsplit(self.path).path)
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
        workspace_match = WORKSPACE_PATH.fullmatch(path)
        if workspace_match is not None:
            payload = self._read_json_body()
            if payload is None or not self._accept_fields(
                payload,
                {"meetingId", "editorial"},
                "workspace bootstrap",
            ):
                return
            self._run_controller(
                lambda: self.server.controller.bootstrap_workspace(
                    workspace_match.group(1),
                    meeting_id=cast(str | None, payload.get("meetingId")),
                    editorial=cast(
                        dict[str, Any],
                        payload.get("editorial"),
                    ),
                )
            )
            return

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
            raw_version = self.headers.get("X-Expected-Manifest-Version")
            try:
                expected_version = int(raw_version or "")
            except ValueError:
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "X-Expected-Manifest-Version must be an integer",
                )
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

    def do_DELETE(self) -> None:
        if not self._authorized():
            return
        match = SOURCE_PATH.fullmatch(urlsplit(self.path).path)
        if match is None:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        payload = self._read_json_body()
        if payload is None or not self._accept_fields(
            payload,
            {"expectedManifestVersion", "confirmReferenced"},
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
                confirm_referenced=cast(
                    bool,
                    payload.get("confirmReferenced", False),
                ),
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

    def _run_controller(self, operation) -> None:
        try:
            result = operation()
        except WorkspaceError as exc:
            if isinstance(exc, (VersionConflict, ConfirmationRequired)):
                status = HTTPStatus.CONFLICT
            elif isinstance(exc, WorkspaceNotFound):
                status = HTTPStatus.NOT_FOUND
            elif isinstance(
                exc,
                (ValidationUnavailable, UpstreamUnavailable),
            ):
                status = HTTPStatus.SERVICE_UNAVAILABLE
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
            self._send_json(HTTPStatus.OK, result)

    def _send_error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
) -> ControllerHTTPServer:
    if not bearer_token:
        raise ValueError("controller bearer token must not be empty")
    server = ControllerHTTPServer((host, port), ControllerRequestHandler)
    server.controller = WorkspaceController(workspace_root)
    server.bearer_token = bearer_token
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the WXPost workspace API")
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("WXPOST_WORKSPACE_ROOT", "/workspace"),
    )
    parser.add_argument(
        "--token", default=os.environ.get("WXPOST_CONTROLLER_TOKEN", "")
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = build_server(
        workspace_root=args.workspace_root,
        bearer_token=args.token,
        host=args.host,
        port=args.port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
