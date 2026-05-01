import pytest

from app.agents.runtime.contracts import AgentKind, RouteKind
from app.agents.runtime.store import (
    AgentTurnRecord,
    InMemoryUnifiedAgentTurnStore,
    SupabaseUnifiedAgentTurnStore,
)


def _make_turn(seq: int = 1) -> AgentTurnRecord:
    return AgentTurnRecord(
        seq=seq,
        agent_kind=AgentKind.STATISTICS,
        route=RouteKind.SPECIALIST,
        user_message="who won most awards?",
        assistant_text="Liz won twice.",
        tool_trace=[{"id": "t1", "name": "member_award_matrix", "status": "ok"}],
        router_decision={"route": "specialist", "agent_kind": "statistics"},
        domain_payload={"done": {"seq": 3, "final_text": "Liz won twice."}},
    )


@pytest.mark.asyncio
async def test_in_memory_store_saves_and_loads_turn():
    store = InMemoryUnifiedAgentTurnStore()
    turn = _make_turn()

    await store.save_turn("s1", user_id="u1", turn=turn)

    loaded = await store.load_turn("s1", 1, user_id="u1")
    assert loaded == turn
    assert await store.load_turn("s1", 99, user_id="u1") is None


@pytest.mark.asyncio
async def test_in_memory_store_loads_latest_turn():
    store = InMemoryUnifiedAgentTurnStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=1))
    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=2))

    loaded = await store.load_latest("s1", user_id="u1")

    assert loaded is not None
    assert loaded.seq == 2
    assert await store.load_latest("missing", user_id="u1") is None


@pytest.mark.asyncio
async def test_in_memory_store_load_returns_tail_and_history():
    store = InMemoryUnifiedAgentTurnStore()
    assert await store.load("nope", user_id="u1") == (0, [])

    turn1 = _make_turn(seq=1)
    turn1.history_cursor = [{"msg": "a"}]
    await store.save_turn("s1", user_id="u1", turn=turn1)
    turn2 = _make_turn(seq=2)
    turn2.history_cursor = [{"msg": "a"}, {"msg": "b"}]
    await store.save_turn("s1", user_id="u1", turn=turn2)

    tail, hist = await store.load("s1", user_id="u1")
    assert tail == 2
    assert hist == [{"msg": "a"}, {"msg": "b"}]


@pytest.mark.asyncio
async def test_in_memory_store_delete_at_or_after_rewinds_tail():
    store = InMemoryUnifiedAgentTurnStore()
    for seq in range(1, 5):  # 1..4
        await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=seq))

    await store.delete_turns_at_or_after("s1", 3, user_id="u1")

    tail, _ = await store.load("s1", user_id="u1")
    assert tail == 2
    assert await store.load_turn("s1", 3, user_id="u1") is None
    assert await store.load_turn("s1", 4, user_id="u1") is None
    assert await store.load_turn("s1", 2, user_id="u1") is not None


@pytest.mark.asyncio
async def test_in_memory_store_foreign_owner_cannot_read_or_delete():
    """Ownership check: a session owned by u1 is invisible to u2 across
    all read paths, and u2's delete is a silent no-op."""
    store = InMemoryUnifiedAgentTurnStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=1))

    # Foreign reads return empty / None — same shape as "session does
    # not exist" so existence isn't leaked.
    assert await store.load("s1", user_id="u2") == (0, [])
    assert await store.load_turn("s1", 1, user_id="u2") is None
    assert await store.load_latest("s1", user_id="u2") is None

    # Foreign delete is a no-op — original data still present for u1.
    await store.delete_turns_at_or_after("s1", 1, user_id="u2")
    assert await store.load_turn("s1", 1, user_id="u1") is not None


@pytest.mark.asyncio
async def test_in_memory_store_foreign_owner_save_is_silently_dropped():
    """A foreign user's save_turn must not overwrite or take over an
    existing session. The drop is silent — same UX as a foreign read."""
    store = InMemoryUnifiedAgentTurnStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=1))

    # u2 attempts to overwrite seq=1 with their own content.
    hijack = _make_turn(seq=1)
    hijack.user_message = "hijacked"
    await store.save_turn("s1", user_id="u2", turn=hijack)

    # u1's data unchanged.
    loaded = await store.load_turn("s1", 1, user_id="u1")
    assert loaded is not None
    assert loaded.user_message == "who won most awards?"


