import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

import app.agents.meeting.agent as meeting_agent_module
import app.agents.statistics.agent as stats_agent_module
from app.agents.runtime import store as runtime_store_module
from app.agents.runtime.store import InMemoryUnifiedAgentTurnStore
from app.api.routes.auth import get_current_extended_user
from app.api.serv import app
from app.models.users import User


class ForcedArgsTestModel(TestModel):
    """TestModel variant for our agent route tests.

    `forced_args`: deterministic args for specific tools.

    Stock TestModel emits tool calls only when no `ModelResponse` exists
    in `messages` (see test.py:215). Real conversations always have prior
    responses in history, so a follow-up turn would skip tool calls and
    short-circuit to plain text — masking that the agent actually ran.
    Strip prior responses before the decision so tool calls fire on
    every run; harmless for tests, only affects this test fixture.
    """

    def __init__(self, *, forced_args: dict[str, dict], **kwargs):
        super().__init__(**kwargs)
        self._forced_args = forced_args

    def gen_tool_args(self, tool_def: ToolDefinition):
        if tool_def.name in self._forced_args:
            return self._forced_args[tool_def.name]
        return super().gen_tool_args(tool_def)

    def _request(self, messages, model_settings, model_request_parameters):
        # Only on the first model call of THIS run (last message is a
        # fresh UserPromptPart, not a ToolReturn): hide prior responses
        # so TestModel's tool-emission gate opens. Continuation calls
        # (after a tool return) use stock TestModel logic so the run
        # ends with a text response instead of looping on tools.
        if messages and isinstance(messages[-1], ModelRequest):
            is_fresh_user_turn = any(isinstance(p, UserPromptPart) for p in messages[-1].parts)
            if is_fresh_user_turn:
                fresh = [m for m in messages if not isinstance(m, ModelResponse)]
                return super()._request(fresh, model_settings, model_request_parameters)
        return super()._request(messages, model_settings, model_request_parameters)


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
    def fake_user():
        return User(uid="test-user", username="test", full_name="Test User")

    app.dependency_overrides[get_current_extended_user] = fake_user
    yield
    app.dependency_overrides.pop(get_current_extended_user, None)


@pytest.fixture(autouse=True)
def _force_in_memory_stores(monkeypatch):
    unified_store = InMemoryUnifiedAgentTurnStore()

    monkeypatch.setattr(runtime_store_module, "agent_turn_store", unified_store)

    from app.api.routes.agents import meeting as meeting_route
    from app.api.routes.agents import statistics as stats_route
    from app.api.routes.agents import unified as unified_route

    monkeypatch.setattr(meeting_route, "agent_turn_store", unified_store)
    monkeypatch.setattr(stats_route, "agent_turn_store", unified_store)
    monkeypatch.setattr(unified_route, "agent_turn_store", unified_store)
    yield {"unified": unified_store}


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
    from app.agents.runtime.contracts import AgentKind, RouteKind, RouterDecision

    _CANDIDATE_NAMES = ("joyce feng", "leta li", "liz huang", "frank")

    async def fake(req, *, message_history=None):
        msg = (req.user_message or "").lower()
        has_agenda = req.agenda_snapshot is not None

        # Stats lookups, including "find someone for X" patterns whose
        # ultimate goal is a follow-up assignment. The stats agent
        # surfaces candidates; the next turn (user picks) routes to
        # meeting via the candidate-name branch below.
        if "find someone" in msg or "找一个" in msg:
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.STATISTICS,
                intent="historical_statistics_or_lookup",
                reason="stub: find-and-assign → stats first",
            )

        if any(keyword in msg for keyword in ("拿奖", "best evaluator", "tte the most", "attendance", "出勤")):
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.STATISTICS,
                intent="historical_statistics_or_lookup",
                reason="stub: historical lookup",
            )

        # User picks a candidate after stats listed them: route to
        # meeting. This is the "natural cross-agent flow" — meeting
        # reads prior stats reply from session history.
        if any(name in msg for name in _CANDIDATE_NAMES) or "confirm" in msg:
            if not has_agenda:
                return RouterDecision(
                    route=RouteKind.CLARIFY,
                    intent="meeting_edit_without_agenda_snapshot",
                    reason="stub: pick without agenda",
                    clarification_question="I need the current agenda snapshot before I can edit the meeting.",
                )
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.MEETING,
                intent="current_meeting_draft",
                reason="stub: pick after stats → meeting",
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

        if "save" in msg or "保存" in msg:
            if not has_agenda:
                return RouterDecision(
                    route=RouteKind.CLARIFY,
                    intent="meeting_edit_without_agenda_snapshot",
                    reason="stub: save without agenda",
                    clarification_question="I need the current agenda snapshot.",
                )
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.MEETING,
                intent="current_meeting_draft",
                reason="stub: save → meeting",
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
    unified_turn = asyncio.run(stores["unified"].load_turn("u-stats", 1, user_id="test-user"))
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
    unified_turn = asyncio.run(stores["unified"].load_turn("u-meeting", 1, user_id="test-user"))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "meeting"
    assert unified_turn.agenda_before is not None
    assert unified_turn.agenda_before["segments"][0]["id"] == "s1"
    assert unified_turn.agenda_before["segments"][0]["role_taker"]["name"] == "Liz Huang"
    assert unified_turn.agenda_after == events[-1]["data"]["final_agenda"]
    assert unified_turn.tool_trace[0]["name"] == "set_role"


