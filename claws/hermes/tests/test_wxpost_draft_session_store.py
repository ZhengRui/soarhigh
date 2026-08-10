from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3

import pytest

from wxpost_controller.draft_session_store import (
    HERMES_DRAFT_PROTOCOL_VERSION,
    HermesDraftSessionStore,
)
from wxpost_controller.errors import HermesTurnFailed


def test_draft_operation_lifecycle_is_durable_and_request_bound(
    tmp_path: Path,
) -> None:
    store = HermesDraftSessionStore(tmp_path)
    operation_id = "draft-0123456789abcdef0123456789abcdef"
    store.start_draft_operation(
        "wxpost-test",
        operation_id,
        request_fingerprint="request-hash",
        expected_manifest_version=4,
        expected_draft_version=2,
    )

    assert HermesDraftSessionStore(tmp_path).get_draft_operation(
        "wxpost-test", operation_id
    ) == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "running",
        "result": None,
        "error": None,
    }

    store.complete_draft_operation(
        operation_id,
        result={
            "sessionId": "stored-session",
            "reply": "Saved.",
            "draftChanged": True,
            "draftVersion": 3,
        },
    )
    completed = HermesDraftSessionStore(tmp_path).get_draft_operation(
        "wxpost-test", operation_id
    )
    assert completed is not None
    assert completed["state"] == "completed"
    assert completed["result"]["draftVersion"] == 3

    with pytest.raises(HermesTurnFailed, match="already been submitted"):
        store.start_draft_operation(
            "wxpost-test",
            operation_id,
            request_fingerprint="request-hash",
            expected_manifest_version=4,
            expected_draft_version=2,
        )
    with pytest.raises(HermesTurnFailed, match="different request"):
        store.start_draft_operation(
            "wxpost-test",
            operation_id,
            request_fingerprint="different-hash",
            expected_manifest_version=4,
            expected_draft_version=2,
        )


def test_failed_draft_operation_records_transport_error(tmp_path: Path) -> None:
    store = HermesDraftSessionStore(tmp_path)
    operation_id = "draft-fedcba9876543210fedcba9876543210"
    store.start_draft_operation(
        "wxpost-test",
        operation_id,
        request_fingerprint="request-hash",
        expected_manifest_version=4,
        expected_draft_version=2,
    )
    store.fail_draft_operation(
        operation_id,
        error={"code": "hermes_unavailable", "message": "Hermes is offline"},
    )

    failed = store.get_draft_operation("wxpost-test", operation_id)
    assert failed is not None
    assert failed["state"] == "failed"
    assert failed["error"] == {
        "code": "hermes_unavailable",
        "message": "Hermes is offline",
    }


def test_draft_session_store_restores_completed_progress_by_turn_id(
    tmp_path: Path,
) -> None:
    store = HermesDraftSessionStore(tmp_path)
    store.set_session("wxpost-test", "stored-session")
    store.append_completed_progress(
        "stored-session",
        turn_id="draft-second",
        steps=[
            {
                "activityId": "edit-1",
                "label": "Updating a Draft section",
                "toolName": "wxpost_edit_draft",
                "operationNames": ["replaceBodyNode"],
                "completed": True,
                "failed": False,
            }
        ],
    )

    restored = HermesDraftSessionStore(tmp_path).restore_completed_progress(
        "stored-session",
        [
            {"role": "user", "text": "Tighten it once."},
            {
                "role": "assistant",
                "text": "Opening tightened.",
                "turnId": "draft-first",
            },
            {"role": "user", "text": "Tighten the opening."},
            {
                "role": "assistant",
                "text": "Opening tightened.",
                "turnId": "draft-second",
            },
        ],
    )

    assert "steps" not in restored[1]
    assert restored[3]["steps"] == [
        {
            "activityId": "edit-1",
            "label": "Updating a Draft section",
            "toolName": "wxpost_edit_draft",
            "operationNames": ["replaceBodyNode"],
            "completed": True,
            "failed": False,
        }
    ]


