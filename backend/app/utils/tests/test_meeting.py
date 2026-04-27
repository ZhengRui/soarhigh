from app.utils import meeting


def test_text_planner_reasoning_enabled_for_o4_and_gpt5_nano(monkeypatch):
    monkeypatch.setattr(meeting, "MEETING_TEXT_PLANNER_REASONING_EFFORT", "low")

    assert meeting._text_planner_reasoning("o4-mini") == {"effort": "low"}
    assert meeting._text_planner_reasoning("gpt-5-nano") == {"effort": "low"}


def test_text_planner_reasoning_skipped_for_non_reasoning_models():
    assert meeting._text_planner_reasoning("gpt-4.1-mini") is None
    assert meeting._text_planner_reasoning("gpt-4o-mini") is None
