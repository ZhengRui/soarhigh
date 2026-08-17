from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_ROOT = REPO_ROOT / "claws" / "hermes"
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

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
) -> PublicationService:
    store = PublicationStore(tmp_path)
    return PublicationService(
        store,
        api_base_url="https://example.invalid",
        service_token="test-token",
        backend_call=backend_call,
        sleep=sleep,
    ), store


def test_happy_path_ensures_each_item_in_order_then_finalizes(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []
    finalize_response = {
        "state": "published",
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
