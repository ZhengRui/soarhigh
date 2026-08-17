from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_ROOT = REPO_ROOT / "claws" / "hermes"
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from wxpost_controller import publication_runner  # noqa: E402
from wxpost_controller.core import (  # noqa: E402
    SOARHIGH_SERVICE_USER_AGENT,
    InvalidRequest,
)
from wxpost_controller.errors import (  # noqa: E402
    DraftOperationInProgress,
    PublicationOperationNotFound,
)
from wxpost_controller.publication_runner import (  # noqa: E402
    PublicationBackendError,
    PublicationService,
)
from wxpost_controller.publication_store import PublicationStore  # noqa: E402

WORKSPACE_ID = "wxpost-publish-test"
OPERATION_ID = "publish-0123456789abcdef0123456789abcdef"
OTHER_OPERATION_ID = "publish-fedcba9876543210fedcba9876543210"


def _plan(**overrides: Any) -> dict[str, Any]:
    plan = {
        "wxpostId": "11111111-1111-1111-1111-111111111111",
        "draftVersion": 3,
        "manifestVersion": 7,
        "bundleSha256": "a" * 64,
        "items": [
            {
                "sourceId": "M01",
                "kind": "image",
                "filename": "cover.jpg",
                "mimeType": "image/jpeg",
                "sizeBytes": 1024,
                "contentSha256": "b" * 64,
                "meetingFileKey": "meetings/1/cover.jpg",
                "needsWechatVariant": True,
            },
            {
                "sourceId": "M02",
                "kind": "image",
                "filename": "speaker.jpg",
                "mimeType": "image/jpeg",
                "sizeBytes": 2048,
                "contentSha256": "c" * 64,
                "meetingFileKey": "meetings/1/speaker.jpg",
                "needsWechatVariant": False,
            },
        ],
    }
    plan.update(overrides)
    return plan


def _service(
    tmp_path: Path,
    backend_call,
    *,
    sleep=lambda seconds: None,
) -> tuple[PublicationService, PublicationStore]:
    store = PublicationStore(tmp_path)
    return (
        PublicationService(
            store,
            api_base_url="https://example.invalid",
            service_token="test-token",
            backend_call=backend_call,
            sleep=sleep,
        ),
        store,
    )


def test_happy_path_ensures_each_item_in_order_then_finalizes(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []
    finalize_response = {
        "state": "up-to-date",
        "publicRevision": 1,
        "sourceDraftVersion": 3,
        "publicUrl": "https://mp.weixin.qq.com/s/abc",
    }

    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        calls.append((method, path, body))
        if path.endswith("/finalize"):
            return finalize_response
        return {
            "sourceId": body["item"]["sourceId"],
            "publicUrl": f"https://cdn.example/{body['item']['sourceId']}",
            "variantReady": True,
        }

    service, store = _service(tmp_path, backend_call)
    plan = _plan()
    submitted = service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=plan,
        _defer_thread=True,
    )
    assert submitted == {
        "workspaceId": WORKSPACE_ID,
        "operationId": OPERATION_ID,
        "state": "running",
    }

    service._run(WORKSPACE_ID, OPERATION_ID)

    # Two ensure calls in manifest order, then finalize.
    assert len(calls) == 3
    assert (
        calls[0][1]
        == f"/posts/wxposts/workspaces/{WORKSPACE_ID}/publication/assets/ensure"
    )
    assert calls[0][2]["item"]["sourceId"] == "M01"
    assert calls[1][2]["item"]["sourceId"] == "M02"
    assert (
        calls[2][1] == f"/posts/wxposts/workspaces/{WORKSPACE_ID}/publication/finalize"
    )
    assert calls[2][2] == {
        "wxpostId": plan["wxpostId"],
        "expectedManifestVersion": plan["manifestVersion"],
        "expectedDraftVersion": plan["draftVersion"],
        "bundleSha256": plan["bundleSha256"],
    }

    operation = service.operation(WORKSPACE_ID, OPERATION_ID)
    assert operation["state"] == "completed"
    assert operation["result"] == finalize_response
    assert operation["error"] is None
    assert [step["activityId"] for step in operation["steps"]] == [
        "asset-M01",
        "asset-M02",
        "finalize",
    ]
    assert all(step["completed"] and not step["failed"] for step in operation["steps"])
    assert store.running_operation(WORKSPACE_ID) is None


