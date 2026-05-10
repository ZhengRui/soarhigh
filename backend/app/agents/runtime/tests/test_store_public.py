import pytest

from app.agents.runtime.store_public import AgentTurnPublicRecord, InMemoryAgentTurnStorePublic


def _make_turn(seq: int = 1) -> AgentTurnPublicRecord:
    return AgentTurnPublicRecord(
        seq=seq,
        user_message="TT 是什么?",
        assistant_text="TT is Table Topics.",
        tool_trace=[{"id": "t1", "name": "view_skill_public", "status": "ok"}],
        history_cursor=[{"msg": seq}],
        domain_payload={"skill_sources": ["toastmasters-roles"]},
    )


@pytest.mark.asyncio
async def test_public_store_saves_and_loads_tail_history():
    store = InMemoryAgentTurnStorePublic()

    await store.save_turn("s1", channel="miniapp", visitor_key="wx1", turn=_make_turn(seq=1))
    await store.save_turn("s1", channel="miniapp", visitor_key="wx1", turn=_make_turn(seq=2))

    tail, history = await store.load("s1", channel="miniapp", visitor_key="wx1")

    assert tail == 2
    assert history == [{"msg": 2}]


@pytest.mark.asyncio
async def test_public_store_foreign_visitor_cannot_read_or_write():
    store = InMemoryAgentTurnStorePublic()
    await store.save_turn("s1", channel="miniapp", visitor_key="wx1", turn=_make_turn(seq=1))

    assert await store.load("s1", channel="miniapp", visitor_key="wx2") == (0, [])
    assert await store.load_turn("s1", 1, channel="miniapp", visitor_key="wx2") is None

    hijack = _make_turn(seq=2)
    hijack.user_message = "hijack"
    await store.save_turn("s1", channel="miniapp", visitor_key="wx2", turn=hijack)

    assert await store.load_turn("s1", 2, channel="miniapp", visitor_key="wx1") is None
    original = await store.load_turn("s1", 1, channel="miniapp", visitor_key="wx1")
    assert original is not None
    assert original.user_message == "TT 是什么?"


@pytest.mark.asyncio
async def test_public_store_channel_is_part_of_owner_key():
    store = InMemoryAgentTurnStorePublic()
    await store.save_turn("s1", channel="miniapp", visitor_key="same", turn=_make_turn(seq=1))

    assert await store.verify_session_access("s1", channel="miniapp", visitor_key="same") is True
    assert await store.verify_session_access("s1", channel="web", visitor_key="same") is False
    assert await store.verify_session_access("new", channel="web", visitor_key="same") is True
