"""Session store abstraction.

Phase 1 shipped InMemorySessionStore only. Phase 3 adds SupabaseSessionStore
behind the same Protocol so Telegram/Hermes channels and the web UI's ↺
(revert) button have durable per-turn state.

Per-turn rows carry agenda_before/agenda_after snapshots and the Pydantic AI
ModelMessage cursor. That's what enables revert: pick turn N, load its
agenda_before, delete turns >= N, push agenda_before back to the UI.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TurnRecord:
    """One row in meeting_agent_turns. See migration for column semantics."""

    seq: int
    user_message: str
    assistant_text: str
    tool_trace: list[dict] = field(default_factory=list)
    agenda_before: dict = field(default_factory=dict)
    agenda_after: dict = field(default_factory=dict)
    history_cursor: list[dict] = field(default_factory=list)


class SessionStore(Protocol):
    async def load(self, session_id: str) -> tuple[int, list]:
        """Return (tail_seq, history_cursor_of_latest_turn). Missing session → (0, [])."""
        ...

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: TurnRecord,
    ) -> None:
        """Upsert session row, insert turn row, bump tail_seq.

        Per the migration schema tail_seq must equal turn.seq on success; the
        implementation is responsible for that invariant.
        """
        ...

    async def load_turn(self, session_id: str, seq: int) -> TurnRecord | None: ...

    async def delete_turns_at_or_after(self, session_id: str, seq: int) -> None: ...


class InMemorySessionStore:
    """Process-local store. Data is lost on restart. Used by unit tests and
    as the default when SUPABASE is unavailable in dev.

    Not safe across workers; a single-worker FastAPI is fine. The lock guards
    against concurrent asyncio tasks racing on the same session.
    """

    def __init__(self) -> None:
        # session_id -> (tail_seq, {seq -> TurnRecord})
        self._data: dict[str, tuple[int, dict[int, TurnRecord]]] = {}
        self._lock = asyncio.Lock()

    async def load(self, session_id: str) -> tuple[int, list]:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return (0, [])
            tail_seq, turns = entry
            latest = turns.get(tail_seq)
            history = latest.history_cursor if latest else []
            return (tail_seq, history)

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: TurnRecord,
    ) -> None:
        async with self._lock:
            _tail, turns = self._data.get(session_id, (0, {}))
            turns[turn.seq] = turn
            self._data[session_id] = (turn.seq, turns)

    async def load_turn(self, session_id: str, seq: int) -> TurnRecord | None:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return None
            return entry[1].get(seq)

    async def delete_turns_at_or_after(self, session_id: str, seq: int) -> None:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return
            _tail, turns = entry
            for s in list(turns.keys()):
                if s >= seq:
                    del turns[s]
            new_tail = max(turns.keys(), default=0)
            self._data[session_id] = (new_tail, turns)


class SupabaseSessionStore:
    """Durable store backed by the meeting_agent_sessions / meeting_agent_turns
    tables. Uses the service-role client (RLS bypassed); API-layer auth is
    what enforces membership.

    The supabase-py SDK is synchronous, so every call is wrapped in
    asyncio.to_thread to avoid blocking the event loop.
    """

    SESSIONS_TABLE = "meeting_agent_sessions"
    TURNS_TABLE = "meeting_agent_turns"

    def __init__(self, client=None) -> None:
        # Lazy-imported so tests using InMemorySessionStore don't need
        # Supabase env vars configured.
        if client is None:
            from app.db.supabase import supabase as client
        self._client = client

    async def load(self, session_id: str) -> tuple[int, list]:
        def _fetch():
            sess = (
                self._client.table(self.SESSIONS_TABLE)
                .select("tail_seq")
                .eq("session_id", session_id)
                .limit(1)
                .execute()
            )
            if not sess.data:
                return (0, [])
            tail_seq = sess.data[0]["tail_seq"] or 0
            if tail_seq == 0:
                return (0, [])
            turn = (
                self._client.table(self.TURNS_TABLE)
                .select("history_cursor")
                .eq("session_id", session_id)
                .eq("seq", tail_seq)
                .limit(1)
                .execute()
            )
            history = turn.data[0]["history_cursor"] if turn.data else []
            return (tail_seq, history)

        return await asyncio.to_thread(_fetch)

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: TurnRecord,
    ) -> None:
        def _write():
            # Upsert the session row first so the FK in meeting_agent_turns is
            # valid. tail_seq is bumped to match the new turn's seq.
            self._client.table(self.SESSIONS_TABLE).upsert(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "tail_seq": turn.seq,
                }
            ).execute()
            self._client.table(self.TURNS_TABLE).insert(
                {
                    "session_id": session_id,
                    "seq": turn.seq,
                    "user_message": turn.user_message,
                    "assistant_text": turn.assistant_text,
                    "tool_trace": turn.tool_trace,
                    "agenda_before": turn.agenda_before,
                    "agenda_after": turn.agenda_after,
                    "history_cursor": turn.history_cursor,
                }
            ).execute()

        await asyncio.to_thread(_write)

    async def load_turn(self, session_id: str, seq: int) -> TurnRecord | None:
        def _fetch():
            res = (
                self._client.table(self.TURNS_TABLE)
                .select("*")
                .eq("session_id", session_id)
                .eq("seq", seq)
                .limit(1)
                .execute()
            )
            if not res.data:
                return None
            row = res.data[0]
            return TurnRecord(
                seq=row["seq"],
                user_message=row["user_message"],
                assistant_text=row.get("assistant_text") or "",
                tool_trace=row.get("tool_trace") or [],
                agenda_before=row["agenda_before"],
                agenda_after=row["agenda_after"],
                history_cursor=row["history_cursor"],
            )

        return await asyncio.to_thread(_fetch)

    async def delete_turns_at_or_after(self, session_id: str, seq: int) -> None:
        def _delete():
            # Hard delete; the session row stays. tail_seq is bumped back down
            # to (seq - 1) so the next turn picks up where revert left off.
            self._client.table(self.TURNS_TABLE).delete().eq("session_id", session_id).gte("seq", seq).execute()
            self._client.table(self.SESSIONS_TABLE).update({"tail_seq": max(seq - 1, 0)}).eq(
                "session_id", session_id
            ).execute()

        await asyncio.to_thread(_delete)


def _build_default_store() -> SessionStore:
    """Pick the store at import time based on the environment.

    - AGENT_STORE=memory forces InMemory (useful for local dev without Supabase).
    - Otherwise default to SupabaseSessionStore.
    """
    if os.getenv("AGENT_STORE", "").lower() == "memory":
        return InMemorySessionStore()
    try:
        return SupabaseSessionStore()
    except Exception:
        # If supabase env vars aren't set at import time we fall back rather
        # than crashing. The route will surface errors if save actually fails.
        return InMemorySessionStore()


# Process-wide singleton. Tests override via monkeypatch in conftest.
session_store: SessionStore = _build_default_store()
