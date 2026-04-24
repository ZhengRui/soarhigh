import pytest

from app.meeting_agent.store import InMemorySessionStore, TurnRecord


def _make_turn(seq: int, user_message: str = "m", history: list | None = None) -> TurnRecord:
    return TurnRecord(
        seq=seq,
        user_message=user_message,
        assistant_text=f"reply {seq}",
        tool_trace=[],
        agenda_before={"before": seq},
        agenda_after={"after": seq},
        history_cursor=history if history is not None else [{"msg": seq}],
    )


@pytest.mark.asyncio
async def test_empty_session_returns_default():
    store = InMemorySessionStore()
    assert await store.load("nope") == (0, [])


@pytest.mark.asyncio
async def test_save_turn_and_load_returns_latest_history():
    store = InMemorySessionStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(1, history=[{"msg": "a"}]))
    await store.save_turn("s1", user_id="u1", turn=_make_turn(2, history=[{"msg": "a"}, {"msg": "b"}]))
    tail, hist = await store.load("s1")
    assert tail == 2
    assert hist == [{"msg": "a"}, {"msg": "b"}]


@pytest.mark.asyncio
async def test_load_turn_retrieves_specific_seq():
    store = InMemorySessionStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(1, user_message="hi"))
    await store.save_turn("s1", user_id="u1", turn=_make_turn(2, user_message="bye"))

    t1 = await store.load_turn("s1", 1)
    t2 = await store.load_turn("s1", 2)
    assert t1 is not None and t1.user_message == "hi"
    assert t2 is not None and t2.user_message == "bye"
    assert await store.load_turn("s1", 999) is None
    assert await store.load_turn("nope", 1) is None


@pytest.mark.asyncio
async def test_delete_turns_at_or_after_rewinds_tail():
    store = InMemorySessionStore()
    for seq in range(1, 5):  # 1..4
        await store.save_turn("s1", user_id="u1", turn=_make_turn(seq))
    await store.delete_turns_at_or_after("s1", 3)

    tail, _ = await store.load("s1")
    assert tail == 2, "tail_seq should rewind to the highest surviving turn"
    assert await store.load_turn("s1", 3) is None
    assert await store.load_turn("s1", 4) is None
    assert (await store.load_turn("s1", 2)) is not None


@pytest.mark.asyncio
async def test_delete_all_rewinds_to_zero():
    store = InMemorySessionStore()
    await store.save_turn("s1", user_id="u1", turn=_make_turn(1))
    await store.save_turn("s1", user_id="u1", turn=_make_turn(2))
    await store.delete_turns_at_or_after("s1", 1)
    tail, hist = await store.load("s1")
    assert tail == 0
    assert hist == []


@pytest.mark.asyncio
async def test_sessions_are_isolated():
    store = InMemorySessionStore()
    await store.save_turn("sA", user_id="u1", turn=_make_turn(1, history=[{"a": 1}]))
    await store.save_turn("sB", user_id="u2", turn=_make_turn(5, history=[{"b": 9}]))
    assert await store.load("sA") == (1, [{"a": 1}])
    assert await store.load("sB") == (5, [{"b": 9}])


# SupabaseSessionStore tests use a fake client to verify the calls we make
# against the supabase-py fluent API, without a real network round-trip.


class _FakeQuery:
    """Records fluent-chain calls and returns canned data on execute()."""

    def __init__(self, trace: list[dict], table: str, op: str):
        self._trace = trace
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

    def limit(self, n):
        self._entry["limit"] = n
        return self

    def execute(self):
        data = self._entry.pop("_return", [])
        return type("Res", (), {"data": data})()


class _FakeTable:
    def __init__(self, trace: list[dict], name: str):
        self._trace = trace
        self._name = name

    def select(self, *cols, **_):
        q = _FakeQuery(self._trace, self._name, "select")
        return q.select(*cols)

    def insert(self, payload):
        q = _FakeQuery(self._trace, self._name, "insert")
        q._entry["payload"] = payload
        return q

    def upsert(self, payload):
        q = _FakeQuery(self._trace, self._name, "upsert")
        q._entry["payload"] = payload
        return q

    def update(self, payload):
        q = _FakeQuery(self._trace, self._name, "update")
        q._entry["payload"] = payload
        return q

    def delete(self):
        return _FakeQuery(self._trace, self._name, "delete")


class FakeSupabaseClient:
    """Minimal stand-in for the supabase-py Client.

    Pre-seed `returns` keyed by (table, op) with the list to yield from
    execute(); anything unseeded returns empty data.
    """

    def __init__(self, returns: dict[tuple[str, str], list] | None = None):
        self.trace: list[dict] = []
        self._returns = returns or {}

    def table(self, name: str) -> _FakeTable:
        # Install canned return on the next execute() via a pop-trick: we
        # attach _return to the query entry just before execute runs. Simpler:
        # patch _FakeQuery.execute to consult self._returns.
        fake = _FakeTable(self.trace, name)
        fake._returns = self._returns  # type: ignore[attr-defined]
        return fake