def test_unified_route_find_then_assign_routes_stats_then_meeting(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    """Natural cross-agent flow (formerly the 'handoff'): turn 1 routes
    a 'find someone for X and assign' request to stats, turn 2 routes
    the user's pick to meeting. Both turns load the same session_id
    history, so the meeting agent on turn 2 sees the stats agent's
    prior tool calls + reply naturally — no handoff machinery."""
    stores = _force_in_memory_stores

    # Turn 1: stats specialist gathers candidates.
    with stats_agent_module.agent.override(model=TestModel(call_tools=[])):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-find-assign",
                    "user_message": "Find someone who has not done TTE recently and assign them to TTE",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            events_1 = _parse_sse(r.iter_bytes())

    assert events_1[0]["data"]["decision"]["route"] == "specialist"
    assert events_1[0]["data"]["decision"]["agent_kind"] == "statistics"
    assert "handoff_proposal" not in [e["event"] for e in events_1]

    # Turn 2: user picks a candidate, routes to meeting which loads
    # the stats turn's history naturally.
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
                    "session_id": "u-find-assign",
                    "user_message": "Confirm Joyce Feng",
                    "agenda_snapshot": _agenda(),
                }
            ),
        ) as r:
            assert r.status_code == 200
            events_2 = _parse_sse(r.iter_bytes())

    assert events_2[0]["data"]["decision"]["agent_kind"] == "meeting"
    assert events_2[0]["data"]["decision"]["intent"] == "current_meeting_draft"
    tool_end = next(event for event in events_2 if event["event"] == "tool_call_end")
    assert tool_end["data"]["result"] == {"segment_id": "s1", "role_taker": "Joyce Feng"}
    assert "final_agenda" in events_2[-1]["data"]

    unified_turn = asyncio.run(stores["unified"].load_turn("u-find-assign", 2, user_id="test-user"))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "meeting"
    assert unified_turn.route == "specialist"


