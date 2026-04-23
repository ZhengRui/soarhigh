import pytest

from app.agent.store import InMemorySessionStore


@pytest.mark.asyncio
async def test_empty_session_returns_default():
    store = InMemorySessionStore()
    assert await store.load("nope") == (0, [])


@pytest.mark.asyncio
async def test_save_and_load_roundtrip():
    store = InMemorySessionStore()
    await store.save("s1", tail_seq=2, history=[{"fake": "message"}])
    tail, hist = await store.load("s1")
    assert tail == 2
    assert hist == [{"fake": "message"}]


@pytest.mark.asyncio
async def test_overwrite_updates_both_fields():
    store = InMemorySessionStore()
    await store.save("s1", tail_seq=1, history=[{"a": 1}])
    await store.save("s1", tail_seq=3, history=[{"a": 1}, {"b": 2}, {"c": 3}])
    tail, hist = await store.load("s1")
    assert tail == 3
    assert hist == [{"a": 1}, {"b": 2}, {"c": 3}]


@pytest.mark.asyncio
async def test_sessions_are_isolated():
    store = InMemorySessionStore()
    await store.save("sA", tail_seq=1, history=[{"a": 1}])
    await store.save("sB", tail_seq=5, history=[{"b": 9}])
    assert await store.load("sA") == (1, [{"a": 1}])
    assert await store.load("sB") == (5, [{"b": 9}])
