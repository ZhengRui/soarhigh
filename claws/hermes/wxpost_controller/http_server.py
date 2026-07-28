from __future__ import annotations

import argparse
import hmac
import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast

from .core import (
    InvalidRequest,
    InvalidWorkspace,
    ValidationUnavailable,
    VersionConflict,
    WorkspaceController,
    WorkspaceError,
    WorkspaceNotFound,
    error_response,
)

CONTEXT_PATH = re.compile(r"^/workspaces/([^/]+)/context$")
SOURCES_PATH = re.compile(r"^/workspaces/([^/]+)/sources$")
MAX_REQUEST_BYTES = 1_000_000


class ControllerHTTPServer(ThreadingHTTPServer):
    controller: WorkspaceController
    bearer_token: str


class ControllerRequestHandler(BaseHTTPRequestHandler):
    server: ControllerHTTPServer

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if not self._authorized():
            return
        match = CONTEXT_PATH.fullmatch(self.path)
        if match is None:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
            return
        self._run_controller(lambda: self.server.controller.get_context(match.group(1)))

    def do_PATCH(self) -> None:
        if not self._authorized():
            return
        match = SOURCES_PATH.fullmatch(self.path)
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
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "")
        except ValueError:
            self._send_error(
                HTTPStatus.BAD_REQUEST, "invalid_request", "Content-Length required"
            )
            return None
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "invalid_request",
                "request body size is invalid",
            )
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(
                HTTPStatus.BAD_REQUEST, "invalid_json", "request body must be JSON"
            )
            return None
        if not isinstance(payload, dict):
            self._send_error(
                HTTPStatus.BAD_REQUEST, "invalid_request", "JSON object required"
            )
            return None
        return payload

    def _run_controller(self, operation) -> None:
        try:
            result = operation()
        except WorkspaceError as exc:
            if isinstance(exc, VersionConflict):
                status = HTTPStatus.CONFLICT
            elif isinstance(exc, WorkspaceNotFound):
                status = HTTPStatus.NOT_FOUND
            elif isinstance(exc, ValidationUnavailable):
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
