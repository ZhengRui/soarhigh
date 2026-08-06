from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

WECHAT_API_BASE = "https://api.weixin.qq.com"
TOKEN_ERROR_CODES = {40014, 42001}
TOKEN_EXPIRY_BUFFER_SECONDS = 300
PUBLIC_ASSET_PREFIX = "public/wxposts/"
BODY_IMAGE_MAX_BYTES = 1024 * 1024 - 1
COVER_IMAGE_MAX_BYTES = 10 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}")
BODY_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png"}
COVER_IMAGE_TYPES = {
    **BODY_IMAGE_TYPES,
    "image/gif": "gif",
    "image/bmp": "bmp",
}
IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/bmp": (b"BM",),
}


def _encode_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes


class TransportUnavailable(Exception):
    pass


@dataclass(frozen=True)
class AssetSource:
    object_key: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> AssetSource:
        if set(payload) != {"objectKey", "sha256", "sizeBytes"}:
            raise GatewayError(
                "invalid_asset", "Asset source fields are invalid.", status=422
            )
        object_key = payload.get("objectKey")
        sha256 = payload.get("sha256")
        size_bytes = payload.get("sizeBytes")
        if (
            not isinstance(object_key, str)
            or not object_key.startswith(PUBLIC_ASSET_PREFIX)
            or object_key.startswith("/")
            or "\\" in object_key
            or any(part in {"", ".", ".."} for part in object_key.split("/"))
            or not isinstance(sha256, str)
            or SHA256_RE.fullmatch(sha256) is None
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes <= 0
        ):
            raise GatewayError(
                "invalid_asset", "Asset source fields are invalid.", status=422
            )
        return cls(object_key, sha256, size_bytes)


@dataclass(frozen=True)
class AssetResponse:
    status: int
    body: bytes


class AssetFetcher(Protocol):
    def fetch(
        self, url: str, *, maximum: int, timeout: float = 30
    ) -> AssetResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class UrllibAssetFetcher:
    def __init__(self) -> None:
        self._opener = build_opener(ProxyHandler({}), _NoRedirectHandler())

    def fetch(self, url: str, *, maximum: int, timeout: float = 30) -> AssetResponse:
        request = Request(url, headers={"Accept": "image/*"}, method="GET")
        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw_length = response.headers.get("Content-Length")
                try:
                    content_length = int(raw_length) if raw_length is not None else None
                except ValueError:
                    content_length = None
                if content_length is not None and content_length > maximum:
                    raise GatewayError(
                        "invalid_asset",
                        "The OSS image exceeds the allowed size.",
                        status=422,
                    )
                return AssetResponse(
                    status=response.status,
                    body=response.read(maximum + 1),
                )
        except HTTPError as error:
            return AssetResponse(
                status=error.code,
                body=error.read(maximum + 1),
            )
        except GatewayError:
            raise
        except (OSError, URLError) as error:
            raise TransportUnavailable from error


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30,
    ) -> TransportResponse: ...


class UrllibTransport:
    def __init__(self) -> None:
        self._opener = build_opener(ProxyHandler({}))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30,
    ) -> TransportResponse:
        request = Request(url, data=body, headers=dict(headers or {}), method=method)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return TransportResponse(status=response.status, body=response.read())
        except HTTPError as error:
            return TransportResponse(status=error.code, body=error.read())
        except (OSError, URLError) as error:
            raise TransportUnavailable from error


class GatewayError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 502,
        uncertain: bool = False,
        wechat_errcode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.uncertain = uncertain
        self.wechat_errcode = wechat_errcode


