import os

import pytest

from app.agent.agent import USAGE_LIMITS, agent
from app.agent.models import Agenda, AgendaDeps, Meta, Segment


@pytest.mark.live
def test_agent_fires_set_role_for_simple_edit():
    if os.environ.get("GOOGLE_API_KEY", "") in ("", "not-configured"):
        pytest.skip("GOOGLE_API_KEY not set; cannot run live smoke test")

    agenda = Agenda(
        meta=Meta(theme="Test"),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Liz"),
        ],
    )
    deps = AgendaDeps(agenda=agenda, session_id="smoke")
    agent.run_sync(
        "Change the SAA role taker to Joyce",
        deps=deps,
        usage_limits=USAGE_LIMITS,
    )
    # Accept either "Joyce" alone or "Joyce Feng" or similar — the model may expand the name.
    assert "Joyce" in agenda.segments[0].role_taker
