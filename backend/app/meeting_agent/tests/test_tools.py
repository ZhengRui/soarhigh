import re
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from pydantic_ai import ModelRetry

from app.meeting_agent.models import Agenda, AgendaDeps, Meta, Segment
from app.meeting_agent.store import InMemorySessionStore, TurnRecord
from app.meeting_agent.timing import recompute_start_times
from app.meeting_agent.tools import (
    apply_add_segment,
    apply_clone_from_meeting,
    apply_create_from_image,
    apply_create_from_text,
    apply_lookup_meeting,
    apply_move_segment,
    apply_remove_segment,
    apply_revert_last_turn,
    apply_revert_to_turn,
    apply_set_buffer,
    apply_set_duration,
    apply_set_meta,
    apply_set_role,
    apply_set_type,
    apply_shift_segment_time,
    apply_swap_roles,
    apply_swap_time,
)


@dataclass
class FakeCtx:
    deps: AgendaDeps


def make_deps():
    return AgendaDeps(
        session_id="t",
        agenda=Agenda(
            meta=Meta(start_time="19:15"),
            segments=[
                Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Liz"),
                Segment(id="s2", type="TOM", start_time="19:33", duration=2, role_taker=""),
            ],
        ),
    )


def make_deps_3():
    """3-segment agenda with known start times so downstream cascade is easy to assert."""
    agenda = Agenda(
        meta=Meta(start_time="19:15"),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:15", duration=5, role_taker="Liz"),
            Segment(
                id="s2",
                type="TOM",
                start_time="19:20",
                duration=10,
                role_taker="",
                buffer_before=0,
            ),
            Segment(
                id="s3",
                type="Prepared Speech",
                start_time="19:30",
                duration=7,
                role_taker="Joyce",
                buffer_before=0,
            ),
        ],
    )
    return AgendaDeps(session_id="t", agenda=agenda)


def _fake_meeting_with_segments(segment_count: int = 3):
    from app.models.meeting import Attendee, Meeting
    from app.models.meeting import Segment as MeetingSegment

    segments = []
    for i in range(segment_count):
        start_min = 30 + i * 3
        segments.append(
            MeetingSegment(
                id=f"legacy-{i}",
                type=["SAA", "TOM", "Closing Remarks"][i] if i < 3 else "Custom",
                start_time=f"19:{start_min:02d}",
                end_time=f"19:{start_min + 2:02d}",
                duration="2",
                role_taker=Attendee(
                    id=None,
                    name=["Joyce Feng", "Rui Zheng", "Amy Fang"][i] if i < 3 else "",
                    member_id="",
                ),
                title="",
                content="",
                related_segment_ids="",
            )
        )
    return Meeting(
        id=None,
        no=391,
        type="Regular",
        theme="MockTheme",
        manager=Attendee(id=None, name="Rui Zheng", member_id=""),
        date="2026-04-30",
        start_time="19:30",
        end_time="21:30",
        location="L",
        introduction="",
        status="draft",
        awards=[],
        segments=segments,
    )


def _fake_db_meetings():
    return [
        {
            "id": "u1",
            "no": 389,
            "type": "Regular",
            "theme": "T3",
            "date": "2026-04-15",
            "manager": {"name": "Joyce Feng"},
            "segments": [{}] * 18,
        },
        {
            "id": "u2",
            "no": 388,
            "type": "Workshop",
            "theme": "T2",
            "date": "2026-04-08",
            "manager": {"name": "Rui Zheng"},
            "segments": [{}] * 16,
        },
        {
            "id": "u3",
            "no": 387,
            "type": "Regular",
            "theme": "T1",
            "date": "2026-04-01",
            "manager": {"name": "Leta Li"},
            "segments": [{}] * 17,
        },
    ]


async def _seed_lookup_turn(store: InMemorySessionStore, session_id: str, no: int):
    await store.save_turn(
        session_id,
        user_id=None,
        turn=TurnRecord(
            seq=1,
            user_message=f"复制 #{no}",
            assistant_text="Found it. 确认从这期克隆吗?",
            tool_trace=[
                {
                    "id": "tc1",
                    "name": "lookup_meeting",
                    "args": {"query": str(no)},
                    "status": "ok",
                    "result": [
                        {
                            "no": no,
                            "type": "Regular",
                            "date": "2024-11-05",
                            "theme": "Old",
                            "manager_name": "X",
                            "segment_count": 2,
                        }
                    ],
                }
            ],
            agenda_before={"meta": {}, "segments": []},
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )


def _full_meeting_dict_for_clone():
    return {
        "id": "u1",
        "no": 387,
        "type": "Regular",
        "theme": "Old Theme",
        "manager": {"id": None, "name": "Old Manager", "member_id": "x"},
        "date": "2024-11-05",
        "start_time": "19:15",
        "end_time": "21:30",
        "location": "Loc Stable",
        "introduction": "Old intro",
        "status": "published",
        "awards": [],
        "segments": [
            {
                "id": "1",
                "type": "SAA",
                "start_time": "19:30",
                "end_time": "19:33",
                "duration": "3",
                "role_taker": {"id": None, "name": "Joyce Feng", "member_id": "j"},
                "title": "",
                "content": "",
                "related_segment_ids": "",
            },
            {
                "id": "2",
                "type": "TOM",
                "start_time": "19:33",
                "end_time": "19:35",
                "duration": "2",
                "role_taker": {"id": None, "name": "Rui Zheng", "member_id": "r"},
                "title": "",
                "content": "",
                "related_segment_ids": "",
            },
        ],
    }


@pytest.mark.asyncio
async def test_apply_create_from_text_replaces_agenda():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools.plan_meeting_from_text", return_value=_fake_meeting_with_segments()):
        result = await apply_create_from_text(
            ctx,
            raw_text=(
                "SOARHIGH 391st meeting: MockTheme\n"
                "✍ Theme: MockTheme\n"
                "📅 Date: 2026-04-30\n"
                "⏰ Time: 19:30 - 21:30\n"
                "📍 Location: L\n"
                "👧MM: Rui Zheng\n"
            ),
        )

    assert len(deps.agenda.segments) == 3
    assert deps.agenda.meta.no == 391
    assert deps.agenda.meta.theme == "MockTheme"
    assert deps.agenda.meta.manager == "Rui Zheng"
    assert deps.agenda.segments[0].id == "s1"
    assert result["created"] is True
    assert result["segment_count"] == 3
    assert result["meeting_summary"]["no"] == 391
    assert result["meeting_summary"]["manager"] == "Rui Zheng"
    assert result["missing_required_fields"] == []
    assert "validation_issues" in result


def test_strip_membership_suffix():
    """Defense-in-depth: any role_taker / manager arg coming in with a
    "(member)" / "(guest)" suffix (echoed from a past table) gets stripped
    so the underlying field never carries the annotation."""
    from app.meeting_agent.tools import _strip_membership_suffix

    assert _strip_membership_suffix("Joyce Feng (member)") == "Joyce Feng"
    assert _strip_membership_suffix("Lucas (guest)") == "Lucas"
    assert _strip_membership_suffix("All (All)") == "All"
    assert _strip_membership_suffix("  Joyce Feng (member)  ") == "Joyce Feng"
    # Case-insensitive + full-width parens.
    assert _strip_membership_suffix("Liz Huang (Member)") == "Liz Huang"
    assert _strip_membership_suffix("张三（成员）") == "张三（成员）"  # noqa: RUF001 — CJK 成员 not in the regex; left intact
    assert _strip_membership_suffix("Joyce Feng（member）") == "Joyce Feng"  # noqa: RUF001 — fullwidth parens
    # Pass-through cases.
    assert _strip_membership_suffix("Joyce Feng") == "Joyce Feng"
    assert _strip_membership_suffix("") == ""
    assert _strip_membership_suffix(None) == ""
    # Don't mistake a parenthesized substring inside the name.
    assert _strip_membership_suffix("Foo (Trainer)") == "Foo (Trainer)"


@pytest.mark.asyncio
async def test_apply_set_role_strips_membership_suffix_from_arg():
    """Regression: model has been observed copying the annotated display
    string ('Joyce Feng (member)') into a tool arg. The tool must strip
    it so the agenda data stays clean."""
    from app.meeting_agent.tools import apply_set_role

    deps = make_deps()
    deps.agenda.segments[0].id = "s1"
    ctx = FakeCtx(deps=deps)
    result = apply_set_role(ctx, segment_id="s1", role_taker="Joyce Feng (member)")
    assert deps.agenda.segments[0].role_taker == "Joyce Feng"
    assert result["role_taker"] == "Joyce Feng"


def test_apply_add_segment_strips_membership_suffix_from_arg():
    from app.meeting_agent.tools import apply_add_segment

    deps = make_deps()
    deps.agenda.segments[0].id = "s1"
    ctx = FakeCtx(deps=deps)
    apply_add_segment(
        ctx,
        type="Lucky Draw",
        duration_min=5,
        after_id="s1",
        role_taker="Lucas (guest)",
    )
    new_seg = deps.agenda.segments[1]
    assert new_seg.role_taker == "Lucas"


def test_apply_set_meta_strips_membership_suffix_from_manager():
    from app.meeting_agent.tools import apply_set_meta

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    apply_set_meta(ctx, field="manager", value="Vicky Yang (member)")
    assert deps.agenda.meta.manager == "Vicky Yang"


@pytest.mark.asyncio
async def test_apply_preview_meeting_returns_full_segments_without_mutating_agenda():
    """preview_meeting must surface the historical meeting's full segment list
    so the model can show it to the user before they commit to clone — and
    must NOT touch the current agenda state (it's read-only)."""
    from app.meeting_agent.tools import apply_preview_meeting

    deps = make_deps()
    original_segments = list(deps.agenda.segments)
    original_meta = deps.agenda.meta.model_copy()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=_full_meeting_dict_for_clone()):
        result = await apply_preview_meeting(ctx, no=387)

    assert result["no"] == 387
    assert result["type"] == "Regular"
    assert result["theme"] == "Old Theme"
    assert result["manager"] == "Old Manager"
    assert result["start_time"] == "19:15"
    # Full segment list with the four model-facing fields per row.
    assert len(result["segments"]) == 2
    assert result["segments"][0] == {
        "type": "SAA",
        "start_time": "19:30",
        "duration": 3,
        "role_taker": "Joyce Feng",
    }
    assert result["segments"][1]["role_taker"] == "Rui Zheng"
    # Current agenda untouched.
    assert deps.agenda.segments == original_segments
    assert deps.agenda.meta == original_meta


