from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from wxpost_controller.errors import DraftOperationInProgress, HermesTurnFailed
from wxpost_controller.publication_store import PublicationStore


def _start(
    store: PublicationStore,
    operation_id: str,
    *,
    workspace_id: str = "wxpost-test",
    fingerprint: str = "hash-1",
    plan_json: str = '{"steps": []}',
) -> None:
    store.start_operation(
        workspace_id,
        operation_id,
        request_fingerprint=fingerprint,
        plan_json=plan_json,
    )


def _result(state: str = "published") -> dict:
    return {"state": state, "url": "https://mp.weixin.qq.com/s/abc"}


def test_start_and_complete_operation_round_trip(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-0123456789abcdef0123456789abcdef"
    _start(store, operation_id, plan_json='{"steps": ["draft", "publish"]}')

    assert PublicationStore(tmp_path).get_operation(
        "wxpost-test", operation_id
    ) == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "running",
        "result": None,
        "error": None,
        "steps": [],
    }

    store.complete_operation(operation_id, result=_result())

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "completed"
    assert operation["result"] == _result()


def test_fail_operation_persists_error(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-fedcba9876543210fedcba9876543210"
    _start(store, operation_id)

    store.fail_operation(
        operation_id,
        error={"code": "backend_error", "message": "The publish call failed"},
    )

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "failed"
    assert operation["error"] == {
        "code": "backend_error",
        "message": "The publish call failed",
    }


def test_fail_operation_rejects_extra_keys(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-11111111111111111111111111111111"
    _start(store, operation_id)

    with pytest.raises(HermesTurnFailed):
        store.fail_operation(
            operation_id,
            error={
                "code": "backend_error",
                "message": "nope",
                "versionKind": "manifest",
            },
        )


def test_fail_operation_rejects_missing_message(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-aabbccddeeff00112233445566778899"
    _start(store, operation_id)

    with pytest.raises(HermesTurnFailed):
        store.fail_operation(operation_id, error={"code": "backend_error"})

    assert store.get_operation("wxpost-test", operation_id)["state"] == "running"


def test_fail_operation_rejects_wrong_typed_code(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-99887766554433221100ffeeddccbbaa"
    _start(store, operation_id)

    with pytest.raises(HermesTurnFailed):
        store.fail_operation(
            operation_id, error={"code": 500, "message": "nope"}
        )

    assert store.get_operation("wxpost-test", operation_id)["state"] == "running"


def test_complete_operation_requires_state_key(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-22222222222222222222222222222222"
    _start(store, operation_id)

    with pytest.raises(HermesTurnFailed):
        store.complete_operation(operation_id, result={"url": "no state key"})

    with pytest.raises(HermesTurnFailed):
        store.complete_operation(operation_id, result={"state": 123})


def test_operation_identifier_cannot_be_reused_for_different_request(
    tmp_path: Path,
) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-33333333333333333333333333333333"
    _start(store, operation_id, fingerprint="hash-a")

    with pytest.raises(HermesTurnFailed, match="different request"):
        store.start_operation(
            "wxpost-test",
            operation_id,
            request_fingerprint="hash-b",
            plan_json='{"steps": []}',
        )


def test_exact_duplicate_resubmit_is_rejected(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-44444444444444444444444444444444"
    _start(store, operation_id, fingerprint="hash-a")

    with pytest.raises(HermesTurnFailed, match="already been submitted"):
        _start(store, operation_id, fingerprint="hash-a")


def test_second_concurrent_running_operation_is_rejected(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    first_id = "pub-55555555555555555555555555555555"
    second_id = "pub-66666666666666666666666666666666"
    _start(store, first_id)

    with pytest.raises(DraftOperationInProgress):
        _start(store, second_id)


def test_completed_operation_frees_workspace_for_new_run(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    first_id = "pub-77777777777777777777777777777777"
    second_id = "pub-88888888888888888888888888888888"
    _start(store, first_id)
    store.complete_operation(first_id, result=_result())

    _start(store, second_id)

    assert store.get_operation("wxpost-test", second_id)["state"] == "running"


def test_get_operation_unknown_returns_none(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)

    assert store.get_operation("wxpost-test", "does-not-exist") is None


def test_set_steps_and_running_operation_round_trip(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-99999999999999999999999999999999"
    _start(store, operation_id)
    steps = [
        {
            "activityId": "publish-1",
            "label": "Publishing to WeChat",
            "toolName": "wxpost_publish",
            "operationNames": ["publish"],
            "completed": True,
            "failed": False,
        }
    ]

    store.set_steps(operation_id, steps)

    assert store.get_operation("wxpost-test", operation_id)["steps"] == steps
    assert store.running_operation("wxpost-test") == {
        "operationId": operation_id,
        "steps": steps,
    }


def test_running_operation_returns_none_when_workspace_is_idle(
    tmp_path: Path,
) -> None:
    store = PublicationStore(tmp_path)

    assert store.running_operation("wxpost-test") is None


def test_set_steps_rejects_step_missing_required_field(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-bcbcbcbcbcbcbcbcbcbcbcbcbcbcbcbc"
    _start(store, operation_id)
    malformed_step = {
        # missing "label"
        "activityId": "publish-1",
        "completed": True,
        "failed": False,
    }

    with pytest.raises(HermesTurnFailed):
        store.set_steps(operation_id, [malformed_step])

    assert store.get_operation("wxpost-test", operation_id)["steps"] == []


def test_set_steps_rejects_wrong_typed_required_field(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd"
    _start(store, operation_id)
    malformed_step = {
        "activityId": "publish-1",
        "label": "Publishing to WeChat",
        "completed": "true",  # must be bool, not str
        "failed": False,
    }

    with pytest.raises(HermesTurnFailed):
        store.set_steps(operation_id, [malformed_step])

    assert store.get_operation("wxpost-test", operation_id)["steps"] == []


def test_set_steps_rejects_wrong_typed_optional_tool_name(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-dededededededededededededededede0"
    _start(store, operation_id)
    malformed_step = {
        "activityId": "publish-1",
        "label": "Publishing to WeChat",
        "completed": False,
        "failed": False,
        "toolName": 123,  # must be str
    }

    with pytest.raises(HermesTurnFailed):
        store.set_steps(operation_id, [malformed_step])

    assert store.get_operation("wxpost-test", operation_id)["steps"] == []


def test_set_steps_rejects_wrong_typed_operation_names_entries(
    tmp_path: Path,
) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-efefefefefefefefefefefefefefefef"
    _start(store, operation_id)
    malformed_step = {
        "activityId": "publish-1",
        "label": "Publishing to WeChat",
        "completed": False,
        "failed": False,
        "operationNames": ["a", 5],  # every entry must be str
    }

    with pytest.raises(HermesTurnFailed):
        store.set_steps(operation_id, [malformed_step])

    assert store.get_operation("wxpost-test", operation_id)["steps"] == []


def test_plan_round_trip(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    _start(store, operation_id, plan_json='{"steps": ["draft", "publish"]}')

    assert store.plan(operation_id) == {"steps": ["draft", "publish"]}


def test_plan_returns_none_for_unknown_operation(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)

    assert store.plan("does-not-exist") is None


def test_service_startup_marks_interrupted_operations_failed(tmp_path: Path) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    _start(store, operation_id)

    store.fail_interrupted_operations()

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "failed"
    assert operation["error"] == {
        "code": "controller_restarted",
        "message": (
            "The publication was interrupted by a restart; "
            "publish again to resume."
        ),
    }


def test_fail_interrupted_operations_does_not_touch_settled_operations(
    tmp_path: Path,
) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-cccccccccccccccccccccccccccccccc"
    _start(store, operation_id)
    store.complete_operation(operation_id, result=_result())

    store.fail_interrupted_operations()

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "completed"
    assert operation["error"] is None


def test_store_uses_its_own_database_file_separate_from_draft_store(
    tmp_path: Path,
) -> None:
    store = PublicationStore(tmp_path)
    operation_id = "pub-dddddddddddddddddddddddddddddddd"
    _start(store, operation_id)

    database = tmp_path / ".wxpost-controller" / "publication.sqlite3"
    assert database.exists()
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        assert row == ("1",)


def test_store_serializes_concurrent_operation_writers(tmp_path: Path) -> None:
    def write(index: int) -> None:
        store = PublicationStore(tmp_path)
        operation_id = f"pub-{index:032x}"
        _start(store, operation_id, workspace_id=f"wxpost-{index}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(24)))

    store = PublicationStore(tmp_path)
    assert all(
        store.get_operation(f"wxpost-{index}", f"pub-{index:032x}") is not None
        for index in range(24)
    )
