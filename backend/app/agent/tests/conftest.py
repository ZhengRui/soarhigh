import pytest

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