@pytest.mark.asyncio
async def test_apply_preview_meeting_unknown_no_raises_modelretry():
    from app.meeting_agent.tools import apply_preview_meeting

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=None):
        with pytest.raises(ModelRetry, match="not found"):
            await apply_preview_meeting(ctx, no=9999)


def test_db_get_meeting_by_no_uses_two_targeted_queries():
    """Regression: the lookup must NOT scan the bulk `_db_meetings_recent` page.
    That path builds a `.in_(500 meeting_ids)` URL (~18 KB) which under
    concurrent calls (e.g. 3 parallel preview_meeting on the same turn)
    overflows PostgREST / cloudflare URL-length limits and returns 400
    "JSON could not be generated" — also caps segments at 1000 rows so
    late-time segments disappear. Replace with two cheap targeted queries:
    `get_meeting_id_by_no` then `get_meeting_by_id`."""
    from app.meeting_agent.tools import _db_get_meeting_by_no

    full_complete = {
        "id": "uuid-425",
        "no": 425,
        "type": "Workshop",
        "manager": {"id": None, "name": "Joyce", "member_id": ""},
        "segments": [
            {"id": "1", "type": "SAA", "start_time": "19:30", "duration": "2"},
            {"id": "2", "type": "Workshop", "start_time": "20:08", "duration": "29"},
            {"id": "3", "type": "Awards", "start_time": "21:11", "duration": "3"},
            {"id": "4", "type": "Closing Remarks", "start_time": "21:14", "duration": "1"},
        ],
        "start_time": "19:15",
        "end_time": "21:30",
    }
    with (
        patch("app.meeting_agent.tools.get_meeting_id_by_no", return_value="uuid-425") as mock_id,
        patch("app.meeting_agent.tools.get_meeting_by_id", return_value=full_complete) as mock_full,
        patch("app.meeting_agent.tools._db_meetings_recent") as mock_bulk,
    ):
        result = _db_get_meeting_by_no(425)

    mock_id.assert_called_once_with(425)
    mock_full.assert_called_once_with("uuid-425", user_id=None)
    # The bulk-recent path must NOT be touched anymore.
    mock_bulk.assert_not_called()
    assert len(result["segments"]) == 4
    assert result["segments"][-1]["type"] == "Closing Remarks"


