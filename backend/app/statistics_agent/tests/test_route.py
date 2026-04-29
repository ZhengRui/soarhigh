import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

import app.statistics_agent.agent as stats_agent_module
from app.api.routes.auth import get_current_user
from app.api.serv import app
from app.models.users import User
from app.statistics_agent import store as store_module
from app.statistics_agent.store import InMemoryStatsSessionStore


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
    app.dependency_overrides[get_current_user] = lambda: User(
        uid="test-user",
        username="test",
        full_name="Test User",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _force_in_memory_stats_store(monkeypatch):
    fake = InMemoryStatsSessionStore()
    monkeypatch.setattr(store_module, "session_store", fake)
    from app.api.routes import statistics_agent as route_module

    monkeypatch.setattr(route_module, "session_store", fake)
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

    with patch("app.services.meeting_lookup.fetch_meeting_full", return_value=fake_full_meeting):
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
