"""Session store abstraction.

Phase 1: in-memory only. Phase 3 adds SupabaseSessionStore behind the same Protocol.
"""

import asyncio
from typing import Protocol


class SessionStore(Protocol):
    async def load(self, session_id: str) -> tuple[int, list]: ...

    async def save(self, session_id: str, tail_seq: int, history: list) -> None: ...


class InMemorySessionStore:
    """Process-local session store. Data is lost on restart.

    Not thread-safe across workers; FastAPI with a single worker is fine.
    The lock guards against concurrent asyncio tasks racing on the same session.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[int, list]] = {}
        self._lock = asyncio.Lock()

    async def load(self, session_id: str) -> tuple[int, list]:
        async with self._lock:
            return self._data.get(session_id, (0, []))

    async def save(self, session_id: str, tail_seq: int, history: list) -> None:
        async with self._lock:
            self._data[session_id] = (tail_seq, history)


# Process-wide singleton for Phase 1. Phase 3 replaces with SupabaseSessionStore.
session_store: SessionStore = InMemorySessionStore()