def test_db_get_meeting_by_no_serializes_concurrent_callers():
    """supabase-py wraps a SYNC httpx client which is NOT thread-safe.
    When several tool calls in one turn (e.g. parallel `preview_meeting`)
    drive concurrent worker-thread DB queries, the shared httpx state
    corrupts and the upstream returns `RemoteProtocolError: Server
    disconnected`. The agent-side helper must hold a module-level lock
    so concurrent callers fall through one at a time."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.meeting_agent.tools import _db_get_meeting_by_no

    in_flight = 0
    max_in_flight = 0
    barrier = threading.Lock()

    def _slow_id(no, user_id=None):
        nonlocal in_flight, max_in_flight
        with barrier:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        # Simulate the real query taking measurable time so any racing
        # threads have a chance to overlap if the lock is missing.
        threading.Event().wait(0.05)
        with barrier:
            in_flight -= 1
        return f"uuid-{no}"

    def _slow_full(meeting_id, user_id=None):
        nonlocal in_flight, max_in_flight
        with barrier:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        threading.Event().wait(0.05)
        with barrier:
            in_flight -= 1
        return {"id": meeting_id, "no": int(meeting_id.split("-")[1]), "segments": []}

    with (
        patch("app.meeting_agent.tools.get_meeting_id_by_no", side_effect=_slow_id),
        patch("app.meeting_agent.tools.get_meeting_by_id", side_effect=_slow_full),
    ):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_db_get_meeting_by_no, [446, 425, 413, 387]))

    # Lock guarantees at most one DB-helper invocation runs at a time.
    assert max_in_flight == 1, f"expected serialized DB access, observed {max_in_flight} concurrent"
    # All four calls returned correct results.
    assert [r["no"] for r in results] == [446, 425, 413, 387]


def test_db_get_meeting_by_no_returns_none_when_id_lookup_misses():
    """Unknown `no` → None (caller raises ModelRetry). No second query fired."""
    from app.meeting_agent.tools import _db_get_meeting_by_no

    with (
        patch("app.meeting_agent.tools.get_meeting_id_by_no", return_value=None),
        patch("app.meeting_agent.tools.get_meeting_by_id") as mock_full,
    ):
        assert _db_get_meeting_by_no(9999) is None
    mock_full.assert_not_called()


@pytest.mark.asyncio
async def test_apply_create_from_template_regular_2ps_replaces_agenda():
    """The deterministic template path: no LLM call, all 22 segments laid out
    back-to-back from the 19:15 warmup. Validates the structure surfaces in
    the standard tool-result shape so the model treats it identically to the
    other creation paths."""
    from app.meeting_agent.tools import apply_create_from_template

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = await apply_create_from_template(ctx, template="regular_2ps")

    assert result["created"] is True
    assert result["segment_count"] == 22
    # First segment: 19:15 warmup with role_taker "All".
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[0].duration == 15
    assert "Warm Up" in deps.agenda.segments[0].type
    assert deps.agenda.segments[0].role_taker == "All"
    # Second segment: SAA at 19:30 (back-to-back from warmup end).
    assert deps.agenda.segments[1].start_time == "19:30"
    # Last segment: Closing Remarks at 21:14, default president Amy Fang.
    last = deps.agenda.segments[-1]
    assert "Closing Remarks" in last.type
    assert last.role_taker == "Amy Fang"
    # Meeting type is set; meta.start_time matches the first segment (19:15)
    # so a later set_duration / add_segment doesn't re-anchor the warmup
    # forward by 15 min via recompute_start_times. end_time is left blank
    # so the user fills it (or accepts the implicit 21:15 from the agenda).
    assert deps.agenda.meta.type == "Regular"
    assert deps.agenda.meta.start_time == "19:15"
    # All buffer_before are 0 — back-to-back layout per user preference.
    assert all(seg.buffer_before == 0 for seg in deps.agenda.segments)


@pytest.mark.asyncio
async def test_apply_create_from_template_custom_single_segment():
    """The Custom template gives the user a blank slate with ONE placeholder
    segment — no warmup, no canonical structure (Custom meetings have no
    fixed convention; warmup-at-19:15 is Regular/Workshop only)."""
    from app.meeting_agent.tools import apply_create_from_template

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = await apply_create_from_template(ctx, template="custom")

    assert result["created"] is True
    assert result["segment_count"] == 1
    # Type is Custom, NOT Regular — the form's type-dropdown should reflect this.
    assert deps.agenda.meta.type == "Custom"
    # meta.start_time matches the placeholder segment (19:15) so subsequent
    # structural edits don't re-anchor it forward via recompute_start_times.
    assert deps.agenda.meta.start_time == "19:15"
    # Exactly ONE placeholder segment, positioned at the 19:15 / 15-min slot
    # (matches the standard pre-meeting warmup window so users have a sensible
    # anchor to start customizing from).
    assert len(deps.agenda.segments) == 1
    assert deps.agenda.segments[0].id == "s1"
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[0].duration == 15
    # Type is the generic placeholder, NOT the canonical Regular/Workshop
    # "Members and Guests Registration, Warm Up" label — Custom has no fixed
    # convention; user customizes via set_type.
    assert "Warm Up" not in deps.agenda.segments[0].type


@pytest.mark.asyncio
async def test_apply_create_from_template_aliases():
    """Template name lookup is case-insensitive and accepts common aliases the
    model is likely to forward verbatim from the user."""
    from app.meeting_agent.tools import apply_create_from_template

    for name in ("regular", "Regular_2_PS", "  Regular  ", "regular 2 ps", "2ps"):
        deps = make_deps()
        ctx = FakeCtx(deps=deps)
        result = await apply_create_from_template(ctx, template=name)
        assert result["segment_count"] == 22, f"alias {name!r} did not resolve to regular_2ps"

    # Custom template aliases resolve to the single-segment blank.
    for name in ("custom", "Custom_Blank", "BLANK"):
        deps = make_deps()
        ctx = FakeCtx(deps=deps)
        result = await apply_create_from_template(ctx, template=name)
        assert result["segment_count"] == 1, f"alias {name!r} did not resolve to custom"
        assert deps.agenda.meta.type == "Custom"


@pytest.mark.asyncio
async def test_template_warmup_survives_subsequent_structural_edit():
    """Regression: Regular template's 19:15 warmup must not shift forward
    when the user makes a structural edit that triggers recompute_start_times.
    Pre-fix, meta.start_time was 19:30 while seg[0].start_time was 19:15;
    set_duration / set_buffer / add_segment / etc. would re-anchor at 19:30
    and slide every segment forward by 15 minutes."""
    from app.meeting_agent.tools import apply_create_from_template, apply_set_duration

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    await apply_create_from_template(ctx, template="regular_2ps")
    assert deps.agenda.segments[0].start_time == "19:15"

    # Trigger a structural edit on a downstream segment — this calls
    # recompute_start_times which re-anchors from meta.start_time.
    saa = deps.agenda.segments[1]
    apply_set_duration(ctx, segment_id=saa.id, duration_min=5)

    # Warmup must STILL be at 19:15.
    assert (
        deps.agenda.segments[0].start_time == "19:15"
    ), "Warmup shifted off 19:15 after a structural edit — meta.start_time anchor mismatch"


@pytest.mark.asyncio
async def test_custom_template_segment_survives_subsequent_structural_edit():
    """Regression for Custom template: same anchor-mismatch foot-gun as the
    Regular template but with a single placeholder segment."""
    from app.meeting_agent.tools import apply_create_from_template, apply_set_duration

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    await apply_create_from_template(ctx, template="custom")
    assert deps.agenda.segments[0].start_time == "19:15"

    seg = deps.agenda.segments[0]
    apply_set_duration(ctx, segment_id=seg.id, duration_min=20)

    assert deps.agenda.segments[0].start_time == "19:15"


@pytest.mark.asyncio
async def test_apply_create_from_template_unknown_raises_modelretry():
    from app.meeting_agent.tools import apply_create_from_template

    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="Unknown template"):
        await apply_create_from_template(ctx, template="nonexistent")


def test_segments_summary_does_not_leak_membership_to_model():
    """Membership annotation is a pure render-layer concern handled by
    `_format_role_display` (route addendum) and the frontend form. The
    tool result the LLM sees must NEVER contain `(member)` / `(guest)` —
    if the model can see the annotated form, it has been observed to copy
    it back into a tool argument (e.g. add_segment role_taker), corrupting
    the agenda data."""
    from app.meeting_agent.models import Agenda, Meta, Segment
    from app.meeting_agent.tools import _segments_summary

    agenda = Agenda(
        meta=Meta(),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:30", duration=2, role_taker="Liz Huang"),
            Segment(id="s2", type="Opening Remarks", start_time="19:32", duration=2, role_taker="Lucas"),
            Segment(id="s3", type="Table Topic Session", start_time="19:34", duration=20, role_taker="All"),
        ],
    )
    out = _segments_summary(agenda)
    for row in out:
        assert "role_taker_display" not in row, (
            "role_taker_display must NOT be in segments tool result; "
            "membership annotation lives in render layer only"
        )
        # Plain bare names — exactly what the model should pass back as args.
        assert "(member)" not in row["role_taker"]
        assert "(guest)" not in row["role_taker"]
    assert out[0]["role_taker"] == "Liz Huang"
    assert out[1]["role_taker"] == "Lucas"
    assert out[2]["role_taker"] == "All"


def test_format_role_display_helper_for_render_layer():
    """`_format_role_display` is the deterministic helper the route addendum
    uses to render the segment table. Lives in tools.py because it shares the
    CLUB_MEMBERS source-of-truth import; never exported into a tool result."""
    from app.meeting_agent.tools import _format_role_display

    assert _format_role_display("Liz Huang") == "Liz Huang (member)"
    assert _format_role_display("amy fang") == "amy fang (member)"  # case-insensitive
    assert _format_role_display("Lucas") == "Lucas (guest)"
    assert _format_role_display("All") == "All"
    assert _format_role_display("") == "—"


@pytest.mark.asyncio
async def test_apply_create_from_text_preserves_planner_start_times():
    """The tool trusts the planner's start_times verbatim. Back-to-back
    layout and the 19:15 warmup are enforced via the developer prompt
    (Notes 2 and 8 in app/utils/prompts.py), NOT via tool-side recompute —
    re-anchoring on meta.start_time would overwrite the planner's pre-meeting
    warmup positioning."""
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    # _fake_meeting_with_segments lays out segments at 19:30 / 19:33 / 19:36.
    # The tool must NOT shift them; whatever the planner returned is what we keep.
    with patch("app.meeting_agent.tools.plan_meeting_from_text", return_value=_fake_meeting_with_segments()):
        await apply_create_from_text(
            ctx,
            raw_text=(
                "SOARHIGH 391st meeting: MockTheme\n"
                "✍ Theme: MockTheme\n"
                "📅 Date: 2026-04-30\n"
                "⏰ Time: 19:30 - 21:30\n"
                "📍 Location: L\n"
                "👧MM: Rui Zheng\n"
            ),
        )

    assert deps.agenda.segments[0].start_time == "19:30"
    assert deps.agenda.segments[1].start_time == "19:33"
    assert deps.agenda.segments[2].start_time == "19:36"


@pytest.mark.asyncio
async def test_apply_create_from_text_reports_missing_required_fields_from_source():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools.plan_meeting_from_text", return_value=_fake_meeting_with_segments()):
        result = await apply_create_from_text(
            ctx,
            raw_text=(
                "SOARHIGH 391st meeting: MockTheme\n"
                "✍ Theme: MockTheme\n"
                "📅 Date: 2026-04-30\n"
                "⏰ Time: 19:30 - 21:30\n"
                "📍 Location: L\n"
                "SAA: Joyce\n"
            ),
        )

    assert deps.agenda.meta.manager is None
    assert result["meeting_summary"]["manager"] is None
    assert {"field": "manager", "label": "Meeting Manager"} in result["missing_required_fields"]


@pytest.mark.asyncio
async def test_apply_create_from_text_propagates_value_error_as_modelretry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools.plan_meeting_from_text", side_effect=ValueError("OpenAI rate limit")):
        with pytest.raises(ModelRetry, match="rate limit"):
            await apply_create_from_text(ctx, raw_text="bad")


@pytest.mark.asyncio
async def test_lookup_by_digit_returns_single_match():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools._db_meetings_recent", return_value=_fake_db_meetings()):
        result = await apply_lookup_meeting(ctx, query="388")
    assert len(result) == 1
    assert result[0]["no"] == 388
    assert result[0]["type"] == "Workshop"


@pytest.mark.asyncio
async def test_lookup_by_descriptor_filters_by_type_recent_first():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools._db_meetings_recent", return_value=_fake_db_meetings()):
        result = await apply_lookup_meeting(ctx, query="最近一次 workshop")
    assert len(result) == 1
    assert result[0]["no"] == 388


@pytest.mark.asyncio
async def test_lookup_descriptor_returns_top_5_recent_when_no_filter():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools._db_meetings_recent", return_value=_fake_db_meetings()):
        result = await apply_lookup_meeting(ctx, query="上次")
    assert result[0]["no"] == 389


@pytest.mark.asyncio
async def test_lookup_unknown_digit_returns_empty():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with patch("app.meeting_agent.tools._db_meetings_recent", return_value=_fake_db_meetings()):
        result = await apply_lookup_meeting(ctx, query="999")
    assert result == []


@pytest.mark.asyncio
async def test_clone_from_meeting_clears_specified_fields(monkeypatch):
    store = InMemorySessionStore()
    from app.meeting_agent import store as store_module

    monkeypatch.setattr(store_module, "session_store", store)
    deps = make_deps()
    deps.session_id = "clone-happy"
    deps.current_user_message = "确认"
    ctx = FakeCtx(deps=deps)
    await _seed_lookup_turn(store, deps.session_id, 387)

    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=_full_meeting_dict_for_clone()):
        result = await apply_clone_from_meeting(ctx, no=387)

    assert deps.agenda.meta.no is None
    assert deps.agenda.meta.theme in (None, "")
    assert deps.agenda.meta.manager in (None, "")
    assert deps.agenda.meta.date in (None, "")
    assert deps.agenda.meta.introduction in (None, "")
    assert deps.agenda.meta.type == "Regular"
    assert deps.agenda.meta.start_time == "19:15"
    assert deps.agenda.meta.location == "Loc Stable"
    assert [s.role_taker for s in deps.agenda.segments] == ["", ""]
    assert [s.id for s in deps.agenda.segments] == ["s1", "s2"]
    assert result["cloned_from_no"] == 387
    assert result["segment_count"] == 2
    assert "validation_issues" in result


@pytest.mark.asyncio
async def test_clone_refuses_without_prior_lookup(monkeypatch):
    store = InMemorySessionStore()
    from app.meeting_agent import store as store_module

    monkeypatch.setattr(store_module, "session_store", store)
    deps = make_deps()
    deps.session_id = "clone-no-lookup"
    deps.current_user_message = "确认"
    ctx = FakeCtx(deps=deps)

    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=_full_meeting_dict_for_clone()):
        with pytest.raises(ModelRetry, match="lookup_meeting"):
            await apply_clone_from_meeting(ctx, no=387)
    assert deps.agenda.meta.start_time == "19:15"
    assert len(deps.agenda.segments) == 2


@pytest.mark.asyncio
async def test_clone_refuses_when_lookup_was_for_a_different_no(monkeypatch):
    store = InMemorySessionStore()
    from app.meeting_agent import store as store_module

    monkeypatch.setattr(store_module, "session_store", store)
    deps = make_deps()
    deps.session_id = "clone-wrong-no"
    deps.current_user_message = "确认"
    ctx = FakeCtx(deps=deps)
    await _seed_lookup_turn(store, deps.session_id, 999)

    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=_full_meeting_dict_for_clone()):
        with pytest.raises(ModelRetry, match="lookup_meeting"):
            await apply_clone_from_meeting(ctx, no=387)


@pytest.mark.asyncio
async def test_clone_refuses_without_explicit_confirmation(monkeypatch):
    store = InMemorySessionStore()
    from app.meeting_agent import store as store_module

    monkeypatch.setattr(store_module, "session_store", store)
    deps = make_deps()
    deps.session_id = "clone-no-confirm"
    deps.current_user_message = "不是这个"
    ctx = FakeCtx(deps=deps)
    await _seed_lookup_turn(store, deps.session_id, 387)

    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=_full_meeting_dict_for_clone()):
        with pytest.raises(ModelRetry, match="explicit confirmation"):
            await apply_clone_from_meeting(ctx, no=387)


@pytest.mark.asyncio
async def test_clone_from_meeting_unknown_no_raises_modelretry(monkeypatch):
    store = InMemorySessionStore()
    from app.meeting_agent import store as store_module

    monkeypatch.setattr(store_module, "session_store", store)
    deps = make_deps()
    deps.session_id = "clone-unknown"
    deps.current_user_message = "确认"
    ctx = FakeCtx(deps=deps)
    await _seed_lookup_turn(store, deps.session_id, 9999)

    with patch("app.meeting_agent.tools._db_get_meeting_by_no", return_value=None):
        with pytest.raises(ModelRetry, match="not found"):
            await apply_clone_from_meeting(ctx, no=9999)


@pytest.mark.asyncio
async def test_create_from_image_uses_deps_image_bytes():
    deps = make_deps()
    deps.image_data = b"fake-bytes"
    deps.image_content_type = "image/png"
    ctx = FakeCtx(deps=deps)

    with patch(
        "app.meeting_agent.tools.parse_meeting_agenda_image",
        return_value=_fake_meeting_with_segments(),
    ) as mock:
        result = await apply_create_from_image(ctx)
        mock.assert_called_once_with(b"fake-bytes", "image/png")

    assert len(deps.agenda.segments) == 3
    assert result["created"] is True
    assert deps.image_data is None
    assert deps.image_content_type is None


@pytest.mark.asyncio
async def test_create_from_image_refuses_when_no_image_attached():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="no image"):
        await apply_create_from_image(ctx)


def test_set_role_mutates_target_segment():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_role(ctx, segment_id="s2", role_taker="Joyce Feng")
    assert result["segment_id"] == "s2"
    assert result["role_taker"] == "Joyce Feng"
    assert deps.agenda.segments[1].role_taker == "Joyce Feng"
    # other segments untouched
    assert deps.agenda.segments[0].role_taker == "Liz"


# --- set_type ---


def test_set_type_changes_only_type():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    original_start = deps.agenda.segments[1].start_time
    original_duration = deps.agenda.segments[1].duration
    original_role = deps.agenda.segments[1].role_taker

    result = apply_set_type(ctx, segment_id="s2", type="Ice Breaker")

    assert result == {"segment_id": "s2", "type": "Ice Breaker"}
    assert deps.agenda.segments[1].type == "Ice Breaker"
    # Nothing else on this segment changed.
    assert deps.agenda.segments[1].start_time == original_start
    assert deps.agenda.segments[1].duration == original_duration
    assert deps.agenda.segments[1].role_taker == original_role
    # Other segments untouched.
    assert deps.agenda.segments[0].type == "SAA"


# --- set_duration ---


def test_set_duration_happy_path_recomputes_downstream():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # s1 was 5 min starting 19:15. Bump to 10 -> s2 shifts from 19:20 to 19:25,
    # and s3 shifts from 19:30 to 19:35.
    result = apply_set_duration(ctx, segment_id="s1", duration_min=10)

    assert result == {"segment_id": "s1", "duration_min": 10}
    assert deps.agenda.segments[0].duration == 10
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:25"
    assert deps.agenda.segments[2].start_time == "19:35"


def test_set_duration_zero_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="duration must be positive"):
        apply_set_duration(ctx, segment_id="s1", duration_min=0)
    # No mutation
    assert deps.agenda.segments[0].duration == 3


def test_set_duration_negative_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="duration must be positive"):
        apply_set_duration(ctx, segment_id="s1", duration_min=-5)
    assert deps.agenda.segments[0].duration == 3


# --- set_buffer ---


def test_set_buffer_happy_path_recomputes_downstream():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Adding a 3-min buffer before s2 should shift s2 from 19:20 -> 19:23,
    # and s3 from 19:30 -> 19:33.
    result = apply_set_buffer(ctx, segment_id="s2", buffer_min=3)

    assert result == {"segment_id": "s2", "buffer_min": 3}
    assert deps.agenda.segments[1].buffer_before == 3
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:23"
    assert deps.agenda.segments[2].start_time == "19:33"


def test_set_buffer_negative_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="buffer_min must be >= 0"):
        apply_set_buffer(ctx, segment_id="s2", buffer_min=-1)
    assert deps.agenda.segments[1].buffer_before == 0


# --- set_meta ---


def test_set_meta_theme_updates_field():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_meta(ctx, field="theme", value="Dream Big")

    assert result == {"field": "theme", "value": "Dream Big"}
    assert deps.agenda.meta.theme == "Dream Big"


def test_set_meta_type_updates_meeting_type():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_meta(ctx, field="type", value="Workshop")

    assert result == {"field": "type", "value": "Workshop"}
    assert deps.agenda.meta.type == "Workshop"


def test_set_meta_type_rejects_invalid_value():
    deps = make_deps()
    original_type = deps.agenda.meta.type
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="Meeting type must be one of"):
        apply_set_meta(ctx, field="type", value="Special Event")
    # Assert nothing was mutated on refusal.
    assert deps.agenda.meta.type == original_type


def test_set_meta_type_accepts_regular_workshop_custom():
    for t in ("Regular", "Workshop", "Custom"):
        deps = make_deps()
        ctx = FakeCtx(deps=deps)
        apply_set_meta(ctx, field="type", value=t)
        assert deps.agenda.meta.type == t


def test_set_meta_start_time_cascades_segment_times():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Shift meeting 45 min later: 19:15 -> 20:00.
    result = apply_set_meta(ctx, field="start_time", value="20:00")

    assert result == {"field": "start_time", "value": "20:00"}
    assert deps.agenda.meta.start_time == "20:00"
    assert deps.agenda.segments[0].start_time == "20:00"
    assert deps.agenda.segments[1].start_time == "20:05"
    assert deps.agenda.segments[2].start_time == "20:15"


def test_set_meta_unknown_field_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="Unknown meta field"):
        apply_set_meta(ctx, field="bogus", value="x")
    # No side-effects
    assert deps.agenda.meta.theme is None


def test_set_meta_end_time_is_editable():
    """end_time has to be editable via set_meta — it's listed in
    _REQUIRED_MEETING_FIELDS, so the agent will surface it as missing
    and must have a way to fix it. Pre-fix it was rejected as 'Unknown
    meta field' even though set_meta's docstring claimed it was 'derived'."""
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_meta(ctx, field="end_time", value="21:30")
    assert result == {"field": "end_time", "value": "21:30"}
    assert deps.agenda.meta.end_time == "21:30"
    # Empty value clears it (consistent with how other optional string
    # fields collapse to None on blank input).
    apply_set_meta(ctx, field="end_time", value="")
    assert deps.agenda.meta.end_time is None


def test_set_meta_no_non_integer_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="Meeting number must be an integer"):
        apply_set_meta(ctx, field="no", value="not-a-number")
    assert deps.agenda.meta.no is None


def test_set_meta_no_integer_coerces():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_meta(ctx, field="no", value="123")

    assert result == {"field": "no", "value": "123"}
    assert deps.agenda.meta.no == 123


def test_set_meta_empty_string_clears_field():
    deps = make_deps()
    deps.agenda.meta.theme = "Dream Big"
    ctx = FakeCtx(deps=deps)
    result = apply_set_meta(ctx, field="theme", value="")

    assert result == {"field": "theme", "value": ""}
    assert deps.agenda.meta.theme is None


# --- add_segment ---


def test_add_segment_after_anchor_inserts_at_next_index():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Insert a new 4-min segment after s2 -> new seg lands at index 2.
    # s1 5min @19:15, s2 10min @19:20, new 4min @19:30, s3 @19:34.
    result = apply_add_segment(
        ctx,
        type="Break",
        duration_min=4,
        after_id="s2",
    )

    assert result["type"] == "Break"
    assert result["duration_min"] == 4
    assert result["role_taker"] == ""
    assert result["inserted_at_index"] == 2
    assert len(deps.agenda.segments) == 4
    assert deps.agenda.segments[2].id == result["new_segment_id"]
    assert deps.agenda.segments[2].type == "Break"
    assert deps.agenda.segments[2].duration == 4
    # Downstream recompute
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:20"
    assert deps.agenda.segments[2].start_time == "19:30"
    assert deps.agenda.segments[3].start_time == "19:34"


def test_add_segment_before_anchor_inserts_at_anchor_index():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    result = apply_add_segment(
        ctx,
        type="Opening",
        duration_min=2,
        before_id="s1",
    )

    assert result["inserted_at_index"] == 0
    assert len(deps.agenda.segments) == 4
    assert deps.agenda.segments[0].type == "Opening"
    assert deps.agenda.segments[1].id == "s1"
    # New segment starts at meeting start time.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:17"
    assert deps.agenda.segments[2].start_time == "19:22"
    assert deps.agenda.segments[3].start_time == "19:32"


def test_add_segment_with_both_anchors_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="exactly one"):
        apply_add_segment(ctx, type="X", duration_min=3, after_id="s1", before_id="s2")
    assert len(deps.agenda.segments) == 3


def test_add_segment_with_no_anchor_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="exactly one"):
        apply_add_segment(ctx, type="X", duration_min=3)
    assert len(deps.agenda.segments) == 3


def test_add_segment_zero_duration_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="positive"):
        apply_add_segment(ctx, type="X", duration_min=0, after_id="s1")
    assert len(deps.agenda.segments) == 3


def test_add_segment_unknown_anchor_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown anchor"):
        apply_add_segment(ctx, type="X", duration_min=3, after_id="ghost")
    assert len(deps.agenda.segments) == 3


def test_add_segment_empty_type_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="non-empty"):
        apply_add_segment(ctx, type="   ", duration_min=3, after_id="s1")
    assert len(deps.agenda.segments) == 3


def test_add_segment_assigns_short_hex_id():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    result = apply_add_segment(ctx, type="Workshop", duration_min=5, after_id="s3")
    assert re.fullmatch(r"[0-9a-f]{5}", result["new_segment_id"])


def test_add_segment_role_taker_propagates():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    result = apply_add_segment(
        ctx,
        type="Joke Master",
        duration_min=2,
        after_id="s1",
        role_taker="Alice",
    )
    assert result["role_taker"] == "Alice"
    new_seg = next(s for s in deps.agenda.segments if s.id == result["new_segment_id"])
    assert new_seg.role_taker == "Alice"


# --- remove_segment ---


def test_remove_segment_shrinks_list():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    result = apply_remove_segment(ctx, segment_id="s2")

    assert result == {"removed_segment_id": "s2"}
    assert len(deps.agenda.segments) == 2
    assert [s.id for s in deps.agenda.segments] == ["s1", "s3"]
    # s3 now follows s1 directly: 19:15 + 5 = 19:20.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:20"


def test_remove_segment_unknown_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_remove_segment(ctx, segment_id="ghost")
    assert len(deps.agenda.segments) == 3


# --- move_segment ---


def test_move_segment_after_anchor():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Move s1 to after s3 -> [s2, s3, s1].
    result = apply_move_segment(ctx, segment_id="s1", after_id="s3")

    assert result["segment_id"] == "s1"
    assert result["new_index"] == 2
    assert [s.id for s in deps.agenda.segments] == ["s2", "s3", "s1"]
    # s2 10min @19:15, s3 7min @19:25, s1 5min @19:32.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:25"
    assert deps.agenda.segments[2].start_time == "19:32"


def test_move_segment_before_anchor():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Move s3 to before s1 -> [s3, s1, s2].
    result = apply_move_segment(ctx, segment_id="s3", before_id="s1")

    assert result["segment_id"] == "s3"
    assert result["new_index"] == 0
    assert [s.id for s in deps.agenda.segments] == ["s3", "s1", "s2"]
    # s3 7min @19:15, s1 5min @19:22, s2 10min @19:27.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:22"
    assert deps.agenda.segments[2].start_time == "19:27"


def test_move_segment_to_itself_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="itself"):
        apply_move_segment(ctx, segment_id="s2", after_id="s2")
    assert [s.id for s in deps.agenda.segments] == ["s1", "s2", "s3"]


def test_move_segment_both_anchors_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="exactly one"):
        apply_move_segment(ctx, segment_id="s1", after_id="s2", before_id="s3")


def test_move_segment_unknown_segment_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_move_segment(ctx, segment_id="ghost", after_id="s1")


def test_move_segment_unknown_anchor_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown anchor"):
        apply_move_segment(ctx, segment_id="s1", after_id="ghost")


# --- shift_segment_time ---


def test_shift_later_positive_delta_happy_path():
    deps = make_deps_3()
    # Give s2 a buffer_before of 2 so we have something to inspect.
    deps.agenda.segments[1].buffer_before = 2
    ctx = FakeCtx(deps=deps)

    result = apply_shift_segment_time(ctx, segment_id="s2", delta_min=3)

    assert result["segment_id"] == "s2"
    assert result["delta_min"] == 3
    assert result["new_buffer_before"] == 5
    assert result["direction"] == "later"
    assert deps.agenda.segments[1].buffer_before == 5
    # s1 @19:15 (5m) -> s2 @19:15+5+5=19:25 -> s3 @19:25+10=19:35.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:25"
    assert deps.agenda.segments[2].start_time == "19:35"


def test_shift_earlier_within_gap():
    deps = make_deps_3()
    deps.agenda.segments[1].buffer_before = 5
    # Recompute so we start from a self-consistent state.
    recompute_start_times(deps.agenda)
    ctx = FakeCtx(deps=deps)

    result = apply_shift_segment_time(ctx, segment_id="s2", delta_min=-3)

    assert result["delta_min"] == -3
    assert result["new_buffer_before"] == 2
    assert result["direction"] == "earlier"
    assert deps.agenda.segments[1].buffer_before == 2
    # s1 @19:15 (5m) -> s2 @19:15+5+2=19:22 -> s3 @19:22+10=19:32.
    assert deps.agenda.segments[1].start_time == "19:22"
    assert deps.agenda.segments[2].start_time == "19:32"


def test_shift_earlier_exceeds_gap_raises():
    deps = make_deps_3()
    deps.agenda.segments[1].buffer_before = 2
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="min gap available"):
        apply_shift_segment_time(ctx, segment_id="s2", delta_min=-5)
    # Unchanged
    assert deps.agenda.segments[1].buffer_before == 2


def test_shift_first_segment_earlier_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="first segment"):
        apply_shift_segment_time(ctx, segment_id="s1", delta_min=-1)


def test_shift_zero_delta_is_noop():
    deps = make_deps_3()
    before_bufs = [s.buffer_before for s in deps.agenda.segments]
    before_starts = [s.start_time for s in deps.agenda.segments]
    ctx = FakeCtx(deps=deps)

    result = apply_shift_segment_time(ctx, segment_id="s2", delta_min=0)

    assert result == {"segment_id": "s2", "delta_min": 0}
    assert [s.buffer_before for s in deps.agenda.segments] == before_bufs
    assert [s.start_time for s in deps.agenda.segments] == before_starts


def test_shift_unknown_segment_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_shift_segment_time(ctx, segment_id="ghost", delta_min=3)


# --- swap_roles ---


def test_swap_roles_exchanges_only_role_taker():
    deps = make_deps_3()
    # s1.role_taker="Liz"; give s2 a real name so the swap is observable.
    deps.agenda.segments[0].role_taker = "Alice"
    deps.agenda.segments[1].role_taker = "Bob"
    # Capture pre-swap state for other fields.
    s1_before = {
        "type": deps.agenda.segments[0].type,
        "duration": deps.agenda.segments[0].duration,
        "start_time": deps.agenda.segments[0].start_time,
        "buffer_before": deps.agenda.segments[0].buffer_before,
    }
    s2_before = {
        "type": deps.agenda.segments[1].type,
        "duration": deps.agenda.segments[1].duration,
        "start_time": deps.agenda.segments[1].start_time,
        "buffer_before": deps.agenda.segments[1].buffer_before,
    }
    ctx = FakeCtx(deps=deps)

    result = apply_swap_roles(ctx, segment_id_a="s1", segment_id_b="s2")

    assert result == {
        "segment_id_a": "s1",
        "segment_id_b": "s2",
        "role_taker_a": "Bob",
        "role_taker_b": "Alice",
    }
    assert deps.agenda.segments[0].role_taker == "Bob"
    assert deps.agenda.segments[1].role_taker == "Alice"
    # Every other field on each segment is unchanged.
    assert deps.agenda.segments[0].type == s1_before["type"]
    assert deps.agenda.segments[0].duration == s1_before["duration"]
    assert deps.agenda.segments[0].start_time == s1_before["start_time"]
    assert deps.agenda.segments[0].buffer_before == s1_before["buffer_before"]
    assert deps.agenda.segments[1].type == s2_before["type"]
    assert deps.agenda.segments[1].duration == s2_before["duration"]
    assert deps.agenda.segments[1].start_time == s2_before["start_time"]
    assert deps.agenda.segments[1].buffer_before == s2_before["buffer_before"]
    # Untouched third segment.
    assert deps.agenda.segments[2].role_taker == "Joyce"


def test_swap_roles_with_same_id_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="itself"):
        apply_swap_roles(ctx, segment_id_a="s1", segment_id_b="s1")
    assert deps.agenda.segments[0].role_taker == "Liz"


def test_swap_roles_unknown_id_a_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_swap_roles(ctx, segment_id_a="ghost", segment_id_b="s2")
    # Unchanged.
    assert deps.agenda.segments[0].role_taker == "Liz"
    assert deps.agenda.segments[2].role_taker == "Joyce"


def test_swap_roles_unknown_id_b_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_swap_roles(ctx, segment_id_a="s1", segment_id_b="ghost")
    assert deps.agenda.segments[0].role_taker == "Liz"
    assert deps.agenda.segments[2].role_taker == "Joyce"


def test_swap_roles_does_not_recompute_times():
    deps = make_deps_3()
    starts_before = [s.start_time for s in deps.agenda.segments]
    ctx = FakeCtx(deps=deps)

    apply_swap_roles(ctx, segment_id_a="s1", segment_id_b="s3")

    starts_after = [s.start_time for s in deps.agenda.segments]
    assert starts_after == starts_before


# --- swap_time ---


def test_swap_time_adjacent_segments():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Swap s1 and s2 -> order [s2, s1, s3].
    result = apply_swap_time(ctx, segment_id_a="s1", segment_id_b="s2")

    assert result["segment_id_a"] == "s1"
    assert result["segment_id_b"] == "s2"
    # s1 was at idx 0, s2 at idx 1. After swap a is at 1, b at 0.
    assert result["new_index_a"] == 1
    assert result["new_index_b"] == 0
    assert [s.id for s in deps.agenda.segments] == ["s2", "s1", "s3"]
    # s2 10min @19:15, s1 5min @19:25, s3 7min @19:30.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:25"
    assert deps.agenda.segments[2].start_time == "19:30"


def test_swap_time_non_adjacent_segments():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    # Swap s1 and s3 -> order [s3, s2, s1].
    result = apply_swap_time(ctx, segment_id_a="s1", segment_id_b="s3")

    assert result["new_index_a"] == 2
    assert result["new_index_b"] == 0
    assert [s.id for s in deps.agenda.segments] == ["s3", "s2", "s1"]
    # s3 7min @19:15, s2 10min @19:22, s1 5min @19:32.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:22"
    assert deps.agenda.segments[2].start_time == "19:32"


def test_swap_time_swaps_buffer_before_values():
    deps = make_deps_3()
    # Set buffer_before on s2 and s3 so we can track slot-level gaps.
    deps.agenda.segments[1].buffer_before = 5  # gap at slot 1
    deps.agenda.segments[2].buffer_before = 1  # gap at slot 2
    recompute_start_times(deps.agenda)
    ctx = FakeCtx(deps=deps)

    apply_swap_time(ctx, segment_id_a="s2", segment_id_b="s3")

    # Order is now [s1, s3, s2].
    assert [s.id for s in deps.agenda.segments] == ["s1", "s3", "s2"]
    # Segment NOW at slot 1 (old s2's position) is s3 — it should carry
    # the buffer_before that was originally at that slot = 5.
    assert deps.agenda.segments[1].id == "s3"
    assert deps.agenda.segments[1].buffer_before == 5
    # Segment NOW at slot 2 (old s3's position) is s2 — carries buffer = 1.
    assert deps.agenda.segments[2].id == "s2"
    assert deps.agenda.segments[2].buffer_before == 1
    # Cascade: s1 5min @19:15, s3 (buf 5) 7min @19:25, s2 (buf 1) 10min @19:33.
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:25"
    assert deps.agenda.segments[2].start_time == "19:33"


def test_swap_time_with_same_id_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="itself"):
        apply_swap_time(ctx, segment_id_a="s2", segment_id_b="s2")
    assert [s.id for s in deps.agenda.segments] == ["s1", "s2", "s3"]


def test_swap_time_unknown_id_raises():
    deps = make_deps_3()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_swap_time(ctx, segment_id_a="s1", segment_id_b="ghost")
    # Unchanged order.
    assert [s.id for s in deps.agenda.segments] == ["s1", "s2", "s3"]
    with pytest.raises(ModelRetry, match="unknown segment"):
        apply_swap_time(ctx, segment_id_a="ghost", segment_id_b="s2")
    assert [s.id for s in deps.agenda.segments] == ["s1", "s2", "s3"]


# ---------------------------------------------------------------------------
# apply_revert_last_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revert_last_turn_restores_agenda_before_of_latest_turn(monkeypatch):
    """Seeds an InMemory store with one turn whose agenda_before differs from
    the current in-memory agenda. The tool should replace ctx.deps.agenda
    wholesale so it matches the stored snapshot."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    # The "before" state we want to restore: 1 segment, specific role.
    before_snapshot = {
        "meta": {"start_time": "19:15"},
        "segments": [
            {
                "id": "s1",
                "type": "SAA",
                "start_time": "19:30",
                "duration": 3,
                "role_taker": "Original",
                "buffer_before": 0,
            },
        ],
    }
    await fake_store.save_turn(
        "sess-rev",
        user_id="u",
        turn=TurnRecord(
            seq=1,
            user_message="change SAA to Modified",
            assistant_text="ok",
            tool_trace=[{"id": "t1", "name": "set_role", "args": {}, "status": "ok", "result": {}}],
            agenda_before=before_snapshot,
            agenda_after={"meta": {"start_time": "19:15"}, "segments": []},  # irrelevant
            history_cursor=[],
        ),
    )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    # Current in-memory agenda is different from agenda_before — after revert
    # it should match `before_snapshot` exactly.
    deps = AgendaDeps(
        session_id="sess-rev",
        agenda=Agenda(
            meta=Meta(start_time="19:15"),
            segments=[
                Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Modified"),
                Segment(id="s2", type="Extra", start_time="19:33", duration=5, role_taker=""),
            ],
        ),
    )
    ctx = FakeCtx(deps=deps)

    result = await apply_revert_last_turn(ctx)

    assert result["undone_seq"] == 1
    assert result["restored_after_seq"] == 0  # undid turn 1 → now at initial point
    assert result["n_segments"] == 1
    # Metadata the agent will paraphrase — names make the semantic clear:
    # the instruction that got UNDONE, not the current state.
    assert result["undone_user_message"] == "change SAA to Modified"
    assert result["undone_tool_names"] == ["set_role"]
    # ctx.deps.agenda now matches before_snapshot exactly.
    assert len(ctx.deps.agenda.segments) == 1
    assert ctx.deps.agenda.segments[0].role_taker == "Original"
    assert ctx.deps.agenda.segments[0].id == "s1"


