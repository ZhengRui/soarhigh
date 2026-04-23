from dataclasses import dataclass

from app.agent.models import Agenda, AgendaDeps, Meta, Segment
from app.agent.tools import apply_set_role


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


def test_set_role_mutates_target_segment():
    deps = make_deps()
    ctx = FakeCtx(deps=deps)
    result = apply_set_role(ctx, segment_id="s2", new_role_taker="Joyce Feng")
    assert result["segment_id"] == "s2"
    assert result["new_role_taker"] == "Joyce Feng"
    assert deps.agenda.segments[1].role_taker == "Joyce Feng"
    # other segments untouched
    assert deps.agenda.segments[0].role_taker == "Liz"
