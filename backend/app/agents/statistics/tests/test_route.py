import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

import app.agents.statistics.agent as stats_agent_module
from app.agents.runtime import store as store_module
from app.agents.runtime.contracts import AgentKind
from app.agents.runtime.policy import AgentPolicyError
from app.agents.runtime.store import InMemoryUnifiedAgentTurnStore
from app.api.routes.auth import get_current_extended_user
from app.api.serv import app
from app.models.users import User


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


@pytest.fixture
def mock_auth_dep():
    app.dependency_overrides[get_current_extended_user] = lambda: User(
        uid="test-user",
        username="test",
        full_name="Test User",
    )
    yield
    app.dependency_overrides.pop(get_current_extended_user, None)


@pytest.fixture(autouse=True)
def _force_in_memory_stats_store(monkeypatch):
    fake = InMemoryUnifiedAgentTurnStore()
    monkeypatch.setattr(store_module, "agent_turn_store", fake)
    from app.api.routes.agents import statistics as route_module

    monkeypatch.setattr(route_module, "agent_turn_store", fake)
    yield fake


def test_stats_preview_meeting_appends_folded_preview_blocks(client, mock_auth_dep):
    fake_full_meeting = {
        "id": "uuid-451",
        "no": 451,
        "type": "Regular",
        "manager": {"id": None, "name": "Vicky Yang", "member_id": ""},
        "theme": "Rat Race Or Lying Flat?",
        "date": "2026-04-22",
        "start_time": "19:15",
        "end_time": "21:35",
        "location": "Loc",
        "introduction": "Finding a comfortable life balance.",
        "segments": [
            {
                "id": "1",
                "type": "Meeting Rules Introduction (SAA)",
                "start_time": "19:30",
                "duration": "2",
                # Liz is a club member; her DB segments carry a real
                # `member_id`. The renderer trusts that (DB-authoritative)
                # over the static CLUB_MEMBERS list — verifying the Phase A
                # bugfix flow end-to-end through the stats route.
                "role_taker": {"id": "att-liz", "name": "Liz Huang", "member_id": "m-liz"},
            },
        ],
    }
    test_model = ForcedArgsTestModel(
        call_tools=["preview_meeting"],
        forced_args={"preview_meeting": {"no": 451}},
    )

    with (
        patch("app.services.meeting_lookup.fetch_meeting_full", return_value=fake_full_meeting),
        patch("app.api.routes.agents.statistics.require_tool_allowed") as policy_check,
    ):
        with stats_agent_module.agent.override(model=test_model):
            with client.stream(
                "POST",
                "/statistics-agent/turn",
                json={"session_id": "stats-preview", "user_message": "查看 #451"},
            ) as r:
                assert r.status_code == 200
                events = _parse_sse(r.iter_bytes())

    text = "".join(e["data"]["chunk"] for e in events if e["event"] == "assistant_text")
    assert "<summary>📌 Meeting #451 Meta</summary>" in text
    assert "<summary>📝 Meeting #451 Introduction</summary>" in text
    assert "Finding a comfortable life balance." in text
    assert "<summary>📋 Meeting #451 Agenda</summary>" in text
    assert "| Meeting No. | 451 |" in text
    assert "Liz Huang (member)" in text
    policy_check.assert_called_once_with(AgentKind.STATISTICS, "preview_meeting")


def test_stats_route_fails_closed_when_registered_tool_blocked_by_policy(client, mock_auth_dep):
    """Configuration-mistake guard: a tool that's REGISTERED on the agent
    but rejected by policy must fail closed (raise → SSE error). The
    startup test should catch this in CI, but if CI is bypassed we still
    refuse to run the disallowed tool."""
    test_model = ForcedArgsTestModel(
        call_tools=["preview_meeting"],
        forced_args={"preview_meeting": {"no": 451}},
    )

    with (
        patch(
            "app.api.routes.agents.statistics.require_tool_allowed",
            side_effect=AgentPolicyError("blocked by policy"),
        ),
        stats_agent_module.agent.override(model=test_model),
    ):
        with client.stream(
            "POST",
            "/statistics-agent/turn",
            json={"session_id": "stats-policy", "user_message": "查看 #451"},
        ) as r:
            assert r.status_code == 200
            events = _parse_sse(r.iter_bytes())

    # Registered+rejected → outer except handler converts to an error event.
    assert events[-1]["event"] == "error"
    assert "blocked by policy" in events[-1]["data"]["message"]


def test_statistics_turn_rejects_wechat_user():
    """Mock get_current_extended_user to return a WeChatUser; expect 403
    with the require_member gate's exact detail message.

    Intentionally does NOT request the auth fixture — that fixture
    overrides the dep with a bound User. This test needs a WeChatUser
    instead, so it installs its own override and cleans up in finally.
    """
    from app.api.routes.agents import statistics as statistics_route
    from app.models.wechat_user import WeChatUser

    def fake_dep():
        return WeChatUser(wxid="wx-1", attendee_id=None)

    app.dependency_overrides[statistics_route.get_current_extended_user] = fake_dep
    try:
        local_client = TestClient(app)
        # /statistics-agent/turn accepts a typed JSON body
        # (StatisticsAgentTurnRequest) — not multipart/form. Sending JSON
        # is the right shape; payload doesn't carry agenda_snapshot since
        # the statistics agent is read-only.
        r = local_client.post(
            "/statistics-agent/turn",
            json={
                "session_id": "s1",
                "user_message": "hi",
            },
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "Agent access requires a bound club member account."
    finally:
        app.dependency_overrides.clear()
