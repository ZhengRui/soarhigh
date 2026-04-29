from app.agents.meeting.models import Agenda, Meta, Segment
from app.models.meeting import Attendee


def test_agenda_roundtrip():
    """Phase B: Segment.role_taker is a structured Attendee (or None). The
    string-coercer accepts a bare name for backwards compatibility — useful
    for the agent's tool-side templates and persisted-history rehydration —
    and lifts it into Attendee(name, member_id="")."""
    agenda = Agenda(
        meta=Meta(no=451, theme="Test", start_time="19:15", end_time="21:30"),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Liz"),
        ],
    )
    assert agenda.segments[0].id == "s1"
    rt = agenda.segments[0].role_taker
    assert rt is not None
    assert rt.name == "Liz"
    assert rt.member_id == ""
    # model_dump now produces the structured Attendee dict for downstream
    # consumers (frontend `applyAgendaSnapshot`, persisted TurnRecord).
    assert agenda.model_dump()["segments"][0]["role_taker"] == {
        "id": None,
        "name": "Liz",
        "member_id": "",
    }


def test_segment_role_taker_string_coercer_handles_blank_and_attendee():
    """Verify each branch of the role_taker coercer.

    - Empty / whitespace string → None (segment has no role taker)
    - Bare name → Attendee(name=<stripped>, member_id="") (guest by default;
      the frontend resolveAttendee fixes member_id when it knows the name)
    - Already-an-Attendee → preserved verbatim
    - dict input → coerced to Attendee with same fields
    - dict with empty name → None (avoids zombie Attendees from stale rows)
    """
    cases = [
        (None, None),
        ("", None),
        ("   ", None),
        ("Joyce Feng", Attendee(id=None, name="Joyce Feng", member_id="")),
        (
            Attendee(id="att-1", name="Joyce Feng", member_id="m1"),
            Attendee(id="att-1", name="Joyce Feng", member_id="m1"),
        ),
        ({"id": None, "name": "Liz", "member_id": ""}, Attendee(id=None, name="Liz", member_id="")),
        ({"id": None, "name": "", "member_id": ""}, None),
    ]
    for raw, expected in cases:
        seg = Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker=raw)
        assert seg.role_taker == expected, f"input={raw!r} expected={expected!r} got={seg.role_taker!r}"
