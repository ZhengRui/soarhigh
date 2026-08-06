from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

import pytest

from wechat_gateway.core import (
    GatewayError,
    OfficialAccountGateway,
    TransportResponse,
    TransportUnavailable,
)
from wechat_gateway.http_server import (
    BODY_IMAGE_REQUEST_LIMIT,
    COVER_REQUEST_LIMIT,
    GatewayHTTPServer,
    GatewayRequestHandler,
)


class FakeTransport:
    def __init__(self, handler: Callable[..., TransportResponse]) -> None:
        self.handler = handler
        self.requests: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self.lock = threading.Lock()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30,
    ) -> TransportResponse:
        del timeout
        with self.lock:
            self.requests.append((method, url, dict(headers or {}), body))
        return self.handler(method=method, url=url, headers=headers or {}, body=body)


def response(payload: dict, status: int = 200) -> TransportResponse:
    return TransportResponse(status=status, body=json.dumps(payload).encode())


def test_access_token_is_cached_and_refreshed_once_across_concurrent_callers() -> None:
    token_calls = 0
    lock = threading.Lock()

    def handler(**kwargs: Any) -> TransportResponse:
        nonlocal token_calls
        assert kwargs["url"].endswith("/cgi-bin/stable_token")
        with lock:
            token_calls += 1
        return response({"access_token": "shared-token", "expires_in": 7200})

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )
    results: list[str] = []
    threads = [
        threading.Thread(target=lambda: results.append(gateway.access_token()))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["shared-token"] * 8
    assert token_calls == 1


def test_token_error_refreshes_once_then_retries_the_same_typed_operation() -> None:
    token_calls = 0
    upload_tokens: list[str] = []
    force_refresh_values: list[bool] = []

    def handler(**kwargs: Any) -> TransportResponse:
        nonlocal token_calls
        url = kwargs["url"]
        if "/stable_token" in url:
            token_calls += 1
            force_refresh_values.append(json.loads(kwargs["body"])["force_refresh"])
            return response(
                {"access_token": f"token-{token_calls}", "expires_in": 7200}
            )
        upload_tokens.append(url.split("access_token=", 1)[1])
        if len(upload_tokens) == 1:
            return response({"errcode": 42001, "errmsg": "expired"})
        return response({"url": "https://mmbiz.qpic.cn/body.jpg"})

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )

    assert gateway.upload_body_image(
        b"multipart", "multipart/form-data; boundary=test"
    ) == ("https://mmbiz.qpic.cn/body.jpg")
    assert token_calls == 2
    assert upload_tokens == ["token-1", "token-2"]
    assert force_refresh_values == [False, True]


def test_concurrent_token_errors_share_one_refresh() -> None:
    token_calls = 0
    old_token_requests = threading.Barrier(2)

    def handler(**kwargs: Any) -> TransportResponse:
        nonlocal token_calls
        url = kwargs["url"]
        if "/stable_token" in url:
            token_calls += 1
            token = "old-token" if token_calls == 1 else "new-token"
            return response({"access_token": token, "expires_in": 7200})
        if "access_token=old-token" in url:
            old_token_requests.wait(timeout=2)
            return response({"errcode": 42001, "errmsg": "expired"})
        return response({"url": "https://mmbiz.qpic.cn/body.jpg"})

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )
    assert gateway.access_token() == "old-token"
    results: list[str] = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                gateway.upload_body_image(
                    b"multipart", "multipart/form-data; boundary=test"
                )
            )
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["https://mmbiz.qpic.cn/body.jpg"] * 2
    assert token_calls == 2


def test_draft_add_transport_failure_is_uncertain_and_never_retried() -> None:
    add_calls = 0

    def handler(**kwargs: Any) -> TransportResponse:
        nonlocal add_calls
        if "/stable_token" in kwargs["url"]:
            return response({"access_token": "token", "expires_in": 7200})
        if "/draft/add" in kwargs["url"]:
            add_calls += 1
            raise TransportUnavailable
        raise AssertionError(kwargs["url"])

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )

    with pytest.raises(GatewayError, match="response was unavailable") as caught:
        gateway.add_draft({"title": "Test"})
    assert caught.value.code == "upstream_result_uncertain"
    assert caught.value.uncertain is True
    assert add_calls == 1


