"""Unit tests for the classifier's server-side post-processing.

Live LLM behavior is covered in test_router_evals.py (marked
@pytest.mark.live). These tests assert the deterministic mapping from
LLM choice → RouterDecision, including the agenda-snapshot guard and
HandoffPayload construction.
"""

from app.agents.router.classifier import _RouterChoice, _to_decision
from app.agents.runtime.contracts import AgentKind, RouteKind


def test_specialist_meeting_with_agenda_routes_to_meeting():
    decision = _to_decision(
        _RouterChoice(route="specialist_meeting", reason="edit current draft"),
        user_message="set Timer to Joyce",
        has_agenda=True,
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.MEETING
    assert decision.intent == "current_meeting_draft"


def test_specialist_meeting_without_agenda_clarifies():
    decision = _to_decision(
        _RouterChoice(route="specialist_meeting", reason="edit current draft"),
        user_message="set Timer to Joyce",
        has_agenda=False,
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.intent == "meeting_edit_without_agenda_snapshot"
    assert decision.clarification_question


def test_specialist_statistics_routes_to_stats():
    decision = _to_decision(
        _RouterChoice(route="specialist_statistics", reason="historical lookup"),
        user_message="who won Best Evaluator this year?",
        has_agenda=False,
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.STATISTICS
    assert decision.intent == "historical_statistics_or_lookup"


def test_handoff_builds_payload_with_user_message_constraint():
    decision = _to_decision(
        _RouterChoice(route="handoff_stats_to_meeting", reason="cross-domain"),
        user_message="assign someone who hasn't done TTE",
        has_agenda=True,
    )

    assert decision.route == RouteKind.HANDOFF
    assert decision.intent == "statistics_to_meeting_handoff"
    assert decision.handoff is not None
    assert decision.handoff.source_agent == AgentKind.STATISTICS
    assert decision.handoff.target_agent == AgentKind.MEETING
    assert decision.handoff.intent == "assign_role_from_stats"
    assert decision.handoff.requires_confirmation is True
    assert decision.handoff.constraints == {"user_message": "assign someone who hasn't done TTE"}


def test_clarify_uses_llm_question_when_provided():
    decision = _to_decision(
        _RouterChoice(
            route="clarify",
            reason="ambiguous",
            clarification_question="Do you mean the current draft, or last year's stats?",
        ),
        user_message="hello",
        has_agenda=False,
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.intent == "ambiguous_agent_target"
    assert decision.clarification_question == "Do you mean the current draft, or last year's stats?"


def test_clarify_falls_back_to_default_question_when_missing():
    decision = _to_decision(
        _RouterChoice(route="clarify", reason="ambiguous"),
        user_message="hello",
        has_agenda=False,
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.clarification_question


def test_direct_answer_emits_router_response():
    decision = _to_decision(
        _RouterChoice(
            route="direct_answer",
            reason="greeting",
            direct_response="Hi! I can help edit the current agenda or look up past meetings.",
        ),
        user_message="hello",
        has_agenda=False,
    )

    assert decision.route == RouteKind.DIRECT_ANSWER
    assert decision.intent == "router_direct_answer"
    assert decision.direct_response == "Hi! I can help edit the current agenda or look up past meetings."
    assert decision.agent_kind is None
    assert decision.handoff is None


def test_direct_answer_without_response_falls_back_to_clarify():
    """Defensive: if the LLM picks direct_answer but forgets to fill
    direct_response, we fall back to clarify rather than emit an empty
    assistant message."""
    decision = _to_decision(
        _RouterChoice(route="direct_answer", reason="confused"),
        user_message="hmm",
        has_agenda=False,
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.intent == "ambiguous_agent_target"


def _proposal() -> dict:
    return {
        "intent": "assign_role_from_stats",
        "facts": [{"full_name": "Leta Li", "username": "leta"}],
        "constraints": {"user_message": "find someone for TTE"},
        "requires_confirmation": True,
    }


def test_specialist_meeting_with_pending_handoff_confirmation_attaches_proposal():
    proposal = _proposal()
    decision = _to_decision(
        _RouterChoice(
            route="specialist_meeting",
            reason="user picked Leta Li",
            is_handoff_confirmation=True,
        ),
        user_message="选 Leta Li 吧",
        has_agenda=True,
        pending_handoff=proposal,
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.MEETING
    assert decision.intent == "confirmed_handoff_meeting_mutation"
    assert decision.metadata["pending_handoff"] == proposal


def test_specialist_meeting_with_pending_handoff_but_not_a_confirmation_is_normal_edit():
    """User has a pending handoff but their reply is a different edit —
    treat as a normal meeting edit, do NOT attach the handoff."""
    proposal = _proposal()
    decision = _to_decision(
        _RouterChoice(
            route="specialist_meeting",
            reason="unrelated edit",
            is_handoff_confirmation=False,
        ),
        user_message="把 Theme 改成 Resilience",
        has_agenda=True,
        pending_handoff=proposal,
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.MEETING
    assert decision.intent == "current_meeting_draft"
    assert "pending_handoff" not in decision.metadata


def test_handoff_confirmation_without_agenda_clarifies_with_audit_metadata():
    proposal = _proposal()
    decision = _to_decision(
        _RouterChoice(
            route="specialist_meeting",
            reason="user picked Leta Li",
            is_handoff_confirmation=True,
        ),
        user_message="选 Leta Li 吧",
        has_agenda=False,
        pending_handoff=proposal,
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.intent == "handoff_confirmation_without_agenda_snapshot"
    assert decision.metadata["pending_handoff"] == proposal


def test_clarify_with_pending_handoff_relabels_intent_and_keeps_proposal():
    """Vague confirmation ('yes' alone): LLM clarifies, server re-labels
    the intent so the audit trail surfaces this as a vague confirmation
    bounce rather than a generic ambiguous-target clarify."""
    proposal = _proposal()
    decision = _to_decision(
        _RouterChoice(
            route="clarify",
            reason="vague confirmation",
            clarification_question="Which candidate? e.g. 'Leta Li'.",
        ),
        user_message="yes",
        has_agenda=True,
        pending_handoff=proposal,
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.intent == "handoff_confirmation_needs_details"
    assert decision.clarification_question == "Which candidate? e.g. 'Leta Li'."
    assert decision.metadata["pending_handoff"] == proposal
