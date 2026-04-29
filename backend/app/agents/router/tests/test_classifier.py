from app.agents.router.classifier import classify_turn
from app.agents.runtime.contracts import AgentKind, RouteKind
from app.models.agent import AgentTurnRequest


def _agenda() -> dict:
    return {
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


def test_routes_award_count_to_statistics():
    decision = classify_turn(
        AgentTurnRequest(
            session_id="s1",
            user_message="今年谁拿 Best Evaluator 最多?",
        )
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.STATISTICS


def test_routes_current_agenda_edit_to_meeting_when_snapshot_exists():
    decision = classify_turn(
        AgentTurnRequest(
            session_id="s1",
            user_message="set Timer to Joyce Feng",
            agenda_snapshot=_agenda(),
        )
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.MEETING


def test_clarifies_meeting_edit_without_snapshot():
    decision = classify_turn(
        AgentTurnRequest(
            session_id="s1",
            user_message="set Timer to Joyce Feng",
        )
    )

    assert decision.route == RouteKind.CLARIFY
    assert decision.intent == "meeting_edit_without_agenda_snapshot"


def test_historical_meeting_preview_defaults_to_statistics():
    decision = classify_turn(
        AgentTurnRequest(
            session_id="s1",
            user_message="show me #451",
            agenda_snapshot=_agenda(),
        )
    )

    assert decision.route == RouteKind.SPECIALIST
    assert decision.agent_kind == AgentKind.STATISTICS


def test_cross_domain_request_is_recognized_as_handoff():
    decision = classify_turn(
        AgentTurnRequest(
            session_id="s1",
            user_message="Find who has not done TTE recently, then assign one to this meeting",
            agenda_snapshot=_agenda(),
        )
    )

    assert decision.route == RouteKind.HANDOFF
    assert decision.handoff is not None
    assert decision.handoff.source_agent == AgentKind.STATISTICS
    assert decision.handoff.target_agent == AgentKind.MEETING
    assert decision.handoff.requires_confirmation is True
