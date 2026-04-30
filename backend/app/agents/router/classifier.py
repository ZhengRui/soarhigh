"""LLM-backed router classifier.

The unified route boundary is unchanged: import `classify_turn` and await
it. Internally the classifier delegates to a small Pydantic AI Agent with
structured output, then server post-processing builds the final
RouterDecision (applying the agenda-snapshot guard and constructing the
HandoffPayload).
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.runtime.contracts import AgentKind, HandoffPayload, RouteKind, RouterDecision
from app.agents.runtime.model_settings import build_model_settings
from app.config import GOOGLE_API_KEY, OPENAI_API_KEY, ROUTER_AGENT_MODEL, ROUTER_THINKING_LEVEL
from app.models.agents.unified import AgentTurnRequest

os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")
os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY or "not-configured")


class _RouterChoice(BaseModel):
    """LLM intermediate output. Server post-processes into RouterDecision."""

    route: Literal[
        "specialist_meeting",
        "specialist_statistics",
        "handoff_stats_to_meeting",
        "clarify",
    ]
    reason: str = Field(description="One sentence explaining the routing choice.")
    clarification_question: str | None = Field(
        default=None,
        description=("REQUIRED when route='clarify'. The question to ask the user. " "Leave null for any other route."),
    )


_ROUTER_SYSTEM_PROMPT = """\
You are a router for a Toastmasters meeting tool. Classify exactly one user
message into one of four routes. Return only the structured choice.

- specialist_meeting: the user wants to view, edit, or mutate the CURRENT
  meeting agenda draft. Examples: "set Timer to Joyce Feng",
  "change the theme to Resilience", "show the current agenda",
  "clone #451 into this draft", "把 Timer 改成 Joyce Feng",
  "看一下当前议程".

- specialist_statistics: the user asks about HISTORICAL meetings, attendance,
  role participation, awards, rankings, counts, or looks up a specific
  meeting by number / name / theme. Examples:
  "who won Best Evaluator this year?", "which meetings did Frank host?",
  "show me #451", "When was the last time Joyce did TTE?",
  "今年谁拿 Best Evaluator 最多?", "Frank 最近主持过哪些会议?".

- handoff_stats_to_meeting: the user wants a HISTORICAL-fact lookup AND a
  current-draft mutation in one turn. Examples:
  "find someone who hasn't done TTE recently and assign them to this meeting",
  "找一个最近没做过 TTE 的人, 安排到这次会议".

- clarify: the request is genuinely ambiguous between current-draft and
  historical lookup, or has no clear target at all. Set
  clarification_question to a short question that disambiguates.

You will be told whether the current meeting agenda is loaded. Even when no
agenda is loaded, still pick specialist_meeting if the user clearly wants to
edit the current draft — the server applies the agenda-missing guard.
"""

_agent: Agent[None, _RouterChoice] = Agent(
    ROUTER_AGENT_MODEL,
    output_type=_RouterChoice,
    system_prompt=_ROUTER_SYSTEM_PROMPT,
    retries=2,
    model_settings=build_model_settings(ROUTER_AGENT_MODEL, thinking_level=ROUTER_THINKING_LEVEL),
)


async def classify_turn(req: AgentTurnRequest) -> RouterDecision:
    user_message = req.user_message or ""
    has_agenda = req.agenda_snapshot is not None
    prompt = f"User message: {user_message}\n" f"Current meeting agenda loaded: {'yes' if has_agenda else 'no'}"
    result = await _agent.run(prompt)
    return _to_decision(result.output, user_message=user_message, has_agenda=has_agenda)


def _to_decision(
    choice: _RouterChoice,
    *,
    user_message: str,
    has_agenda: bool,
) -> RouterDecision:
    if choice.route == "specialist_meeting":
        if not has_agenda:
            return RouterDecision(
                route=RouteKind.CLARIFY,
                intent="meeting_edit_without_agenda_snapshot",
                reason="The request is a current-meeting edit, but no agenda_snapshot was supplied.",
                clarification_question=(
                    "I need the current agenda snapshot before I can edit the meeting. "
                    "Please retry from a meeting draft page."
                ),
            )
        return RouterDecision(
            route=RouteKind.SPECIALIST,
            agent_kind=AgentKind.MEETING,
            intent="current_meeting_draft",
            reason=choice.reason,
        )

    if choice.route == "specialist_statistics":
        return RouterDecision(
            route=RouteKind.SPECIALIST,
            agent_kind=AgentKind.STATISTICS,
            intent="historical_statistics_or_lookup",
            reason=choice.reason,
        )

    if choice.route == "handoff_stats_to_meeting":
        return RouterDecision(
            route=RouteKind.HANDOFF,
            intent="statistics_to_meeting_handoff",
            reason=choice.reason,
            handoff=HandoffPayload(
                source_agent=AgentKind.STATISTICS,
                target_agent=AgentKind.MEETING,
                intent="assign_role_from_stats",
                constraints={"user_message": user_message},
                requires_confirmation=True,
            ),
        )

    question = (choice.clarification_question or "").strip() or (
        "Do you want me to edit the current meeting draft, " "or answer a historical statistics question?"
    )
    return RouterDecision(
        route=RouteKind.CLARIFY,
        intent="ambiguous_agent_target",
        reason=choice.reason,
        clarification_question=question,
    )
