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


class PublicationStore:
    """Durable Controller state for async WxPost publication operations.

    Deliberately backed by its own SQLite file (``publication.sqlite3``,
    separate from the Draft Assistant's ``controller.sqlite3``) so this
    store's schema can evolve independently of ``HermesDraftStore``.
    """

    _SCHEMA_VERSION = 1

    def __init__(self, workspace_root: Path) -> None:
        self._directory = workspace_root / ".wxpost-controller"
        self._path = self._directory / "publication.sqlite3"
        self._initialize()

    def start_operation(
        self,
        workspace_id: str,
        operation_id: str,
        *,
        request_fingerprint: str,
        plan_json: str,
    ) -> None:
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                existing = connection.execute(
                    """
                    SELECT workspace_id, request_fingerprint
                    FROM publication_operations
                    WHERE operation_id = ?
                    """,
                    (operation_id,),
                ).fetchone()
                identity = (workspace_id, request_fingerprint)
                if existing is not None:
                    if tuple(existing) != identity:
                        raise HermesTurnFailed(
                            "Publication operation identifier was reused "
                            "for a different request"
                        )
                    raise HermesTurnFailed(
                        "Publication operation has already been submitted"
                    )
                # One in-flight publication per workspace. The check runs
                # inside the BEGIN IMMEDIATE transaction, so two concurrent
                # submits cannot both pass it.
                running = connection.execute(
                    """
                    SELECT operation_id FROM publication_operations
                    WHERE workspace_id = ? AND state = 'running'
                    LIMIT 1
                    """,
                    (workspace_id,),
                ).fetchone()
                if running is not None:
                    raise DraftOperationInProgress(
                        "another publication operation is already running "
                        "for this workspace"
                    )
                connection.execute(
                    """
                    INSERT INTO publication_operations(
                        operation_id, workspace_id, request_fingerprint,
                        plan_json, state
                    ) VALUES (?, ?, ?, ?, 'running')
                    """,
                    (operation_id, workspace_id, request_fingerprint, plan_json),
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
            raise HermesTurnFailed("Publication operation result is invalid")
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
            raise HermesTurnFailed("Publication operation error is invalid")
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
                FROM publication_operations
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

        if not isinstance(steps, list) or not all(
            self._valid_progress_step(step) for step in steps
        ):
            raise HermesTurnFailed("Publication operation steps are invalid")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE publication_operations
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
                SELECT operation_id, steps_json
                FROM publication_operations
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
            "steps": json.loads(str(row[1])) if row[1] is not None else [],
        }

    def plan(self, operation_id: str) -> dict[str, Any] | None:
        """Return the runner input plan for an operation, if it exists."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT plan_json FROM publication_operations
                WHERE operation_id = ?
                """,
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row[0]))

    def fail_interrupted_operations(self) -> None:
        error = json.dumps(
            {
                "code": "controller_restarted",
                "message": (
                    "The publication was interrupted by a restart; "
                    "publish again to resume."
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE publication_operations
                SET state = 'failed', error_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE state = 'running'
                """,
                (error,),
            )

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
                UPDATE publication_operations
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
                raise HermesTurnFailed("Publication operation is not running")

    def _initialize(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        if self._directory.is_symlink():
            raise HermesTurnFailed("Publication store directory is unsafe")
        if self._path.is_symlink():
            raise HermesTurnFailed("Publication store must not be a symlink")
        with serialize_controller_database_initialization(self._directory):
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    """
                )
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()
                stored_version = int(row[0]) if row is not None else None
                self._begin_immediate(connection)
                if stored_version not in {None, self._SCHEMA_VERSION}:
                    raise HermesTurnFailed(
                        "Publication store schema is incompatible"
                    )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS publication_operations (
                        operation_id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        plan_json TEXT NOT NULL,
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
                    CREATE INDEX IF NOT EXISTS publication_operations_workspace
                    ON publication_operations(workspace_id, created_at)
                    """
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(self._SCHEMA_VERSION),),
                )

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
                "Publication Controller state is unavailable"
            ) from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _begin_immediate(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    @classmethod
    def _valid_operation_result(cls, result: object) -> bool:
        if not isinstance(result, dict):
            return False
        return isinstance(result.get("state"), str)

    @staticmethod
    def _valid_operation_error(error: object) -> bool:
        if not isinstance(error, dict):
            return False
        if set(error) != {"code", "message"}:
            return False
        return isinstance(error["code"], str) and isinstance(error["message"], str)

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
