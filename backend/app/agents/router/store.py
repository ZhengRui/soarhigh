"""Router decision persistence."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Protocol

from app.agents.runtime.contracts import RouterDecision


@dataclass
class RouterDecisionRecord:
    seq: int
    user_message: str
    decision: dict


class RouterDecisionStore(Protocol):
    async def save_decision(
        self,
        session_id: str,
        user_id: str | None,
        user_message: str,
        decision: RouterDecision,
    ) -> RouterDecisionRecord: ...


class InMemoryRouterDecisionStore:
    def __init__(self) -> None:
        self._data: dict[str, list[RouterDecisionRecord]] = {}
        self._lock = asyncio.Lock()

    async def save_decision(
        self,
        session_id: str,
        user_id: str | None,
        user_message: str,
        decision: RouterDecision,
    ) -> RouterDecisionRecord:
        async with self._lock:
            records = self._data.setdefault(session_id, [])
            record = RouterDecisionRecord(
                seq=len(records) + 1,
                user_message=user_message,
                decision=decision.model_dump(mode="json"),
            )
            records.append(record)
            return record

    async def load_decisions(self, session_id: str) -> list[RouterDecisionRecord]:
        async with self._lock:
            return list(self._data.get(session_id, []))


class SupabaseRouterDecisionStore:
    TABLE = "agent_router_decisions"

    def __init__(self, client=None) -> None:
        if client is None:
            from app.db.supabase import supabase as client
        self._client = client

    async def save_decision(
        self,
        session_id: str,
        user_id: str | None,
        user_message: str,
        decision: RouterDecision,
    ) -> RouterDecisionRecord:
        decision_json = decision.model_dump(mode="json")

        def _write() -> RouterDecisionRecord:
            latest = (
                self._client.table(self.TABLE)
                .select("seq")
                .eq("session_id", session_id)
                .order("seq", desc=True)
                .limit(1)
                .execute()
            )
            seq = int(latest.data[0]["seq"]) + 1 if latest.data else 1
            self._client.table(self.TABLE).insert(
                {
                    "session_id": session_id,
                    "seq": seq,
                    "user_id": user_id,
                    "user_message": user_message,
                    "decision": decision_json,
                }
            ).execute()
            return RouterDecisionRecord(seq=seq, user_message=user_message, decision=decision_json)

        return await asyncio.to_thread(_write)


def _build_default_store() -> RouterDecisionStore:
    if os.getenv("AGENT_STORE", "").lower() == "memory":
        return InMemoryRouterDecisionStore()
    try:
        return SupabaseRouterDecisionStore()
    except Exception:
        return InMemoryRouterDecisionStore()


decision_store: RouterDecisionStore = _build_default_store()
