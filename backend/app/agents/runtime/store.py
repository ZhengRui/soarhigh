"""Unified turn persistence for the top-level agent endpoint.

The specialist stores remain the source of truth for model history and meeting
revert. This store records the user-facing `/agent/turn` envelope so a single
conversation can contain router-only, meeting, and statistics turns.
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
    domain_payload: dict = field(default_factory=dict)


class UnifiedAgentTurnStore(Protocol):
    async def save_turn(
        self,
        session_id: str,
        user_id: str | None,
        turn: AgentTurnRecord,
    ) -> None: ...

    async def load_turn(self, session_id: str, seq: int) -> AgentTurnRecord | None: ...

    async def load_latest(self, session_id: str) -> AgentTurnRecord | None: ...


class InMemoryUnifiedAgentTurnStore:
    """Process-local store used by tests and local dev without Supabase."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[int, dict[int, AgentTurnRecord]]] = {}
        self._lock = asyncio.Lock()

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


class SupabaseUnifiedAgentTurnStore:
    """Durable store backed by agent_sessions / agent_turns."""

    SESSIONS_TABLE = "agent_sessions"
    TURNS_TABLE = "agent_turns"

    def __init__(self, client=None) -> None:
        if client is None:
            from app.db.supabase import supabase as client

        self._client = client

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
            if not res.data:
                return None
            row = res.data[0]
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
                domain_payload=row.get("domain_payload") or {},
            )

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
            if not res.data:
                return None
            row = res.data[0]
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
                domain_payload=row.get("domain_payload") or {},
            )

        return await asyncio.to_thread(_fetch)


def _build_default_store() -> UnifiedAgentTurnStore:
    if os.getenv("AGENT_STORE", "").lower() == "memory":
        return InMemoryUnifiedAgentTurnStore()
    try:
        return SupabaseUnifiedAgentTurnStore()
    except Exception:
        return InMemoryUnifiedAgentTurnStore()


agent_turn_store: UnifiedAgentTurnStore = _build_default_store()
