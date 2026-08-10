from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from wxpost_controller.draft_store import HermesDraftStore
from wxpost_controller.errors import HermesTurnFailed


def _start(
    store: HermesDraftStore,
    operation_id: str,
    *,
    workspace_id: str = "wxpost-test",
    message: str = "Tighten the opening.",
    selected_text: str | None = None,
) -> None:
    store.start_operation(
        workspace_id,
        operation_id,
        request_fingerprint=f"hash-{operation_id}",
        member_message=message,
        selected_text=selected_text,
        expected_manifest_version=4,
        expected_draft_version=2,
    )


def _result(reply: str = "Saved.") -> dict:
    return {
        "reply": reply,
        "draftChanged": True,
        "draftVersion": 3,
        "steps": [
            {
                "activityId": "edit-1",
                "label": "Updating the Draft title",
                "toolName": "wxpost_edit_draft",
                "operationNames": ["replaceMetadata"],
                "completed": True,
                "failed": False,
            }
        ],
    }


def test_operation_lifecycle_is_durable_and_drives_conversation_history(
    tmp_path: Path,
) -> None:
    store = HermesDraftStore(tmp_path)
    operation_id = "draft-0123456789abcdef0123456789abcdef"
    _start(store, operation_id, selected_text="The original opening.")

    assert HermesDraftStore(tmp_path).get_operation("wxpost-test", operation_id) == {
        "workspaceId": "wxpost-test",
        "operationId": operation_id,
        "state": "running",
        "result": None,
        "error": None,
    }
    assert store.history("wxpost-test") == []

    store.complete_operation(operation_id, result=_result())

    assert store.get_operation("wxpost-test", operation_id)["result"] == _result()
    assert store.history("wxpost-test") == [
        {
            "role": "user",
            "text": "Tighten the opening.",
            "selectedText": "The original opening.",
        },
        {
            "role": "assistant",
            "text": "Saved.",
            "turnId": operation_id,
            "steps": _result()["steps"],
        },
    ]
    assert store.completed_turns("wxpost-test") == [
        {
            "operationId": operation_id,
            "memberMessage": "Tighten the opening.",
            "selectedText": "The original opening.",
            "assistantReply": "Saved.",
            "expectedDraftVersion": 2,
            "draftChanged": True,
            "draftVersionAfter": 3,
            "steps": _result()["steps"],
        }
    ]


def test_operation_identifier_cannot_be_reused(tmp_path: Path) -> None:
    store = HermesDraftStore(tmp_path)
    operation_id = "draft-0123456789abcdef0123456789abcdef"
    _start(store, operation_id)

    with pytest.raises(HermesTurnFailed, match="already been submitted"):
        _start(store, operation_id)
    with pytest.raises(HermesTurnFailed, match="different request"):
        store.start_operation(
            "wxpost-test",
            operation_id,
            request_fingerprint="different",
            member_message="Different request",
            selected_text=None,
            expected_manifest_version=4,
            expected_draft_version=2,
        )


def test_failed_and_running_operations_are_not_chat_messages(tmp_path: Path) -> None:
    store = HermesDraftStore(tmp_path)
    failed_id = "draft-fedcba9876543210fedcba9876543210"
    running_id = "draft-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    _start(store, failed_id)
    _start(store, running_id)
    store.fail_operation(
        failed_id,
        error={"code": "hermes_unavailable", "message": "Hermes is offline"},
    )

    assert store.history("wxpost-test") == []
    assert store.completed_turns("wxpost-test") == []
    assert store.get_operation("wxpost-test", failed_id)["error"] == {
        "code": "hermes_unavailable",
        "message": "Hermes is offline",
    }


def test_reset_and_workspace_delete_remove_only_their_conversation(
    tmp_path: Path,
) -> None:
    store = HermesDraftStore(tmp_path)
    first = "draft-11111111111111111111111111111111"
    second = "draft-22222222222222222222222222222222"
    _start(store, first)
    _start(store, second, workspace_id="wxpost-other")
    store.complete_operation(first, result=_result("First"))
    store.complete_operation(second, result=_result("Second"))

    store.reset_history("wxpost-test")

    assert store.history("wxpost-test") == []
    assert store.history("wxpost-other")[1]["text"] == "Second"
    store.remove_workspace("wxpost-other")
    assert store.history("wxpost-other") == []


