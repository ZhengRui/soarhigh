"""Session store for the statistics agent.

Shape mirrors `app.meeting_agent.store` but the persisted row drops the
agenda_before / agenda_after columns — stats is read-only, there's no
draft to revert. Phase 3 will collapse all per-agent tables into a
single `agent_turns` envelope; for Phase 2 we keep them physically
separate to ship without a migration coupling.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class StatsTurnRecord:
    """One row in statistics_agent_turns. Read-only agent — no agenda
    snapshots needed."""

    seq: int
    user_message: str
    assistant_text: str
    tool_trace: list[dict] = field(default_factory=list)
    history_cursor: list[dict] = field(default_factory=list)


class StatsSessionStore(Protocol):
    async def load(self, session_id: str) -> tuple[int, list]:
        """Return (tail_seq, history_cursor_of_latest_turn). Missing → (0, [])."""
        ...

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: StatsTurnRecord,
    ) -> None: ...

    async def load_turn(self, session_id: str, seq: int) -> StatsTurnRecord | None: ...


class InMemoryStatsSessionStore:
    """Process-local store. Same purpose as the meeting agent's
    InMemorySessionStore."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[int, dict[int, StatsTurnRecord]]] = {}
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
        turn: StatsTurnRecord,
    ) -> None:
        async with self._lock:
            _tail, turns = self._data.get(session_id, (0, {}))
            turns[turn.seq] = turn
            self._data[session_id] = (turn.seq, turns)

    async def load_turn(self, session_id: str, seq: int) -> StatsTurnRecord | None:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return None
            return entry[1].get(seq)


class SupabaseStatsSessionStore:
    """Durable store backed by statistics_agent_sessions /
    statistics_agent_turns. Mirrors SupabaseSessionStore from the
    meeting agent but without the agenda columns."""

    SESSIONS_TABLE = "statistics_agent_sessions"
    TURNS_TABLE = "statistics_agent_turns"

    def __init__(self, client=None) -> None:
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
        turn: StatsTurnRecord,
    ) -> None:
        def _write():
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
                    "history_cursor": turn.history_cursor,
                }
            ).execute()

        await asyncio.to_thread(_write)

    async def load_turn(self, session_id: str, seq: int) -> StatsTurnRecord | None:
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
            return StatsTurnRecord(
                seq=row["seq"],
                user_message=row["user_message"],
                assistant_text=row.get("assistant_text") or "",
                tool_trace=row.get("tool_trace") or [],
                history_cursor=row["history_cursor"],
            )

        return await asyncio.to_thread(_fetch)


def _build_default_store() -> StatsSessionStore:
    if os.getenv("AGENT_STORE", "").lower() == "memory":
        return InMemoryStatsSessionStore()
    try:
        return SupabaseStatsSessionStore()
    except Exception:
        return InMemoryStatsSessionStore()


session_store: StatsSessionStore = _build_default_store()
