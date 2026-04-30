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

import json
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
    is_handoff_confirmation: bool = Field(
        default=False,
        description=(
            "Set TRUE only when (a) a 'Pending handoff awaiting confirmation' block "
            "is included in the prompt AND (b) the current user reply is completing "
            "or confirming that pending handoff (names a candidate from the proposal, "
            "or otherwise indicates 'go ahead with the proposed edit'). Set FALSE in "
            "ALL other cases — including: no pending handoff exists; the reply is a "
            "different request even though a pending handoff exists; the reply is too "
            "vague ('yes' / '好的' alone, no candidate named) to act on. When TRUE, "
            "set route='specialist_meeting'. When the reply is too vague, set "
            "route='clarify' and is_handoff_confirmation=FALSE."
        ),
    )


_ROUTER_SYSTEM_PROMPT = """\
You are the manager-router for a Toastmasters meeting tool. You have NO
TOOLS yourself. Your only job is to classify each user turn into one of
five routes, and (for direct_answer) to write a brief reply.

PENDING HANDOFF FAST PATH (CHECK FIRST — overrides general routing):
If the prompt includes a line "Pending handoff awaiting confirmation: {...}"
the previous turn already proposed a current-agenda edit and listed
candidate people from historical stats. Before evaluating the general
ROUTES below, scan that block's `candidates` array and the user's reply:

- ANY candidate's `full_name` or `username` appears (literally or with
  light Chinese particles like "选 / 就 / 用 / X 吧") in the reply
  → route="specialist_meeting", is_handoff_confirmation=TRUE.
  This is the DEFAULT outcome — do NOT clarify just because the role
  was not re-stated; the role is established in `constraints` already.
  Examples that MUST trigger this path:
    "选 Leta Li 吧"           → confirm Leta Li
    "就选 Leta Li 吧"         → confirm Leta Li
    "Leta"                    → confirm Leta Li (first-name match)
    "就 Joyce"                → confirm Joyce Feng
    "Confirm Joyce as Timer"  → confirm (also re-states role)
    "用 Frank 吧"             → confirm Frank Zeng

- Explicit cancellation ("算了" / "不要了" / "cancel" / "skip it")
  → route="direct_answer", brief acknowledgement.

- Ask for different / more candidates ("再找几个" / "换一批" /
  "other options") → route="specialist_statistics".

- Truly nameless / no-cancel reply ("yes" / "好的" / "ok" alone)
  → route="clarify"; clarification_question must reference the
  candidate list explicitly (e.g. "选 Leta Li 还是 Joyce Feng?").

DO NOT use the generic "edit the draft or look up history?" clarify
question when a pending handoff is present — that wastes the turn.
End of fast path.

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

- clarify: LAST RESORT. Use ONLY when ALL of these hold:
  (a) the message is genuinely ambiguous between current-draft
      editing and historical statistics — could plausibly be either
      intent;
  (b) the conversation history does NOT establish an active thread
      that resolves the ambiguity;
  (c) routing to either specialist would be substantively wrong, not
      just slightly suboptimal.
  Set `clarification_question` to a short question that disambiguates.

  NEVER clarify when ANY of these apply:
  - The message is a capability / about-the-system question →
    direct_answer.
  - The message is a follow-up reference that fits the recent
    thread ("X 呢", "怎么没…", "再看一下", "他", "刚才那个",
    pronouns, bare-noun follow-ups) → that thread's specialist.
  - The user is correcting or questioning the prior agent action
    ("不是 X 是 Y", "搞错了", "应该是…", "no, that's wrong",
    "you missed X", "为什么没…") → the specialist that handled
    the prior turn.
  - The message mixes a capability / meta question with a domain
    ask in one turn (HYBRID — see below) → the domain specialist.
  - You are merely UNCERTAIN but history points at one specialist →
    route there. Specialists can ask their own follow-up questions
    if they need to. "I want to be sure" is not a reason to
    clarify — it wastes a turn.

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

CONVERSATION HISTORY (use it aggressively to RESOLVE, not as a hint to ask):
The conversation history above includes tool calls and tool results made
by SPECIALIST AGENTS (meeting / statistics). You did NOT make those tool
calls — you have NO tools at all. Treat them as facts about what the
specialists did, not as your own actions.

Use history to RESOLVE ambiguity:
- Follow-up references ("再看一下", "他", "X 呢", "刚才那个", pronouns,
  bare-noun follow-ups) → continue the recent thread's specialist.
- Topic continuity: an active editing thread + an under-specified
  edit-shaped message → specialist_meeting. An active stats thread +
  an under-specified data question → specialist_statistics.
- Domain switches: only switch when the message clearly opens a new
  domain. Otherwise stay on the active thread.
- Corrections / questioning of the prior agent action ("不是 X 是 Y",
  "搞错了", "应该是…", "no, that's wrong", "你为什么没…", "you
  missed X") → route back to the specialist that handled the prior
  turn. NEVER clarify these.

HYBRID MESSAGES (capability + domain in one turn):
A single user message may mix a capability / meta question
(e.g. "你能做 parallel tool calls 吗?", "为什么没改 meeting manager?",
"你是不是漏了 X?", "did you forget Y?") WITH a domain ask or
follow-up (anything about the current agenda or historical data).
In that case pick the DOMAIN as the primary intent and route to
that specialist — the specialist can address the meta sidenote in
its reply text while doing the domain work. Do NOT clarify just
because two intents coexist; do NOT direct_answer just because the
sidenote is meta-ish.

PENDING HANDOFF DETAIL (see also fast path at top):
When a `Pending handoff awaiting confirmation` block is present and
none of the fast-path triggers fired (no candidate match, no cancel,
no "more candidates" intent), classify on the message's own merits
per ROUTES. If the user pivots to a wholly new request (e.g. "show
me #451" / "把 Theme 改成 X"), is_handoff_confirmation=FALSE — even
if the route ends up specialist_meeting, this is a NEW edit, not a
confirmation. The server will keep the prior pending handoff alive
for a future turn.

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


def _compact_pending_handoff(proposal: dict) -> dict:
    """Trim the proposal to fields the LLM router needs for classification.

    The full proposal carries verbose stats facts plus rendering metadata.
    The router only needs the original intent, the candidate list, and the
    constraints (which carry the original user_message that established
    the target role) to decide whether the current reply is a confirmation.
    """
    return {
        "intent": proposal.get("intent"),
        "candidates": proposal.get("facts", [])[:10],
        "constraints": proposal.get("constraints", {}),
    }


def _candidate_names_from_proposal(proposal: dict, *, limit: int = 3) -> list[str]:
    """Extract human-readable candidate names from a pending handoff proposal.

    Used to build context-aware clarification questions when the router
    has to bounce a vague confirmation back to the user. Falls back across
    `full_name` → `username` → `name` per fact entry.
    """
    names: list[str] = []
    for fact in proposal.get("facts", []) or []:
        if not isinstance(fact, dict):
            continue
        for key in ("full_name", "username", "name"):
            value = fact.get(key)
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
                break
        if len(names) >= limit:
            break
    return names


def _handoff_clarify_question(proposal: dict, *, language: str) -> str:
    """Context-aware default clarification text when a pending handoff is
    awaiting confirmation. Surfaces actual candidate names so the user
    sees this is the handoff bounce, not the generic ambiguous-target
    fallback.
    """
    names = _candidate_names_from_proposal(proposal)
    if language == "zh":
        if names:
            example = names[0]
            others = names[1:]
            others_part = f"(其他候选: {', '.join(others)})" if others else "(完整名单见上方列表)"
            return f"想从上一轮候选名单里选谁? 例如回复 " f'"就选 {example} 吧" 或 "确认 {example}"。{others_part}'
        return "想从上一轮候选名单里选谁? 直接回复候选人姓名即可。"
    if names:
        example = names[0]
        others = names[1:]
        others_part = f"(others: {', '.join(others)})" if others else "(see the list above)"
        return (
            f"Which candidate should I assign? Reply with a name like "
            f'"{example}" or "Confirm {example}". {others_part}'
        )
    return "Which candidate from the previous list should I assign? " "Reply with the name."


def _detect_user_language(text: str) -> str:
    """Lightweight CJK-vs-Latin heuristic to localize default clarification
    fallbacks. Mirrors the unified route's detector — duplicated here
    instead of imported to keep the classifier free of route imports.
    """
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if cjk == 0 and latin == 0:
        return "en"
    return "zh" if cjk > latin else "en"


async def classify_turn(
    req: AgentTurnRequest,
    *,
    message_history: list | None = None,
    pending_handoff: dict | None = None,
) -> RouterDecision:
    user_message = req.user_message or ""
    has_agenda = req.agenda_snapshot is not None
    prompt_parts = [
        f"User message: {user_message}",
        f"Current meeting agenda loaded: {'yes' if has_agenda else 'no'}",
    ]
    if pending_handoff is not None:
        compact = _compact_pending_handoff(pending_handoff)
        prompt_parts.append(f"Pending handoff awaiting confirmation: {json.dumps(compact, ensure_ascii=False)}")
    prompt = "\n".join(prompt_parts)
    # Replace any persisted SystemPromptPart in history with the router's
    # own prompt — Pydantic AI doesn't auto-inject _sys_parts when
    # history is non-empty, and prior specialists' system prompts would
    # otherwise override the router's identity.
    history = replace_system_prompt(message_history or [], _ROUTER_SYSTEM_PROMPT)
    result = await _agent.run(prompt, message_history=history)
    return _to_decision(
        result.output,
        user_message=user_message,
        has_agenda=has_agenda,
        pending_handoff=pending_handoff,
    )


def _to_decision(
    choice: _RouterChoice,
    *,
    user_message: str,
    has_agenda: bool,
    pending_handoff: dict | None = None,
) -> RouterDecision:
    language = _detect_user_language(user_message)
    if choice.route == "specialist_meeting":
        # Confirmed handoff: LLM marked this reply as completing a pending
        # handoff. Server attaches the proposal to metadata; the unified
        # dispatch wraps the user message with handoff context before
        # handing off to the meeting agent.
        if pending_handoff is not None and choice.is_handoff_confirmation:
            if not has_agenda:
                missing_msg = (
                    "我需要当前议程快照才能应用 handoff。请从会议草稿页面重新发送。"
                    if language == "zh"
                    else (
                        "I need the current agenda snapshot before I can apply that confirmed handoff. "
                        "Please retry from a meeting draft page."
                    )
                )
                return RouterDecision(
                    route=RouteKind.CLARIFY,
                    intent="handoff_confirmation_without_agenda_snapshot",
                    reason=(
                        "A confirmed handoff needs the current agenda snapshot "
                        "before the meeting agent can apply it."
                    ),
                    clarification_question=missing_msg,
                    metadata={"pending_handoff": pending_handoff},
                )
            return RouterDecision(
                route=RouteKind.SPECIALIST,
                agent_kind=AgentKind.MEETING,
                intent="confirmed_handoff_meeting_mutation",
                reason=choice.reason,
                metadata={"pending_handoff": pending_handoff},
            )
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

    llm_question = (choice.clarification_question or "").strip()
    # Clarify with a pending handoff in flight: keep the audit trail by
    # carrying the proposal through metadata, and re-label the intent so
    # the unified store / debugging sees this is a vague-confirmation
    # bounce, not a generic ambiguous turn. Use a context-aware default
    # question that surfaces the actual candidate names from the proposal
    # — that's how the user (and we, while debugging) tell at a glance
    # that the handoff context was loaded.
    if pending_handoff is not None:
        question = llm_question or _handoff_clarify_question(pending_handoff, language=language)
        return RouterDecision(
            route=RouteKind.CLARIFY,
            intent="handoff_confirmation_needs_details",
            reason=choice.reason,
            clarification_question=question,
            metadata={"pending_handoff": pending_handoff},
        )
    default_generic = (
        "你想让我修改当前会议草稿, 还是回答历史统计问题?"
        if language == "zh"
        else "Do you want me to edit the current meeting draft, or answer a historical statistics question?"
    )
    return RouterDecision(
        route=RouteKind.CLARIFY,
        intent="ambiguous_agent_target",
        reason=choice.reason,
        clarification_question=llm_question or default_generic,
    )
