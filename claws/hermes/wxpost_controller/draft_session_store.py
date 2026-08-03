from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from .errors import DraftSessionStoreUnavailable, HermesTurnFailed

HERMES_DRAFT_PROTOCOL_VERSION = 7


class HermesDraftSessionStore:
    """Transactional Controller state for Hermes Draft sessions and UI progress."""

    _SCHEMA_VERSION = 1

    def __init__(self, workspace_root: Path) -> None:
        self._directory = workspace_root / ".wxpost-controller"
        self._path = self._directory / "controller.sqlite3"
        self._legacy_path = self._directory / "draft-sessions.json"
        self._initialize()

    def get(self, workspace_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT session_locator FROM workspace_sessions WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def set_session(self, workspace_id: str, session_id: str) -> None:
        if not session_id:
            raise HermesTurnFailed("Hermes session identifier must not be empty")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workspace_sessions(workspace_id, session_locator)
                VALUES (?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    session_locator = excluded.session_locator,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (workspace_id, session_id),
            )

    def replace_and_schedule_cleanup(
        self,
        workspace_id: str,
        session_id: str,
        *,
        previous_session_id: str | None = None,
    ) -> None:
        if not session_id:
            raise HermesTurnFailed("Hermes session identifier must not be empty")
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                row = connection.execute(
                    "SELECT session_locator FROM workspace_sessions WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone()
                previous = previous_session_id or (
                    str(row[0]) if row is not None else None
                )
                connection.execute(
                    """
                    INSERT INTO workspace_sessions(workspace_id, session_locator)
                    VALUES (?, ?)
                    ON CONFLICT(workspace_id) DO UPDATE SET
                        session_locator = excluded.session_locator,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (workspace_id, session_id),
                )
                if previous and previous != session_id:
                    self._retire_session(connection, previous)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def remove_and_schedule_cleanup(
        self,
        workspace_id: str,
        *,
        fallback_session_id: str | None = None,
    ) -> None:
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                row = connection.execute(
                    "SELECT session_locator FROM workspace_sessions WHERE workspace_id = ?",
                    (workspace_id,),
                ).fetchone()
                previous = str(row[0]) if row is not None else fallback_session_id
                connection.execute(
                    "DELETE FROM workspace_sessions WHERE workspace_id = ?",
                    (workspace_id,),
                )
                if previous:
                    self._retire_session(connection, previous)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def append_completed_progress(
        self,
        session_id: str,
        *,
        turn_id: str,
        steps: list[dict[str, Any]],
    ) -> None:
        if not session_id or not turn_id or not steps:
            return
        if not all(self._valid_progress_step(step) for step in steps):
            raise HermesTurnFailed("Draft progress metadata is invalid")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO turn_progress(session_id, turn_id, steps_json)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, turn_id) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    created_at = CURRENT_TIMESTAMP
                """,
                (
                    session_id,
                    turn_id,
                    json.dumps(steps, ensure_ascii=False, sort_keys=True),
                ),
            )

    def restore_completed_progress(
        self,
        session_id: str | None,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not session_id:
            return messages
        self._reconcile_legacy_progress(session_id, messages)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT turn_id, steps_json FROM turn_progress WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        steps_by_turn = {str(row[0]): json.loads(str(row[1])) for row in rows}
        for message in messages:
            turn_id = message.get("turnId")
            if message.get("role") == "assistant" and turn_id in steps_by_turn:
                message["steps"] = steps_by_turn[turn_id]
        return messages

    def pending_deletions(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT session_locator FROM pending_session_deletions "
                "ORDER BY session_locator"
            ).fetchall()
        return [str(row[0]) for row in rows]

    def mark_deleted(self, session_id: str) -> None:
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                connection.execute(
                    "DELETE FROM pending_session_deletions WHERE session_locator = ?",
                    (session_id,),
                )
                connection.execute(
                    "DELETE FROM turn_progress WHERE session_id = ?", (session_id,)
                )
                connection.execute(
                    "DELETE FROM legacy_turn_progress WHERE session_id = ?",
                    (session_id,),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def integrity_check(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row is not None else ""

    def _initialize(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        if self._directory.is_symlink():
            raise HermesTurnFailed("Draft session store directory is unsafe")
        if self._path.is_symlink():
            raise HermesTurnFailed("Draft session store must not be a symlink")
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_sessions (
                    workspace_id TEXT PRIMARY KEY,
                    session_locator TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS pending_session_deletions (
                    session_locator TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS turn_progress (
                    session_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(session_id, turn_id)
                );
                CREATE TABLE IF NOT EXISTS legacy_turn_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_sequence INTEGER NOT NULL,
                    assistant_text TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    UNIQUE(session_id, turn_sequence)
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema_version', ?)",
                (str(self._SCHEMA_VERSION),),
            )
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None or str(row[0]) != str(self._SCHEMA_VERSION):
                raise HermesTurnFailed("Draft session store schema is incompatible")
        self._migrate_legacy_json()
        self._retire_incompatible_protocol()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._path, timeout=5)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            if connection.in_transaction:
                connection.commit()
        except HermesTurnFailed:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as error:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise DraftSessionStoreUnavailable(
                "Draft session store is unavailable"
            ) from error
        except Exception:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _begin_immediate(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    def _migrate_legacy_json(self) -> None:
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                migrated = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'legacy_json_imported'"
                ).fetchone()
                if migrated is not None:
                    connection.commit()
                elif not self._legacy_path.exists():
                    connection.execute(
                        "INSERT INTO metadata(key, value) VALUES "
                        "('legacy_json_imported', 'true')"
                    )
                    connection.commit()
                    return
                else:
                    if self._legacy_path.is_symlink():
                        raise HermesTurnFailed(
                            "Legacy Draft session data must not be a symlink"
                        )
                    payload = self._validated_legacy_payload()
                    self._import_legacy_payload(connection, payload)
                    connection.execute(
                        "INSERT INTO metadata(key, value) VALUES "
                        "('legacy_json_imported', 'true')"
                    )
                    connection.commit()
            except Exception:
                connection.rollback()
                raise
        self._remove_legacy_json()

    def _remove_legacy_json(self) -> None:
        try:
            self._legacy_path.unlink(missing_ok=True)
        except OSError:
            return

    def _validated_legacy_payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._legacy_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HermesTurnFailed("Legacy Draft session data is invalid") from error
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise HermesTurnFailed("Legacy Draft session data is invalid")
        sessions = payload.get("sessions")
        pending = payload.get("pendingDeletions", [])
        progress = payload.get("completedProgress", {})
        if not isinstance(sessions, dict) or not all(
            isinstance(workspace_id, str)
            and workspace_id
            and isinstance(session_id, str)
            and session_id
            for workspace_id, session_id in sessions.items()
        ):
            raise HermesTurnFailed("Legacy Draft session data is invalid")
        if not isinstance(pending, list) or not all(
            isinstance(session_id, str) and session_id for session_id in pending
        ):
            raise HermesTurnFailed("Legacy Draft session data is invalid")
        if not isinstance(progress, dict):
            raise HermesTurnFailed("Legacy Draft session data is invalid")
        for session_id, turns in progress.items():
            if (
                not isinstance(session_id, str)
                or not session_id
                or not isinstance(turns, list)
            ):
                raise HermesTurnFailed("Legacy Draft session data is invalid")
            for turn in turns:
                if not isinstance(turn, dict):
                    raise HermesTurnFailed("Legacy Draft session data is invalid")
                assistant_text = turn.get("assistantText")
                steps = turn.get("steps")
                if (
                    not isinstance(assistant_text, str)
                    or not isinstance(steps, list)
                    or not all(self._valid_progress_step(step) for step in steps)
                ):
                    raise HermesTurnFailed("Legacy Draft session data is invalid")
        return payload

    def _import_legacy_payload(
        self,
        connection: sqlite3.Connection,
        payload: dict[str, Any],
    ) -> None:
        sessions = payload["sessions"]
        pending = set(payload.get("pendingDeletions", []))
        compatible = (
            payload.get("draftProtocolVersion", HERMES_DRAFT_PROTOCOL_VERSION)
            == HERMES_DRAFT_PROTOCOL_VERSION
        )
        if compatible:
            connection.executemany(
                "INSERT OR REPLACE INTO workspace_sessions"
                "(workspace_id, session_locator) VALUES (?, ?)",
                sessions.items(),
            )
            for session_id, turns in payload.get("completedProgress", {}).items():
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO legacy_turn_progress(
                        session_id, turn_sequence, assistant_text, steps_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [
                        (
                            session_id,
                            sequence,
                            turn["assistantText"],
                            json.dumps(
                                turn["steps"], ensure_ascii=False, sort_keys=True
                            ),
                        )
                        for sequence, turn in enumerate(turns)
                    ],
                )
        else:
            pending.update(sessions.values())
        connection.executemany(
            "INSERT OR IGNORE INTO pending_session_deletions(session_locator) "
            "VALUES (?)",
            [(session_id,) for session_id in pending],
        )

    def _retire_incompatible_protocol(self) -> None:
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                row = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'draft_protocol_version'"
                ).fetchone()
                stored = int(row[0]) if row is not None else None
                if stored is not None and stored != HERMES_DRAFT_PROTOCOL_VERSION:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO pending_session_deletions(session_locator)
                        SELECT session_locator FROM workspace_sessions
                        """
                    )
                    connection.execute("DELETE FROM workspace_sessions")
                    connection.execute("DELETE FROM turn_progress")
                    connection.execute("DELETE FROM legacy_turn_progress")
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES ('draft_protocol_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(HERMES_DRAFT_PROTOCOL_VERSION),),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _retire_session(connection: sqlite3.Connection, session_id: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO pending_session_deletions(session_locator) VALUES (?)",
            (session_id,),
        )
        connection.execute(
            "DELETE FROM turn_progress WHERE session_id = ?", (session_id,)
        )
        connection.execute(
            "DELETE FROM legacy_turn_progress WHERE session_id = ?", (session_id,)
        )

    def _reconcile_legacy_progress(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        with self._connect() as connection:
            legacy_rows = connection.execute(
                """
                SELECT id, assistant_text, steps_json
                FROM legacy_turn_progress
                WHERE session_id = ?
                ORDER BY turn_sequence
                """,
                (session_id,),
            ).fetchall()
        if not legacy_rows:
            return
        search_before = len(messages)
        matches: list[tuple[int, str, str]] = []
        for row in reversed(legacy_rows):
            for index in range(search_before - 1, -1, -1):
                message = messages[index]
                turn_id = message.get("turnId")
                if (
                    message.get("role") == "assistant"
                    and message.get("text") == row[1]
                    and isinstance(turn_id, str)
                    and turn_id
                ):
                    matches.append((int(row[0]), turn_id, str(row[2])))
                    search_before = index
                    break
        if not matches:
            return
        with self._connect() as connection:
            self._begin_immediate(connection)
            try:
                for legacy_id, turn_id, steps_json in matches:
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO turn_progress(
                            session_id, turn_id, steps_json
                        ) VALUES (?, ?, ?)
                        """,
                        (session_id, turn_id, steps_json),
                    )
                    connection.execute(
                        "DELETE FROM legacy_turn_progress WHERE id = ?",
                        (legacy_id,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

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
