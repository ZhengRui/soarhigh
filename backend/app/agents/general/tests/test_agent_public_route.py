import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

import app.agents.general.agent_public as agent_public_module
from app.agents.runtime.history import _SKILL_BODY_PLACEHOLDER
from app.agents.runtime.store_public import InMemoryAgentTurnStorePublic
from app.api.routes.agents import agent_public as route_module
from app.api.routes.agents import identity_public as identity_module
from app.api.serv import app
from app.models.users import User
from app.models.wechat_user import WeChatUser


class ForcedArgsTestModel(TestModel):
    def __init__(self, *, forced_args: dict[str, dict], **kwargs):
        super().__init__(**kwargs)
        self._forced_args = forced_args

    def gen_tool_args(self, tool_def: ToolDefinition):
        if tool_def.name in self._forced_args:
            return self._forced_args[tool_def.name]
        return super().gen_tool_args(tool_def)


class _NoopRateLimiter:
    async def check(self, *_args, **_kwargs):
        return None

    async def release(self, **_kwargs):
        return None


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


@pytest.fixture(autouse=True)
def _public_route_fakes(monkeypatch):
    store = InMemoryAgentTurnStorePublic()
    monkeypatch.setattr(route_module, "agent_turn_store_public", store)
    monkeypatch.setattr(route_module, "rate_limiter_public", _NoopRateLimiter())
    yield store


def _override_user(user):
    app.dependency_overrides[route_module.get_optional_extended_user] = lambda: user


def _clear_overrides():
    app.dependency_overrides.pop(route_module.get_optional_extended_user, None)


def test_agent_public_rejects_bound_member(client):
    _override_user(User(uid="u1", username="u", full_name="User"))
    try:
        res = client.post(
            "/agent-public/turn",
            json={"session_id": "agent-public:web:member-test", "user_message": "hi"},
        )
    finally:
        _clear_overrides()

    assert res.status_code == 403
    assert "Bound members" in res.json()["detail"]


def test_agent_public_rejects_invalid_session_id_before_stream(client):
    res = client.post(
        "/agent-public/turn",
        json={"session_id": "member-session", "user_message": "hi"},
    )

    assert res.status_code == 422


def test_agent_public_rejects_oversized_message_before_stream(client):
    res = client.post(
        "/agent-public/turn",
        json={
            "session_id": "agent-public:web:oversized-message",
            "user_message": "x" * 4001,
        },
    )

    assert res.status_code == 422


def test_agent_public_guest_streams_and_saves_compact_skill_trace(client, _public_route_fakes):
    store = _public_route_fakes
    _override_user(WeChatUser(wxid="wx-public", attendee_id=None))
    test_model = ForcedArgsTestModel(
        call_tools=["view_skill_public"],
        forced_args={"view_skill_public": {"name": "toastmasters-roles"}},
    )

    try:
        with agent_public_module.agent_public.override(model=test_model):
            with client.stream(
                "POST",
                "/agent-public/turn",
                json={"session_id": "agent-public:miniapp:test", "user_message": "TT 是什么?"},
            ) as res:
                assert res.status_code == 200
                events = _parse_sse(res.iter_bytes())
    finally:
        _clear_overrides()

    assert events[0]["event"] != "router_decision"
    tool_start = next(e for e in events if e["event"] == "tool_call_start")
    assert tool_start["data"]["name"] == "view_skill_public"
    tool_end = next(e for e in events if e["event"] == "tool_call_end")
    assert tool_end["data"]["result"]["skill"] == "toastmasters-roles"
    assert isinstance(tool_end["data"]["result"]["body_length"], int)
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["sources"] == ["toastmasters-roles"]

    turn = asyncio.run(
        store.load_turn(
            "agent-public:miniapp:test",
            1,
            channel="miniapp",
            visitor_key="wx-public",
        )
    )
    assert turn is not None
    assert turn.agent_kind == "general"
    assert turn.domain_payload["skill_sources"] == ["toastmasters-roles"]
    assert turn.tool_trace[0]["result"]["skill"] == "toastmasters-roles"

    skill_returns = [
        part
        for msg in turn.history_cursor
        for part in msg.get("parts", [])
        if part.get("part_kind") == "tool-return" and part.get("tool_name") == "view_skill_public"
    ]
    assert skill_returns
    assert all(part["content"] == _SKILL_BODY_PLACEHOLDER for part in skill_returns)


def test_agent_public_session_is_owned_by_wxid(client, _public_route_fakes):
    store = _public_route_fakes
    _override_user(WeChatUser(wxid="wx-owner", attendee_id=None))
    test_model = TestModel(call_tools=[])

    try:
        with agent_public_module.agent_public.override(model=test_model):
            with client.stream(
                "POST",
                "/agent-public/turn",
                json={"session_id": "agent-public:miniapp:owned", "user_message": "hello"},
            ) as res:
                assert res.status_code == 200
                _parse_sse(res.iter_bytes())
    finally:
        _clear_overrides()

    assert asyncio.run(
        store.verify_session_access(
            "agent-public:miniapp:owned",
            channel="miniapp",
            visitor_key="wx-owner",
        )
    )
    assert not asyncio.run(
        store.verify_session_access(
            "agent-public:miniapp:owned",
            channel="miniapp",
            visitor_key="wx-other",
        )
    )

    _override_user(WeChatUser(wxid="wx-other", attendee_id=None))
    try:
        res = client.post(
            "/agent-public/turn",
            json={"session_id": "agent-public:miniapp:owned", "user_message": "hi"},
        )
    finally:
        _clear_overrides()

    assert res.status_code == 200
    events = _parse_sse([res.content])
    assert events[0]["event"] == "error"
    assert events[0]["data"]["reason"] == "session_unavailable"


def test_agent_public_web_visitor_cookie_streams(_public_route_fakes):
    store = _public_route_fakes
    secure_client = TestClient(app, base_url="https://testserver")

    visitor_res = secure_client.post("/agent-public/visitor")
    assert visitor_res.status_code == 200
    visitor_id = visitor_res.json()["visitor_id"]
    assert visitor_id

    test_model = TestModel(call_tools=[])
    with agent_public_module.agent_public.override(model=test_model):
        with secure_client.stream(
            "POST",
            "/agent-public/turn",
            json={"session_id": "agent-public:web:test", "user_message": "hello"},
        ) as res:
            assert res.status_code == 200
            events = _parse_sse(res.iter_bytes())

    assert events[-1]["event"] == "done"
    turn = asyncio.run(
        store.load_turn(
            "agent-public:web:test",
            1,
            channel="web",
            visitor_key=visitor_id,
        )
    )
    assert turn is not None


def test_agent_public_visitor_cookie_secure_flag_is_configurable(monkeypatch):
    monkeypatch.setattr(identity_module, "AGENT_PUBLIC_COOKIE_SECURE", False)
    client = TestClient(app, base_url="http://testserver")

    res = client.post("/agent-public/visitor")

    assert res.status_code == 200
    assert "secure" not in res.headers["set-cookie"].lower()