@pytest.mark.asyncio
async def test_in_memory_store_none_owner_cannot_be_taken_over():
    """A session first stored with user_id=None has owner=None recorded
    in the dict. A subsequent save with user_id='u' must NOT overwrite
    the owner (the previous bug: `dict.get` returned None for both
    "key absent" and "value is None", letting the second save sneak past
    the `is not None` guard)."""
    store = InMemoryUnifiedAgentTurnStore()
    # First save claims the session for None.
    await store.save_turn("s-none", user_id=None, turn=_make_turn(seq=1))

    # u tries to take over.
    hijack = _make_turn(seq=2)
    hijack.user_message = "takeover attempt"
    await store.save_turn("s-none", user_id="u", turn=hijack)

    # Original owner (None) still owns the session and sees the original
    # turn; the takeover is silently dropped.
    loaded = await store.load_turn("s-none", 1, user_id=None)
    assert loaded is not None
    assert loaded.user_message == "who won most awards?"
    assert await store.load_turn("s-none", 2, user_id=None) is None
    # The would-be takeover sees nothing.
    assert await store.load_turn("s-none", 2, user_id="u") is None


@pytest.mark.asyncio
async def test_in_memory_verify_session_access():
    """verify_session_access mirrors the read-side ownership check:
    True for new (unclaimed) sessions and for sessions owned by the
    caller; False only for foreign-owned sessions."""
    store = InMemoryUnifiedAgentTurnStore()
    # New session: anyone can claim.
    assert await store.verify_session_access("s-new", user_id="u1") is True
    assert await store.verify_session_access("s-new", user_id=None) is True

    await store.save_turn("s-claimed", user_id="u1", turn=_make_turn(seq=1))
    assert await store.verify_session_access("s-claimed", user_id="u1") is True
    assert await store.verify_session_access("s-claimed", user_id="u2") is False
    assert await store.verify_session_access("s-claimed", user_id=None) is False


@pytest.mark.asyncio
async def test_supabase_verify_session_access():
    """Supabase implementation: foreign owner → False; matching owner
    or absent session → True."""
    client_match = _FakeClient(returns={("agent_sessions", "select"): [{"tail_seq": 1, "user_id": "u1"}]})
    store_match = SupabaseUnifiedAgentTurnStore(client=client_match)
    assert await store_match.verify_session_access("s", user_id="u1") is True
    assert await store_match.verify_session_access("s", user_id="u2") is False

    client_missing = _FakeClient(returns={("agent_sessions", "select"): []})
    store_missing = SupabaseUnifiedAgentTurnStore(client=client_missing)
    assert await store_missing.verify_session_access("s", user_id="u1") is True


class _FakeQuery:
    def __init__(self, trace: list[dict], table: str, op: str, returns: dict[tuple[str, str], list]):
        self._trace = trace
        self._returns = returns
        self._entry = {"table": table, "op": op, "filters": [], "payload": None}
        self._trace.append(self._entry)

    def select(self, *cols, **_):
        self._entry["select"] = cols
        return self

    def eq(self, col, val):
        self._entry["filters"].append(("eq", col, val))
        return self

    def gte(self, col, val):
        self._entry["filters"].append(("gte", col, val))
        return self

    def order(self, col, *, desc=False):
        self._entry["order"] = (col, desc)
        return self

    def limit(self, n):
        self._entry["limit"] = n
        return self

    def execute(self):
        key = (self._entry["table"], self._entry["op"])
        return type("Res", (), {"data": self._returns.get(key, [])})()


class _FakeTable:
    def __init__(self, trace: list[dict], name: str, returns: dict[tuple[str, str], list]):
        self._trace = trace
        self._name = name
        self._returns = returns

    def select(self, *cols, **_):
        query = _FakeQuery(self._trace, self._name, "select", self._returns)
        return query.select(*cols)

    def insert(self, payload):
        query = _FakeQuery(self._trace, self._name, "insert", self._returns)
        query._entry["payload"] = payload
        return query

    def upsert(self, payload):
        query = _FakeQuery(self._trace, self._name, "upsert", self._returns)
        query._entry["payload"] = payload
        return query

    def update(self, payload):
        query = _FakeQuery(self._trace, self._name, "update", self._returns)
        query._entry["payload"] = payload
        return query

    def delete(self):
        return _FakeQuery(self._trace, self._name, "delete", self._returns)


class _FakeClient:
    def __init__(self, returns: dict[tuple[str, str], list] | None = None):
        self.trace: list[dict] = []
        self._returns = returns or {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self.trace, name, self._returns)


