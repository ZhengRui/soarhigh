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
        specialist_seq=3,
        domain_payload={"done": {"seq": 3, "final_text": "Liz won twice."}},
    )


@pytest.mark.asyncio
async def test_in_memory_store_saves_and_loads_turn():
    store = InMemoryUnifiedAgentTurnStore()
    turn = _make_turn()

    await store.save_turn("s1", user_id="u1", turn=turn)

    loaded = await store.load_turn("s1", 1)
    assert loaded == turn
    assert await store.load_turn("s1", 99) is None


@pytest.mark.asyncio
async def test_in_memory_store_loads_latest_turn():
    store = InMemoryUnifiedAgentTurnStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=1))
    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=2))

    loaded = await store.load_latest("s1")

    assert loaded is not None
    assert loaded.seq == 2
    assert await store.load_latest("missing") is None


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


class _FakeClient:
    def __init__(self, returns: dict[tuple[str, str], list] | None = None):
        self.trace: list[dict] = []
        self._returns = returns or {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self.trace, name, self._returns)


@pytest.mark.asyncio
async def test_supabase_store_upserts_session_then_inserts_turn():
    client = _FakeClient()
    store = SupabaseUnifiedAgentTurnStore(client=client)

    await store.save_turn("s1", user_id="u1", turn=_make_turn(seq=4))

    ops = [(entry["table"], entry["op"]) for entry in client.trace]
    assert ops == [("agent_sessions", "upsert"), ("agent_turns", "insert")]
    assert client.trace[0]["payload"] == {"session_id": "s1", "user_id": "u1", "tail_seq": 4}
    turn_payload = client.trace[1]["payload"]
    assert turn_payload["session_id"] == "s1"
    assert turn_payload["seq"] == 4
    assert turn_payload["agent_kind"] == "statistics"
    assert turn_payload["route"] == "specialist"
    assert turn_payload["specialist_seq"] == 3
    assert turn_payload["router_decision"] == {"route": "specialist", "agent_kind": "statistics"}
    assert turn_payload["domain_payload"] == {"done": {"seq": 3, "final_text": "Liz won twice."}}


@pytest.mark.asyncio
async def test_supabase_store_loads_turn():
    client = _FakeClient(
        returns={
            (
                "agent_turns",
                "select",
            ): [
                {
                    "seq": 2,
                    "agent_kind": "meeting",
                    "route": "specialist",
                    "user_message": "set Timer to Liz",
                    "assistant_text": "Done.",
                    "tool_trace": [{"id": "t1"}],
                    "router_decision": {"route": "specialist", "agent_kind": "meeting"},
                    "specialist_seq": 5,
                    "agenda_before": {"segments": []},
                    "agenda_after": {"segments": [{"id": "s1"}]},
                    "domain_payload": {"done": {"seq": 5}},
                }
            ],
        }
    )
    store = SupabaseUnifiedAgentTurnStore(client=client)

    loaded = await store.load_turn("s1", 2)

    assert loaded == AgentTurnRecord(
        seq=2,
        agent_kind="meeting",
        route="specialist",
        user_message="set Timer to Liz",
        assistant_text="Done.",
        tool_trace=[{"id": "t1"}],
        router_decision={"route": "specialist", "agent_kind": "meeting"},
        specialist_seq=5,
        agenda_before={"segments": []},
        agenda_after={"segments": [{"id": "s1"}]},
        domain_payload={"done": {"seq": 5}},
    )
    assert client.trace[0]["filters"] == [("eq", "session_id", "s1"), ("eq", "seq", 2)]


@pytest.mark.asyncio
async def test_supabase_store_loads_latest_turn():
    client = _FakeClient(
        returns={
            (
                "agent_turns",
                "select",
            ): [
                {
                    "seq": 7,
                    "agent_kind": "router",
                    "route": "handoff",
                    "user_message": "assign someone",
                    "assistant_text": "Confirm details.",
                    "tool_trace": [],
                    "router_decision": {"route": "handoff"},
                    "specialist_seq": None,
                    "agenda_before": {"segments": []},
                    "agenda_after": None,
                    "domain_payload": {"handoff_proposal": {"requires_confirmation": True}},
                }
            ],
        }
    )
    store = SupabaseUnifiedAgentTurnStore(client=client)

    loaded = await store.load_latest("s1")

    assert loaded is not None
    assert loaded.seq == 7
    assert loaded.domain_payload["handoff_proposal"]["requires_confirmation"] is True
    assert client.trace[0]["filters"] == [("eq", "session_id", "s1")]
    assert client.trace[0]["order"] == ("seq", True)
