import json
from pathlib import Path

import pytest

from app.agents.meeting.models import Agenda
from app.agents.router.classifier import classify_turn
from app.models.agent import AgentTurnRequest

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


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_router_eval_cases(case: dict):
    decision = classify_turn(
        AgentTurnRequest(
            session_id=f"eval:{case['id']}",
            user_message=case["user_message"],
            agenda_snapshot=_agenda() if case["has_agenda"] else None,
        )
    )

    assert decision.route == case["expected_route"]
    assert decision.agent_kind == case["expected_agent_kind"]
    assert decision.intent == case["expected_intent"]
