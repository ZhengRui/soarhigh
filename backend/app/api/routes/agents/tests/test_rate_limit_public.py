import pytest
from fastapi import HTTPException

from app.api.routes.agents.rate_limit_public import (
    InMemoryRateLimiterPublic,
    PublicRateLimitIdentity,
    SupabaseRateLimiterPublic,
)


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_blocks_concurrent_session():
    limiter = InMemoryRateLimiterPublic(per_minute=10, per_day=10)
    identity = PublicRateLimitIdentity(channel="miniapp", visitor_key="wx1")

    await limiter.check(identity, session_id="s1")
    with pytest.raises(HTTPException) as exc:
        await limiter.check(identity, session_id="s1")

    assert exc.value.status_code == 429
    assert "already running" in exc.value.detail

    await limiter.release(session_id="s1")
    await limiter.check(identity, session_id="s1")


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_enforces_minute_limit():
    limiter = InMemoryRateLimiterPublic(per_minute=1, per_day=10)
    identity = PublicRateLimitIdentity(channel="miniapp", visitor_key="wx1")

    await limiter.check(identity, session_id="s1")
    await limiter.release(session_id="s1")

    with pytest.raises(HTTPException) as exc:
        await limiter.check(identity, session_id="s2")

    assert exc.value.status_code == 429
    assert "minute" in exc.value.detail


class _FakeRpc:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _FakeSupabase:
    def __init__(self, allowed_by_bucket=None):
        self.allowed_by_bucket = allowed_by_bucket or {}
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        allowed = self.allowed_by_bucket.get(params["p_bucket"], True)
        return _FakeRpc([{"allowed": allowed}])


@pytest.mark.asyncio
async def test_supabase_rate_limiter_uses_rpc_for_minute_and_day():
    client = _FakeSupabase()
    limiter = SupabaseRateLimiterPublic(client=client, per_minute=3, per_day=9)
    identity = PublicRateLimitIdentity(channel="web", visitor_key="visitor1")

    await limiter.check(identity, session_id="s1")

    assert [call[0] for call in client.calls] == [
        "increment_agent_rate_limit_public",
        "increment_agent_rate_limit_public",
    ]
    assert [call[1]["p_bucket"] for call in client.calls] == ["minute", "day"]
    assert [call[1]["p_key"] for call in client.calls] == ["web:visitor1", "web:visitor1"]
    assert [call[1]["p_limit"] for call in client.calls] == [3, 9]


@pytest.mark.asyncio
async def test_supabase_rate_limiter_releases_inflight_on_rpc_block():
    client = _FakeSupabase({"minute": True, "day": False})
    limiter = SupabaseRateLimiterPublic(client=client, per_minute=3, per_day=1)
    identity = PublicRateLimitIdentity(channel="web", visitor_key="visitor1")

    with pytest.raises(HTTPException) as exc:
        await limiter.check(identity, session_id="s1")

    assert exc.value.status_code == 429
    assert "day" in exc.value.detail

    with pytest.raises(HTTPException) as retry_exc:
        await limiter.check(identity, session_id="s1")

    assert "day" in retry_exc.value.detail
    assert len(client.calls) == 4