@pytest.mark.asyncio
async def test_supabase_store_upserts_session_then_inserts_turn():
    # New session: agent_sessions select returns empty, so save proceeds
    # without a foreign-owner check failing.
    client = _FakeClient(returns={("agent_sessions", "select"): []})
    store = SupabaseUnifiedAgentTurnStore(client=client)

    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=4))

    ops = [(entry["table"], entry["op"]) for entry in client.trace]
    # First op is the ownership-check select on agent_sessions; then
    # the upsert + insert.
    assert ops == [
        ("agent_sessions", "select"),
        ("agent_sessions", "upsert"),
        ("agent_turns", "insert"),
    ]
    assert client.trace[1]["payload"] == {"session_id": "s1", "user_id": "u1", "tail_seq": 4}
    turn_payload = client.trace[2]["payload"]
    assert turn_payload["session_id"] == "s1"
    assert turn_payload["seq"] == 4
    assert turn_payload["agent_kind"] == "statistics"
    assert turn_payload["route"] == "specialist"
    assert turn_payload["router_decision"] == {"route": "specialist", "agent_kind": "statistics"}
    assert turn_payload["domain_payload"] == {"done": {"seq": 3, "final_text": "Liz won twice."}}


@pytest.mark.asyncio
async def test_supabase_store_save_turn_dropped_for_foreign_owner():
    """Existing session owned by u1 → u2's save_turn is a no-op (no
    upsert, no insert)."""
    client = _FakeClient(
        returns={("agent_sessions", "select"): [{"tail_seq": 4, "user_id": "u1"}]},
    )
    store = SupabaseUnifiedAgentTurnStore(client=client)

    await store.save_turn("s1", user_id="u2", turn=_make_turn(seq=5))

    ops = [(entry["table"], entry["op"]) for entry in client.trace]
    assert ops == [("agent_sessions", "select")]


@pytest.mark.asyncio
async def test_supabase_store_loads_turn():
    client = _FakeClient(
        returns={
            ("agent_sessions", "select"): [{"tail_seq": 2, "user_id": "u1"}],
            ("agent_turns", "select"): [
                {
                    "seq": 2,
                    "agent_kind": "meeting",
                    "route": "specialist",
                    "user_message": "set Timer to Liz",
                    "assistant_text": "Done.",
                    "tool_trace": [{"id": "t1"}],
                    "router_decision": {"route": "specialist", "agent_kind": "meeting"},
                    "agenda_before": {"segments": []},
                    "agenda_after": {"segments": [{"id": "s1"}]},
                    "domain_payload": {"done": {"seq": 5}},
                }
            ],
        }
    )
    store = SupabaseUnifiedAgentTurnStore(client=client)

    loaded = await store.load_turn("s1", 2, user_id="u1")

    assert loaded == AgentTurnRecord(
        seq=2,
        agent_kind="meeting",
        route="specialist",
        user_message="set Timer to Liz",
        assistant_text="Done.",
        tool_trace=[{"id": "t1"}],
        router_decision={"route": "specialist", "agent_kind": "meeting"},
        agenda_before={"segments": []},
        agenda_after={"segments": [{"id": "s1"}]},
        domain_payload={"done": {"seq": 5}},
    )
    # First select is the ownership check on agent_sessions; second is
    # the actual turn fetch.
    turns_select = next(e for e in client.trace if e["table"] == "agent_turns" and e["op"] == "select")
    assert turns_select["filters"] == [("eq", "session_id", "s1"), ("eq", "seq", 2)]


@pytest.mark.asyncio
async def test_supabase_store_load_turn_foreign_owner_returns_none():
    client = _FakeClient(
        returns={("agent_sessions", "select"): [{"tail_seq": 2, "user_id": "u1"}]},
    )
    store = SupabaseUnifiedAgentTurnStore(client=client)

    # u2 querying u1's session → ownership check fails, no second query.
    assert await store.load_turn("s1", 2, user_id="u2") is None
    ops = [(entry["table"], entry["op"]) for entry in client.trace]
    assert ops == [("agent_sessions", "select")]


@pytest.mark.asyncio
async def test_supabase_store_loads_latest_turn():
    client = _FakeClient(
        returns={
            ("agent_sessions", "select"): [{"tail_seq": 7, "user_id": "u1"}],
            ("agent_turns", "select"): [
                {
                    "seq": 7,
                    "agent_kind": "router",
                    "route": "clarify",
                    "user_message": "huh?",
                    "assistant_text": "Could you clarify?",
                    "tool_trace": [],
                    "router_decision": {"route": "clarify"},
                    "agenda_before": {"segments": []},
                    "agenda_after": None,
                    "domain_payload": {"note": "ambiguous_target"},
                }
            ],
        }
    )
    store = SupabaseUnifiedAgentTurnStore(client=client)

    loaded = await store.load_latest("s1", user_id="u1")

    assert loaded is not None
    assert loaded.seq == 7
    assert loaded.domain_payload["note"] == "ambiguous_target"
    turns_select = next(e for e in client.trace if e["table"] == "agent_turns" and e["op"] == "select")
    assert turns_select["filters"] == [("eq", "session_id", "s1")]
    assert turns_select["order"] == ("seq", True)
