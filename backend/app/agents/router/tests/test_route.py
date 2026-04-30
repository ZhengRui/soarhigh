import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

import app.agents.meeting.agent as meeting_agent_module
import app.agents.statistics.agent as stats_agent_module
from app.agents.router import store as router_store_module
from app.agents.router.store import InMemoryRouterDecisionStore
from app.agents.runtime import store as runtime_store_module
from app.agents.runtime.store import InMemoryUnifiedAgentTurnStore
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


def _turn_kwargs(body: dict) -> dict:
    """Wrap a JSON body as multipart form for the /agent/turn endpoint.

    The endpoint accepts multipart so it can receive optional images for the
    create-from-image flow; tests that send no image just put the JSON in the
    `payload` field."""
    return {"data": {"payload": json.dumps(body)}}


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
    router_store = InMemoryRouterDecisionStore()
    unified_store = InMemoryUnifiedAgentTurnStore()

    monkeypatch.setattr(router_store_module, "decision_store", router_store)
    monkeypatch.setattr(runtime_store_module, "agent_turn_store", unified_store)

    from app.api.routes.agents import meeting as meeting_route
    from app.api.routes.agents import statistics as stats_route
    from app.api.routes.agents import unified as unified_route

    monkeypatch.setattr(meeting_route, "agent_turn_store", unified_store)
    monkeypatch.setattr(stats_route, "agent_turn_store", unified_store)
    monkeypatch.setattr(unified_route, "decision_store", router_store)
    monkeypatch.setattr(unified_route, "agent_turn_store", unified_store)
    yield {"router": router_store, "unified": unified_store}


@pytest.fixture(autouse=True)
def _fake_members_directory(monkeypatch):
    monkeypatch.setattr(
        "app.db.core.get_members",
        lambda: [
            {"id": "m-joyce", "username": "joyce", "full_name": "Joyce Feng"},
            {"id": "m-liz", "username": "liz", "full_name": "Liz Huang"},
        ],
    )


@pytest.fixture(autouse=True)
def _stub_classifier(monkeypatch):
    """Deterministic classifier stub for unified-route plumbing tests.

    Real LLM behavior is covered separately by test_router_evals.py
    (live). These tests assert the route's SSE / persistence / dispatch
    given a known classifier output, so we map message keywords to
    fixed RouterDecisions instead of calling Pydantic AI.
    """
    from app.agents.runtime.contracts import AgentKind, HandoffPayload, RouteKind, RouterDecision

    async def fake(req):
        msg = (req.user_message or "").lower()
        has_agenda = req.agenda_snapshot is not None

        if "find someone" in msg or "找一个" in msg:
            return RouterDecision(
                route=RouteKind.HANDOFF,
                intent="statistics_to_meeting_handoff",
                reason="stub: cross-domain handoff",
                handoff=HandoffPayload(
                    source_agent=AgentKind.STATISTICS,
                    target_agent=AgentKind.MEETING,
                    intent="assign_role_from_stats",
                    constraints={"user_message": req.user_message or ""},
                    requires_confirmation=True,
                ),
            )

        if any(keyword in msg for keyword in ("拿奖", "best evaluator", "tte the most", "attendance", "出勤")):
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.STATISTICS,
                intent="historical_statistics_or_lookup",
                reason="stub: historical lookup",
            )

        if "set " in msg or "把 timer 改成" in msg:
            if not has_agenda:
                return RouterDecision(
                    route=RouteKind.CLARIFY,
                    intent="meeting_edit_without_agenda_snapshot",
                    reason="stub: missing agenda",
                    clarification_question=("I need the current agenda snapshot before I can edit the meeting."),
                )
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.MEETING,
                intent="current_meeting_draft",
                reason="stub: meeting edit",
            )

        return RouterDecision(
            route=RouteKind.CLARIFY,
            intent="ambiguous_agent_target",
            reason="stub: ambiguous",
            clarification_question="Edit the current draft, or look up history?",
        )

    from app.api.routes.agents import unified as unified_route

    monkeypatch.setattr(unified_route, "classify_turn", fake)


