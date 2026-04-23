import os

import pytest

from app.config import GOOGLE_API_KEY

# Skip collection entirely when the Google API key is unavailable; importing
# app.agent.agent with no key raises at Agent(...) construction time.
if not (os.environ.get("GOOGLE_API_KEY") or GOOGLE_API_KEY):
    pytest.skip("GOOGLE_API_KEY not set; skipping live agent smoke test", allow_module_level=True)

from app.agent.agent import USAGE_LIMITS, agent
from app.agent.models import Agenda, AgendaDeps, Meta, Segment


@pytest.mark.live
def test_agent_fires_set_role_for_simple_edit():
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