def _patch_returns(client: FakeSupabaseClient):
    """After FakeSupabaseClient-driven calls run, back-fill canned `data` via
    a monkeypatch on _FakeQuery.execute. Kept as a helper so each test can
    declare returns concisely."""
    originals = _FakeQuery.execute

    def execute(self):
        key = (self._entry["table"], self._entry["op"])
        data = client._returns.get(key, [])
        return type("Res", (), {"data": data})()

    _FakeQuery.execute = execute  # type: ignore[method-assign]
    return originals


@pytest.mark.asyncio
async def test_supabase_load_missing_session_returns_default(monkeypatch):
    from app.meeting_agent.store import SupabaseSessionStore

    client = FakeSupabaseClient(returns={})
    original_execute = _patch_returns(client)
    try:
        store = SupabaseSessionStore(client=client)
        assert await store.load("missing") == (0, [])
    finally:
        _FakeQuery.execute = original_execute  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_supabase_load_reads_history_from_latest_turn(monkeypatch):
    from app.meeting_agent.store import SupabaseSessionStore

    client = FakeSupabaseClient(
        returns={
            ("meeting_agent_sessions", "select"): [{"tail_seq": 3}],
            ("meeting_agent_turns", "select"): [{"history_cursor": [{"msg": "hello"}]}],
        }
    )
    original_execute = _patch_returns(client)
    try:
        store = SupabaseSessionStore(client=client)
        tail, hist = await store.load("s1")
        assert tail == 3
        assert hist == [{"msg": "hello"}]
    finally:
        _FakeQuery.execute = original_execute  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_supabase_save_turn_upserts_session_then_inserts_turn(monkeypatch):
    from app.meeting_agent.store import SupabaseSessionStore

    client = FakeSupabaseClient()
    original_execute = _patch_returns(client)
    try:
        store = SupabaseSessionStore(client=client)
        turn = TurnRecord(
            seq=4,
            user_message="set timer",
            assistant_text="ok",
            tool_trace=[{"id": "t1", "name": "set_role", "status": "ok"}],
            agenda_before={"segments": []},
            agenda_after={"segments": ["x"]},
            history_cursor=[{"m": 1}],
        )
        await store.save_turn("s1", user_id="u1", turn=turn)

        ops = [(e["table"], e["op"]) for e in client.trace]
        assert ops == [
            ("meeting_agent_sessions", "upsert"),
            ("meeting_agent_turns", "insert"),
        ]
        sess_payload = client.trace[0]["payload"]
        assert sess_payload == {"session_id": "s1", "user_id": "u1", "tail_seq": 4}
        turn_payload = client.trace[1]["payload"]
        assert turn_payload["session_id"] == "s1"
        assert turn_payload["seq"] == 4
        assert turn_payload["user_message"] == "set timer"
        assert turn_payload["tool_trace"] == [{"id": "t1", "name": "set_role", "status": "ok"}]
        assert turn_payload["agenda_before"] == {"segments": []}
        assert turn_payload["agenda_after"] == {"segments": ["x"]}
        assert turn_payload["history_cursor"] == [{"m": 1}]
    finally:
        _FakeQuery.execute = original_execute  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_supabase_delete_turns_deletes_then_rewinds_tail(monkeypatch):
    from app.meeting_agent.store import SupabaseSessionStore

    client = FakeSupabaseClient()
    original_execute = _patch_returns(client)
    try:
        store = SupabaseSessionStore(client=client)
        await store.delete_turns_at_or_after("s1", 3)

        ops = [(e["table"], e["op"]) for e in client.trace]
        assert ops == [
            ("meeting_agent_turns", "delete"),
            ("meeting_agent_sessions", "update"),
        ]
        # The delete query must filter on session_id and seq >= target.
        delete_filters = client.trace[0]["filters"]
        assert ("eq", "session_id", "s1") in delete_filters
        assert ("gte", "seq", 3) in delete_filters
        # tail_seq rewinds to seq-1 (min 0).
        assert client.trace[1]["payload"] == {"tail_seq": 2}
    finally:
        _FakeQuery.execute = original_execute  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_supabase_delete_rewinds_to_zero_for_seq_1(monkeypatch):
    from app.meeting_agent.store import SupabaseSessionStore

    client = FakeSupabaseClient()
    original_execute = _patch_returns(client)
    try:
        store = SupabaseSessionStore(client=client)
        await store.delete_turns_at_or_after("s1", 1)
        assert client.trace[1]["payload"] == {"tail_seq": 0}
    finally:
        _FakeQuery.execute = original_execute  # type: ignore[method-assign]