def test_service_startup_marks_interrupted_operations_failed(tmp_path: Path) -> None:
    store = HermesDraftStore(tmp_path)
    operation_id = "draft-33333333333333333333333333333333"
    _start(store, operation_id)

    store.fail_interrupted_operations()

    operation = store.get_operation("wxpost-test", operation_id)
    assert operation["state"] == "failed"
    assert operation["error"]["code"] == "controller_restarted"


def test_schema_v1_upgrade_retires_persistent_sessions_and_discards_history(
    tmp_path: Path,
) -> None:
    directory = tmp_path / ".wxpost-controller"
    directory.mkdir()
    database = directory / "controller.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata VALUES ('schema_version', '1');
            CREATE TABLE workspace_sessions (
                workspace_id TEXT PRIMARY KEY,
                session_locator TEXT NOT NULL
            );
            INSERT INTO workspace_sessions VALUES ('wxpost-test', 'old-session');
            CREATE TABLE turn_progress (session_id TEXT, turn_id TEXT, steps_json TEXT);
            CREATE TABLE legacy_turn_progress (
                id INTEGER PRIMARY KEY, session_id TEXT,
                turn_sequence INTEGER, assistant_text TEXT, steps_json TEXT
            );
            CREATE TABLE draft_operations (operation_id TEXT PRIMARY KEY);
            """
        )

    store = HermesDraftStore(tmp_path)

    assert store.pending_deletions() == ["old-session"]
    assert store.history("wxpost-test") == []
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "workspace_sessions" not in tables
        assert "turn_progress" not in tables
        assert "legacy_turn_progress" not in tables
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone() == ("3",)


def test_schema_v2_upgrade_adds_selected_text_without_losing_operations(
    tmp_path: Path,
) -> None:
    directory = tmp_path / ".wxpost-controller"
    directory.mkdir()
    database = directory / "controller.sqlite3"
    operation_id = "draft-44444444444444444444444444444444"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            f"""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata VALUES ('schema_version', '2');
            CREATE TABLE pending_session_deletions (
                session_locator TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE draft_operations (
                operation_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                member_message TEXT NOT NULL,
                expected_manifest_version INTEGER NOT NULL,
                expected_draft_version INTEGER NOT NULL,
                state TEXT NOT NULL,
                result_json TEXT,
                error_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO draft_operations(
                operation_id, workspace_id, request_fingerprint,
                member_message, expected_manifest_version,
                expected_draft_version, state, result_json
            ) VALUES (
                '{operation_id}', 'wxpost-test', 'old-hash',
                'Remember this.', 4, 2, 'completed',
                '{{"reply":"Remembered.","draftChanged":false,"draftVersion":2,"steps":[]}}'
            );
            """
        )

    store = HermesDraftStore(tmp_path)

    assert store.history("wxpost-test") == [
        {"role": "user", "text": "Remember this."},
        {"role": "assistant", "text": "Remembered.", "turnId": operation_id},
    ]
    with sqlite3.connect(database) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(draft_operations)")
        }
        assert "selected_text" in columns
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone() == ("3",)


def test_initialization_does_not_delete_unsupported_legacy_json(tmp_path: Path) -> None:
    directory = tmp_path / ".wxpost-controller"
    directory.mkdir()
    legacy_path = directory / "draft-sessions.json"
    legacy_path.write_text(
        '{"version":1,"sessions":{"wxpost-test":"old-session"}}',
        encoding="utf-8",
    )

    store = HermesDraftStore(tmp_path)

    assert legacy_path.exists()
    assert store.pending_deletions() == []


def test_store_serializes_concurrent_operation_writers(tmp_path: Path) -> None:
    def write(index: int) -> None:
        store = HermesDraftStore(tmp_path)
        operation_id = f"draft-{index:032x}"
        _start(store, operation_id, workspace_id=f"wxpost-{index}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(24)))

    store = HermesDraftStore(tmp_path)
    assert store.integrity_check() == "ok"
    assert all(
        store.get_operation(f"wxpost-{index}", f"draft-{index:032x}") is not None
        for index in range(24)
    )


def test_session_cleanup_queue_is_idempotent(tmp_path: Path) -> None:
    store = HermesDraftStore(tmp_path)

    store.schedule_cleanup("ephemeral-session")
    store.schedule_cleanup("ephemeral-session")

    assert store.pending_deletions() == ["ephemeral-session"]
    store.mark_deleted("ephemeral-session")
    assert store.pending_deletions() == []
