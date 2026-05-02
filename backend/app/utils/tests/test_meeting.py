from app.utils import meeting


def test_text_planner_reasoning_enabled_for_o4_and_gpt5_nano(monkeypatch):
    monkeypatch.setattr(meeting, "MEETING_TEXT_PLANNER_REASONING_EFFORT", "low")

    assert meeting._text_planner_reasoning("o4-mini") == {"effort": "low"}
    assert meeting._text_planner_reasoning("gpt-5-nano") == {"effort": "low"}


def test_text_planner_reasoning_skipped_for_non_reasoning_models():
    assert meeting._text_planner_reasoning("gpt-4.1-mini") is None
    assert meeting._text_planner_reasoning("gpt-4o-mini") is None
    assert meeting._text_planner_reasoning("deepseek-chat") is None


def test_is_deepseek_model_detects_legacy_and_v4_ids():
    assert meeting._is_deepseek_model("deepseek-chat") is True
    assert meeting._is_deepseek_model("deepseek-reasoner") is True
    assert meeting._is_deepseek_model("deepseek-v4-flash") is True
    assert meeting._is_deepseek_model("deepseek:deepseek-chat") is True


def test_is_deepseek_model_rejects_other_providers():
    assert meeting._is_deepseek_model("o4-mini") is False
    assert meeting._is_deepseek_model("gpt-5-nano") is False
    assert meeting._is_deepseek_model("gpt-4o") is False
    assert meeting._is_deepseek_model("openai:o4-mini") is False


def test_normalize_segment_type_passes_through_canonical():
    assert meeting._normalize_segment_type("Timer") == "Timer"
    assert meeting._normalize_segment_type("Prepared Speech") == "Prepared Speech"
    assert meeting._normalize_segment_type("Meeting Rules Introduction (SAA)") == "Meeting Rules Introduction (SAA)"
    assert (
        meeting._normalize_segment_type("Members and Guests Registration, Warm up")
        == "Members and Guests Registration, Warm up"
    )


def test_normalize_segment_type_translates_known_shorthand():
    assert meeting._normalize_segment_type("SAA") == "Meeting Rules Introduction (SAA)"
    assert meeting._normalize_segment_type("TOM") == "TOM (Toastmaster of Meeting) Introduction"
    assert meeting._normalize_segment_type("PS1") == "Prepared Speech"
    assert meeting._normalize_segment_type("PS3") == "Prepared Speech"
    assert meeting._normalize_segment_type("ie") == "Prepared Speech Evaluation"
    # IE / PS shorthand symmetry — registration text uses both styles.
    assert meeting._normalize_segment_type("IE1") == "Prepared Speech Evaluation"
    assert meeting._normalize_segment_type("IE3") == "Prepared Speech Evaluation"
    assert meeting._normalize_segment_type("MOT") == "Moment of Truth"
    # prompt-typo capitalisation safety net
    assert (
        meeting._normalize_segment_type("Members and Guests Registration, Warm Up")
        == "Members and Guests Registration, Warm up"
    )


def test_normalize_segment_type_preserves_custom_names():
    """Genuinely user-defined types (not in canonical set, not in alias
    map) round-trip unchanged so users keep their custom labels."""
    assert meeting._normalize_segment_type("破冰演讲") == "破冰演讲"
    assert meeting._normalize_segment_type("Lightning Round") == "Lightning Round"
    assert meeting._normalize_segment_type("Special Workshop: Storytelling") == "Special Workshop: Storytelling"
