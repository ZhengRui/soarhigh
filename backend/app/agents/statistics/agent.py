"""Pydantic AI agent registration for the statistics agent.

Read-only. The tool surface stays deliberately small: dashboard-backed
statistics tools plus shared historical meeting lookup / preview
primitives.
"""

import asyncio
import os
from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.agents.runtime.model_settings import build_model_settings
from app.agents.statistics import tools as _tools
from app.agents.statistics.models import StatsDeps
from app.agents.statistics.prompts import STATS_SYSTEM_PROMPT
from app.config import GOOGLE_API_KEY, OPENAI_API_KEY, STATISTICS_AGENT_MODEL, STATISTICS_THINKING_LEVEL
from app.services import meeting_lookup

# Bridge .env values to os.environ — Pydantic AI providers read keys at
# Agent() construction. Same trick as the meeting agent.
os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")
os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY or "not-configured")

USAGE_LIMITS = UsageLimits(request_limit=15, total_tokens_limit=500_000)


agent = Agent(
    STATISTICS_AGENT_MODEL,
    system_prompt=STATS_SYSTEM_PROMPT,
    deps_type=StatsDeps,
    retries=2,
    model_settings=build_model_settings(STATISTICS_AGENT_MODEL, thinking_level=STATISTICS_THINKING_LEVEL),
)


# ---------- Dashboard-backed statistics tools ----------


@agent.tool
async def meeting_attendance_list(
    ctx: RunContext[StatsDeps],
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: Literal["Regular", "Workshop", "Custom"] | None = None,
    meeting_no: int | None = None,
    sort_by: Literal["date", "member_count", "guest_count", "total_count"] = "date",
    sort_order: Literal["asc", "desc"] = "asc",
    limit: int = 50,
    include_names: bool = False,
) -> dict:
    """Dashboard-backed per-meeting attendance rows.

    Use for questions about attendance per meeting, meeting attendance
    rankings, average attendance, member/guest counts, or who attended a
    specific meeting. This uses the same smart-merge attendance
    definition as the dashboard's "Attendance per Meeting" chart.
    """
    return await _tools.apply_meeting_attendance_list(
        ctx,
        date_from=date_from,
        date_to=date_to,
        type_filter=type_filter,
        meeting_no=meeting_no,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        include_names=include_names,
    )


@agent.tool
async def member_role_matrix(
    ctx: RunContext[StatsDeps],
    date_from: str | None = None,
    date_to: str | None = None,
    member: str | None = None,
    role_filter: Literal[
        "SAA",
        "President",
        "TOM",
        "Timer",
        "Grammarian",
        "HarkMaster",
        "GuestIntroHost",
        "TTM",
        "PreparedSpeech",
        "TTE",
        "IE",
        "GE",
        "MoT",
        "WorkshopSpeaker",
    ]
    | None = None,
    role_group: Literal["evaluation", "speaker", "hosting", "facilitator"] | None = None,
    group_by: Literal["member", "role", "member_role", "meeting"] = "member_role",
    sort_by: Literal["count", "name", "date"] = "count",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = 50,
    include_meetings: bool = True,
) -> dict:
    """Dashboard-backed member-role matrix.

    Use for questions about who took which roles, counts by member,
    counts by role, or which meetings a member filled a dashboard role.
    Use role_filter for one exact matrix column, or role_group for a
    broader category like evaluation = TTE + IE + GE. Counts role
    assignments, not full attendance.

    DOES NOT INCLUDE Meeting Manager (会议经理) — that role lives on
    the meeting metadata, not on segments. For "X 组织 / managed /
    做 Meeting Manager / 担任会议经理" questions, use
    `meeting_manager_matrix` (exact aggregate counts) or
    `lookup_meeting` with name_substring=X (to get the actual meeting
    list) — NOT this matrix.

    Chinese "X 主持" → use this matrix with role_group="hosting" (TOM,
    TTM, MoT, GuestIntroHost, HarkMaster, SAA). 主持 refers to in-
    meeting hosting roles, NOT Meeting Manager — keep them separate
    even though a Meeting Manager often also signs up as TTM.
    """
    return await _tools.apply_member_role_matrix(
        ctx,
        date_from=date_from,
        date_to=date_to,
        member=member,
        role_filter=role_filter,
        role_group=role_group,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        include_meetings=include_meetings,
    )


@agent.tool
async def meeting_manager_matrix(
    ctx: RunContext[StatsDeps],
    date_from: str | None = None,
    date_to: str | None = None,
    type_filter: Literal["Regular", "Workshop", "Custom"] | None = None,
    sort_by: Literal["count", "name"] = "count",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = 50,
) -> dict:
    """Per-manager meeting-manager (会议经理) counts, server-aggregated.

    Use for questions about who organized / managed how many meetings,
    Meeting Manager rankings, or per-person organize counts.
    Triggers: "X 组织过多少次会议?", "今年每个会员组织了多少次会议?",
    "Meeting Manager 排名", "做 Meeting Manager 最多的是谁?",
    "担任会议经理的次数".

    The aggregation runs in Python over the full date range — counts
    are exact. Do NOT use lookup_meeting to count cards yourself; this
    tool is the canonical source.

    Result groups are {member_id, full_name, username, count,
    is_member}. INCLUDES managers whose attendee does NOT resolve to a
    current member (former members, guests, broken links) — those rows
    have member_id="" and is_member=false. Treat them as legitimate
    managers, not noise. The result envelope also includes
    `total_meetings` (sum of all counts) so you can spot-check your
    reply against ground truth.
    """
    return await _tools.apply_meeting_manager_matrix(
        ctx,
        date_from=date_from,
        date_to=date_to,
        type_filter=type_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )


