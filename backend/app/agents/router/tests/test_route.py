import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

import app.agents.meeting.agent as meeting_agent_module
import app.agents.statistics.agent as stats_agent_module
from app.agents.meeting import store as meeting_store_module
from app.agents.meeting.store import InMemorySessionStore
from app.agents.router import store as router_store_module
from app.agents.router.store import InMemoryRouterDecisionStore
from app.agents.statistics import store as stats_store_module
from app.agents.statistics.store import InMemoryStatsSessionStore
from app.api.routes.auth import get_current_user
from app.api.serv import app
from app.models.users import User


class ForcedArgsTestModel(TestModel):
    def __init__(self, *, forced_args: dict[str, dict], **kwargs):
        super().__init__(**kwargs)
        self._forced_args = forced_args

    def gen_tool_args(self, tool_def: ToolDefinition):
        if tool_def.name in self._forced_args:
            return self._forced_args[tool_def.name]
        return super().gen_tool_args(tool_def)


def _parse_sse(byte_chunks):
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


def _agenda() -> dict:
    return {
        "meta": {"start_time": "19:15", "end_time": "21:30"},
        "segments": [
            {
                "id": "s1",
                "type": "Timer",
                "start_time": "19:30",
                "duration": 3,
                "role_taker": "Liz Huang",
                "buffer_before": 0,
            }
        ],
    }


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_auth_dep():
    app.dependency_overrides[get_current_user] = lambda: User(
        uid="test-user",
        username="test",
        full_name="Test User",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _force_in_memory_stores(monkeypatch):
    meeting_store = InMemorySessionStore()
    stats_store = InMemoryStatsSessionStore()
    router_store = InMemoryRouterDecisionStore()

    monkeypatch.setattr(meeting_store_module, "session_store", meeting_store)
    monkeypatch.setattr(stats_store_module, "session_store", stats_store)
    monkeypatch.setattr(router_store_module, "decision_store", router_store)

    from app.api.routes import agent as unified_route
    from app.api.routes import meeting_agent as meeting_route
    from app.api.routes import statistics_agent as stats_route

    monkeypatch.setattr(meeting_route, "session_store", meeting_store)
    monkeypatch.setattr(stats_route, "session_store", stats_store)
    monkeypatch.setattr(unified_route, "decision_store", router_store)
    yield router_store


@pytest.fixture(autouse=True)
def _fake_members_directory(monkeypatch):
    monkeypatch.setattr(
        "app.db.core.get_members",
        lambda: [
            {"id": "m-joyce", "username": "joyce", "full_name": "Joyce Feng"},
            {"id": "m-liz", "username": "liz", "full_name": "Liz Huang"},
        ],
    )


def test_unified_route_emits_router_decision_then_dispatches_to_statistics(client, mock_auth_dep):
    test_model = TestModel(call_tools=[])

    with stats_agent_module.agent.override(model=test_model):
        with client.stream(
            "POST",
            "/agent/turn",
            json={"session_id": "u-stats", "user_message": "今年谁拿奖最多?"},
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["agent_kind"] == "statistics"
    assert events[0]["data"]["decision"]["route"] == "specialist"
    assert "assistant_text" in [event["event"] for event in events]
    assert events[-1]["event"] == "done"


def test_unified_route_emits_router_decision_then_dispatches_to_meeting(client, mock_auth_dep):
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Joyce Feng"}},
    )

    with meeting_agent_module.agent.override(model=test_model):
        with client.stream(
            "POST",
            "/agent/turn",
            json={
                "session_id": "u-meeting",
                "user_message": "set Timer to Joyce Feng",
                "agenda_snapshot": _agenda(),
            },
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["agent_kind"] == "meeting"
    tool_end = next(event for event in events if event["event"] == "tool_call_end")
    assert tool_end["data"]["result"] == {"segment_id": "s1", "role_taker": "Joyce Feng"}
    assert "final_agenda" in events[-1]["data"]


@pytest.mark.asyncio
async def test_unified_route_clarifies_meeting_edit_without_snapshot(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    router_store: InMemoryRouterDecisionStore = _force_in_memory_stores

    with client.stream(
        "POST",
        "/agent/turn",
        json={"session_id": "u-clarify", "user_message": "set Timer to Joyce Feng"},
    ) as r:
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    assert [event["event"] for event in events] == ["router_decision", "assistant_text", "done"]
    assert events[0]["data"]["decision"]["route"] == "clarify"
    assert events[-1]["data"]["router_only"] is True

    records = await router_store.load_decisions("u-clarify")
    assert len(records) == 1
    assert records[0].decision["route"] == "clarify"


def test_unified_route_requires_auth(client):
    r = client.post("/agent/turn", json={"session_id": "u-auth", "user_message": "hello"})
    assert r.status_code in (401, 403)