def test_ensure_backend_error_fails_operation_with_backend_code(
    tmp_path: Path,
) -> None:
    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if body["item"]["sourceId"] == "M01":
            raise PublicationBackendError(
                "invalid_wechat_image",
                "cover.jpg cannot be converted for WeChat",
            )
        raise AssertionError("should not reach the second item or finalize")

    service, _store = _service(tmp_path, backend_call)
    service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=_plan(),
        _defer_thread=True,
    )

    service._run(WORKSPACE_ID, OPERATION_ID)

    operation = service.operation(WORKSPACE_ID, OPERATION_ID)
    assert operation["state"] == "failed"
    assert operation["error"] == {
        "code": "invalid_wechat_image",
        "message": "cover.jpg cannot be converted for WeChat",
    }
    steps = {step["activityId"]: step for step in operation["steps"]}
    assert steps["asset-M01"]["failed"] is True
    assert steps["asset-M01"]["completed"] is False
    assert steps["asset-M02"]["completed"] is False
    assert steps["asset-M02"]["failed"] is False


def test_network_failure_retries_once_then_fails_backend_unreachable(
    tmp_path: Path,
) -> None:
    attempts: list[str] = []
    sleeps: list[float] = []

    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        attempts.append(body["item"]["sourceId"])
        raise URLError("connection refused")

    service, _store = _service(
        tmp_path,
        backend_call,
        sleep=lambda seconds: sleeps.append(seconds),
    )
    service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=_plan(),
        _defer_thread=True,
    )

    service._run(WORKSPACE_ID, OPERATION_ID)

    # One retry: two attempts against the first item, then give up.
    assert attempts == ["M01", "M01"]
    assert sleeps == [2]
    operation = service.operation(WORKSPACE_ID, OPERATION_ID)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "backend_unreachable"
    steps = {step["activityId"]: step for step in operation["steps"]}
    assert steps["asset-M01"]["failed"] is True


def test_duplicate_submit_raises_draft_operation_in_progress(tmp_path: Path) -> None:
    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("backend_call should not run for a deferred submit")

    service, _store = _service(tmp_path, backend_call)
    service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=_plan(),
        _defer_thread=True,
    )

    with pytest.raises(DraftOperationInProgress):
        service.submit(
            WORKSPACE_ID,
            operation_id=OTHER_OPERATION_ID,
            plan=_plan(),
            _defer_thread=True,
        )


def test_submit_rejects_an_invalid_operation_id(tmp_path: Path) -> None:
    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("backend_call should not run for a rejected submit")

    service, _store = _service(tmp_path, backend_call)

    with pytest.raises(InvalidRequest):
        service.submit(
            WORKSPACE_ID,
            operation_id="not-a-valid-operation-id",
            plan=_plan(),
            _defer_thread=True,
        )


def test_operation_lookup_raises_publication_operation_not_found(
    tmp_path: Path,
) -> None:
    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("backend_call should not run for a lookup")

    service, _store = _service(tmp_path, backend_call)

    with pytest.raises(PublicationOperationNotFound):
        service.operation(WORKSPACE_ID, OPERATION_ID)


def test_current_reports_running_operation_and_none_when_idle(
    tmp_path: Path,
) -> None:
    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("backend_call should not run for a deferred submit")

    service, _store = _service(tmp_path, backend_call)
    assert service.current(WORKSPACE_ID) == {"running": None}

    service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=_plan(),
        _defer_thread=True,
    )
    running = service.current(WORKSPACE_ID)["running"]
    assert running["operationId"] == OPERATION_ID


