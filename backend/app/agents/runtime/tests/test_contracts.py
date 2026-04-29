import pytest
from pydantic import ValidationError

from app.agents.runtime.contracts import AgentKind, HandoffPayload, RouteKind, RouterDecision
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


def test_router_decision_requires_handoff_payload_for_handoff_route():
    with pytest.raises(ValidationError, match="handoff payload"):
        RouterDecision(
            route=RouteKind.HANDOFF,
            intent="assign_role_from_stats",
            reason="The user asked for historical candidates and a draft assignment.",
        )


def test_handoff_payload_requires_distinct_specialists():
    with pytest.raises(ValidationError, match="must be different"):
        HandoffPayload(
            source_agent=AgentKind.STATISTICS,
            target_agent=AgentKind.STATISTICS,
            intent="member_role_candidates",
        )

    with pytest.raises(ValidationError, match="specialist agents"):
        HandoffPayload(
            source_agent=AgentKind.ROUTER,
            target_agent=AgentKind.MEETING,
            intent="assign_role_from_stats",
        )
