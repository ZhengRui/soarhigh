def test_view_skill_name_schema_is_constrained_to_registry_names():
    from app.agents.general.agent import agent, skill_registry

    tool = agent._function_toolset.tools["view_skill"]
    schema = tool.tool_def.parameters_json_schema

    assert schema["properties"]["name"]["enum"] == skill_registry.all_names()


def test_quick_links_are_always_loaded_not_manifest_only():
    from app.agents.general.agent import skill_registry

    assert "SoarHigh 邀请函" in skill_registry.render_always_loaded()
    assert "soarhigh-quick-links" not in skill_registry.render_manifest()
