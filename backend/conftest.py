"""Global test guard: block real Supabase access from non-live tests.

The suite runs with the production service-role key loaded from .env, and
database isolation used to be convention only (every test stubs the db-layer
functions it touches). One missed stub during the 2026-08 publication work
silently inserted a fixture row into the production wxposts table. This
autouse fixture turns a forgotten stub into a loud test failure: any call
that would reach Supabase raises unless the test is marked ``live``.
"""

from __future__ import annotations

import pytest

import app.db.core as db_core
import app.db.supabase as db_supabase


class ProductionAccessBlocked(RuntimeError):
    """A non-live test tried to reach the real Supabase database."""


def _blocked(*args: object, **kwargs: object) -> None:
    raise ProductionAccessBlocked(
        "Test attempted real Supabase access. Stub the db-layer function it "
        "calls (monkeypatch), or mark the test with @pytest.mark.live."
    )


@pytest.fixture(autouse=True)
def _block_supabase(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("live"):
        return
    # Patch the client class, not the shared instance: every module holds a
    # reference to the same object, and user clients minted per-request share
    # the class, so this covers all of them in one place.
    client_type = type(db_supabase.supabase)
    monkeypatch.setattr(client_type, "table", _blocked)
    monkeypatch.setattr(client_type, "rpc", _blocked)
    # create_user_client builds a fresh (blocked-anyway) client and performs
    # network auth setup; block it at both import sites.
    monkeypatch.setattr(db_supabase, "create_user_client", _blocked)
    monkeypatch.setattr(db_core, "create_user_client", _blocked)