@pytest.mark.asyncio
async def test_revert_last_turn_skips_chit_chat_turns(monkeypatch):
    """When the most recent turn is chit-chat (no edit tools — e.g. a
    describe/question turn), revert_last_turn should walk back past it and
    undo the most recent actual EDIT turn. Matches user intuition: '撤销' is
    always about reversing state changes, not reversing descriptions."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    # Turn 1: real edit. agenda_before has ONE specific segment we can check.
    edit_before = {
        "meta": {},
        "segments": [
            {
                "id": "s1",
                "type": "OriginalType",
                "start_time": "19:30",
                "duration": 3,
                "role_taker": "",
                "buffer_before": 0,
            }
        ],
    }
    await fake_store.save_turn(
        "sess",
        user_id="u",
        turn=TurnRecord(
            seq=1,
            user_message="add a segment",
            assistant_text="ok",
            tool_trace=[{"id": "t1", "name": "add_segment", "args": {}, "status": "ok", "result": {}}],
            agenda_before=edit_before,
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )
    # Turn 2: chit-chat — user just asked for a summary. No tool calls.
    await fake_store.save_turn(
        "sess",
        user_id="u",
        turn=TurnRecord(
            seq=2,
            user_message="教一下刚才的操作",
            assistant_text="you added a segment",
            tool_trace=[],
            agenda_before={"meta": {}, "segments": []},
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    deps = AgendaDeps(session_id="sess", agenda=Agenda(meta=Meta(), segments=[]))
    ctx = FakeCtx(deps=deps)
    result = await apply_revert_last_turn(ctx)

    # Should target turn 1 (the edit), NOT turn 2 (chit-chat).
    assert result["undone_seq"] == 1
    assert result["undone_user_message"] == "add a segment"
    assert result["undone_tool_names"] == ["add_segment"]
    # Agenda matches edit_before — the chit-chat turn was transparently skipped.
    assert len(deps.agenda.segments) == 1
    assert deps.agenda.segments[0].type == "OriginalType"


@pytest.mark.asyncio
async def test_revert_last_turn_refuses_when_only_chit_chat(monkeypatch):
    """A session with only describe/question turns has no edits to undo.
    The tool must refuse rather than silently no-op, so the agent can tell
    the user instead of falsely claiming to have reverted."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    await fake_store.save_turn(
        "sess",
        user_id="u",
        turn=TurnRecord(
            seq=1,
            user_message="hi",
            assistant_text="hello!",
            tool_trace=[],
            agenda_before={"meta": {}, "segments": []},
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    deps = AgendaDeps(session_id="sess", agenda=Agenda(meta=Meta(), segments=[]))
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="no edits"):
        await apply_revert_last_turn(ctx)


