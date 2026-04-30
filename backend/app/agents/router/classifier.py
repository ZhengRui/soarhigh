"""LLM-backed router classifier.

The unified route boundary is unchanged: import `classify_turn` and await
it. Internally the classifier delegates to a small Pydantic AI Agent with
structured output, then server post-processing builds the final
RouterDecision (applying the agenda-snapshot guard and constructing the
HandoffPayload).

The router is context-aware: callers pass the unified message_history
(same JSON-decoded list specialists use), and the LLM sees prior
specialist tool calls / replies. The system prompt explicitly tells the
router that those tool calls were made by specialists, not by itself —
the router has no tools.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.agents.meeting.history import replace_system_prompt
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
        "direct_answer",
        "clarify",
    ]
    reason: str = Field(description="One sentence explaining the routing choice.")
    clarification_question: str | None = Field(
        default=None,
        description=("REQUIRED when route='clarify'. The question to ask the user. Leave null for any other route."),
    )
    direct_response: str | None = Field(
        default=None,
        description=(
            "REQUIRED when route='direct_answer'. A friendly, brief reply to the user. "
            "Leave null for any other route."
        ),
    )


_ROUTER_SYSTEM_PROMPT = """\
You are the manager-router for a Toastmasters meeting tool. You have NO
TOOLS yourself. Your only job is to classify each user turn into one of
five routes, and (for direct_answer) to write a brief reply.

ROUTES:

- specialist_meeting: the user wants to view, edit, mutate, OR CREATE a
  meeting agenda draft. Includes creating a new meeting from scratch
  (template, text description, uploaded image, or by cloning a past
  meeting). Examples:
  edit:    "set Timer to Joyce Feng", "change the theme to Resilience",
           "show the current agenda", "把 Timer 改成 Joyce Feng",
           "看一下当前议程".
  create:  "create a meeting", "create a new regular meeting",
           "make a workshop meeting from template",
           "create a meeting from this text: ...",
           "clone #451 into this draft",
           "创建一个会议吧", "新建一个会议", "新建一个例会",
           "用模板创建一个 Workshop", "从 #451 克隆".

- specialist_statistics: the user asks about HISTORICAL meetings,
  attendance, role participation, awards, rankings, counts, or looks up
  a specific meeting by number / name / theme. Examples:
  "who won Best Evaluator this year?", "which meetings did Frank host?",
  "show me #451", "When was the last time Joyce did TTE?",
  "今年谁拿 Best Evaluator 最多?", "Frank 最近主持过哪些会议?".

- handoff_stats_to_meeting: the user wants a HISTORICAL-fact lookup AND
  a current-draft mutation in one turn. Examples:
  "find someone who hasn't done TTE recently and assign them to this meeting",
  "找一个最近没做过 TTE 的人, 安排到这次会议".

- direct_answer: small talk, greetings/thanks/goodbyes, AND
  capability/about-the-system questions ("what can you do?",
  "你能做什么?", "what tools do you have?", "你有哪些工具", "会议管理
  能做什么?", "how does the stats agent work?"). Also use for brief
  follow-up exchanges that do NOT need tool access (e.g. "got it",
  "再问个问题"). ALWAYS prefer direct_answer over clarify for
  capability questions — the user is asking ABOUT the system, not
  asking the system to do something ambiguous. Set `direct_response`
  in the user's language.

  However: bias AGAINST direct_answer when the user wants the system
  to actually DO something that touches a specialist's domain.
  Specifically, if the user asks about a specialist's tool, behavior,
  or refusal regarding actual past data ("why did lookup_meeting fail
  in turn 3?"), route to that specialist — they have the tool and the
  refusal logic. Do NOT guess answers to data/edit questions.

- clarify: genuinely ambiguous between current-draft editing and
  historical lookup, with no clear default. Set
  `clarification_question` to a short question that disambiguates.
  NEVER use clarify for capability questions — those are always
  direct_answer.

USER-FACING NAMES (CRITICAL):
The route literals (`specialist_meeting`, `specialist_statistics`,
`handoff_stats_to_meeting`, `direct_answer`, `clarify`) are INTERNAL
classification labels. NEVER mention them in `direct_response` or any
text shown to the user. When describing the system to users, use
natural names:
- specialist_meeting → "meeting agent" / "会议管理助手" / "议程编辑"
- specialist_statistics → "statistics agent" / "统计分析助手" / "历史
  数据查询"
- The router itself → just speak as "I" / "我"; don't expose its name.

CONVERSATION HISTORY:
The conversation history above includes tool calls and tool results made
by SPECIALIST AGENTS (meeting / statistics). You did NOT make those tool
calls — you have NO tools at all. Treat them as facts about what the
specialists did, not as your own actions. Use the history to disambiguate
follow-up references ("再看一下", "他", pronouns), recognize topic
continuity (a stats follow-up usually stays statistics), and notice
genuine domain switches.

CONTEXT FLAG:
You will be told whether the current meeting agenda is loaded. This is
INFORMATIONAL ONLY — it does NOT bias the route. Always classify by the
message content, not by the flag:
- A clearly stats-shaped question (counts, rankings, attendance,
  awards, historical lookups, words like 今年 / this year / recent /
  排序 / sort / count / how many) routes to specialist_statistics
  regardless of whether an agenda is loaded. The agenda being loaded
  does NOT mean the user wants to edit it.
- A clearly meeting-edit request (set / change / clone / show current /
  show this agenda) routes to specialist_meeting. If no agenda is
  loaded, still pick specialist_meeting; the server handles the
  missing-agenda case.
"""

_agent: Agent[None, _RouterChoice] = Agent(
    ROUTER_AGENT_MODEL,
    output_type=_RouterChoice,
    system_prompt=_ROUTER_SYSTEM_PROMPT,
    retries=2,
    model_settings=build_model_settings(ROUTER_AGENT_MODEL, thinking_level=ROUTER_THINKING_LEVEL),
)


async def classify_turn(
    req: AgentTurnRequest,
    *,
    message_history: list | None = None,
) -> RouterDecision:
    user_message = req.user_message or ""
    has_agenda = req.agenda_snapshot is not None
    prompt = f"User message: {user_message}\nCurrent meeting agenda loaded: {'yes' if has_agenda else 'no'}"
    # Replace any persisted SystemPromptPart in history with the router's
    # own prompt — Pydantic AI doesn't auto-inject _sys_parts when
    # history is non-empty, and prior specialists' system prompts would
    # otherwise override the router's identity.
    history = replace_system_prompt(message_history or [], _ROUTER_SYSTEM_PROMPT)
    result = await _agent.run(prompt, message_history=history)
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

    if choice.route == "direct_answer":
        response = (choice.direct_response or "").strip()
        if not response:
            return RouterDecision(
                route=RouteKind.CLARIFY,
                intent="ambiguous_agent_target",
                reason="(direct_answer was chosen but no direct_response was provided)",
                clarification_question=(
                    "Do you want me to edit the current meeting draft, or answer a historical statistics question?"
                ),
            )
        return RouterDecision(
            route=RouteKind.DIRECT_ANSWER,
            intent="router_direct_answer",
            reason=choice.reason,
            direct_response=response,
        )

    question = (choice.clarification_question or "").strip() or (
        "Do you want me to edit the current meeting draft, or answer a historical statistics question?"
    )
    return RouterDecision(
        route=RouteKind.CLARIFY,
        intent="ambiguous_agent_target",
        reason=choice.reason,
        clarification_question=question,
    )