def test_typed_operations_map_to_the_exact_wechat_api_contract() -> None:
    transport: FakeTransport

    def handler(**kwargs: Any) -> TransportResponse:
        url = kwargs["url"]
        if "/stable_token" in url:
            return response({"access_token": "token", "expires_in": 7200})
        if "/media/uploadimg" in url:
            return response({"url": "https://mmbiz.qpic.cn/body.jpg"})
        if "/material/add_material" in url:
            assert "type=image" in url
            return response({"media_id": "cover-id"})
        if "/draft/add" in url:
            assert json.loads(kwargs["body"]) == {"articles": [{"title": "Test"}]}
            return response({"media_id": "draft-id"})
        if "/draft/update" in url:
            assert json.loads(kwargs["body"]) == {
                "media_id": "draft-id",
                "index": 0,
                "articles": {"title": "Updated"},
            }
            return response({"errcode": 0})
        if "/draft/get" in url:
            assert json.loads(kwargs["body"]) == {"media_id": "draft-id"}
            return response(
                {"news_item": [{"title": "Updated", "content": "<p>Body</p>"}]}
            )
        if "/draft/batchget" in url:
            assert json.loads(kwargs["body"]) == {
                "offset": 0,
                "count": 20,
                "no_content": 0,
            }
            return response({"item": [{"media_id": "draft-id"}]})
        raise AssertionError(url)

    transport = FakeTransport(handler)
    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=transport,
    )

    assert gateway.upload_body_image(
        b"body", "multipart/form-data; boundary=x"
    ).endswith("body.jpg")
    assert (
        gateway.upload_cover(b"cover", "multipart/form-data; boundary=x") == "cover-id"
    )
    assert gateway.add_draft({"title": "Test"}) == "draft-id"
    gateway.update_draft("draft-id", {"title": "Updated"})
    assert gateway.get_draft("draft-id")["content"] == "<p>Body</p>"
    assert gateway.batch_get_drafts(count=20) == [{"media_id": "draft-id"}]


def test_draft_update_sends_unicode_as_utf8_and_readback_remains_strict() -> None:
    update_body: bytes | None = None

    def handler(**kwargs: Any) -> TransportResponse:
        nonlocal update_body
        if "/stable_token" in kwargs["url"]:
            return response({"access_token": "token", "expires_in": 7200})
        if "/draft/update" in kwargs["url"]:
            update_body = kwargs["body"]
            return response({"errcode": 0})
        assert "/draft/get" in kwargs["url"]
        return response(
            {
                "news_item": [
                    {
                        "title": "Fidelity · Component Lab",
                        "content": "<p>“Quoted” — correctly</p>",
                    }
                ]
            }
        )

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )

    article = {
        "title": "Fidelity · Component Lab",
        "content": "<p>“Quoted” — correctly</p>",
    }
    gateway.update_draft("draft-id", article)
    assert update_body is not None
    assert b"Fidelity \xc2\xb7 Component Lab" in update_body
    assert "“Quoted” — correctly".encode() in update_body
    assert b"\\u00b7" not in update_body
    assert b"\\u201c" not in update_body
    assert gateway.get_draft("draft-id") == article


def test_draft_readback_rejects_invalid_utf8_instead_of_rewriting_content() -> None:
    def handler(**kwargs: Any) -> TransportResponse:
        if "/stable_token" in kwargs["url"]:
            return response({"access_token": "token", "expires_in": 7200})
        assert "/draft/get" in kwargs["url"]
        return TransportResponse(
            status=200,
            body=b'{"news_item":[{"title":"Fidelity \xb7 Component Lab"}]}',
        )

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )

    with pytest.raises(GatewayError, match="invalid API JSON") as caught:
        gateway.get_draft("draft-id")
    assert caught.value.code == "invalid_upstream_response"


def test_draft_add_invalid_json_is_uncertain_and_not_retried() -> None:
    add_calls = 0

    def handler(**kwargs: Any) -> TransportResponse:
        nonlocal add_calls
        if "/stable_token" in kwargs["url"]:
            return response({"access_token": "token", "expires_in": 7200})
        assert "/draft/add" in kwargs["url"]
        add_calls += 1
        return TransportResponse(status=200, body=b"{invalid")

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )

    with pytest.raises(GatewayError, match="invalid API JSON") as caught:
        gateway.add_draft({"title": "Draft"})
    assert caught.value.uncertain is True
    assert add_calls == 1


def test_non_success_wechat_status_is_never_reported_as_update_success() -> None:
    def handler(**kwargs: Any) -> TransportResponse:
        if "/stable_token" in kwargs["url"]:
            return response({"access_token": "token", "expires_in": 7200})
        assert "/draft/update" in kwargs["url"]
        return response({}, status=500)

    gateway = OfficialAccountGateway(
        app_id="app-id",
        app_secret="app-secret",
        transport=FakeTransport(handler),
    )

    with pytest.raises(GatewayError, match="HTTP 500") as caught:
        gateway.update_draft("draft-id", {"title": "Draft"})
    assert caught.value.code == "upstream_unavailable"
    assert caught.value.uncertain is False


class FakeGateway:
    def __init__(self) -> None:
        self.upload: tuple[bytes, str] | None = None
        self.article: dict | None = None

    def upload_body_image(self, body: bytes, content_type: str) -> str:
        self.upload = (body, content_type)
        return "https://mmbiz.qpic.cn/body.jpg"

    def upload_cover(self, body: bytes, content_type: str) -> str:
        self.upload = (body, content_type)
        return "cover-id"

    def add_draft(self, article: dict) -> str:
        if article.get("fail"):
            raise GatewayError(
                "upstream_result_uncertain",
                "The WeChat API response was unavailable.",
                uncertain=True,
            )
        self.article = article
        return "draft-id"

    def update_draft(self, media_id: str, article: dict) -> None:
        assert media_id == "draft/id"
        self.article = article

    def get_draft(self, media_id: str) -> dict:
        assert media_id == "draft/id"
        return {"title": "Draft", "content": "<p>Body</p>"}

    def batch_get_drafts(self, *, count: int) -> list[dict]:
        assert count == 10
        return [{"media_id": "draft-id"}]


