"""Rate limiting for AgentPublic.

Vercel/WAF can provide coarse IP-level protection, but the model-cost boundary
needs an application-level key after identity resolution: channel + visitor_key.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from fastapi import HTTPException

from ....config import AGENT_PUBLIC_LIMIT_PER_DAY, AGENT_PUBLIC_LIMIT_PER_MINUTE


def _window_start(now: datetime, bucket: str) -> datetime:
    now = now.astimezone(UTC)
    if bucket == "minute":
        return now.replace(second=0, microsecond=0)
    if bucket == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown bucket: {bucket}")


@dataclass(frozen=True)
class PublicRateLimitIdentity:
    channel: str
    visitor_key: str

    @property
    def key(self) -> str:
        return f"{self.channel}:{self.visitor_key}"


class RateLimiterPublic(Protocol):
    async def check(self, identity: PublicRateLimitIdentity, *, session_id: str) -> None:
        """Raise HTTPException(429) if the request should be blocked."""
        ...

    async def release(self, *, session_id: str) -> None:
        """Release in-flight session bookkeeping."""
        ...


class InMemoryRateLimiterPublic:
    """Test/local fallback. Not sufficient for production Vercel instances."""

    def __init__(
        self,
        *,
        per_minute: int = AGENT_PUBLIC_LIMIT_PER_MINUTE,
        per_day: int = AGENT_PUBLIC_LIMIT_PER_DAY,
    ) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self._counts: dict[tuple[str, str, datetime], int] = {}
        self._inflight: set[str] = set()
        self._lock = asyncio.Lock()

    async def check(self, identity: PublicRateLimitIdentity, *, session_id: str) -> None:
        now = datetime.now(UTC)
        async with self._lock:
            if session_id in self._inflight:
                raise HTTPException(status_code=429, detail="Another turn is already running for this session.")
            for bucket, limit in (("minute", self.per_minute), ("day", self.per_day)):
                key = (identity.key, bucket, _window_start(now, bucket))
                next_count = self._counts.get(key, 0) + 1
                if next_count > limit:
                    raise HTTPException(status_code=429, detail=f"Public Agent {bucket} limit exceeded.")
                self._counts[key] = next_count
            self._inflight.add(session_id)

    async def release(self, *, session_id: str) -> None:
        async with self._lock:
            self._inflight.discard(session_id)


class SupabaseRateLimiterPublic:
    """Shared-store rate limiter for serverless deployments.

    Minute/day counters use the `increment_agent_rate_limit_public` RPC.
    In-flight session tracking is process-local by design here; it is a UX
    guard against accidental double taps, while the durable counters protect
    model cost across instances.
    """

    def __init__(
        self,
        client=None,
        *,
        per_minute: int = AGENT_PUBLIC_LIMIT_PER_MINUTE,
        per_day: int = AGENT_PUBLIC_LIMIT_PER_DAY,
    ) -> None:
        if client is None:
            from app.db.supabase import supabase as client

        self._client = client
        self.per_minute = per_minute
        self.per_day = per_day
        self._inflight: set[str] = set()
        self._lock = asyncio.Lock()

    def _increment(self, identity: PublicRateLimitIdentity, bucket: str, limit: int, now: datetime) -> None:
        res = self._client.rpc(
            "increment_agent_rate_limit_public",
            {
                "p_key": identity.key,
                "p_bucket": bucket,
                "p_window_start": _window_start(now, bucket).isoformat(),
                "p_limit": limit,
            },
        ).execute()
        row = res.data[0] if res.data else {}
        if row and row.get("allowed") is False:
            raise HTTPException(status_code=429, detail=f"Public Agent {bucket} limit exceeded.")

    async def check(self, identity: PublicRateLimitIdentity, *, session_id: str) -> None:
        now = datetime.now(UTC)
        async with self._lock:
            if session_id in self._inflight:
                raise HTTPException(status_code=429, detail="Another turn is already running for this session.")
            self._inflight.add(session_id)
        try:
            await asyncio.to_thread(self._increment, identity, "minute", self.per_minute, now)
            await asyncio.to_thread(self._increment, identity, "day", self.per_day, now)
        except Exception:
            async with self._lock:
                self._inflight.discard(session_id)
            raise

    async def release(self, *, session_id: str) -> None:
        async with self._lock:
            self._inflight.discard(session_id)


def _build_default_rate_limiter_public() -> RateLimiterPublic:
    try:
        return SupabaseRateLimiterPublic()
    except Exception:
        return InMemoryRateLimiterPublic()


rate_limiter_public: RateLimiterPublic = _build_default_rate_limiter_public()
