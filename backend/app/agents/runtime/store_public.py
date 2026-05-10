"""Public Agent turn persistence.

Separate from `store.py` on purpose: member Agent sessions are owned by
auth.users.id, while Public Agent sessions are owned by (channel,
visitor_key). Keeping the stores separate prevents guest/public history
from being mixed into member Agent history.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Literal, Protocol

PublicChannel = Literal["miniapp", "web"]


@dataclass
class AgentTurnPublicRecord:
    """One row in agent_turns_public."""

    seq: int
    user_message: str
    agent_kind: str = "general"
    assistant_text: str = ""
    tool_trace: list[dict] = field(default_factory=list)
    history_cursor: list[dict] = field(default_factory=list)
    domain_payload: dict = field(default_factory=dict)


def _row_to_record(row: dict) -> AgentTurnPublicRecord:
    return AgentTurnPublicRecord(
        seq=row["seq"],
        agent_kind=row.get("agent_kind") or "general",
        user_message=row["user_message"],
        assistant_text=row.get("assistant_text") or "",
        tool_trace=row.get("tool_trace") or [],
        history_cursor=row.get("history_cursor") or [],
        domain_payload=row.get("domain_payload") or {},
    )


class AgentTurnStorePublic(Protocol):
    async def load(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> tuple[int, list]:
        """Return (tail_seq, latest history_cursor). Missing or foreign
        owner returns (0, []) without leaking session existence."""
        ...

    async def save_turn(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
        turn: AgentTurnPublicRecord,
    ) -> None:
        """Persist a public turn, claiming a new session for
        (channel, visitor_key) on first write."""
        ...

    async def load_turn(
        self,
        session_id: str,
        seq: int,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> AgentTurnPublicRecord | None: ...

    async def verify_session_access(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> bool:
        """True for unclaimed or matching-owner sessions."""
        ...


class InMemoryAgentTurnStorePublic:
    """Process-local public store used by tests and local fallback."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[int, dict[int, AgentTurnPublicRecord]]] = {}
        self._owners: dict[str, tuple[str, str]] = {}
        self._lock = asyncio.Lock()

    def _owner_matches(self, session_id: str, channel: str, visitor_key: str) -> bool:
        owner = self._owners.get(session_id)
        return owner == (channel, visitor_key) if session_id in self._owners else True

    async def load(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> tuple[int, list]:
        async with self._lock:
            if not self._owner_matches(session_id, channel, visitor_key):
                return (0, [])
            entry = self._data.get(session_id)
            if entry is None:
                return (0, [])
            tail_seq, turns = entry
            latest = turns.get(tail_seq)
            return (tail_seq, latest.history_cursor if latest else [])

    async def save_turn(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
        turn: AgentTurnPublicRecord,
    ) -> None:
        async with self._lock:
            if session_id in self._owners and self._owners[session_id] != (channel, visitor_key):
                return
            self._owners[session_id] = (channel, visitor_key)
            _tail, turns = self._data.get(session_id, (0, {}))
            turns[turn.seq] = turn
            self._data[session_id] = (turn.seq, turns)

    async def load_turn(
        self,
        session_id: str,
        seq: int,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> AgentTurnPublicRecord | None:
        async with self._lock:
            if not self._owner_matches(session_id, channel, visitor_key):
                return None
            entry = self._data.get(session_id)
            if entry is None:
                return None
            return entry[1].get(seq)

    async def verify_session_access(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> bool:
        async with self._lock:
            return self._owner_matches(session_id, channel, visitor_key)


class SupabaseAgentTurnStorePublic:
    """Durable Public Agent store backed by agent_sessions_public /
    agent_turns_public. Ownership is enforced in service code because the
    service-role Supabase client bypasses RLS."""

    SESSIONS_TABLE = "agent_sessions_public"
    TURNS_TABLE = "agent_turns_public"

    def __init__(self, client=None) -> None:
        if client is None:
            from app.db.supabase import supabase as client

        self._client = client

    def _fetch_session(self, session_id: str) -> dict | None:
        sess = (
            self._client.table(self.SESSIONS_TABLE)
            .select("tail_seq, channel, visitor_key")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        return sess.data[0] if sess.data else None

    @staticmethod
    def _session_matches(sess: dict | None, *, channel: str, visitor_key: str) -> bool:
        return sess is None or (sess.get("channel") == channel and sess.get("visitor_key") == visitor_key)

    async def load(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> tuple[int, list]:
        def _fetch() -> tuple[int, list]:
            sess = self._fetch_session(session_id)
            if sess is None or not self._session_matches(sess, channel=channel, visitor_key=visitor_key):
                return (0, [])
            tail_seq = sess.get("tail_seq") or 0
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
        *,
        channel: PublicChannel,
        visitor_key: str,
        turn: AgentTurnPublicRecord,
    ) -> None:
        def _write() -> None:
            sess = self._fetch_session(session_id)
            if not self._session_matches(sess, channel=channel, visitor_key=visitor_key):
                return
            self._client.table(self.SESSIONS_TABLE).upsert(
                {
                    "session_id": session_id,
                    "channel": channel,
                    "visitor_key": visitor_key,
                    "tail_seq": turn.seq,
                }
            ).execute()
            self._client.table(self.TURNS_TABLE).insert(
                {
                    "session_id": session_id,
                    "seq": turn.seq,
                    "agent_kind": turn.agent_kind,
                    "user_message": turn.user_message,
                    "assistant_text": turn.assistant_text,
                    "tool_trace": turn.tool_trace,
                    "history_cursor": turn.history_cursor,
                    "domain_payload": turn.domain_payload,
                }
            ).execute()

        await asyncio.to_thread(_write)

    async def load_turn(
        self,
        session_id: str,
        seq: int,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> AgentTurnPublicRecord | None:
        def _fetch() -> AgentTurnPublicRecord | None:
            sess = self._fetch_session(session_id)
            if sess is None or not self._session_matches(sess, channel=channel, visitor_key=visitor_key):
                return None
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

    async def verify_session_access(
        self,
        session_id: str,
        *,
        channel: PublicChannel,
        visitor_key: str,
    ) -> bool:
        def _check() -> bool:
            sess = self._fetch_session(session_id)
            return self._session_matches(sess, channel=channel, visitor_key=visitor_key)

        return await asyncio.to_thread(_check)


def _build_default_store_public() -> AgentTurnStorePublic:
    if os.getenv("AGENT_PUBLIC_STORE", "").lower() == "memory":
        return InMemoryAgentTurnStorePublic()
    try:
        return SupabaseAgentTurnStorePublic()
    except Exception:
        return InMemoryAgentTurnStorePublic()


agent_turn_store_public: AgentTurnStorePublic = _build_default_store_public()
