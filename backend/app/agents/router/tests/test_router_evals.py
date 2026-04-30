"""LLM router regression suite.

Marked `live` because each case hits the real provider. Run with
`uv run pytest -m live` after a model / prompt change. Default CI skips
these per pyproject's `addopts = "-m 'not live'"`.
"""

import json
from pathlib import Path

import pytest

from app.agents.meeting.models import Agenda
from app.agents.router.classifier import classify_turn
from app.models.agents.unified import AgentTurnRequest

# Session-scoped loop so the module-level Pydantic AI agent's httpx client
# stays bound to one live event loop across the whole parametrized run.
# Default function-scope creates a fresh loop per test, which collides with
# the agent's reused httpx connection pool.
pytestmark = pytest.mark.asyncio(loop_scope="session")

_EVALS_PATH = Path(__file__).resolve().parents[1] / "evals" / "router_cases.json"


def _agenda() -> Agenda:
    return Agenda.model_validate(
        {
            "meta": {"start_time": "19:15", "end_time": "21:30"},
            "segments": [
                {
                    "id": "s1",
                    "type": "Timer",
                    "start_time": "19:30",
                    "duration": 3,
                    "role_taker": "",
                    "buffer_before": 0,
                }
            ],
        }
    )


def _load_cases() -> list[dict]:
    return json.loads(_EVALS_PATH.read_text(encoding="utf-8"))


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
async def test_router_eval_cases(case: dict):
    decision = await classify_turn(
        AgentTurnRequest(
            session_id=f"eval:{case['id']}",
            user_message=case["user_message"],
            agenda_snapshot=_agenda() if case["has_agenda"] else None,
        )
    )

    assert decision.route == case["expected_route"]
    assert decision.agent_kind == case["expected_agent_kind"]
    assert decision.intent == case["expected_intent"]
