def test_load_skill_instruction_mentions_meeting_manager_workflow():
    from app.agents.general.prompts import LOAD_SKILL_INSTRUCTION

    assert "soarhigh-meeting-manager" in LOAD_SKILL_INSTRUCTION
    assert "会议经理" in LOAD_SKILL_INSTRUCTION
    assert "准备流程" in LOAD_SKILL_INSTRUCTION
