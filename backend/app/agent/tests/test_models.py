from app.agent.models import Agenda, Meta, Segment


def test_agenda_roundtrip():
    agenda = Agenda(
        meta=Meta(no=451, theme="Test", start_time="19:15", end_time="21:30"),
        segments=[
            Segment(id="s1", type="SAA", start_time="19:30", duration=3, role_taker="Liz"),
        ],
    )
    assert agenda.segments[0].id == "s1"
    assert agenda.model_dump()["segments"][0]["role_taker"] == "Liz"