@pytest.mark.asyncio
async def test_revert_last_turn_refuses_when_previous_turn_was_revert(monkeypatch):
    """Consecutive-revert guard: if the previous turn was itself a revert,
    revert_last_turn must refuse to prevent ping-pong. The refusal message
    should include a list of recent non-revert edit turns for the agent to
    present to the user."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    # Turn 1: a real edit.
    await fake_store.save_turn(
        "sess",
        user_id="u",
        turn=TurnRecord(
            seq=1,
            user_message="把 SAA 改成 Joyce",
            assistant_text="ok",
            tool_trace=[{"id": "t1", "name": "set_role", "args": {}, "status": "ok", "result": {}}],
            agenda_before={"meta": {}, "segments": []},
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )
    # Turn 2: a previous revert. This is what makes the new call consecutive.
    await fake_store.save_turn(
        "sess",
        user_id="u",
        turn=TurnRecord(
            seq=2,
            user_message="撤销一下",
            assistant_text="已撤销",
            tool_trace=[{"id": "t2", "name": "revert_last_turn", "args": {}, "status": "ok", "result": {}}],
            agenda_before={"meta": {}, "segments": []},
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    deps = AgendaDeps(session_id="sess", agenda=Agenda(meta=Meta(), segments=[]))
    ctx = FakeCtx(deps=deps)

    with pytest.raises(ModelRetry) as exc:
        await apply_revert_last_turn(ctx)
    msg = str(exc.value)
    # The refusal must explain the reason and suggest the alternative tool.
    assert "Consecutive revert blocked" in msg
    assert "revert_to_turn" in msg
    # Direction phrasing is "state AFTER [edit]" per the user-preferred
    # framing (easier to visualize than "state BEFORE [op]").
    assert "state AFTER" in msg
    assert "VERBATIM" in msg  # agent must pass the user's seq unchanged
    # Restore points: seq 0 (initial) is always offered; each edit turn is
    # listed with its description.
    assert "seq 0" in msg
    assert "initial state" in msg
    assert "seq 1" in msg
    assert "把 SAA 改成 Joyce" in msg


@pytest.mark.asyncio
async def test_revert_to_turn_applies_agenda_after_of_target(monkeypatch):
    """revert_to_turn(after_seq=N) restores agenda_after of turn N (the state
    that existed right after turn N completed). 'AFTER' semantics — the seq
    the user picks maps directly to the parameter."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    # Seed three turns. Each one's agenda_after has a distinct segment type
    # so we can verify the RIGHT turn's after-state got restored.
    for seq in range(1, 4):
        await fake_store.save_turn(
            "s",
            user_id="u",
            turn=TurnRecord(
                seq=seq,
                user_message=f"turn {seq}",
                assistant_text=f"reply {seq}",
                tool_trace=[{"id": f"t{seq}", "name": "set_role", "args": {}, "status": "ok", "result": {}}],
                agenda_before={"meta": {}, "segments": []},  # irrelevant for this test
                agenda_after={
                    "meta": {"start_time": "19:00"},
                    "segments": [
                        {
                            "id": f"s{seq}",
                            "type": f"state_after_{seq}",
                            "start_time": "19:30",
                            "duration": 5,
                            "role_taker": "",
                            "buffer_before": 0,
                        }
                    ],
                },
                history_cursor=[],
            ),
        )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    deps = AgendaDeps(
        session_id="s",
        agenda=Agenda(meta=Meta(), segments=[Segment(id="other", type="X", start_time="20:00", duration=5)]),
    )
    ctx = FakeCtx(deps=deps)

    result = await apply_revert_to_turn(ctx, after_seq=2)

    assert result["restored_after_seq"] == 2
    # Agenda now matches agenda_after of turn 2.
    assert len(deps.agenda.segments) == 1
    assert deps.agenda.segments[0].type == "state_after_2"
    # No turns deleted — soft revert.
    tail, _ = await fake_store.load("s")
    assert tail == 3


