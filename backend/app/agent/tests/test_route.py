import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from app.agent import agent as agent_module
from app.api.serv import app


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
        forced_args={"set_role": {"segment_id": "s1", "new_role_taker": "Test"}},
    )
    with agent_module.agent.override(model=test_model):
        with client.stream("POST", "/agent/turn", json=body) as r:
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


def test_turn_requires_auth(client):
    """Without the auth override, POST /agent/turn must reject."""
    body = {
        "session_id": "t2",
        "user_message": "hello",
        "agenda_snapshot": {
            "meta": {},
            "segments": [],
        },
    }
    r = client.post("/agent/turn", json=body)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"