def test_unified_route_emits_router_decision_then_dispatches_to_statistics(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    stores = _force_in_memory_stores
    test_model = TestModel(call_tools=[])

    with stats_agent_module.agent.override(model=test_model):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs({"session_id": "u-stats", "user_message": "今年谁拿奖最多?"}),
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["agent_kind"] == "statistics"
    assert events[0]["data"]["decision"]["route"] == "specialist"
    assert "assistant_text" in [event["event"] for event in events]
    assert events[-1]["event"] == "done"
    unified_turn = asyncio.run(stores["unified"].load_turn("u-stats", 1))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "statistics"
    assert unified_turn.route == "specialist"
    assert unified_turn.seq == events[-1]["data"]["seq"]
    assert unified_turn.router_decision["agent_kind"] == "statistics"


def test_unified_route_emits_router_decision_then_dispatches_to_meeting(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    stores = _force_in_memory_stores
    test_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Joyce Feng"}},
    )

    with meeting_agent_module.agent.override(model=test_model):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-meeting",
                    "user_message": "set Timer to Joyce Feng",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["agent_kind"] == "meeting"
    tool_end = next(event for event in events if event["event"] == "tool_call_end")
    assert tool_end["data"]["result"] == {"segment_id": "s1", "role_taker": "Joyce Feng"}
    assert "final_agenda" in events[-1]["data"]
    unified_turn = asyncio.run(stores["unified"].load_turn("u-meeting", 1))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "meeting"
    assert unified_turn.agenda_before is not None
    assert unified_turn.agenda_before["segments"][0]["id"] == "s1"
    assert unified_turn.agenda_before["segments"][0]["role_taker"]["name"] == "Liz Huang"
    assert unified_turn.agenda_after == events[-1]["data"]["final_agenda"]
    assert unified_turn.tool_trace[0]["name"] == "set_role"


def test_unified_route_handoff_runs_statistics_then_emits_proposal(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    stores = _force_in_memory_stores
    test_model = TestModel(call_tools=[])

    with stats_agent_module.agent.override(model=test_model):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-handoff",
                    "user_message": "Find someone who has not done TTE recently and assign them to TTE",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["route"] == "handoff"
    assert "handoff_proposal" in [event["event"] for event in events]
    assert [event["event"] for event in events].count("done") == 1
    proposal = next(event for event in events if event["event"] == "handoff_proposal")
    assert proposal["data"]["source_agent"] == "statistics"
    assert proposal["data"]["target_agent"] == "meeting"
    assert proposal["data"]["requires_confirmation"] is True
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["router_only"] is True
    assert events[-1]["data"]["handoff_requires_confirmation"] is True

    unified_turn = asyncio.run(stores["unified"].load_turn("u-handoff", 1))
    assert unified_turn is not None
    assert unified_turn.route == "handoff"
    assert unified_turn.agent_kind == "router"
    assert unified_turn.agenda_before is not None
    assert unified_turn.domain_payload["handoff_proposal"]["requires_confirmation"] is True


def test_unified_route_confirmed_handoff_dispatches_to_meeting(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    stores = _force_in_memory_stores

    with stats_agent_module.agent.override(model=TestModel(call_tools=[])):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-handoff-confirm",
                    "user_message": "Find someone who has not done TTE recently and assign them to Timer",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            first_events = _parse_sse(r.iter_bytes())

    assert "handoff_proposal" in [event["event"] for event in first_events]

    meeting_model = ForcedArgsTestModel(
        call_tools=["set_role"],
        forced_args={"set_role": {"segment_id": "s1", "role_taker": "Joyce Feng"}},
    )
    with meeting_agent_module.agent.override(model=meeting_model):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-handoff-confirm",
                    "user_message": "Confirm Joyce Feng as Timer",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["agent_kind"] == "meeting"
    assert events[0]["data"]["decision"]["intent"] == "confirmed_handoff_meeting_mutation"
    tool_end = next(event for event in events if event["event"] == "tool_call_end")
    assert tool_end["data"]["result"] == {"segment_id": "s1", "role_taker": "Joyce Feng"}
    assert events[-1]["event"] == "done"
    assert "final_agenda" in events[-1]["data"]

    unified_turn = asyncio.run(stores["unified"].load_turn("u-handoff-confirm", 2))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "meeting"
    assert unified_turn.route == "specialist"
    # The audit trail for a confirmed handoff lives in router_decision.metadata.
    assert unified_turn.router_decision["metadata"]["pending_handoff"]["requires_confirmation"] is True


def test_unified_route_vague_handoff_confirmation_clarifies(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    stores = _force_in_memory_stores

    with stats_agent_module.agent.override(model=TestModel(call_tools=[])):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-handoff-vague",
                    "user_message": "Find someone who has not done TTE recently and assign them to Timer",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            _parse_sse(r.iter_bytes())

    with client.stream(
        "POST",
        "/agent/turn",
        **_turn_kwargs(
            {
                "session_id": "u-handoff-vague",
                "user_message": "yes, do it",
                "agenda_snapshot": _agenda(),
            }
        ),
    ) as r:
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    assert [event["event"] for event in events] == ["router_decision", "assistant_text", "done"]
    assert events[0]["data"]["decision"]["route"] == "clarify"
    assert events[0]["data"]["decision"]["intent"] == "handoff_confirmation_needs_details"
    unified_turn = asyncio.run(stores["unified"].load_turn("u-handoff-vague", 2))
    assert unified_turn is not None
    assert unified_turn.route == "clarify"


@pytest.mark.asyncio
async def test_unified_route_clarifies_meeting_edit_without_snapshot(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    router_store: InMemoryRouterDecisionStore = _force_in_memory_stores["router"]
    unified_store: InMemoryUnifiedAgentTurnStore = _force_in_memory_stores["unified"]

    with client.stream(
        "POST",
        "/agent/turn",
        **_turn_kwargs({"session_id": "u-clarify", "user_message": "set Timer to Joyce Feng"}),
    ) as r:
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    assert [event["event"] for event in events] == ["router_decision", "assistant_text", "done"]
    assert events[0]["data"]["decision"]["route"] == "clarify"
    assert events[-1]["data"]["router_only"] is True

    records = await router_store.load_decisions("u-clarify")
    assert len(records) == 1
    assert records[0].decision["route"] == "clarify"
    unified_turn = await unified_store.load_turn("u-clarify", 1)
    assert unified_turn is not None
    assert unified_turn.agent_kind == "router"
    assert unified_turn.route == "clarify"
    assert unified_turn.specialist_seq is None


@pytest.mark.asyncio
async def test_unified_route_handoff_without_agenda_clarifies(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    unified_store: InMemoryUnifiedAgentTurnStore = _force_in_memory_stores["unified"]

    with client.stream(
        "POST",
        "/agent/turn",
        **_turn_kwargs(
            {
                "session_id": "u-handoff-missing-agenda",
                "user_message": "Find someone who has not done TTE recently and assign them to TTE",
            }
        ),
    ) as r:
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    assert [event["event"] for event in events] == ["router_decision", "assistant_text", "done"]
    assert events[0]["data"]["decision"]["route"] == "clarify"
    assert events[-1]["data"]["router_only"] is True
    unified_turn = await unified_store.load_turn("u-handoff-missing-agenda", 1)
    assert unified_turn is not None
    assert unified_turn.route == "clarify"


def test_unified_route_requires_auth(client):
    r = client.post("/agent/turn", **_turn_kwargs({"session_id": "u-auth", "user_message": "hello"}))
    assert r.status_code in (401, 403)
