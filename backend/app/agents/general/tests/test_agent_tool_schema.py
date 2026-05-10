def test_view_skill_name_schema_is_constrained_to_registry_names():
    from app.agents.general.agent import agent, skill_registry

    tool = agent._function_toolset.tools["view_skill"]
    schema = tool.tool_def.parameters_json_schema

    assert schema["properties"]["name"]["enum"] == skill_registry.all_names()


def test_quick_links_are_always_loaded_not_manifest_only():
    from app.agents.general.agent import skill_registry

    assert "SoarHigh 邀请函" in skill_registry.render_always_loaded()
    assert "soarhigh-quick-links" not in skill_registry.render_manifest()


def test_public_agent_excludes_meeting_manager_skill():
    from app.agents.general.agent_public import agent_public, skill_registry_public

    assert "soarhigh-meeting-manager" not in skill_registry_public.all_names()
    assert "soarhigh-meeting-manager" not in skill_registry_public.render_manifest()

    tool = agent_public._function_toolset.tools["view_skill_public"]
    schema = tool.tool_def.parameters_json_schema
    assert "soarhigh-meeting-manager" not in schema["properties"]["name"]["enum"]
    assert schema["properties"]["name"]["enum"] == skill_registry_public.all_names()


def test_public_agent_tool_surface_is_narrow():
    from app.agents.general.agent_public import agent_public

    tool_names = {tool_def.name for tool_def in agent_public._function_toolset.tools.values()}
    assert tool_names == {"view_skill_public", "lookup_meeting_public"}


def test_public_agent_topic_lookup_strategy_is_documented():
    from app.agents.general.agent_public import agent_public, compose_system_prompt_public

    prompt = compose_system_prompt_public()
    tool_description = agent_public._function_toolset.tools["lookup_meeting_public"].tool_def.description

    assert "Topic search strategy" in prompt
    assert "theme_substring" in prompt
    assert "introduction_substring" in prompt
    assert "cross-language keyword" in prompt

    assert "Topic search convention" in tool_description
    assert "theme_substring" in tool_description
    assert "introduction_substring" in tool_description
    assert "bilingual keyword" in tool_description
