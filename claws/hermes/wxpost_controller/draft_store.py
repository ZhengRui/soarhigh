from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .errors import (
    DraftOperationInProgress,
    DraftStoreUnavailable,
    HermesTurnFailed,
)
from .sqlite_support import serialize_controller_database_initialization


class HermesDraftStore:
    """Durable Controller state for Draft Assistant operations and cleanup."""

    _SCHEMA_VERSION = 4

    def __init__(self, workspace_root: Path) -> None:
        self._directory = workspace_root / ".wxpost-controller"
        self._path = self._directory / "controller.sqlite3"
        self._initialize()

    def start_operation(
        self,
        workspace_id: str,
        operation_id: str,
        *,
        request_fingerprint: str,
        member_message: str,
        selected_text: str | None,
        expected_manifest_version: int,
        expected_draft_version: int,
    ) -> None:
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                existing = connection.execute(
                    """
                    SELECT workspace_id, request_fingerprint, selected_text,
                           expected_manifest_version, expected_draft_version
                    FROM draft_operations
                    WHERE operation_id = ?
                    """,
                    (operation_id,),
                ).fetchone()
                identity = (
                    workspace_id,
                    request_fingerprint,
                    selected_text,
                    expected_manifest_version,
                    expected_draft_version,
                )
                if existing is not None:
                    if tuple(existing) != identity:
                        raise HermesTurnFailed(
                            "Draft operation identifier was reused for a different request"
                        )
                    raise HermesTurnFailed("Draft operation has already been submitted")
                # One in-flight turn per workspace. The check runs inside the
                # BEGIN IMMEDIATE transaction, so two concurrent submits
                # cannot both pass it.
                running = connection.execute(
                    """
                    SELECT operation_id FROM draft_operations
                    WHERE workspace_id = ? AND state = 'running'
                    LIMIT 1
                    """,
                    (workspace_id,),
                ).fetchone()
                if running is not None:
                    raise DraftOperationInProgress(
                        "another Draft Assistant operation is already running "
                        "for this workspace"
                    )
                connection.execute(
                    """
                    INSERT INTO draft_operations(
                        operation_id, workspace_id, request_fingerprint,
                        member_message, selected_text, expected_manifest_version,
                        expected_draft_version, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running')
                    """,
                    (
                        operation_id,
                        workspace_id,
                        request_fingerprint,
                        member_message,
                        selected_text,
                        expected_manifest_version,
                        expected_draft_version,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def complete_operation(
        self,
        operation_id: str,
        *,
        result: dict[str, Any],
    ) -> None:
        if not self._valid_operation_result(result):
            raise HermesTurnFailed("Draft operation result is invalid")
        self._finish_operation(
            operation_id,
            state="completed",
            payload_column="result_json",
            payload=result,
        )

    def fail_operation(
        self,
        operation_id: str,
        *,
        error: dict[str, Any],
    ) -> None:
        if not self._valid_operation_error(error):
            raise HermesTurnFailed("Draft operation error is invalid")
        self._finish_operation(
            operation_id,
            state="failed",
            payload_column="error_json",
            payload=error,
        )

    def get_operation(
        self,
        workspace_id: str,
        operation_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state, result_json, error_json, steps_json
                FROM draft_operations
                WHERE workspace_id = ? AND operation_id = ?
                """,
                (workspace_id, operation_id),
            ).fetchone()
        if row is None:
            return None
        result = json.loads(str(row[1])) if row[1] is not None else None
        error = json.loads(str(row[2])) if row[2] is not None else None
        return {
            "workspaceId": workspace_id,
            "operationId": operation_id,
            "state": str(row[0]),
            "result": result,
            "error": error,
            # Live progress for polling clients: accumulated while the
            # operation is still running, before any result exists.
            "steps": json.loads(str(row[3])) if row[3] is not None else [],
        }

    def set_steps(self, operation_id: str, steps: list[dict[str, Any]]) -> None:
        """Persist the running operation's progress steps for polling."""

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE draft_operations
                SET steps_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE operation_id = ? AND state = 'running'
                """,
                (json.dumps(steps, ensure_ascii=False), operation_id),
            )

    def running_operation(self, workspace_id: str) -> dict[str, Any] | None:
        """Return the workspace's in-flight operation for reconnecting clients."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT operation_id, member_message, selected_text, steps_json
                FROM draft_operations
                WHERE workspace_id = ? AND state = 'running'
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "operationId": str(row[0]),
            "memberMessage": str(row[1]),
            "selectedText": str(row[2]) if row[2] is not None else None,
            "steps": json.loads(str(row[3])) if row[3] is not None else [],
        }

    def completed_turns(self, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT operation_id, member_message, selected_text,
                       expected_draft_version, result_json
                FROM draft_operations
                WHERE workspace_id = ? AND state = 'completed'
                ORDER BY created_at, rowid
                """,
                (workspace_id,),
            ).fetchall()
        return [self._completed_turn(row) for row in rows]

    def history(self, workspace_id: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for turn in self.completed_turns(workspace_id):
            member: dict[str, Any] = {
                "role": "user",
                "text": turn["memberMessage"],
            }
            if turn["selectedText"] is not None:
                member["selectedText"] = turn["selectedText"]
            messages.append(member)
            assistant: dict[str, Any] = {
                "role": "assistant",
                "text": turn["assistantReply"],
                "turnId": turn["operationId"],
            }
            steps = turn["steps"]
            if steps:
                assistant["steps"] = steps
            messages.append(assistant)
        return messages

    def reset_history(self, workspace_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM draft_operations WHERE workspace_id = ?",
                (workspace_id,),
            )

    def remove_workspace(self, workspace_id: str) -> None:
        self.reset_history(workspace_id)

    def fail_interrupted_operations(self) -> None:
        error = json.dumps(
            {
                "code": "controller_restarted",
                "message": "The Draft Assistant operation was interrupted by a restart.",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE draft_operations
                SET state = 'failed', error_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE state = 'running'
                """,
                (error,),
            )

    def session_binding(self, workspace_id: str) -> str | None:
        """Return the workspace's persistent Hermes session id, if bound."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_id FROM draft_sessions WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def bind_session(self, workspace_id: str, session_id: str) -> None:
        if not session_id:
            raise HermesTurnFailed("Hermes session identifier must not be empty")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO draft_sessions(workspace_id, session_id)
                VALUES (?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (workspace_id, session_id),
            )

    def unbind_session(self, workspace_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM draft_sessions WHERE workspace_id = ?",
                (workspace_id,),
            )

    def pending_deletions(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT session_locator FROM pending_session_deletions "
                "ORDER BY session_locator"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def schedule_cleanup(self, session_id: str) -> None:
        if not session_id:
            raise HermesTurnFailed("Hermes session identifier must not be empty")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO pending_session_deletions(session_locator)
                VALUES (?)
                """,
                (session_id,),
            )

    def mark_deleted(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM pending_session_deletions WHERE session_locator = ?",
                (session_id,),
            )

    def integrity_check(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row is not None else ""

    def _finish_operation(
        self,
        operation_id: str,
        *,
        state: str,
        payload_column: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE draft_operations
                SET state = ?, {payload_column} = ?, updated_at = CURRENT_TIMESTAMP
                WHERE operation_id = ? AND state = 'running'
                """,
                (
                    state,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    operation_id,
                ),
            )
            if cursor.rowcount != 1:
                raise HermesTurnFailed("Draft operation is not running")

    def _initialize(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        if self._directory.is_symlink():
            raise HermesTurnFailed("Draft store directory is unsafe")
        if self._path.is_symlink():
            raise HermesTurnFailed("Draft store must not be a symlink")
        with serialize_controller_database_initialization(self._directory):
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS pending_session_deletions (
                        session_locator TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS draft_sessions (
                        workspace_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()
                stored_version = int(row[0]) if row is not None else None
                self._begin_immediate(connection)
                if stored_version == 1:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO pending_session_deletions(session_locator)
                        SELECT session_locator FROM workspace_sessions
                        """
                    )
                    connection.execute("DROP TABLE IF EXISTS workspace_sessions")
                    connection.execute("DROP TABLE IF EXISTS turn_progress")
                    connection.execute("DROP TABLE IF EXISTS legacy_turn_progress")
                    connection.execute("DROP TABLE IF EXISTS draft_operations")
                elif stored_version == 2:
                    connection.execute(
                        "ALTER TABLE draft_operations ADD COLUMN selected_text TEXT"
                    )
                    connection.execute(
                        "ALTER TABLE draft_operations ADD COLUMN steps_json TEXT"
                    )
                elif stored_version == 3:
                    connection.execute(
                        "ALTER TABLE draft_operations ADD COLUMN steps_json TEXT"
                    )
                elif stored_version not in {None, self._SCHEMA_VERSION}:
                    raise HermesTurnFailed("Draft store schema is incompatible")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS draft_operations (
                        operation_id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        member_message TEXT NOT NULL,
                        selected_text TEXT,
                        expected_manifest_version INTEGER NOT NULL,
                        expected_draft_version INTEGER NOT NULL,
                        state TEXT NOT NULL
                            CHECK(state IN ('running', 'completed', 'failed')),
                        result_json TEXT,
                        error_json TEXT,
                        steps_json TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS draft_operations_workspace
                    ON draft_operations(workspace_id, created_at)
                    """
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(self._SCHEMA_VERSION),),
                )
                connection.execute(
                    "DELETE FROM metadata WHERE key IN "
                    "('draft_protocol_version', 'legacy_json_imported')"
                )

    @staticmethod
    def _completed_turn(row: tuple[Any, ...]) -> dict[str, Any]:
        (
            operation_id,
            member_message,
            selected_text,
            expected_draft_version,
            result_json,
        ) = row
        result = json.loads(str(result_json))
        return {
            "operationId": str(operation_id),
            "memberMessage": str(member_message),
            "selectedText": str(selected_text) if selected_text is not None else None,
            "assistantReply": str(result["reply"]),
            "expectedDraftVersion": int(expected_draft_version),
            "draftChanged": bool(result["draftChanged"]),
            "draftVersionAfter": int(result["draftVersion"]),
            "steps": result.get("steps", []),
        }

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._path, timeout=5)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.rollback()
            raise DraftStoreUnavailable(
                "Draft Controller state is unavailable"
            ) from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _begin_immediate(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    @classmethod
    def _valid_operation_result(cls, result: object) -> bool:
        if not isinstance(result, dict) or set(result) != {
            "reply",
            "draftChanged",
            "draftVersion",
            "steps",
        }:
            return False
        return (
            isinstance(result["reply"], str)
            and isinstance(result["draftChanged"], bool)
            and type(result["draftVersion"]) is int
            and result["draftVersion"] >= 0
            and isinstance(result["steps"], list)
            and all(cls._valid_progress_step(step) for step in result["steps"])
        )

    @staticmethod
    def _valid_operation_error(error: object) -> bool:
        if not isinstance(error, dict):
            return False
        if not isinstance(error.get("code"), str):
            return False
        if not isinstance(error.get("message"), str):
            return False
        if not set(error).issubset(
            {
                "code",
                "message",
                "versionKind",
                "expectedVersion",
                "actualVersion",
            }
        ):
            return False
        return (
            "versionKind" not in error or isinstance(error["versionKind"], str)
        ) and all(
            type(error[name]) is int
            for name in ("expectedVersion", "actualVersion")
            if name in error
        )

    @staticmethod
    def _valid_progress_step(step: object) -> bool:
        if not isinstance(step, dict):
            return False
        if not isinstance(step.get("activityId"), str):
            return False
        if not isinstance(step.get("label"), str):
            return False
        if not isinstance(step.get("completed"), bool):
            return False
        if not isinstance(step.get("failed"), bool):
            return False
        tool_name = step.get("toolName")
        if tool_name is not None and not isinstance(tool_name, str):
            return False
        operation_names = step.get("operationNames")
        return operation_names is None or (
            isinstance(operation_names, list)
            and all(isinstance(name, str) for name in operation_names)
        )
