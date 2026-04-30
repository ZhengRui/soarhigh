import pytest
from pydantic import ValidationError

from app.agents.runtime.contracts import AgentKind, RouteKind, RouterDecision
from app.agents.runtime.envelopes import ToolResultEnvelope, normalize_tool_result


def test_tool_result_envelope_accepts_existing_stats_shape():
    envelope = normalize_tool_result(
        {
            "value": {
                "groups": [],
                "references": [{"meeting_id": "m1", "role_key": "TTE"}],
            },
            "scope": {"date_from": "2026-01-01", "date_to": "2026-04-29"},
            "coverage": {"status": "complete", "source": "dashboard_member_role_matrix"},
            "scanned_count": 1,
        }
    )

    assert isinstance(envelope, ToolResultEnvelope)
    assert envelope.coverage is not None
    assert envelope.coverage.status == "complete"
    assert envelope.references == [{"meeting_id": "m1", "role_key": "TTE"}]
    assert envelope.requires_confirmation is False


def test_router_decision_serializes_specialist_route():
    decision = RouterDecision(
        route=RouteKind.SPECIALIST,
        agent_kind=AgentKind.STATISTICS,
        intent="award_count",
        reason="Historical award count question.",
        confidence=0.86,
    )

    dumped = decision.model_dump(mode="json")
    assert dumped["route"] == "specialist"
    assert dumped["agent_kind"] == "statistics"
    assert dumped["confidence"] == 0.86


def test_router_decision_requires_clarification_question():
    with pytest.raises(ValidationError, match="clarification_question"):
        RouterDecision(
            route=RouteKind.CLARIFY,
            intent="ambiguous_current_vs_historical_meeting",
            reason="The user said 'that meeting' without a current or historical anchor.",
        )
