from dataclasses import dataclass

import pytest
from pydantic_ai import ModelRetry

from app.agent.models import Agenda, AgendaDeps, Meta, Segment
from app.agent.tools import (
    apply_set_buffer,
    apply_set_duration,
    apply_set_meta,
    apply_set_role,
    apply_set_type,
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
