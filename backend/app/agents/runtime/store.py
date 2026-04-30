"""Unified turn persistence for the agent endpoints.

Single source of truth for both /agent/turn (router-mediated) and the standalone
/meeting-agent/turn / /statistics-agent/turn endpoints. One row per user
message, regardless of which specialist handled it. `history_cursor` carries
the Pydantic AI ModelMessage[] so the next turn — possibly run by a different
specialist — picks up the conversation seamlessly.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Protocol

from app.agents.runtime.contracts import AgentKind, RouteKind


def _enum_value(value: AgentKind | RouteKind | str) -> str:
    return value.value if isinstance(value, AgentKind | RouteKind) else value


@dataclass
class AgentTurnRecord:
    """One row in the unified agent_turns table."""

    seq: int
    agent_kind: AgentKind | str
    route: RouteKind | str
    user_message: str
    assistant_text: str = ""
    tool_trace: list[dict] = field(default_factory=list)
    router_decision: dict = field(default_factory=dict)
    specialist_seq: int | None = None
    agenda_before: dict | None = None
    agenda_after: dict | None = None
    history_cursor: list[dict] = field(default_factory=list)
    domain_payload: dict = field(default_factory=dict)


def _row_to_record(row: dict) -> AgentTurnRecord:
    return AgentTurnRecord(
        seq=row["seq"],
        agent_kind=row["agent_kind"],
        route=row["route"],
        user_message=row["user_message"],
        assistant_text=row.get("assistant_text") or "",
        tool_trace=row.get("tool_trace") or [],
        router_decision=row.get("router_decision") or {},
        specialist_seq=row.get("specialist_seq"),
        agenda_before=row.get("agenda_before"),
        agenda_after=row.get("agenda_after"),
        history_cursor=row.get("history_cursor") or [],
        domain_payload=row.get("domain_payload") or {},
    )


class UnifiedAgentTurnStore(Protocol):
    async def load(self, session_id: str) -> tuple[int, list]:
        """Return (tail_seq, history_cursor_of_latest_turn). Missing → (0, [])."""
        ...

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: AgentTurnRecord,
    ) -> None: ...

    async def load_turn(self, session_id: str, seq: int) -> AgentTurnRecord | None: ...

    async def load_latest(self, session_id: str) -> AgentTurnRecord | None: ...

    async def delete_turns_at_or_after(self, session_id: str, seq: int) -> None: ...


class InMemoryUnifiedAgentTurnStore:
    """Process-local store used by tests and local dev without Supabase."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[int, dict[int, AgentTurnRecord]]] = {}
        self._lock = asyncio.Lock()

    async def load(self, session_id: str) -> tuple[int, list]:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return (0, [])
            tail_seq, turns = entry
            latest = turns.get(tail_seq)
            return (tail_seq, latest.history_cursor if latest else [])

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: AgentTurnRecord,
    ) -> None:
        async with self._lock:
            _tail, turns = self._data.get(session_id, (0, {}))
            turns[turn.seq] = turn
            self._data[session_id] = (turn.seq, turns)

    async def load_turn(self, session_id: str, seq: int) -> AgentTurnRecord | None:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return None
            return entry[1].get(seq)

    async def load_latest(self, session_id: str) -> AgentTurnRecord | None:
        async with self._lock:
            entry = self._data.get(session_id)
            if entry is None:
                return None
            tail_seq, turns = entry
            return turns.get(tail_seq)

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


class SupabaseUnifiedAgentTurnStore:
    """Durable store backed by agent_sessions / agent_turns."""

    SESSIONS_TABLE = "agent_sessions"
    TURNS_TABLE = "agent_turns"

    def __init__(self, client=None) -> None:
        if client is None:
            from app.db.supabase import supabase as client

        self._client = client

    async def load(self, session_id: str) -> tuple[int, list]:
        def _fetch() -> tuple[int, list]:
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
            return (tail_seq, history or [])

        return await asyncio.to_thread(_fetch)

    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: AgentTurnRecord,
    ) -> None:
        def _write() -> None:
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
                    "agent_kind": _enum_value(turn.agent_kind),
                    "route": _enum_value(turn.route),
                    "user_message": turn.user_message,
                    "assistant_text": turn.assistant_text,
                    "tool_trace": turn.tool_trace,
                    "router_decision": turn.router_decision,
                    "specialist_seq": turn.specialist_seq,
                    "agenda_before": turn.agenda_before,
                    "agenda_after": turn.agenda_after,
                    "history_cursor": turn.history_cursor,
                    "domain_payload": turn.domain_payload,
                }
            ).execute()

        await asyncio.to_thread(_write)

    async def load_turn(self, session_id: str, seq: int) -> AgentTurnRecord | None:
        def _fetch() -> AgentTurnRecord | None:
            res = (
                self._client.table(self.TURNS_TABLE)
                .select("*")
                .eq("session_id", session_id)
                .eq("seq", seq)
                .limit(1)
                .execute()
            )
            return _row_to_record(res.data[0]) if res.data else None

        return await asyncio.to_thread(_fetch)

    async def load_latest(self, session_id: str) -> AgentTurnRecord | None:
        def _fetch() -> AgentTurnRecord | None:
            res = (
                self._client.table(self.TURNS_TABLE)
                .select("*")
                .eq("session_id", session_id)
                .order("seq", desc=True)
                .limit(1)
                .execute()
            )
            return _row_to_record(res.data[0]) if res.data else None

        return await asyncio.to_thread(_fetch)

    async def delete_turns_at_or_after(self, session_id: str, seq: int) -> None:
        def _delete() -> None:
            self._client.table(self.TURNS_TABLE).delete().eq("session_id", session_id).gte("seq", seq).execute()
            self._client.table(self.SESSIONS_TABLE).update({"tail_seq": max(seq - 1, 0)}).eq(
                "session_id", session_id
            ).execute()

        await asyncio.to_thread(_delete)


def _build_default_store() -> UnifiedAgentTurnStore:
    if os.getenv("AGENT_STORE", "").lower() == "memory":
        return InMemoryUnifiedAgentTurnStore()
    try:
        return SupabaseUnifiedAgentTurnStore()
    except Exception:
        return InMemoryUnifiedAgentTurnStore()


agent_turn_store: UnifiedAgentTurnStore = _build_default_store()