@pytest.mark.asyncio
async def test_revert_to_turn_after_seq_0_restores_initial_state(monkeypatch):
    """after_seq=0 is the 'initial state' restore point — agenda_before of
    turn 1 (what existed before any edits)."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    initial = {"meta": {"start_time": "19:00"}, "segments": []}
    await fake_store.save_turn(
        "s",
        user_id="u",
        turn=TurnRecord(
            seq=1,
            user_message="first edit",
            assistant_text="ok",
            tool_trace=[{"id": "t1", "name": "add_segment", "args": {}, "status": "ok", "result": {}}],
            agenda_before=initial,
            agenda_after={
                "meta": {"start_time": "19:00"},
                "segments": [
                    {
                        "id": "x",
                        "type": "X",
                        "start_time": "19:30",
                        "duration": 5,
                        "role_taker": "",
                        "buffer_before": 0,
                    }
                ],
            },
            history_cursor=[],
        ),
    )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    deps = AgendaDeps(
        session_id="s",
        agenda=Agenda(meta=Meta(), segments=[Segment(id="junk", type="Junk", start_time="20:00", duration=5)]),
    )
    ctx = FakeCtx(deps=deps)
    result = await apply_revert_to_turn(ctx, after_seq=0)

    assert result["restored_after_seq"] == 0
    assert len(deps.agenda.segments) == 0  # initial state has no segments


@pytest.mark.asyncio
async def test_revert_to_turn_unknown_seq_refuses(monkeypatch):
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore

    monkeypatch.setattr(store_module, "session_store", InMemorySessionStore())
    ctx = FakeCtx(deps=AgendaDeps(session_id="empty", agenda=Agenda(meta=Meta(), segments=[])))
    with pytest.raises(ModelRetry, match="not found"):
        await apply_revert_to_turn(ctx, after_seq=5)


@pytest.mark.asyncio
async def test_revert_to_turn_negative_seq_refuses(monkeypatch):
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore

    monkeypatch.setattr(store_module, "session_store", InMemorySessionStore())
    ctx = FakeCtx(deps=AgendaDeps(session_id="x", agenda=Agenda(meta=Meta(), segments=[])))
    with pytest.raises(ModelRetry, match=">= 0"):
        await apply_revert_to_turn(ctx, after_seq=-1)


@pytest.mark.asyncio
async def test_revert_to_turn_0_on_empty_session_refuses(monkeypatch):
    """after_seq=0 on a never-saved session should refuse — there's no
    turn 1's agenda_before to load."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore

    monkeypatch.setattr(store_module, "session_store", InMemorySessionStore())
    ctx = FakeCtx(deps=AgendaDeps(session_id="none", agenda=Agenda(meta=Meta(), segments=[])))
    with pytest.raises(ModelRetry, match="no turns"):
        await apply_revert_to_turn(ctx, after_seq=0)