def test_unexpected_exception_is_caught_as_publication_runner_error(
    tmp_path: Path,
) -> None:
    def backend_call(method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    service, _store = _service(tmp_path, backend_call)
    service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=_plan(),
        _defer_thread=True,
    )

    service._run(WORKSPACE_ID, OPERATION_ID)

    operation = service.operation(WORKSPACE_ID, OPERATION_ID)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "publication_runner_error"


# --- Default backend transport (_call_backend / _parse_backend_error) ---
#
# Every test above injects a fake backend_call, so the urllib-based default
# transport used in production is otherwise never exercised. These stub
# urllib.request.urlopen directly.


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _http_error(status: int, body: bytes) -> HTTPError:
    return HTTPError(
        url="https://api.example/publication/assets/ensure",
        code=status,
        msg="error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


def _default_service(tmp_path: Path) -> PublicationService:
    store = PublicationStore(tmp_path)
    return PublicationService(
        store,
        api_base_url="https://api.example",
        service_token="secret-token",
    )


def test_default_backend_call_sends_the_expected_request_and_parses_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["user_agent"] = request.get_header("User-agent")
        captured["content_type"] = request.get_header("Content-type")
        return _FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(publication_runner, "urlopen", fake_urlopen)

    service = _default_service(tmp_path)
    result = service._call_backend("POST", "/path", {"a": 1})

    assert result == {"ok": True}
    assert captured["url"] == "https://api.example/path"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 90
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["user_agent"] == SOARHIGH_SERVICE_USER_AGENT
    assert captured["content_type"] == "application/json"


def test_default_backend_call_returns_parsed_json_on_200(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        return _FakeResponse(json.dumps({"sourceId": "M01"}).encode())

    monkeypatch.setattr(publication_runner, "urlopen", fake_urlopen)

    service = _default_service(tmp_path)
    assert service._call_backend("POST", "/path", {}) == {"sourceId": "M01"}


def test_default_backend_call_raises_typed_error_from_error_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps(
        {"error": {"code": "invalid_wechat_image", "message": "bad image"}}
    ).encode()

    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        raise _http_error(422, body)

    monkeypatch.setattr(publication_runner, "urlopen", fake_urlopen)

    service = _default_service(tmp_path)
    with pytest.raises(PublicationBackendError) as caught:
        service._call_backend("POST", "/path", {})
    assert caught.value.code == "invalid_wechat_image"
    assert caught.value.message == "bad image"


def test_default_backend_call_falls_back_to_backend_error_on_unparseable_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        raise _http_error(500, b"not json")

    monkeypatch.setattr(publication_runner, "urlopen", fake_urlopen)

    service = _default_service(tmp_path)
    with pytest.raises(PublicationBackendError) as caught:
        service._call_backend("POST", "/path", {})
    assert caught.value.code == "backend_error"


def test_default_backend_call_raises_typed_error_on_200_with_non_json_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        return _FakeResponse(b"not json")

    monkeypatch.setattr(publication_runner, "urlopen", fake_urlopen)

    service = _default_service(tmp_path)
    with pytest.raises(PublicationBackendError) as caught:
        service._call_backend("POST", "/path", {})
    assert caught.value.code == "backend_error"


def test_default_transport_200_non_json_body_fails_the_current_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: a malformed 200 during an ensure call must fail that step
    and the operation, exactly like a typed backend error response — not
    escape as an unhandled exception."""

    def fake_urlopen(request, timeout=None):  # noqa: ANN001
        return _FakeResponse(b"not json")

    monkeypatch.setattr(publication_runner, "urlopen", fake_urlopen)

    store = PublicationStore(tmp_path)
    service = PublicationService(
        store,
        api_base_url="https://api.example",
        service_token="secret-token",
    )
    service.submit(
        WORKSPACE_ID,
        operation_id=OPERATION_ID,
        plan=_plan(),
        _defer_thread=True,
    )

    service._run(WORKSPACE_ID, OPERATION_ID)

    operation = service.operation(WORKSPACE_ID, OPERATION_ID)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "backend_error"
    steps = {step["activityId"]: step for step in operation["steps"]}
    assert steps["asset-M01"]["failed"] is True
    assert steps["asset-M01"]["completed"] is False