class OfficialAccountGateway:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        asset_base_url: str,
        transport: HttpTransport | None = None,
        asset_fetcher: AssetFetcher | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not app_id or not app_secret:
            raise ValueError("WeChat Official Account credentials are required.")
        self._app_id = app_id
        self._app_secret = app_secret
        base = urlsplit(asset_base_url)
        if (
            base.scheme not in {"http", "https"}
            or not base.netloc
            or base.username is not None
            or base.password is not None
            or base.query
            or base.fragment
        ):
            raise ValueError("WECHAT_ASSET_BASE_URL must be an HTTP(S) origin or path.")
        self._asset_base_url = asset_base_url.rstrip("/") + "/"
        self._transport = transport or UrllibTransport()
        self._asset_fetcher = asset_fetcher or UrllibAssetFetcher()
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def _decode_json(self, response: TransportResponse, *, context: str) -> dict:
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GatewayError(
                "invalid_upstream_response", f"WeChat returned invalid {context} JSON."
            ) from error
        if not isinstance(payload, dict):
            raise GatewayError(
                "invalid_upstream_response", f"WeChat returned invalid {context} JSON."
            )
        return payload

    def _fetch_access_token_locked(self, *, force_refresh: bool) -> str:
        body = _encode_json(
            {
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret,
                "force_refresh": force_refresh,
            }
        )
        try:
            response = self._transport.request(
                "POST",
                f"{WECHAT_API_BASE}/cgi-bin/stable_token",
                headers={"Content-Type": "application/json"},
                body=body,
            )
        except TransportUnavailable as error:
            raise GatewayError(
                "upstream_unavailable", "Could not obtain a WeChat access token."
            ) from error
        if not 200 <= response.status < 300:
            raise GatewayError(
                "upstream_unavailable",
                f"WeChat access-token API returned HTTP {response.status}.",
            )
        payload = self._decode_json(response, context="access-token")
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            errcode = payload.get("errcode")
            message = payload.get("errmsg", "unknown error")
            if errcode == 40164:
                message = "The VPS IP is not in the WeChat Official Account IP allowlist (40164)."
            else:
                message = f"WeChat rejected the Official Account credentials ({errcode or 'unknown'}): {message}"
            raise GatewayError(
                "wechat_token_error",
                message,
                wechat_errcode=errcode if isinstance(errcode, int) else None,
            )
        expires_in = payload.get("expires_in", 7200)
        if not isinstance(expires_in, int) or expires_in <= 0:
            expires_in = 7200
        self._token = token
        self._token_expires_at = self._clock() + expires_in
        return token

    def access_token(self) -> str:
        with self._token_lock:
            if (
                self._token
                and self._token_expires_at > self._clock() + TOKEN_EXPIRY_BUFFER_SECONDS
            ):
                return self._token
            return self._fetch_access_token_locked(force_refresh=False)

    def _refresh_stale_token(self, stale_token: str) -> str:
        with self._token_lock:
            if (
                self._token
                and self._token != stale_token
                and self._token_expires_at > self._clock() + TOKEN_EXPIRY_BUFFER_SECONDS
            ):
                return self._token
            self._token = None
            self._token_expires_at = 0
            return self._fetch_access_token_locked(force_refresh=True)

    def _wechat_request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        params: Mapping[str, str] | None = None,
        uncertain_on_transport: bool = False,
        retry_token: bool = True,
        token: str | None = None,
    ) -> dict:
        access_token = token or self.access_token()
        query = urlencode({**dict(params or {}), "access_token": access_token})
        headers = {"Content-Type": content_type} if content_type else {}
        try:
            response = self._transport.request(
                method,
                f"{WECHAT_API_BASE}{path}?{query}",
                headers=headers,
                body=body,
            )
        except TransportUnavailable as error:
            raise GatewayError(
                "upstream_result_uncertain"
                if uncertain_on_transport
                else "upstream_unavailable",
                "The WeChat API response was unavailable.",
                uncertain=uncertain_on_transport,
            ) from error
        if not 200 <= response.status < 300:
            raise GatewayError(
                "upstream_result_uncertain"
                if uncertain_on_transport
                else "upstream_unavailable",
                f"WeChat API returned HTTP {response.status}.",
                uncertain=uncertain_on_transport,
            )
        try:
            payload = self._decode_json(response, context="API")
        except GatewayError as error:
            if not uncertain_on_transport:
                raise
            raise GatewayError(
                error.code,
                str(error),
                status=error.status,
                uncertain=True,
                wechat_errcode=error.wechat_errcode,
            ) from error
        errcode = payload.get("errcode", 0)
        if errcode in TOKEN_ERROR_CODES and retry_token:
            refreshed = self._refresh_stale_token(access_token)
            return self._wechat_request(
                method,
                path,
                body=body,
                content_type=content_type,
                params=params,
                uncertain_on_transport=uncertain_on_transport,
                retry_token=False,
                token=refreshed,
            )
        if errcode:
            raise GatewayError(
                "wechat_api_error",
                f"WeChat API error {errcode}: {payload.get('errmsg', 'unknown error')}",
                wechat_errcode=errcode if isinstance(errcode, int) else None,
            )
        return payload

    def _asset_url(self, object_key: str) -> str:
        return f"{self._asset_base_url}{quote(object_key, safe='/')}"

    def _download_asset(
        self,
        source: AssetSource,
        *,
        allowed_types: Mapping[str, str],
        maximum: int,
    ) -> tuple[bytes, str, str]:
        if source.size_bytes > maximum:
            raise GatewayError(
                "invalid_asset", "The OSS image exceeds the allowed size.", status=422
            )
        try:
            response = self._asset_fetcher.fetch(
                self._asset_url(source.object_key), maximum=maximum
            )
        except TransportUnavailable as error:
            raise GatewayError(
                "asset_unavailable", "The OSS image could not be downloaded."
            ) from error
        if not 200 <= response.status < 300:
            raise GatewayError(
                "asset_unavailable",
                f"The OSS image returned HTTP {response.status}.",
            )
        if not response.body:
            raise GatewayError("invalid_asset", "The OSS image is empty.", status=422)
        if len(response.body) > maximum:
            raise GatewayError(
                "invalid_asset", "The OSS image exceeds the allowed size.", status=422
            )
        if len(response.body) != source.size_bytes:
            raise GatewayError(
                "asset_changed",
                "The OSS image size no longer matches the Public Revision.",
                status=409,
            )
        if hashlib.sha256(response.body).hexdigest() != source.sha256:
            raise GatewayError(
                "asset_changed",
                "The OSS image content no longer matches the Public Revision.",
                status=409,
            )
        detected_mime_type = next(
            (
                mime_type
                for mime_type, signatures in IMAGE_SIGNATURES.items()
                if any(response.body.startswith(signature) for signature in signatures)
            ),
            None,
        )
        if detected_mime_type not in allowed_types:
            raise GatewayError(
                "invalid_asset",
                "The OSS image content is not a supported image type.",
                status=422,
            )
        return (
            response.body,
            detected_mime_type,
            allowed_types[detected_mime_type],
        )

    @staticmethod
    def _multipart_image(
        content: bytes, *, filename: str, mime_type: str
    ) -> tuple[bytes, str]:
        boundary = f"soarhigh-{secrets.token_hex(16)}"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {mime_type}\r\n\r\n".encode(),
                content,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
        )
        return body, f"multipart/form-data; boundary={boundary}"

    def upload_body_image(self, source: AssetSource) -> str:
        content, mime_type, extension = self._download_asset(
            source,
            allowed_types=BODY_IMAGE_TYPES,
            maximum=BODY_IMAGE_MAX_BYTES,
        )
        body, content_type = self._multipart_image(
            content,
            filename=f"body.{extension}",
            mime_type=mime_type,
        )
        payload = self._wechat_request(
            "POST",
            "/cgi-bin/media/uploadimg",
            body=body,
            content_type=content_type,
        )
        url = payload.get("url")
        if not isinstance(url, str) or not url:
            raise GatewayError(
                "invalid_upstream_response", "WeChat did not return a body-image URL."
            )
        return url

    def upload_cover(self, source: AssetSource) -> str:
        content, mime_type, extension = self._download_asset(
            source,
            allowed_types=COVER_IMAGE_TYPES,
            maximum=COVER_IMAGE_MAX_BYTES,
        )
        body, content_type = self._multipart_image(
            content,
            filename=f"cover.{extension}",
            mime_type=mime_type,
        )
        payload = self._wechat_request(
            "POST",
            "/cgi-bin/material/add_material",
            body=body,
            content_type=content_type,
            params={"type": "image"},
        )
        media_id = payload.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise GatewayError(
                "invalid_upstream_response", "WeChat did not return a cover media ID."
            )
        return media_id

    def add_draft(self, article: dict) -> str:
        payload = self._wechat_request(
            "POST",
            "/cgi-bin/draft/add",
            body=_encode_json({"articles": [article]}),
            content_type="application/json",
            uncertain_on_transport=True,
        )
        media_id = payload.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise GatewayError(
                "invalid_upstream_response",
                "WeChat did not return a draft media ID.",
                uncertain=True,
            )
        return media_id

    def update_draft(self, media_id: str, article: dict) -> None:
        self._wechat_request(
            "POST",
            "/cgi-bin/draft/update",
            body=_encode_json({"media_id": media_id, "index": 0, "articles": article}),
            content_type="application/json",
        )

    def get_draft(self, media_id: str) -> dict:
        payload = self._wechat_request(
            "POST",
            "/cgi-bin/draft/get",
            body=_encode_json({"media_id": media_id}),
            content_type="application/json",
        )
        items = payload.get("news_item")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise GatewayError(
                "invalid_upstream_response",
                "WeChat returned an invalid draft readback.",
            )
        return items[0]

    def batch_get_drafts(self, *, count: int) -> list[dict]:
        payload = self._wechat_request(
            "POST",
            "/cgi-bin/draft/batchget",
            body=_encode_json({"offset": 0, "count": count, "no_content": 0}),
            content_type="application/json",
        )
        items = payload.get("item")
        if not isinstance(items, list):
            raise GatewayError(
                "invalid_upstream_response", "WeChat returned an invalid draft list."
            )
        return [item for item in items if isinstance(item, dict)]
