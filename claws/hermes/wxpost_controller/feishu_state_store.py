from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
from typing import Callable, Iterator

from .core import InvalidRequest, InvalidWorkspace
from .sqlite_support import serialize_controller_database_initialization


class FeishuStateStore:
    """Persistent Feishu navigation state, separate from Draft chat sessions."""

    CONFIRMATION_TTL_SECONDS = 10 * 60
    READ_ONLY = "readonly"
    EDITING = "editing"

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        directory = Path(workspace_root).expanduser().resolve() / ".wxpost-controller"
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            raise InvalidWorkspace("Controller state directory is unsafe")
        self._path = directory / "controller.sqlite3"
        if self._path.is_symlink():
            raise InvalidWorkspace("Controller state database is unsafe")
        self._clock = clock
        self._initialize()

    def active_workspace(self, scope_key: str) -> str | None:
        scope_key = self._validate_scope_key(scope_key)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT workspace_id FROM feishu_workspace_bindings WHERE scope_key = ?",
                (scope_key,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def interaction_mode(self, scope_key: str) -> str:
        scope_key = self._validate_scope_key(scope_key)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT mode FROM feishu_interaction_modes WHERE scope_key = ?",
                (scope_key,),
            ).fetchone()
        return str(row[0]) if row is not None else self.READ_ONLY

    def set_interaction_mode(self, scope_key: str, mode: str) -> None:
        scope_key = self._validate_scope_key(scope_key)
        if mode not in {self.READ_ONLY, self.EDITING}:
            raise InvalidRequest("unsupported Feishu interaction mode")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feishu_interaction_modes(scope_key, mode)
                VALUES (?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    mode = excluded.mode,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (scope_key, mode),
            )

    def clear_confirmation(self, scope_key: str) -> None:
        scope_key = self._validate_scope_key(scope_key)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM feishu_pending_confirmations WHERE scope_key = ?",
                (scope_key,),
            )
            connection.execute(
                "DELETE FROM feishu_mode_confirmations WHERE scope_key = ?",
                (scope_key,),
            )

    def stage_editing_confirmation(
        self,
        scope_key: str,
        *,
        message_id: str,
        requested_by_user_id: str,
    ) -> None:
        scope_key = self._validate_scope_key(scope_key)
        if not message_id or not requested_by_user_id:
            raise InvalidRequest("editing confirmation requires a message and member")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feishu_mode_confirmations(
                    scope_key, requested_message_id, requested_by_user_id,
                    expires_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    requested_message_id = excluded.requested_message_id,
                    requested_by_user_id = excluded.requested_by_user_id,
                    expires_at = excluded.expires_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scope_key,
                    message_id,
                    requested_by_user_id,
                    self._clock() + self.CONFIRMATION_TTL_SECONDS,
                ),
            )

    def consume_editing_confirmation(
        self,
        scope_key: str,
        *,
        message_id: str,
        requested_by_user_id: str,
    ) -> bool:
        scope_key = self._validate_scope_key(scope_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT requested_message_id, requested_by_user_id, expires_at
                FROM feishu_mode_confirmations
                WHERE scope_key = ?
                """,
                (scope_key,),
            ).fetchone()
            if row is None:
                return False
            if (
                str(row[0]) == message_id
                or str(row[1]) != requested_by_user_id
                or float(row[2]) <= self._clock()
            ):
                if float(row[2]) <= self._clock():
                    connection.execute(
                        "DELETE FROM feishu_mode_confirmations WHERE scope_key = ?",
                        (scope_key,),
                    )
                return False
            connection.execute(
                "DELETE FROM feishu_mode_confirmations WHERE scope_key = ?",
                (scope_key,),
            )
        return True

    def bind(self, scope_key: str, workspace_id: str) -> None:
        scope_key = self._validate_scope_key(scope_key)
        if not workspace_id:
            raise InvalidRequest("workspaceId is required")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feishu_workspace_bindings(
                    scope_key, workspace_id
                ) VALUES (?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    workspace_id = excluded.workspace_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (scope_key, workspace_id),
            )

    def clear_workspace(self, workspace_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM feishu_workspace_bindings WHERE workspace_id = ?",
                (workspace_id,),
            )

    def stage_confirmation(
        self,
        scope_key: str,
        *,
        action: str,
        payload: str,
        message_id: str,
        requested_by_user_id: str,
    ) -> None:
        scope_key = self._validate_scope_key(scope_key)
        if not action or not payload or not message_id or not requested_by_user_id:
            raise InvalidRequest(
                "confirmation action, payload, messageId, and member are required"
            )
        expires_at = self._clock() + self.CONFIRMATION_TTL_SECONDS
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feishu_pending_confirmations(
                    scope_key, action, payload, requested_message_id,
                    requested_by_user_id, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    action = excluded.action,
                    payload = excluded.payload,
                    requested_message_id = excluded.requested_message_id,
                    requested_by_user_id = excluded.requested_by_user_id,
                    expires_at = excluded.expires_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scope_key,
                    action,
                    payload,
                    message_id,
                    requested_by_user_id,
                    expires_at,
                ),
            )

    def consume_confirmation(
        self,
        scope_key: str,
        *,
        action: str,
        payload: str,
        message_id: str,
        requested_by_user_id: str,
    ) -> bool:
        staged_payload = self._consume_confirmation(
            scope_key,
            action=action,
            expected_payload=payload,
            message_id=message_id,
            requested_by_user_id=requested_by_user_id,
        )
        return staged_payload is not None

    def consume_staged_confirmation(
        self,
        scope_key: str,
        *,
        action: str,
        message_id: str,
        requested_by_user_id: str,
    ) -> str | None:
        """Consume a later member-confirmed payload without making Hermes echo it."""

        return self._consume_confirmation(
            scope_key,
            action=action,
            expected_payload=None,
            message_id=message_id,
            requested_by_user_id=requested_by_user_id,
        )

    def _consume_confirmation(
        self,
        scope_key: str,
        *,
        action: str,
        expected_payload: str | None,
        message_id: str,
        requested_by_user_id: str,
    ) -> str | None:
        scope_key = self._validate_scope_key(scope_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT action, payload, requested_message_id,
                       requested_by_user_id, expires_at
                FROM feishu_pending_confirmations
                WHERE scope_key = ?
                """,
                (scope_key,),
            ).fetchone()
            if row is None:
                return None
            payload = str(row[1])
            if str(row[0]) != action or (
                expected_payload is not None and payload != expected_payload
            ):
                return None
            if str(row[2]) == message_id:
                return None
            if str(row[3]) != requested_by_user_id:
                return None
            if float(row[4]) <= self._clock():
                connection.execute(
                    "DELETE FROM feishu_pending_confirmations WHERE scope_key = ?",
                    (scope_key,),
                )
                return None
            connection.execute(
                "DELETE FROM feishu_pending_confirmations WHERE scope_key = ?",
                (scope_key,),
            )
        return payload

    @staticmethod
    def _validate_scope_key(scope_key: str) -> str:
        value = scope_key.strip()
        parts = value.split(":")
        if len(parts) < 5 or parts[0] != "agent" or parts[2] != "feishu":
            raise InvalidRequest("an active Feishu conversation is required")
        return value

    def _initialize(self) -> None:
        with serialize_controller_database_initialization(self._path.parent):
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                CREATE TABLE IF NOT EXISTS feishu_workspace_bindings (
                    scope_key TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_feishu_bindings_workspace
                    ON feishu_workspace_bindings(workspace_id);
                CREATE TABLE IF NOT EXISTS feishu_interaction_modes (
                    scope_key TEXT PRIMARY KEY,
                    mode TEXT NOT NULL CHECK(mode IN ('readonly', 'editing')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS feishu_mode_confirmations (
                    scope_key TEXT PRIMARY KEY,
                    requested_message_id TEXT NOT NULL,
                    requested_by_user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                    """
                )
                confirmation_columns = {
                    str(row[1])
                    for row in connection.execute(
                        "PRAGMA table_info(feishu_pending_confirmations)"
                    )
                }
                required_confirmation_columns = {
                    "scope_key",
                    "action",
                    "payload",
                    "requested_message_id",
                    "requested_by_user_id",
                    "expires_at",
                    "created_at",
                    "updated_at",
                }
                if confirmation_columns and not required_confirmation_columns.issubset(
                    confirmation_columns
                ):
                    # Confirmations are short-lived interaction state. Clearing
                    # an obsolete shape is safer than preserving an action that
                    # is not bound to a member or expiry.
                    connection.execute("DROP TABLE feishu_pending_confirmations")
                connection.execute(
                    """
                CREATE TABLE IF NOT EXISTS feishu_pending_confirmations (
                    scope_key TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    requested_message_id TEXT NOT NULL,
                    requested_by_user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                    """
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self._path, timeout=5)
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            if connection.in_transaction:
                connection.commit()
        except sqlite3.Error as error:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise InvalidWorkspace("Feishu Controller state is unavailable") from error
        finally:
            if connection is not None:
                connection.close()
