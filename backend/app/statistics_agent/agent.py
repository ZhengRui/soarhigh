"""Pydantic AI agent registration for the statistics agent.

Read-only. The tool surface stays deliberately small: dashboard-backed
statistics tools plus shared historical meeting lookup / preview
primitives.
"""

import os
from typing import Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.config import GOOGLE_API_KEY, MEETING_AGENT_MODEL, OPENAI_API_KEY
from app.services import meeting_lookup
from app.statistics_agent import tools as _tools
from app.statistics_agent.models import StatsDeps
from app.statistics_agent.prompts import STATS_SYSTEM_PROMPT

# Bridge .env values to os.environ — Pydantic AI providers read keys at
# Agent() construction. Same trick as the meeting agent.
os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")
os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY or "not-configured")

USAGE_LIMITS = UsageLimits(request_limit=15, total_tokens_limit=500_000)

_GEMINI_THINKING_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro"}


def _build_model_settings(model_spec: str):
    if any(m in model_spec for m in _GEMINI_THINKING_MODELS):
        from pydantic_ai.models.google import GoogleModelSettings

        return GoogleModelSettings(
            google_thinking_config={
                "thinking_budget": -1,
                "include_thoughts": True,
            },
        )
    return None


# Reuse the same model the meeting agent uses (Phase 2 doesn't introduce
# a separate config). Phase 3 may select a smaller/faster classifier
# model for the router — orthogonal.
agent = Agent(
    MEETING_AGENT_MODEL,
    system_prompt=STATS_SYSTEM_PROMPT,
    deps_type=StatsDeps,
    retries=2,
    model_settings=_build_model_settings(MEETING_AGENT_MODEL),
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
async def member_award_matrix(
    ctx: RunContext[StatsDeps],
    date_from: str | None = None,
    date_to: str | None = None,
    member: str | None = None,
    category_filters: list[str] | None = None,
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
    and raw custom category text like "Best Joke" or "Custom".
    """
    return await _tools.apply_member_award_matrix(
        ctx,
        date_from=date_from,
        date_to=date_to,
        member=member,
        category_filters=category_filters,
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
    """READ-ONLY. Find historical meetings by structured filter. See
    the meeting agent's `lookup_meeting` docstring for full semantics —
    same tool, same envelope."""
    _tools.refuse_lookup_if_aggregate_count(ctx)
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
