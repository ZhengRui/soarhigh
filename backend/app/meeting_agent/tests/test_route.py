import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from app.api.serv import app
from app.meeting_agent import agent as agent_module
from app.meeting_agent.store import InMemorySessionStore


class ForcedArgsTestModel(TestModel):
    """TestModel variant that forces deterministic args for specific tools."""

    def __init__(self, *, forced_args: dict[str, dict], **kwargs):
        super().__init__(**kwargs)
        self._forced_args = forced_args

    def gen_tool_args(self, tool_def: ToolDefinition):
        if tool_def.name in self._forced_args:
            return self._forced_args[tool_def.name]
        return super().gen_tool_args(tool_def)


def _parse_sse(byte_chunks):
    """Parse SSE byte stream into a list of {"event": ..., "data": ...} dicts."""
    buffer = b""
    events = []
    for chunk in byte_chunks:
        buffer += chunk
        while b"\n\n" in buffer:
            raw, buffer = buffer.split(b"\n\n", 1)
            lines = raw.decode("utf-8").splitlines()
            event_name = None
            data = None
            for line in lines:
                if line.startswith("event: "):
                    event_name = line[len("event: ") :]
                if line.startswith("data: "):
                    data = json.loads(line[len("data: ") :])
            if event_name:
                events.append({"event": event_name, "data": data})
    return events


@pytest.fixture
def client():
    return TestClient(app)


def test_turn_happy_path_streams_done(client, mock_auth_dep):
    body = {
        "session_id": "t1",
        "user_message": "change SAA to Joyce",
        "agenda_snapshot": {
            "meta": {"start_time": "19:15", "end_time": "21:30"},
            "segments": [
                {
                    "id": "s1",
                    "type": "SAA",
                    "start_time": "19:30",
                    "duration": 3,
                    "role_taker": "Liz",
                    "buffer_before": 0,
                }
            ],
        },
    }

    # TestModel will deterministically call set_role with plausible-looking args.
    # We force segment_id=s1 to match the snapshot we send; otherwise TestModel's
    # auto-generated "a" string triggers the tool's ValueError for unknown segment.
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Test"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", json=body) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    types = [e["event"] for e in events]
    assert "tool_call_start" in types, f"expected tool_call_start, got: {types}"
    assert "tool_call_end" in types, f"expected tool_call_end, got: {types}"
    assert types[-1] == "done", f"last event should be 'done', got: {types[-1]} (full: {types})"

    # Sanity: agenda_after in the last tool_call_end should be a dict with segments
    last_tool_end = next(e for e in reversed(events) if e["event"] == "tool_call_end")
    assert "agenda_after" in last_tool_end["data"]
    assert isinstance(last_tool_end["data"]["agenda_after"], dict)

    # Regression guard: `result` must carry the actual tool return value, not None.
    # apply_set_role returns {"segment_id": ..., "role_taker": ...}. If we
    # incorrectly read event.content instead of event.result.content, this asserts.
    assert last_tool_end["data"]["result"] is not None, (
        "tool_call_end.result was None — likely using FunctionToolResultEvent.content " "instead of .result.content"
    )
    assert last_tool_end["data"]["result"] == {
        "segment_id": "s1",
        "role_taker": "Test",
    }