@agent.tool
async def member_award_matrix(
    ctx: RunContext[StatsDeps],
    date_from: str | None = None,
    date_to: str | None = None,
    member: str | None = None,
    category_filters: list[str] | None = None,
    meeting_no: int | None = None,
    group_by: Literal["winner", "category", "winner_category", "meeting"] = "winner_category",
    sort_by: Literal["count", "name", "date"] = "count",
    sort_order: Literal["asc", "desc"] = "desc",
    limit: int = 50,
    include_meetings: bool = True,
) -> dict:
    """Dashboard-style member/winner award matrix.

    Use for questions about who won which awards, counts by award winner,
    counts by category, or awards given by meeting. Award winners are stored
    as raw names; unresolved guests or ambiguous names are included as raw
    winner groups. category_filters accepts standard category keys like BestPS
    and raw custom category text like "Best Joke" or "Custom". Use meeting_no
    to scope to a single meeting (e.g. "第408期获奖情况" → meeting_no=408,
    group_by="winner_category").
    """
    return await _tools.apply_member_award_matrix(
        ctx,
        date_from=date_from,
        date_to=date_to,
        member=member,
        category_filters=category_filters,
        meeting_no=meeting_no,
        group_by=group_by,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        include_meetings=include_meetings,
    )


# ---------- Shared lookup tools (read-only; same as meeting agent) ----------
#
# Both agents thin-wrap the same `apply_*` helpers in
# `app.services.meeting_lookup`. One definition of arg validation, one
# envelope shape, one pool-cache helper — both agents stay in sync.


@agent.tool
async def lookup_meeting(
    ctx: RunContext[StatsDeps],
    no: int | None = None,
    name_substring: str | None = None,
    theme_substring: str | None = None,
    introduction_substring: str | None = None,
    type_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 5,
) -> dict:
    """READ-ONLY. Find historical meetings by structured filter.

    Filter axes (AND across distinct axes; fire parallel calls for OR):
    - `no`: exact display number; bypasses pool scan.
    - `name_substring`: case-insensitive substring on **meeting manager
      name ONLY**. Use for queries about who **organized / managed**
      a meeting as Meeting Manager (会议经理). Chinese phrasing:
      "组织 / 担任会议经理 / 做 Meeting Manager / 当 Meeting Manager"
      → name_substring=person + the requested date range. Does NOT
      match theme or intro.
      Do NOT use this for "X 主持" — that means in-meeting hosting
      roles (TOM, TTM, MoT, etc.), not Meeting Manager. Use
      `member_role_matrix(member=X, role_group="hosting")` for those.
    - `theme_substring`: substring on `theme` ("Emojis 那次", "主题
      关于教育的").
    - `introduction_substring`: substring on `introduction` body
      ("提到 leadership 的").
    - `type_filter`: Regular / Workshop / Custom.
    - `date_from` / `date_to`: ISO YYYY-MM-DD inclusive bounds.
    - `limit`: max cards returned. Default 5.

    HOW TO ANSWER COUNT QUESTIONS ("多少 / 几次 / how many"):
    Call this with the right filters + date range, then read
    `total_matches` from the result envelope (NOT len(cards), which is
    capped at limit). If `limit_clamped` is True you have only a
    partial sample of cards but `total_matches` is still the full
    count — report it. If the user wants the meeting list AND the
    count, raise `limit` to >= total_matches in a follow-up call.

    For per-manager AGGREGATION ("每个会员组织了多少次会议",
    "Meeting Manager 排名"), do NOT iterate cards from this tool.
    Use `meeting_manager_matrix` instead — it does exact server-side
    counting over the full date range.
    """
    return await meeting_lookup.apply_lookup_meeting(
        ctx,
        no=no,
        name_substring=name_substring,
        theme_substring=theme_substring,
        introduction_substring=introduction_substring,
        type_filter=type_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@agent.tool
async def preview_meeting(ctx: RunContext[StatsDeps], no: int) -> dict:
    """READ-ONLY. Get the full structure of a single historical meeting
    (meta + introduction + segments). Same tool as the meeting agent's
    preview_meeting."""
    return await meeting_lookup.apply_preview_meeting(ctx, no=no)


@agent.tool
async def list_members(ctx: RunContext[StatsDeps]) -> dict:
    """READ-ONLY. List all club members (id, username, full_name).

    Use for questions about who the members are, member-vs-guest
    classification, member counts ("我们俱乐部有多少会员?",
    "现在有哪些会员?", "Frank 是会员吗?"), or to provide a roster as
    context for follow-up role/award lookups.
    """
    from app.db.core import get_members

    rows = await asyncio.to_thread(get_members) or []
    return {"members": rows, "count": len(rows)}