def test_unified_route_find_someone_without_agenda_still_routes_to_stats(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    """No agenda + 'find someone for X and assign' still routes to
    stats — stats can list candidates without needing an agenda. The
    follow-up meeting turn is what enforces the agenda-snapshot
    requirement."""
    stores = _force_in_memory_stores

    with stats_agent_module.agent.override(model=TestModel(call_tools=[])):
        with client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs(
                {
                    "session_id": "u-find-no-agenda",
                    "user_message": "Find someone who has not done TTE recently and assign them to TTE",
                }
            ),
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    assert events[0]["data"]["decision"]["route"] == "specialist"
    assert events[0]["data"]["decision"]["agent_kind"] == "statistics"
    unified_turn = asyncio.run(stores["unified"].load_turn("u-find-no-agenda", 1, user_id="test-user"))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "statistics"


@pytest.mark.asyncio
async def test_unified_route_clarifies_meeting_edit_without_snapshot(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
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

    unified_turn = await unified_store.load_turn("u-clarify", 1, user_id="test-user")
    assert unified_turn is not None
    assert unified_turn.agent_kind == "router"
    assert unified_turn.route == "clarify"


def test_unified_route_requires_auth(client):
    r = client.post("/agent/turn", **_turn_kwargs({"session_id": "u-auth", "user_message": "hello"}))
    assert r.status_code in (401, 403)


def test_unified_route_rejects_foreign_session_before_running_model(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    """A session_id owned by another user must be rejected at the route
    entry — no router LLM call, no specialist dispatch, no save attempt
    that the attacker could probe via subsequent persistence checks.
    Generic 'session_unavailable' error mirrors the shape of any
    server error, so 'foreign' / 'expired' / 'invalid' are
    indistinguishable client-side."""
    from app.agents.runtime.contracts import AgentKind, RouteKind
    from app.agents.runtime.store import AgentTurnRecord

    stores = _force_in_memory_stores
    # Pre-claim "u-foreign" for someone OTHER than test-user.
    asyncio.run(
        stores["unified"].save_turn(
            "u-foreign",
            user_id="other-user",
            turn=AgentTurnRecord(
                seq=1,
                agent_kind=AgentKind.MEETING,
                route=RouteKind.SPECIALIST,
                user_message="hello",
                assistant_text="hi",
            ),
        )
    )

    classify_calls: list = []
    from app.api.routes.agents import unified as unified_route

    original = unified_route.classify_turn

    async def counting(req, *, message_history=None):
        classify_calls.append(req.user_message)
        return await original(req, message_history=message_history)

    # Wrap the autouse stub so we can prove the router was NOT invoked.
    import contextlib

    @contextlib.contextmanager
    def _swap():
        prior = unified_route.classify_turn
        unified_route.classify_turn = counting
        try:
            yield
        finally:
            unified_route.classify_turn = prior

    with (
        _swap(),
        client.stream(
            "POST",
            "/agent/turn",
            **_turn_kwargs({"session_id": "u-foreign", "user_message": "hello"}),
        ) as r,
    ):
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    # Only one event: a generic error. Router never ran.
    assert classify_calls == []
    assert events == [
        {
            "event": "error",
            "data": {
                "reason": "session_unavailable",
                "recoverable": False,
                "message": "Session unavailable.",
            },
        }
    ]


def _turn_kwargs_with_image(body: dict, image_bytes: bytes, content_type: str = "image/jpeg") -> dict:
    """Multipart form for /agent/turn with an attached image."""
    return {
        "data": {"payload": json.dumps(body)},
        "files": {"image": ("agenda.jpg", image_bytes, content_type)},
    }


def test_meeting_route_foreign_session_with_bad_image_returns_session_unavailable_sse(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
):
    """Direct meeting route: a foreign-owned session_id + an invalid
    image (wrong content-type) must return the generic session_unavailable
    SSE — NOT an HTTP 400 from image validation. Otherwise an attacker
    could distinguish 'image rejected' (own session, bad image) from
    'session foreign' (any image) and infer ownership state."""
    from app.agents.runtime.contracts import AgentKind, RouteKind
    from app.agents.runtime.store import AgentTurnRecord

    stores = _force_in_memory_stores
    asyncio.run(
        stores["unified"].save_turn(
            "m-foreign",
            user_id="other-user",
            turn=AgentTurnRecord(
                seq=1,
                agent_kind=AgentKind.MEETING,
                route=RouteKind.SPECIALIST,
                user_message="hello",
                assistant_text="hi",
            ),
        )
    )

    # Bad content-type would normally trigger HTTP 400 from image validation.
    bad_image_files = {"image": ("x.gif", b"GIF89a", "image/gif")}
    payload = {
        "session_id": "m-foreign",
        "user_message": "save",
        "agenda_snapshot": _agenda(),
    }

    with client.stream(
        "POST",
        "/meeting-agent/turn",
        data={"payload": json.dumps(payload)},
        files=bad_image_files,
    ) as r:
        # 200 SSE with session_unavailable, NOT 400 HTTP from image validation.
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    assert events == [
        {
            "event": "error",
            "data": {
                "reason": "session_unavailable",
                "recoverable": False,
                "message": "Session unavailable.",
            },
        }
    ]


def test_unified_route_with_image_bypasses_router_and_dispatches_to_meeting(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
    monkeypatch,
):
    """Image attached → unified route skips classify_turn entirely and
    dispatches straight to the meeting agent. Without the short-circuit,
    an empty user_message + image lands at clarify because the router
    has no text to classify."""
    from app.api.routes.agents import unified as unified_route

    # Track whether classify_turn was called. The autouse _stub_classifier
    # already replaced it; wrap that with a counter.
    classify_calls: list = []
    original_fake = unified_route.classify_turn

    async def counting_fake(req, *, message_history=None):
        classify_calls.append(req.user_message)
        return await original_fake(req, message_history=message_history)

    monkeypatch.setattr(unified_route, "classify_turn", counting_fake)

    stores = _force_in_memory_stores
    test_model = ForcedArgsTestModel(
        call_tools=["create_from_image"],
        forced_args={"create_from_image": {}},
    )

    from unittest.mock import patch as mock_patch

    fake_meeting_module = "app.agents.meeting.tools.parse_meeting_agenda_image"
    fake_meeting = _fake_parsed_meeting()

    with mock_patch(fake_meeting_module, return_value=fake_meeting):
        with meeting_agent_module.agent.override(model=test_model):
            with client.stream(
                "POST",
                "/agent/turn",
                **_turn_kwargs_with_image(
                    {
                        "session_id": "u-image",
                        "user_message": "",
                        "agenda_snapshot": _agenda(),
                    },
                    image_bytes=b"fake-jpeg-bytes",
                ),
            ) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    # Router was NOT consulted — the short-circuit fired.
    assert classify_calls == []

    assert events[0]["event"] == "router_decision"
    assert events[0]["data"]["decision"]["agent_kind"] == "meeting"
    assert events[0]["data"]["decision"]["intent"] == "image_attachment_create_from_image"
    tool_start = next(event for event in events if event["event"] == "tool_call_start")
    assert tool_start["data"]["name"] == "create_from_image"

    unified_turn = asyncio.run(stores["unified"].load_turn("u-image", 1, user_id="test-user"))
    assert unified_turn is not None
    assert unified_turn.agent_kind == "meeting"
    assert unified_turn.router_decision["intent"] == "image_attachment_create_from_image"
    assert unified_turn.tool_trace[0]["name"] == "create_from_image"


@pytest.mark.asyncio
async def test_unified_route_with_image_without_agenda_clarifies(
    client,
    mock_auth_dep,
    _force_in_memory_stores,
    monkeypatch,
):
    """Image attached but no agenda_snapshot → clarify (matches the
    existing meeting_edit_without_agenda_snapshot intent)."""
    from app.api.routes.agents import unified as unified_route

    classify_calls: list = []
    original_fake = unified_route.classify_turn

    async def counting_fake(req, *, message_history=None):
        classify_calls.append(req.user_message)
        return await original_fake(req, message_history=message_history)

    monkeypatch.setattr(unified_route, "classify_turn", counting_fake)

    unified_store: InMemoryUnifiedAgentTurnStore = _force_in_memory_stores["unified"]

    with client.stream(
        "POST",
        "/agent/turn",
        **_turn_kwargs_with_image(
            {"session_id": "u-image-no-agenda", "user_message": ""},
            image_bytes=b"fake-jpeg-bytes",
        ),
    ) as r:
        assert r.status_code == 200
        events = _parse_sse(r.iter_bytes())

    # Router was NOT consulted; we still emitted a synthetic clarify.
    assert classify_calls == []

    assert [event["event"] for event in events] == ["router_decision", "assistant_text", "done"]
    assert events[0]["data"]["decision"]["route"] == "clarify"
    assert events[0]["data"]["decision"]["intent"] == "meeting_edit_without_agenda_snapshot"

    unified_turn = await unified_store.load_turn("u-image-no-agenda", 1, user_id="test-user")
    assert unified_turn is not None
    assert unified_turn.agent_kind == "router"
    assert unified_turn.route == "clarify"


def _fake_parsed_meeting():
    """Stand-in Meeting for parse_meeting_agenda_image patching. Mirrors
    the shape used by tests/test_tools.py:_fake_meeting_with_segments()."""
    from app.models.meeting import Attendee, Meeting
    from app.models.meeting import Segment as MeetingSegment

    return Meeting(
        id=None,
        no=391,
        type="Regular",
        theme="ImageTheme",
        manager=Attendee(id=None, name="Rui Zheng", member_id=""),
        date="2026-04-30",
        start_time="19:30",
        end_time="21:30",
        location="L",
        introduction="",
        status="draft",
        segments=[
            MeetingSegment(
                id="legacy-0",
                type="SAA",
                start_time="19:30",
                end_time="19:32",
                duration="2",
                role_taker=Attendee(id=None, name="Joyce Feng", member_id=""),
                title="",
                content="",
                related_segment_ids="",
            )
        ],
    )


def test_unified_route_save_draft_preview_emits_folds(client, mock_auth_dep, _force_in_memory_stores):
    """save_draft preview through unified route → meeting agent dispatch
    → tool returns preview with pending_confirmation=True → route addendum
    appends Meta/Intro/Agenda folds. End-to-end check that the chain
    correctly surfaces the save preview to the user."""
    from datetime import datetime
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    SH = ZoneInfo("Asia/Shanghai")
    fake_now = datetime(2026, 5, 1, 10, 0, tzinfo=SH)

    test_model = ForcedArgsTestModel(
        call_tools=["save_draft"],
        forced_args={"save_draft": {"confirmed": False}},
    )

    agenda_with_no = {
        "meta": {
            "no": 9999,
            "theme": "Resilience",
            "manager": "Joyce Feng",
            "date": "2026-06-01",
            "start_time": "19:30",
            "end_time": "21:30",
        },
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

    with (
        patch("app.agents.meeting.tools.now_shanghai", return_value=fake_now),
        patch("app.agents.meeting.tools.get_meeting_id_by_no", return_value=None),
    ):
        with meeting_agent_module.agent.override(model=test_model):
            with client.stream(
                "POST",
                "/agent/turn",
                **_turn_kwargs(
                    {
                        "session_id": "u-save-preview",
                        "user_message": "save the draft",
                        "agenda_snapshot": agenda_with_no,
                    }
                ),
            ) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    assert "📌 Meeting Meta" in text
    assert "📋 Agenda" in text


def test_unified_route_save_draft_refuses_past_create(client, mock_auth_dep, _force_in_memory_stores):
    """save_draft of an agenda whose start_time is already past →
    ModelRetry inside the tool → SSE tool_call_end carries status=retry."""
    from datetime import datetime
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    SH = ZoneInfo("Asia/Shanghai")
    fake_now = datetime(2026, 5, 10, 19, 31, tzinfo=SH)  # past start_time

    test_model = ForcedArgsTestModel(
        call_tools=["save_draft"],
        forced_args={"save_draft": {"confirmed": False}},
    )

    agenda_past = {
        "meta": {
            "no": 9999,
            "theme": "T",
            "manager": "M",
            "date": "2026-05-10",
            "start_time": "19:30",
            "end_time": "21:30",
        },
        "segments": [],
    }

    with (
        patch("app.agents.meeting.tools.now_shanghai", return_value=fake_now),
        patch("app.agents.meeting.tools.get_meeting_id_by_no", return_value=None),
    ):
        with meeting_agent_module.agent.override(model=test_model):
            with client.stream(
                "POST",
                "/agent/turn",
                **_turn_kwargs(
                    {
                        "session_id": "u-save-past",
                        "user_message": "save",
                        "agenda_snapshot": agenda_past,
                    }
                ),
            ) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    tool_end = next(e for e in events if e["event"] == "tool_call_end")
    assert tool_end["data"]["status"] == "retry"  # ModelRetry → retry status