@pytest.mark.asyncio
async def test_turn_persists_history_cursor_as_json_safe_payload(client, mock_auth_dep, _force_in_memory_store):
    """Regression: `history_cursor` is persisted to Supabase JSONB, which
    supabase-py serializes via json.dumps. Pydantic AI ModelMessage objects
    carry a datetime `timestamp` field; dump_python(mode="json") is what makes
    them JSON-safe. If mode="json" is forgotten, the turn would raise
    `Object of type datetime is not JSON serializable`."""
    store: InMemorySessionStore = _force_in_memory_store

    body = {
        "session_id": "persist-t1",
        "user_message": "hello",
        "agenda_snapshot": {
            "meta": {},
            "segments": [
                {
                    "id": "s1",
                    "type": "SAA",
                    "start_time": "19:30",
                    "duration": 3,
                    "role_taker": "Liz",
                    "buffer_before": 0,
                }
            ],
        },
    }
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Test"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/meeting-agent/turn", json=body) as r:
            assert r.status_code == 200
            # Drain the stream so the route's post-run save_turn() executes.
            for _ in r.iter_bytes():
                pass

    tail, history = await store.load("persist-t1")
    assert tail == 1, f"expected one turn saved, got tail={tail}"
    # The actual regression guard: json.dumps is what supabase-py does internally.
    # If any datetime slipped through, this raises TypeError.
    json.dumps(history)
    turn = await store.load_turn("persist-t1", 1)
    assert turn is not None
    json.dumps(turn.history_cursor)
    json.dumps(turn.tool_trace)
    json.dumps(turn.agenda_before)
    json.dumps(turn.agenda_after)


def test_turn_requires_auth(client):
    """Without the auth override, POST /meeting-agent/turn must reject."""
    body = {
        "session_id": "t2",
        "user_message": "hello",
        "agenda_snapshot": {
            "meta": {},
            "segments": [],
        },
    }
    r = client.post("/meeting-agent/turn", json=body)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# /meeting-agent/revert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revert_returns_agenda_before_and_deletes_later_turns(client, mock_auth_dep, _force_in_memory_store):
    """Seeding the store directly is simpler than driving N turns through the
    SSE route. This exercises just the revert endpoint."""
    from app.meeting_agent.store import TurnRecord

    store = _force_in_memory_store
    for seq in range(1, 4):  # seeds turns 1, 2, 3
        await store.save_turn(
            "rev-s1",
            user_id="test-user",
            turn=TurnRecord(
                seq=seq,
                user_message=f"msg {seq}",
                assistant_text=f"reply {seq}",
                tool_trace=[],
                agenda_before={"snapshot_taken_before": seq},
                agenda_after={"snapshot_taken_after": seq},
                history_cursor=[{"m": seq}],
            ),
        )

    r = client.post("/meeting-agent/revert", json={"session_id": "rev-s1", "target_seq": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    # Reverting to turn 2 returns the agenda as it was BEFORE turn 2 ran.
    assert body["agenda"] == {"snapshot_taken_before": 2}
    assert body["new_tail_seq"] == 1

    # Turns 2 and 3 are gone; turn 1 survives.
    assert await store.load_turn("rev-s1", 1) is not None
    assert await store.load_turn("rev-s1", 2) is None
    assert await store.load_turn("rev-s1", 3) is None
    tail, _ = await store.load("rev-s1")
    assert tail == 1


@pytest.mark.asyncio
async def test_revert_to_first_turn_rewinds_to_zero(client, mock_auth_dep, _force_in_memory_store):
    from app.meeting_agent.store import TurnRecord

    store = _force_in_memory_store
    await store.save_turn(
        "rev-s2",
        user_id="test-user",
        turn=TurnRecord(
            seq=1,
            user_message="only turn",
            assistant_text="reply",
            tool_trace=[],
            agenda_before={"initial": True},
            agenda_after={"initial": True, "after": True},
            history_cursor=[],
        ),
    )
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-s2", "target_seq": 1})
    assert r.status_code == 200, r.text
    assert r.json()["new_tail_seq"] == 0
    assert r.json()["agenda"] == {"initial": True}

    tail, _ = await store.load("rev-s2")
    assert tail == 0


def test_revert_unknown_turn_returns_404(client, mock_auth_dep):
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-none", "target_seq": 1})
    assert r.status_code == 404


def test_revert_bad_seq_returns_400(client, mock_auth_dep):
    r = client.post("/meeting-agent/revert", json={"session_id": "rev-x", "target_seq": 0})
    assert r.status_code == 400


def test_revert_requires_auth(client):
    r = client.post("/meeting-agent/revert", json={"session_id": "whatever", "target_seq": 1})
    assert r.status_code in (401, 403)
