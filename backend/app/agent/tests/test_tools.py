import re
from dataclasses import dataclass

import pytest
from pydantic_ai import ModelRetry

from app.agent.models import Agenda, AgendaDeps, Meta, Segment
from app.agent.timing import recompute_start_times
from app.agent.tools import (
    apply_add_segment,
    apply_move_segment,
    apply_remove_segment,
    apply_set_buffer,
    apply_set_duration,
    apply_set_meta,
    apply_set_role,
    apply_set_type,
    apply_shift_segment_time,
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


def test_set_role_mutates_target_segment():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_role(ctx, segment_id="s2", new_role_taker="Joyce Feng")
    assert result["segment_id"] == "s2"
    assert result["new_role_taker"] == "Joyce Feng"
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

    result = apply_set_type(ctx, segment_id="s2", new_type="Ice Breaker")

    assert result == {"segment_id": "s2", "new_type": "Ice Breaker"}
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
    result = apply_set_duration(ctx, segment_id="s1", new_duration_min=10)

    assert result == {"segment_id": "s1", "new_duration_min": 10}
    assert deps.agenda.segments[0].duration == 10
    assert deps.agenda.segments[0].start_time == "19:15"
    assert deps.agenda.segments[1].start_time == "19:25"
    assert deps.agenda.segments[2].start_time == "19:35"


def test_set_duration_zero_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="duration must be positive"):
        apply_set_duration(ctx, segment_id="s1", new_duration_min=0)
    # No mutation
    assert deps.agenda.segments[0].duration == 3


def test_set_duration_negative_raises_model_retry():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    with pytest.raises(ModelRetry, match="duration must be positive"):
        apply_set_duration(ctx, segment_id="s1", new_duration_min=-5)
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
