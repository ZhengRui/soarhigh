import json
import os

import pytest

from app.meeting_agent.agent import USAGE_LIMITS, agent
from app.meeting_agent.models import Agenda, AgendaDeps, Meta, Segment
from app.meeting_agent.prompts import SNAPSHOT_TEMPLATE


@pytest.mark.live
def test_agent_fires_set_role_for_simple_edit():
    if os.environ.get("GOOGLE_API_KEY", "") in ("", "not-configured"):
        pytest.skip("GOOGLE_API_KEY not set; cannot run live smoke test")

    agenda = Agenda(
        meta=Meta(theme="Test", start_time="19:30"),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Liz"),
        ],
    )
    deps = AgendaDeps(agenda=agenda, session_id="smoke")

    # Mirror what the real /meeting-agent/turn route does: prepend the snapshot so the
    # model can reference segment ids verbatim instead of hallucinating them.
    prompt = SNAPSHOT_TEMPLATE.format(
        snapshot_json=json.dumps(agenda.model_dump(), ensure_ascii=False, indent=2),
        next_seq=1,
        tail_seq=0,
        user_message="Change the SAA role taker to Joyce",
    )
    agent.run_sync(prompt, deps=deps, usage_limits=USAGE_LIMITS)

    # Accept either "Joyce" alone or "Joyce Feng" or similar — the model may expand the name.
    assert "Joyce" in agenda.segments[0].role_taker
