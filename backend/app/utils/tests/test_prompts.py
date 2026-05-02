"""Structural assertions on the text-creation prompts."""

from app.utils.prompts import (
    plan_meeting_from_text_developer_prompt,
    plan_meeting_from_text_user_prompt,
)


def test_developer_prompt_lists_all_19_club_members():
    prompt = plan_meeting_from_text_developer_prompt
    assert "Victory Liu" in prompt
    assert "Albert Ding" in prompt


def test_user_prompt_forbids_buffer_pseudo_segments():
    prompt = plan_meeting_from_text_user_prompt
    assert 'NEVER output a segment whose type is "buffer"' in prompt


def test_user_prompt_disables_buffer_time_on_creation():
    """Per user preference, draft creation must NOT pre-insert buffer time —
    segments are back-to-back; users add gaps manually afterward."""
    prompt = plan_meeting_from_text_user_prompt
    assert "use NO buffer time" in prompt
    assert "user will add buffer/gap time manually" in prompt


def test_user_prompt_requires_warmup_first_segment_for_regular_workshop():
    """Soarhigh club convention: every Regular / Workshop meeting opens with
    a 15-min warmup at 19:15. The planner must include it as the first
    segment with the canonical type label, even if the source text doesn't
    explicitly mention registration."""
    prompt = plan_meeting_from_text_user_prompt
    assert "Members and Guests Registration, Warm up" in prompt
    assert '"19:15"' in prompt
    assert "Custom meetings have no such convention" in prompt


def test_developer_prompt_describes_warmup_segment():
    """Same rule documented in the segment list at the top of the developer
    prompt so the planner sees it twice (segment list + Important Notes)."""
    prompt = plan_meeting_from_text_developer_prompt
    assert "Members and Guests Registration, Warm up" in prompt
    # And the few-shot Example outputs must use the canonical label too.
    assert '"type": "Members and Guests Registration, Warm up"' in prompt
    # Old label should no longer appear in example outputs.
    assert '"type": "Guests Registration"' not in prompt


def test_user_prompt_default_president_is_amy_fang():
    prompt = plan_meeting_from_text_user_prompt
    assert "Amy Fang" in prompt
    assert "Libra Lee" not in prompt


def test_user_prompt_allows_explicit_role_override_for_president_segments():
    prompt = plan_meeting_from_text_user_prompt
    assert "explicitly names someone for the role" in prompt


def test_user_prompt_recognizes_club_intro_alias():
    prompt = plan_meeting_from_text_user_prompt
    assert "Club Intro" in prompt
