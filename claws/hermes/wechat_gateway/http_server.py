from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .core import AssetSource, GatewayError, OfficialAccountGateway

ASSET_REQUEST_LIMIT = 16_384
JSON_REQUEST_LIMIT = 1_100_000
DRAFT_PATH = re.compile(r"^/v1/drafts/([^/]+)$")


class GatewayHTTPServer(ThreadingHTTPServer):
    gateway: OfficialAccountGateway
    bearer_token: str


class GatewayRequestHandler(BaseHTTPRequestHandler):
    server: GatewayHTTPServer
    server_version = "SoarHighWechatGateway/1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if not self._authorized():
            return
        if parsed.path == "/v1/drafts":
            query = parse_qs(parsed.query, keep_blank_values=True)
            if set(query) - {"limit"} or any(
                len(values) != 1 for values in query.values()
            ):
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "Draft list accepts one limit.",
                )
                return
            try:
                limit = int(query.get("limit", ["20"])[0])
            except ValueError:
                limit = 0
            if not 1 <= limit <= 20:
                self._send_error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "invalid_request",
                    "Draft list limit must be 1-20.",
                )
                return
            self._run(
                lambda: {"items": self.server.gateway.batch_get_drafts(count=limit)}
            )
            return
        match = DRAFT_PATH.fullmatch(parsed.path)
        if match:
            media_id = self._media_id(match.group(1))
            if media_id is not None:
                self._run(lambda: {"article": self.server.gateway.get_draft(media_id)})
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if not self._authorized():
            return
        if path == "/v1/images/body":
            payload = self._read_json(limit=ASSET_REQUEST_LIMIT)
            if payload is not None:
                self._run(
                    lambda: {
                        "url": self.server.gateway.upload_body_image(
                            AssetSource.from_payload(payload)
                        )
                    }
                )
            return
        if path == "/v1/images/cover":
            payload = self._read_json(limit=ASSET_REQUEST_LIMIT)
            if payload is not None:
                self._run(
                    lambda: {
                        "mediaId": self.server.gateway.upload_cover(
                            AssetSource.from_payload(payload)
                        )
                    }
                )
            return
        if path == "/v1/drafts":
            payload = self._read_json()
            if payload is not None:
                article = payload.get("article")
                if not isinstance(article, dict):
                    self._send_error(
                        HTTPStatus.UNPROCESSABLE_ENTITY,
                        "invalid_request",
                        "article must be an object.",
                    )
                    return
                self._run(lambda: {"mediaId": self.server.gateway.add_draft(article)})
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")

    def do_PUT(self) -> None:
        if not self._authorized():
            return
        match = DRAFT_PATH.fullmatch(urlsplit(self.path).path)
        if not match:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found", "Route not found.")
            return
        media_id = self._media_id(match.group(1))
        if media_id is None:
            return
        payload = self._read_json()
        if payload is None:
            return
        article = payload.get("article")
        if not isinstance(article, dict):
            self._send_error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "invalid_request",
                "article must be an object.",
            )
            return

        def update() -> dict:
            self.server.gateway.update_draft(media_id, article)
            return {"updated": True}

        self._run(update)

    def _authorized(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.bearer_token}"
        if not hmac.compare_digest(authorization, expected):
            self._send_error(
                HTTPStatus.UNAUTHORIZED, "unauthorized", "Invalid gateway credential."
            )
            return False
        return True

    def _content_length(self, limit: int) -> int | None:
        value = self.headers.get("Content-Length")
        if value is None:
            self._send_error(
                HTTPStatus.LENGTH_REQUIRED,
                "length_required",
                "Content-Length is required.",
            )
            return None
        try:
            length = int(value)
        except ValueError:
            length = -1
        if length <= 0:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_request",
                "Request body must not be empty.",
            )
            return None
        if length > limit:
            self._send_error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "request_too_large",
                "Request body is too large.",
            )
            return None
        return length

    def _read_json(self, *, limit: int = JSON_REQUEST_LIMIT) -> dict[str, Any] | None:
        if self.headers.get_content_type() != "application/json":
            self._send_error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "unsupported_media_type",
                "Requests require application/json.",
            )
            return None
        length = self._content_length(limit)
        if length is None:
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "invalid_json",
                "Request body must be valid JSON.",
            )
            return None
        if not isinstance(payload, dict):
            self._send_error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "invalid_request",
                "Request body must be an object.",
            )
            return None
        return payload

    def _media_id(self, raw_value: str) -> str | None:
        value = unquote(raw_value)
        if (
            not value
            or len(value) > 512
            or any(ord(character) < 32 for character in value)
        ):
            self._send_error(
                HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_request", "Invalid media ID."
            )
            return None
        return value

    def _run(self, operation: Any) -> None:
        try:
            self._send_json(HTTPStatus.OK, operation())
        except GatewayError as error:
            payload: dict[str, Any] = {
                "code": error.code,
                "message": str(error),
                "uncertain": error.uncertain,
            }
            if error.wechat_errcode is not None:
                payload["wechatErrcode"] = error.wechat_errcode
            self._send_json(error.status, payload)

    def _send_error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"code": code, "message": message, "uncertain": False})

    def _send_json(self, status: HTTPStatus | int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        path = urlsplit(self.path).path
        sys.stderr.write(
            f"{self.client_address[0]} {self.command} {path} {code} {size}\n"
        )


def serve(
    *,
    host: str,
    port: int,
    token: str,
    app_id: str,
    app_secret: str,
    asset_base_url: str,
) -> None:
    if not token:
        raise ValueError("WECHAT_GATEWAY_SERVICE_TOKEN is required.")
    server = GatewayHTTPServer((host, port), GatewayRequestHandler)
    server.bearer_token = token
    if not asset_base_url:
        raise ValueError("WECHAT_ASSET_BASE_URL is required.")
    server.gateway = OfficialAccountGateway(
        app_id=app_id,
        app_secret=app_secret,
        asset_base_url=asset_base_url,
    )
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SoarHigh WeChat API gateway.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    serve(
        host=args.host,
        port=args.port,
        token=os.environ.get("WECHAT_GATEWAY_SERVICE_TOKEN", ""),
        app_id=os.environ.get("WECHAT_OFFICIAL_ACCOUNT_APP_ID", ""),
        app_secret=os.environ.get("WECHAT_OFFICIAL_ACCOUNT_APP_SECRET", ""),
        asset_base_url=os.environ.get("WECHAT_ASSET_BASE_URL", ""),
    )


if __name__ == "__main__":
    main()
