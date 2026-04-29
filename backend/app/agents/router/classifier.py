"""Deterministic first-pass router.

This is deliberately simple and testable. The unified route depends on this
module boundary so a later LLM classifier can replace the implementation
without changing endpoint wiring, SSE events, or persistence.
"""

from __future__ import annotations

import re

from app.agents.runtime.contracts import AgentKind, HandoffPayload, RouteKind, RouterDecision
from app.models.agent import AgentTurnRequest

_COUNT_OR_RANK_RE = re.compile(
    r"\b(how many|count|counts|total|number of|rank|ranking|most|least|average|avg|top|bottom)\b",
    re.IGNORECASE,
)
_MEETING_NO_RE = re.compile(r"(?:#|meeting\s*(?:no\.?|number)?\s*)\d{2,4}\b", re.IGNORECASE)

_STATISTICS_TERMS = (
    "attendance",
    "attended",
    "guest count",
    "member count",
    "role count",
    "roles",
    "award",
    "awards",
    "winner",
    "won",
    "best prepared speaker",
    "best evaluator",
    "best table topic",
    "出勤",
    "统计",
    "几次",
    "多少",
    "总共",
    "一共",
    "排名",
    "最多",
    "最少",
    "平均",
    "获奖",
    "奖项",
    "得奖",
    "最佳",
)

_HISTORICAL_TERMS = (
    "recent",
    "recently",
    "last year",
    "this year",
    "year to date",
    "ytd",
    "last month",
    "this month",
    "historical",
    "history",
    "去年",
    "今年",
    "上个月",
    "本月",
    "历史",
)

_RECENT_ROLE_BALANCE_TERMS = (
    "not done",
    "has not done",
    "haven't done",
    "did not do",
    "recently",
    "recent",
    "最近",
    "没做",
    "没有做",
)

_MUTATION_TERMS = (
    "set ",
    "change",
    "update",
    "assign",
    "swap",
    "move",
    "remove",
    "delete",
    "add ",
    "insert",
    "create",
    "clone",
    "copy",
    "revert",
    "undo",
    "duration",
    "buffer",
    "start time",
    "end time",
    "theme",
    "manager",
    "设置",
    "改",
    "换",
    "调整",
    "分配",
    "安排",
    "交换",
    "移动",
    "删除",
    "移除",
    "添加",
    "加一个",
    "创建",
    "生成",
    "克隆",
    "复制",
    "撤销",
    "还原",
    "时长",
    "间隔",
    "主题",
    "经理",
)

_CURRENT_DRAFT_TERMS = (
    "current agenda",
    "draft agenda",
    "this agenda",
    "show agenda",
    "validate agenda",
    "当前议程",
    "当前草稿",
    "这个议程",
    "看一下议程",
    "检查议程",
)

_ROLE_TERMS = (
    "saa",
    "timer",
    "grammarian",
    "hark master",
    "tom",
    "ttm",
    "tte",
    "ie",
    "ge",
    "prepared speech",
    "table topic",
    "evaluator",
    "主持",
    "计时",
    "语法官",
    "即兴",
    "备稿",
    "点评",
)


def classify_turn(req: AgentTurnRequest) -> RouterDecision:
    message = req.user_message or ""
    normalized = _normalize(message)
    has_agenda = req.agenda_snapshot is not None

    if _looks_cross_agent(normalized):
        return RouterDecision(
            route=RouteKind.HANDOFF,
            intent="statistics_to_meeting_handoff",
            reason="The user asks for historical facts and a current-draft mutation in one turn.",
            handoff=HandoffPayload(
                source_agent=AgentKind.STATISTICS,
                target_agent=AgentKind.MEETING,
                intent="assign_role_from_stats",
                constraints={"user_message": message},
                requires_confirmation=True,
            ),
        )

    if _looks_statistics(normalized):
        return RouterDecision(
            route=RouteKind.SPECIALIST,
            agent_kind=AgentKind.STATISTICS,
            intent="historical_statistics_or_lookup",
            reason="The request asks for historical lookup, counts, rankings, attendance, roles, or awards.",
            confidence=0.78,
        )

    if _looks_meeting(normalized):
        if not has_agenda:
            return RouterDecision(
                route=RouteKind.CLARIFY,
                intent="meeting_edit_without_agenda_snapshot",
                reason="The request is a current-meeting edit, but no agenda_snapshot was supplied.",
                clarification_question=(
                    "I need the current agenda snapshot before I can edit the meeting. "
                    "Please retry from a meeting draft page."
                ),
                confidence=0.72,
            )
        return RouterDecision(
            route=RouteKind.SPECIALIST,
            agent_kind=AgentKind.MEETING,
            intent="current_meeting_draft",
            reason="The request targets the current meeting draft.",
            confidence=0.78,
        )

    if has_agenda:
        return RouterDecision(
            route=RouteKind.SPECIALIST,
            agent_kind=AgentKind.MEETING,
            intent="current_meeting_context_default",
            reason="No statistics intent was detected and a current agenda snapshot is available.",
            confidence=0.55,
        )

    return RouterDecision(
        route=RouteKind.CLARIFY,
        intent="ambiguous_agent_target",
        reason="The request does not clearly target current-meeting editing or historical statistics.",
        clarification_question=(
            "Do you want me to edit the current meeting draft, or answer a historical statistics question?"
        ),
        confidence=0.4,
    )


def _normalize(message: str) -> str:
    return " ".join(message.lower().split())


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _looks_statistics(text: str) -> bool:
    if _COUNT_OR_RANK_RE.search(text):
        return True
    if _has_any(text, _STATISTICS_TERMS):
        return True
    if _has_any(text, _HISTORICAL_TERMS) and not _looks_meeting(text):
        return True
    if _MEETING_NO_RE.search(text) and not any(term in text for term in ("clone", "copy", "克隆", "复制")):
        return True
    return False


def _looks_meeting(text: str) -> bool:
    if _has_any(text, _CURRENT_DRAFT_TERMS):
        return True
    if _has_any(text, _MUTATION_TERMS):
        return True
    if _has_any(text, _ROLE_TERMS) and any(term in text for term in ("to ", "给", "设", "换", "改")):
        return True
    return False


def _looks_cross_agent(text: str) -> bool:
    mutates_meeting = any(term in text for term in ("assign", "set ", "安排", "分配", "设置", "改成"))
    if not mutates_meeting:
        return False
    if _looks_statistics(text) and _looks_meeting(text):
        return True
    return _has_any(text, _ROLE_TERMS) and _has_any(text, _RECENT_ROLE_BALANCE_TERMS)