@pytest.mark.asyncio
async def test_revert_last_turn_refuses_when_session_empty(monkeypatch):
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore

    monkeypatch.setattr(store_module, "session_store", InMemorySessionStore())

    deps = AgendaDeps(
        session_id="never-saved",
        agenda=Agenda(meta=Meta(), segments=[]),
    )
    ctx = FakeCtx(deps=deps)

    with pytest.raises(ModelRetry, match="no prior turns"):
        await apply_revert_last_turn(ctx)


@pytest.mark.asyncio
async def test_revert_last_turn_mutates_in_place_not_reassigns(monkeypatch):
    """Regression guard: the agent framework holds a reference to
    ctx.deps.agenda and reads it after the tool returns. If we reassigned
    ctx.deps.agenda = X instead of mutating, the framework would still see
    the old object. Verify the same Agenda instance is updated in place."""
    from app.meeting_agent import store as store_module
    from app.meeting_agent.store import InMemorySessionStore, TurnRecord

    fake_store = InMemorySessionStore()
    # Must be an EDIT turn (not chit-chat) or the tool refuses — the in-place
    # invariant only matters on the success path.
    await fake_store.save_turn(
        "sess",
        user_id="u",
        turn=TurnRecord(
            seq=1,
            user_message="remove everything",
            assistant_text="ok",
            tool_trace=[{"id": "t1", "name": "remove_segment", "args": {}, "status": "ok", "result": {}}],
            agenda_before={"meta": {}, "segments": []},
            agenda_after={"meta": {}, "segments": []},
            history_cursor=[],
        ),
    )
    monkeypatch.setattr(store_module, "session_store", fake_store)

    deps = AgendaDeps(
        session_id="sess",
        agenda=Agenda(
            meta=Meta(),
            segments=[Segment(id="s1", type="X", start_time="19:30", duration=5)],
        ),
    )
    original_agenda_id = id(deps.agenda)
    ctx = FakeCtx(deps=deps)

    await apply_revert_last_turn(ctx)

    # Same python object, emptied contents.
    assert id(deps.agenda) == original_agenda_id
    assert deps.agenda.segments == []
