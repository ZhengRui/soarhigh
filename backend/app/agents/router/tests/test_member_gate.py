import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.agents._shared import require_member
from app.api.serv import app
from app.models.users import User
from app.models.wechat_user import WeChatUser


def test_require_member_accepts_user_with_uid():
    u = User(uid="abc-123", username="x", full_name="X")
    assert require_member(u).uid == "abc-123"


def test_require_member_rejects_wechat_user():
    u = WeChatUser(wxid="wx-1", attendee_id=None)
    with pytest.raises(HTTPException) as exc:
        require_member(u)
    assert exc.value.status_code == 403


def test_require_member_rejects_user_without_uid():
    u = User(uid="", username="x", full_name="X")
    with pytest.raises(HTTPException) as exc:
        require_member(u)
    assert exc.value.status_code == 403


def test_agent_turn_rejects_wechat_user(monkeypatch):
    """Mock get_current_extended_user to return a WeChatUser; expect 403."""
    from app.api.routes.agents import unified

    def fake_dep():
        return WeChatUser(wxid="wx-1", attendee_id=None)

    app.dependency_overrides[unified.get_current_extended_user] = fake_dep
    try:
        client = TestClient(app)
        # /agent/turn is multipart/form-data — payload is a JSON string in
        # the `payload` form field. Sending JSON body would 422 (body
        # parse error), hiding the 403 we want to verify.
        r = client.post(
            "/agent/turn",
            data={
                "payload": json.dumps(
                    {
                        "session_id": "s1",
                        "user_message": "hi",
                        "agenda_snapshot": {"meta": {}, "segments": []},
                    }
                ),
            },
        )
        assert r.status_code == 403
        # Pin the exact `detail` so a future regression that 403s for a
        # different reason (e.g. someone reverts to get_current_user, the
        # WeChatUser fake_dep never fires, but auth still rejects) doesn't
        # silently pass this test.
        assert r.json()["detail"] == "Agent access requires a bound club member account."
    finally:
        app.dependency_overrides.clear()
