"""Agent-gate tests for the minimal stats-agent tool surface."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from pydantic_ai import ModelRetry

from app.statistics_agent import tools as stats_tools
from app.statistics_agent.models import StatsDeps


@dataclass
class FakeCtx:
    deps: StatsDeps


def _deps(message: str = "", today: str = "2026-04-28") -> StatsDeps:
    return StatsDeps(session_id="stats:test", current_user_message=message, today=today)


@pytest.mark.asyncio
async def test_meeting_attendance_list_wraps_dashboard_rows():
    ctx = FakeCtx(deps=_deps())
    attendance_rows = [
        {
            "meeting_id": "m1",
            "meeting_date": "2026-01-07",
            "meeting_theme": "A",
            "meeting_no": 451,
            "member_count": 10,
            "guest_count": 2,
            "member_names": ["Joyce Feng"],
            "guest_names": ["Guest A"],
        },
        {
            "meeting_id": "m2",
            "meeting_date": "2026-01-14",
            "meeting_theme": "B",
            "meeting_no": 452,
            "member_count": 8,
            "guest_count": 5,
            "member_names": ["Frank Zeng"],
            "guest_names": ["Guest B"],
        },
    ]
    meeting_rows = [
        {"id": "m1", "type": "Regular"},
        {"id": "m2", "type": "Workshop"},
    ]

    with (
        patch(
            "app.statistics_agent.tools.get_meeting_attendance_stats",
            return_value=attendance_rows,
        ),
        patch(
            "app.services.meeting_stats.load_meetings_in_range",
            return_value=meeting_rows,
        ),
    ):
        out = await stats_tools.apply_meeting_attendance_list(
            ctx,
            date_from="2026-01-01",
            date_to="2026-12-31",
            type_filter="Regular",
            include_names=True,
        )

    assert out["scope"]["type_filter"] == "Regular"
    assert out["coverage"]["source"] == "dashboard_meeting_attendance"
    assert out["value"]["total_matches"] == 1
    assert out["value"]["summary"]["avg_total_count"] == 12.0
    assert out["value"]["meetings"] == [
        {
            "meeting_id": "m1",
            "no": 451,
            "date": "2026-01-07",
            "theme": "A",
            "type": "Regular",
            "member_count": 10,
            "guest_count": 2,
            "total_count": 12,
            "member_names": ["Joyce Feng"],
            "guest_names": ["Guest A"],
        }
    ]


@pytest.mark.asyncio
async def test_meeting_attendance_list_truncates_after_sorting():
    ctx = FakeCtx(deps=_deps())
    attendance_rows = [
        {
            "meeting_id": "m1",
            "meeting_date": "2026-01-07",
            "meeting_theme": "A",
            "meeting_no": 451,
            "member_count": 10,
            "guest_count": 2,
            "member_names": [],
            "guest_names": [],
        },
        {
            "meeting_id": "m2",
            "meeting_date": "2026-01-14",
            "meeting_theme": "B",
            "meeting_no": 452,
            "member_count": 8,
            "guest_count": 5,
            "member_names": [],
            "guest_names": [],
        },
    ]
    meeting_rows = [
        {"id": "m1", "type": "Regular"},
        {"id": "m2", "type": "Regular"},
    ]

    with (
        patch(
            "app.statistics_agent.tools.get_meeting_attendance_stats",
            return_value=attendance_rows,
        ),
        patch(
            "app.services.meeting_stats.load_meetings_in_range",
            return_value=meeting_rows,
        ),
    ):
        out = await stats_tools.apply_meeting_attendance_list(ctx, sort_by="total_count", sort_order="desc", limit=1)

    assert out["coverage"]["status"] == "truncated"
    assert out["value"]["meetings"][0]["no"] == 452
    assert "member_names" not in out["value"]["meetings"][0]
    assert out["value"]["summary"]["meeting_count"] == 2


@pytest.mark.asyncio
async def test_member_role_matrix_groups_dashboard_rows_by_member():
    ctx = FakeCtx(deps=_deps())
    role_rows = [
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "meeting_id": "m1",
            "meeting_date": "2025-01-07",
            "meeting_theme": "A",
            "meeting_no": 401,
            "role": "Table Topic Evaluation",
        },
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m2",
            "meeting_date": "2025-01-14",
            "meeting_theme": "B",
            "meeting_no": 402,
            "role": "Table Topic Evaluation",
        },
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m3",
            "meeting_date": "2025-01-21",
            "meeting_theme": "C",
            "meeting_no": 403,
            "role": "Prepared Speech 2 Evaluation",
        },
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m4",
            "meeting_date": "2025-01-28",
            "meeting_theme": "D",
            "meeting_no": 404,
            "role": "Unmapped Custom Segment",
        },
    ]

    with patch(
        "app.statistics_agent.tools.get_member_meeting_stats",
        return_value=role_rows,
    ):
        out = await stats_tools.apply_member_role_matrix(
            ctx,
            date_from="2025-01-01",
            date_to="2025-12-31",
            role_filter="TTE",
            group_by="member",
        )

    assert out["coverage"]["source"] == "dashboard_member_role_matrix"
    assert out["value"]["total_rows"] == 2
    assert out["value"]["unmapped_roles"] == ["Unmapped Custom Segment"]
    assert out["value"]["groups"] == [
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "name": "Frank Zeng",
            "count": 1,
            "meeting_count": 1,
            "roles": {"TTE": 1},
            "meetings": [
                {
                    "meeting_id": "m1",
                    "no": 401,
                    "date": "2025-01-07",
                    "theme": "A",
                }
            ],
        },
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "name": "Joyce Feng",
            "count": 1,
            "meeting_count": 1,
            "roles": {"TTE": 1},
            "meetings": [
                {
                    "meeting_id": "m2",
                    "no": 402,
                    "date": "2025-01-14",
                    "theme": "B",
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_member_role_matrix_member_filter_uses_canonical_resolver():
    ctx = FakeCtx(deps=_deps())
    role_rows = [
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m2",
            "meeting_date": "2025-01-14",
            "meeting_theme": "B",
            "meeting_no": 402,
            "role": "Prepared Speech Evaluation",
        }
    ]

    with (
        patch(
            "app.statistics_agent.tools.get_member_meeting_stats",
            return_value=role_rows,
        ),
        patch(
            "app.services.meeting_stats.resolve_member",
            return_value=type(
                "Member",
                (),
                {"id": "mem-joyce", "full_name": "Joyce Feng", "username": "joyce"},
            )(),
        ),
    ):
        out = await stats_tools.apply_member_role_matrix(
            ctx,
            member="Joyce",
            group_by="role",
            include_meetings=False,
        )

    assert out["value"]["groups"] == [
        {
            "role_key": "IE",
            "role_label": "IE",
            "count": 1,
            "member_count": 1,
            "meeting_count": 1,
        }
    ]
    assert out["value"]["references"] == [
        {
            "meeting_id": "m2",
            "no": 402,
            "date": "2025-01-14",
            "theme": "B",
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "role_key": "IE",
            "role_label": "IE",
            "segment_type": "Prepared Speech Evaluation",
        }
    ]
    assert out["value"]["reference_total"] == 1
    assert out["value"]["reference_limit"] == 20


@pytest.mark.asyncio
async def test_member_role_matrix_role_group_expands_to_stable_role_keys():
    ctx = FakeCtx(deps=_deps())
    role_rows = [
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "meeting_id": "m1",
            "meeting_date": "2025-01-07",
            "meeting_theme": "A",
            "meeting_no": 401,
            "role": "Table Topic Evaluation",
        },
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "meeting_id": "m2",
            "meeting_date": "2025-01-14",
            "meeting_theme": "B",
            "meeting_no": 402,
            "role": "Prepared Speech 2 Evaluation",
        },
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "meeting_id": "m3",
            "meeting_date": "2025-01-21",
            "meeting_theme": "C",
            "meeting_no": 403,
            "role": "General Evaluation",
        },
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "meeting_id": "m4",
            "meeting_date": "2025-01-28",
            "meeting_theme": "D",
            "meeting_no": 404,
            "role": "Timer",
        },
    ]

    with (
        patch(
            "app.statistics_agent.tools.get_member_meeting_stats",
            return_value=role_rows,
        ),
        patch(
            "app.services.meeting_stats.resolve_member",
            return_value=type(
                "Member",
                (),
                {"id": "mem-frank", "full_name": "Frank Zeng", "username": "frank"},
            )(),
        ),
    ):
        out = await stats_tools.apply_member_role_matrix(
            ctx,
            member="Frank",
            role_group="evaluation",
            group_by="member",
            include_meetings=False,
        )

    assert out["scope"]["role_group"] == "evaluation"
    assert out["scope"]["role_filter"] is None
    assert out["value"]["role_groups"]["evaluation"] == ["TTE", "IE", "GE"]
    assert out["value"]["total_rows"] == 3
    assert out["value"]["groups"] == [
        {
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "name": "Frank Zeng",
            "count": 3,
            "meeting_count": 3,
            "roles": {"GE": 1, "IE": 1, "TTE": 1},
        }
    ]
    assert [ref["role_key"] for ref in out["value"]["references"]] == ["GE", "IE", "TTE"]


@pytest.mark.asyncio
async def test_member_role_matrix_retries_when_relative_date_scope_missing():
    ctx = FakeCtx(deps=_deps(message="今年谁做 Timer 最多?", today="2026-04-28"))

    with pytest.raises(ModelRetry, match='date_from="2026-01-01"'):
        await stats_tools.apply_member_role_matrix(
            ctx,
            role_filter="Timer",
            group_by="member",
        )


@pytest.mark.asyncio
async def test_meeting_attendance_list_retries_when_relative_date_scope_missing():
    ctx = FakeCtx(deps=_deps(message="今年哪次会议总参会人数最多?", today="2026-04-28"))

    with pytest.raises(ModelRetry, match='date_to="2026-04-28"'):
        await stats_tools.apply_meeting_attendance_list(
            ctx,
            sort_by="total_count",
            sort_order="desc",
        )


def test_stats_lookup_refuses_aggregate_count_questions():
    ctx = FakeCtx(deps=_deps(message="主题里有 AI 的会议有几次?"))

    with pytest.raises(ModelRetry, match="Do not use lookup_meeting"):
        stats_tools.refuse_lookup_if_aggregate_count(ctx)


@pytest.mark.asyncio
async def test_member_role_matrix_hosting_and_facilitator_group_memberships():
    ctx = FakeCtx(deps=_deps())
    role_rows = [
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m1",
            "meeting_date": "2025-01-07",
            "meeting_theme": "A",
            "meeting_no": 401,
            "role": "Opening Remarks (President)",
        },
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m2",
            "meeting_date": "2025-01-14",
            "meeting_theme": "B",
            "meeting_no": 402,
            "role": "Moment of Truth",
        },
        {
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "meeting_id": "m3",
            "meeting_date": "2025-01-21",
            "meeting_theme": "C",
            "meeting_no": 403,
            "role": "Timer",
        },
    ]

    with (
        patch(
            "app.statistics_agent.tools.get_member_meeting_stats",
            return_value=role_rows,
        ),
        patch(
            "app.services.meeting_stats.resolve_member",
            return_value=type(
                "Member",
                (),
                {"id": "mem-joyce", "full_name": "Joyce Feng", "username": "joyce"},
            )(),
        ),
    ):
        hosting = await stats_tools.apply_member_role_matrix(
            ctx,
            member="Joyce",
            role_group="hosting",
            group_by="member",
            include_meetings=False,
        )
        facilitator = await stats_tools.apply_member_role_matrix(
            ctx,
            member="Joyce",
            role_group="facilitator",
            group_by="member",
            include_meetings=False,
        )

    assert hosting["value"]["role_groups"]["hosting"] == [
        "TOM",
        "TTM",
        "GuestIntroHost",
        "MoT",
    ]
    assert hosting["value"]["role_groups"]["facilitator"] == [
        "SAA",
        "Timer",
        "Grammarian",
        "HarkMaster",
    ]
    assert hosting["value"]["groups"][0]["roles"] == {"MoT": 1}
    assert facilitator["value"]["groups"][0]["roles"] == {"Timer": 1}


@pytest.mark.asyncio
async def test_member_role_matrix_rejects_role_filter_and_group_together():
    ctx = FakeCtx(deps=_deps())

    with pytest.raises(ModelRetry, match="Use either role_filter"):
        await stats_tools.apply_member_role_matrix(
            ctx,
            role_filter="IE",
            role_group="evaluation",
        )


@pytest.mark.asyncio
async def test_member_award_matrix_groups_resolved_and_unresolved_winners():
    ctx = FakeCtx(deps=_deps())
    award_rows = [
        {
            "award_id": "a1",
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "winner_resolved": True,
            "winner_name": "Frank Zeng",
            "meeting_id": "m1",
            "meeting_date": "2026-01-07",
            "meeting_theme": "A",
            "meeting_no": 451,
            "category": "Best Evaluator",
        },
        {
            "award_id": "a2",
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "winner_resolved": True,
            "winner_name": "Frank",
            "meeting_id": "m2",
            "meeting_date": "2026-01-14",
            "meeting_theme": "B",
            "meeting_no": 452,
            "category": "Best Evaluator",
        },
        {
            "award_id": "a3",
            "member_id": None,
            "username": None,
            "full_name": None,
            "winner_resolved": False,
            "winner_name": "Guest A",
            "meeting_id": "m3",
            "meeting_date": "2026-01-21",
            "meeting_theme": "C",
            "meeting_no": 453,
            "category": "Best Joke",
        },
    ]

    with patch("app.statistics_agent.tools.get_member_award_stats", return_value=award_rows):
        out = await stats_tools.apply_member_award_matrix(
            ctx,
            date_from="2026-01-01",
            date_to="2026-12-31",
            group_by="winner_category",
            include_meetings=False,
        )

    assert out["coverage"]["source"] == "dashboard_member_award_matrix"
    assert out["value"]["total_rows"] == 3
    assert out["value"]["unresolved_winners"] == [{"winner_name": "Guest A", "count": 1}]
    assert out["value"]["groups"] == [
        {
            "winner_key": "member:mem-frank",
            "winner_name": "Frank Zeng",
            "winner_resolved": True,
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "name": "Frank Zeng",
            "category": "Best Evaluator",
            "count": 2,
            "meeting_count": 2,
        },
        {
            "winner_key": "raw:Guest A",
            "winner_name": "Guest A",
            "winner_resolved": False,
            "member_id": None,
            "username": None,
            "full_name": None,
            "name": "Guest A",
            "category": "Best Joke",
            "count": 1,
            "meeting_count": 1,
        },
    ]
    assert out["value"]["references"][0]["award_id"] == "a3"
    assert out["value"]["reference_total"] == 3
    assert out["value"]["observed_categories"] == ["Best Evaluator", "Best Joke"]


@pytest.mark.asyncio
async def test_member_award_matrix_category_filters_accept_standard_keys_and_raw_custom_text():
    ctx = FakeCtx(deps=_deps())
    award_rows = [
        {
            "award_id": "a1",
            "member_id": "mem-joyce",
            "username": "joyce",
            "full_name": "Joyce Feng",
            "winner_resolved": True,
            "winner_name": "Joyce Feng",
            "meeting_id": "m1",
            "meeting_date": "2026-01-07",
            "meeting_theme": "A",
            "meeting_no": 451,
            "category": "Best Prepared Speaker",
        },
        {
            "award_id": "a2",
            "member_id": None,
            "username": None,
            "full_name": None,
            "winner_resolved": False,
            "winner_name": "Guest A",
            "meeting_id": "m2",
            "meeting_date": "2026-01-14",
            "meeting_theme": "B",
            "meeting_no": 452,
            "category": "Best Joke",
        },
        {
            "award_id": "a3",
            "member_id": None,
            "username": None,
            "full_name": None,
            "winner_resolved": False,
            "winner_name": "Guest B",
            "meeting_id": "m3",
            "meeting_date": "2026-01-21",
            "meeting_theme": "C",
            "meeting_no": 453,
            "category": "Custom",
        },
    ]

    with patch("app.statistics_agent.tools.get_member_award_stats", return_value=award_rows):
        out = await stats_tools.apply_member_award_matrix(
            ctx,
            category_filters=["BestPS", "Best Joke"],
            group_by="category",
            include_meetings=False,
        )
        custom = await stats_tools.apply_member_award_matrix(
            ctx,
            category_filters=["Custom"],
            group_by="category",
            include_meetings=False,
        )

    assert out["scope"]["resolved_category_filters"] == ["best joke", "best prepared speaker"]
    assert [group["category"] for group in out["value"]["groups"]] == [
        "Best Joke",
        "Best Prepared Speaker",
    ]
    assert custom["value"]["groups"] == [
        {
            "category": "Custom",
            "name": "Custom",
            "count": 1,
            "winner_count": 1,
            "meeting_count": 1,
        }
    ]


@pytest.mark.asyncio
async def test_member_award_matrix_member_filter_uses_canonical_resolver():
    ctx = FakeCtx(deps=_deps())
    award_rows = [
        {
            "award_id": "a1",
            "member_id": "mem-frank",
            "username": "frank",
            "full_name": "Frank Zeng",
            "winner_resolved": True,
            "winner_name": "Frank",
            "meeting_id": "m1",
            "meeting_date": "2026-01-07",
            "meeting_theme": "A",
            "meeting_no": 451,
            "category": "Best Evaluator",
        },
        {
            "award_id": "a2",
            "member_id": None,
            "username": None,
            "full_name": None,
            "winner_resolved": False,
            "winner_name": "Frank",
            "meeting_id": "m2",
            "meeting_date": "2026-01-14",
            "meeting_theme": "B",
            "meeting_no": 452,
            "category": "Best Joke",
        },
    ]

    with (
        patch("app.statistics_agent.tools.get_member_award_stats", return_value=award_rows),
        patch(
            "app.services.meeting_stats.resolve_member",
            return_value=type(
                "Member",
                (),
                {"id": "mem-frank", "full_name": "Frank Zeng", "username": "frank"},
            )(),
        ),
    ):
        out = await stats_tools.apply_member_award_matrix(
            ctx,
            member="Frank",
            group_by="winner",
            include_meetings=False,
        )

    assert out["value"]["total_rows"] == 1
    assert out["value"]["groups"][0]["winner_key"] == "member:mem-frank"
    assert out["value"]["unresolved_winners"] == []


@pytest.mark.asyncio
async def test_member_award_matrix_retries_for_unknown_custom_category():
    ctx = FakeCtx(deps=_deps())
    award_rows = [
        {
            "award_id": "a1",
            "member_id": None,
            "username": None,
            "full_name": None,
            "winner_resolved": False,
            "winner_name": "Guest A",
            "meeting_id": "m1",
            "meeting_date": "2026-01-07",
            "meeting_theme": "A",
            "meeting_no": 451,
            "category": "Best Joke",
        }
    ]

    with patch("app.statistics_agent.tools.get_member_award_stats", return_value=award_rows):
        with pytest.raises(ModelRetry, match="Best Joke"):
            await stats_tools.apply_member_award_matrix(
                ctx,
                category_filters=["Best Pun"],
            )


@pytest.mark.asyncio
async def test_member_award_matrix_standard_category_with_no_rows_returns_zero():
    ctx = FakeCtx(deps=_deps())

    with patch("app.statistics_agent.tools.get_member_award_stats", return_value=[]):
        out = await stats_tools.apply_member_award_matrix(
            ctx,
            category_filters=["BestPS"],
            group_by="winner",
        )

    assert out["value"]["total_rows"] == 0
    assert out["value"]["groups"] == []
    assert out["scope"]["resolved_category_filters"] == ["best prepared speaker"]


@pytest.mark.asyncio
async def test_member_award_matrix_retries_when_relative_date_scope_missing():
    ctx = FakeCtx(deps=_deps(message="今年谁拿 Best Evaluator 最多?", today="2026-04-28"))

    with pytest.raises(ModelRetry, match='date_from="2026-01-01"'):
        await stats_tools.apply_member_award_matrix(
            ctx,
            category_filters=["BestEvaluator"],
            group_by="winner",
        )


@pytest.mark.asyncio
async def test_stats_deps_pool_cache_field_default_is_none():
    """Stats deps owns the same per-turn lookup cache as the meeting
    agent, so parallel lookup fan-out shares one recent-meetings fetch."""
    deps = _deps()
    assert deps.meeting_pool_cache is None
    assert deps.meeting_pool_lock is None


@pytest.mark.asyncio
async def test_stats_agent_lookup_meeting_shares_pool_across_parallel_calls():
    """Cross-language theme + intro fan-out can produce multiple
    `lookup_meeting` calls within one turn. They share the deps cache
    so only one Supabase fetch happens."""
    from app.services import meeting_lookup as ml
    from app.statistics_agent.agent import lookup_meeting as agent_tool

    fake_pool = [
        {
            "id": "u1",
            "no": 451,
            "type": "Regular",
            "theme": "T",
            "date": "2026-04-25",
            "manager": {"name": "Joyce Feng"},
            "segments": [],
        },
    ]
    deps = _deps()
    ctx = FakeCtx(deps=deps)
    with patch(
        "app.services.meeting_lookup.db_meetings_recent",
        return_value=fake_pool,
    ) as mock_pool:
        results = await asyncio.gather(
            agent_tool(ctx, theme_substring="T"),
            agent_tool(ctx, theme_substring="t"),
            agent_tool(ctx, introduction_substring="x"),
            agent_tool(ctx, name_substring="Joyce"),
        )

    assert mock_pool.call_count == 1
    assert all("cards" in r for r in results)
    assert ml.MeetingFilters is not None


@pytest.mark.asyncio
async def test_stats_agent_does_not_register_mutation_tools():
    """The statistics agent must stay read-only."""
    from app.statistics_agent.agent import agent

    forbidden = {
        "set_role",
        "set_type",
        "set_duration",
        "set_buffer",
        "set_meta",
        "add_segment",
        "remove_segment",
        "move_segment",
        "swap_roles",
        "swap_time",
        "shift_segment_time",
        "create_from_text",
        "create_from_image",
        "create_from_template",
        "clone_from_meeting",
        "revert_last_turn",
        "revert_to_turn",
    }
    registered = {tool_def.name for tool_def in agent._function_toolset.tools.values()}
    leaked = forbidden & registered
    assert not leaked, (
        f"Mutation tool(s) leaked into the stats agent: {sorted(leaked)}. "
        f"Stats is READ-ONLY. Move these back to the meeting agent."
    )


@pytest.mark.asyncio
async def test_stats_agent_only_registers_lookup_and_preview_tools():
    """Only agreed tools should be registered."""
    from app.statistics_agent.agent import agent

    registered = {tool_def.name for tool_def in agent._function_toolset.tools.values()}
    assert registered == {
        "lookup_meeting",
        "preview_meeting",
        "meeting_attendance_list",
        "member_role_matrix",
        "member_award_matrix",
    }
