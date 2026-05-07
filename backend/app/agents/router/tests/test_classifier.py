"""Unit tests for the classifier's server-side post-processing.

Live LLM behavior is covered in test_router_evals.py (marked
@pytest.mark.live). These tests assert the deterministic mapping from
LLM choice → RouterDecision, including the agenda-snapshot guard.
"""

from app.agents.router.classifier import _ROUTER_SYSTEM_PROMPT, _RouterChoice, _to_decision
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


def test_clarify_default_question_is_localized_for_chinese_user():
    decision = _to_decision(
        _RouterChoice(route="clarify", reason="ambiguous"),
        user_message="呃",
        has_agenda=False,
    )

    assert decision.route == RouteKind.CLARIFY
    assert "当前会议草稿" in (decision.clarification_question or "")


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


def test_router_prompt_routes_meeting_manager_workflow_to_general():
    assert "会议经理" in _ROUTER_SYSTEM_PROMPT
    assert "MM 准备流程" in _ROUTER_SYSTEM_PROMPT
    assert "→ general" in _ROUTER_SYSTEM_PROMPT
