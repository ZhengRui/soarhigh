import pytest

from app.agents.runtime import store as store_module
from app.agents.runtime.store import InMemoryUnifiedAgentTurnStore
from app.api.routes.auth import get_current_user
from app.api.serv import app
from app.models.users import User


@pytest.fixture
def mock_auth_dep():
    """Override the JWT auth dep so tests don't need a real token."""
    app.dependency_overrides[get_current_user] = lambda: User(
        uid="test-user",
        username="test",
        full_name="Test User",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def _force_in_memory_store(monkeypatch):
    """Route tests must not hit Supabase. Swap the unified store singleton for
    a fresh InMemory one. The route imports `agent_turn_store` by name at
    module import time, so we patch both the runtime module and the route's
    namespace."""
    fake = InMemoryUnifiedAgentTurnStore()
    monkeypatch.setattr(store_module, "agent_turn_store", fake)
    from app.api.routes.agents import meeting as route_module

    monkeypatch.setattr(route_module, "agent_turn_store", fake)
    yield fake


@pytest.fixture(autouse=True)
def _fake_members_directory(monkeypatch):
    """Meeting-agent route tests should not hit Supabase for member lookup."""

    monkeypatch.setattr(
        "app.db.core.get_members",
        lambda: [
            {"id": "m-rui", "username": "rui", "full_name": "Rui Zheng"},
            {"id": "m-joyce", "username": "joyce", "full_name": "Joyce Feng"},
            {"id": "m-liz", "username": "liz", "full_name": "Liz Huang"},
            {"id": "m-amy", "username": "amy", "full_name": "Amy Fang"},
        ],
    )
