import pytest

from app.agents.runtime.capabilities import capability_for_tool, tool_names_for_agent
from app.agents.runtime.contracts import AccessMode, AgentKind, HandoffPayload
from app.agents.runtime.policy import (
    AgentPolicyError,
    agent_can_write,
    policy_for_tool,
    require_read_only_toolset,
    require_tool_allowed,
    validate_handoff_policy,
)


def _registered_tool_names(agent) -> set[str]:
    return {tool_def.name for tool_def in agent._function_toolset.tools.values()}


def test_capability_registry_covers_registered_specialist_tools():
    from app.agents.meeting.agent import agent as meeting_agent
    from app.agents.statistics.agent import agent as statistics_agent

    meeting_tools = _registered_tool_names(meeting_agent)
    statistics_tools = _registered_tool_names(statistics_agent)

    assert meeting_tools <= tool_names_for_agent(AgentKind.MEETING)
    assert statistics_tools <= tool_names_for_agent(AgentKind.STATISTICS)
    assert all(capability_for_tool(AgentKind.MEETING, tool_name) for tool_name in meeting_tools)
    assert all(capability_for_tool(AgentKind.STATISTICS, tool_name) for tool_name in statistics_tools)


def test_policy_distinguishes_shared_lookup_tools_by_agent():
    meeting_lookup = policy_for_tool(AgentKind.MEETING, "lookup_meeting")
    statistics_lookup = policy_for_tool(AgentKind.STATISTICS, "lookup_meeting")

    assert meeting_lookup.access == AccessMode.READ
    assert statistics_lookup.access == AccessMode.READ
    assert meeting_lookup.capability_id == "meeting.agenda_read"
    assert statistics_lookup.capability_id == "statistics.meeting_lookup"


def test_statistics_registered_tools_are_read_only():
    from app.agents.statistics.agent import agent

    require_read_only_toolset(AgentKind.STATISTICS, _registered_tool_names(agent))


def test_statistics_agent_cannot_call_meeting_mutation_tools():
    with pytest.raises(AgentPolicyError, match="not allowed"):
        require_tool_allowed(AgentKind.STATISTICS, "set_role")


def test_agent_write_capability_is_explicit():
    assert agent_can_write(AgentKind.MEETING) is True
    assert agent_can_write(AgentKind.STATISTICS) is False


def test_statistics_to_meeting_handoff_requires_confirmation():
    payload = HandoffPayload(
        source_agent=AgentKind.STATISTICS,
        target_agent=AgentKind.MEETING,
        intent="assign_role_from_stats",
        facts=[{"member_id": "m1", "full_name": "Joyce Feng"}],
        requires_confirmation=False,
    )

    with pytest.raises(AgentPolicyError, match="must require user confirmation"):
        validate_handoff_policy(payload)


def test_statistics_to_meeting_handoff_with_confirmation_is_allowed():
    payload = validate_handoff_policy(
        {
            "source_agent": "statistics",
            "target_agent": "meeting",
            "intent": "assign_role_from_stats",
            "facts": [{"member_id": "m1", "full_name": "Joyce Feng"}],
            "requires_confirmation": True,
        }
    )

    assert payload.source_agent == AgentKind.STATISTICS
    assert payload.target_agent == AgentKind.MEETING