@contextmanager
def running_server():
    server = GatewayHTTPServer(("127.0.0.1", 0), GatewayRequestHandler)
    server.gateway = FakeGateway()  # type: ignore[assignment]
    server.bearer_token = "gateway-secret"
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def request(
    server: GatewayHTTPServer,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    connection.request(method, path, body=body, headers=headers or {})
    response_value = connection.getresponse()
    payload = json.loads(response_value.read())
    connection.close()
    return response_value.status, payload


def authorized_headers(**values: str) -> dict[str, str]:
    return {"Authorization": "Bearer gateway-secret", **values}


def test_http_gateway_exposes_health_and_requires_its_independent_token() -> None:
    with running_server() as server:
        assert request(server, "GET", "/healthz") == (200, {"status": "ok"})
        status, payload = request(server, "GET", "/v1/drafts?limit=10")
        assert status == 401
        assert payload["code"] == "unauthorized"
        assert request(
            server,
            "GET",
            "/v1/drafts?limit=10",
            headers=authorized_headers(),
        ) == (200, {"items": [{"media_id": "draft-id"}]})


def test_http_gateway_accepts_only_typed_image_and_draft_payloads() -> None:
    with running_server() as server:
        multipart = b"--x\r\nContent-Disposition: form-data; name=media\r\n\r\nimage\r\n--x--\r\n"
        status, payload = request(
            server,
            "POST",
            "/v1/images/body",
            body=multipart,
            headers=authorized_headers(
                **{"Content-Type": "multipart/form-data; boundary=x"}
            ),
        )
        assert (status, payload) == (200, {"url": "https://mmbiz.qpic.cn/body.jpg"})
        assert server.gateway.upload == (multipart, "multipart/form-data; boundary=x")  # type: ignore[attr-defined]

        article = json.dumps({"article": {"title": "Draft"}}).encode()
        assert request(
            server,
            "POST",
            "/v1/drafts",
            body=article,
            headers=authorized_headers(**{"Content-Type": "application/json"}),
        ) == (200, {"mediaId": "draft-id"})
        assert server.gateway.article == {"title": "Draft"}  # type: ignore[attr-defined]

        assert request(
            server,
            "PUT",
            "/v1/drafts/draft%2Fid",
            body=article,
            headers=authorized_headers(**{"Content-Type": "application/json"}),
        ) == (200, {"updated": True})
        assert (
            request(
                server,
                "GET",
                "/v1/drafts/draft%2Fid",
                headers=authorized_headers(),
            )[1]["article"]["content"]
            == "<p>Body</p>"
        )

        status, payload = request(
            server,
            "POST",
            "/v1/arbitrary-wechat-path",
            body=article,
            headers=authorized_headers(**{"Content-Type": "application/json"}),
        )
        assert status == 404
        assert payload["code"] == "not_found"


def test_http_gateway_rejects_wrong_media_types_and_oversized_requests_before_reading() -> (
    None
):
    with running_server() as server:
        status, payload = request(
            server,
            "POST",
            "/v1/images/body",
            body=b"image",
            headers=authorized_headers(**{"Content-Type": "image/jpeg"}),
        )
        assert status == 415
        assert payload["code"] == "unsupported_media_type"

        for path, limit in (
            ("/v1/images/body", BODY_IMAGE_REQUEST_LIMIT),
            ("/v1/images/cover", COVER_REQUEST_LIMIT),
        ):
            status, payload = request(
                server,
                "POST",
                path,
                body=b"multipart",
                headers=authorized_headers(
                    **{
                        "Content-Type": "multipart/form-data; boundary=x",
                        "Content-Length": str(limit + 1),
                    }
                ),
            )
            assert status == 413
            assert payload["code"] == "request_too_large"

        status, payload = request(
            server,
            "POST",
            "/v1/drafts",
            body=b"{}",
            headers=authorized_headers(
                **{
                    "Content-Type": "application/json",
                    "Content-Length": "1100001",
                }
            ),
        )
        assert status == 413
        assert payload["code"] == "request_too_large"


def test_http_gateway_preserves_structured_upstream_uncertainty() -> None:
    with running_server() as server:
        article = json.dumps({"article": {"fail": True}}).encode()
        status, payload = request(
            server,
            "POST",
            "/v1/drafts",
            body=article,
            headers=authorized_headers(**{"Content-Type": "application/json"}),
        )

    assert status == 502
    assert payload == {
        "code": "upstream_result_uncertain",
        "message": "The WeChat API response was unavailable.",
        "uncertain": True,
    }