def test_draft_session_store_migrates_json_once_and_reconciles_legacy_progress(
    tmp_path: Path,
) -> None:
    registry_directory = tmp_path / ".wxpost-controller"
    registry_directory.mkdir()
    legacy_path = registry_directory / "draft-sessions.json"
    legacy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "draftProtocolVersion": HERMES_DRAFT_PROTOCOL_VERSION,
                "sessions": {"wxpost-test": "stored-session"},
                "pendingDeletions": ["stale-session"],
                "completedProgress": {
                    "stored-session": [
                        {
                            "assistantText": "Done.",
                            "steps": [
                                {
                                    "activityId": "first",
                                    "label": "Reading the saved Draft and media",
                                    "toolName": "wxpost_get_context",
                                    "completed": True,
                                    "failed": False,
                                }
                            ],
                        },
                        {
                            "assistantText": "Done.",
                            "steps": [
                                {
                                    "activityId": "second",
                                    "label": "Updating the Draft title",
                                    "toolName": "wxpost_edit_draft",
                                    "completed": True,
                                    "failed": False,
                                }
                            ],
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    store = HermesDraftSessionStore(tmp_path)

    assert not legacy_path.exists()
    assert store.get("wxpost-test") == "stored-session"
    assert store.pending_deletions() == ["stale-session"]
    messages = [
        {"role": "assistant", "text": "Done.", "turnId": "draft-first"},
        {"role": "assistant", "text": "Done.", "turnId": "draft-second"},
    ]
    restored = store.restore_completed_progress("stored-session", messages)
    assert restored[0]["steps"][0]["activityId"] == "first"
    assert restored[1]["steps"][0]["activityId"] == "second"

    reloaded = HermesDraftSessionStore(tmp_path)
    database = registry_directory / "controller.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM turn_progress").fetchone() == (
            2,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM legacy_turn_progress"
        ).fetchone() == (0,)
    assert reloaded.integrity_check() == "ok"


def test_draft_session_store_rejects_invalid_json_without_partial_import(
    tmp_path: Path,
) -> None:
    registry_directory = tmp_path / ".wxpost-controller"
    registry_directory.mkdir()
    legacy_path = registry_directory / "draft-sessions.json"
    legacy_path.write_text(json.dumps({"version": 1, "sessions": []}), encoding="utf-8")

    with pytest.raises(HermesTurnFailed, match="session data is invalid"):
        HermesDraftSessionStore(tmp_path)

    assert legacy_path.exists()
    with sqlite3.connect(registry_directory / "controller.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workspace_sessions"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT COUNT(*) FROM pending_session_deletions"
        ).fetchone() == (0,)


def test_draft_session_store_serializes_concurrent_writers(tmp_path: Path) -> None:
    def write_session(index: int) -> None:
        HermesDraftSessionStore(tmp_path).set_session(
            f"wxpost-{index}", f"session-{index}"
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_session, range(24)))

    store = HermesDraftSessionStore(tmp_path)
    assert store.integrity_check() == "ok"
    assert all(
        store.get(f"wxpost-{index}") == f"session-{index}" for index in range(24)
    )


def test_draft_session_store_serializes_concurrent_legacy_migration(
    tmp_path: Path,
) -> None:
    registry_directory = tmp_path / ".wxpost-controller"
    registry_directory.mkdir()
    (registry_directory / "draft-sessions.json").write_text(
        json.dumps(
            {
                "version": 1,
                "draftProtocolVersion": HERMES_DRAFT_PROTOCOL_VERSION,
                "sessions": {"wxpost-test": "stored-session"},
                "pendingDeletions": [],
            }
        ),
        encoding="utf-8",
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(
            executor.map(lambda _: HermesDraftSessionStore(tmp_path), range(8))
        )

    assert all(store.get("wxpost-test") == "stored-session" for store in stores)
    assert stores[0].integrity_check() == "ok"
    assert not (registry_directory / "draft-sessions.json").exists()


def test_draft_session_store_retires_sessions_after_protocol_change(
    tmp_path: Path,
) -> None:
    store = HermesDraftSessionStore(tmp_path)
    store.set_session("wxpost-test", "stored-session")
    store.append_completed_progress(
        "stored-session",
        turn_id="draft-before-upgrade",
        steps=[
            {
                "activityId": "context-1",
                "label": "Reading the saved Draft and media",
                "completed": True,
                "failed": False,
            }
        ],
    )
    database = tmp_path / ".wxpost-controller" / "controller.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'draft_protocol_version'",
            (str(HERMES_DRAFT_PROTOCOL_VERSION - 1),),
        )

    upgraded = HermesDraftSessionStore(tmp_path)

    assert upgraded.get("wxpost-test") is None
    assert upgraded.pending_deletions() == ["stored-session"]
    restored = upgraded.restore_completed_progress(
        "stored-session",
        [
            {
                "role": "assistant",
                "text": "Old reply.",
                "turnId": "draft-before-upgrade",
            }
        ],
    )
    assert "steps" not in restored[0]


def test_store_schedules_standalone_session_cleanup_idempotently(
    tmp_path: Path,
) -> None:
    store = HermesDraftSessionStore(tmp_path)

    store.schedule_cleanup("feishu-old-session")
    store.schedule_cleanup("feishu-old-session")

    assert store.pending_deletions() == ["feishu-old-session"]
