"""Runtime policy checks for agent routing and tool ownership."""

from __future__ import annotations

from pydantic import BaseModel

from app.agents.runtime.capabilities import capabilities_for_agent, capability_for_tool
from app.agents.runtime.contracts import AccessMode, AgentKind


class AgentPolicyError(ValueError):
    """Raised when a router or specialist violates a runtime boundary."""


class ToolPolicy(BaseModel):
    agent_kind: AgentKind
    tool_name: str
    capability_id: str
    access: AccessMode


def _coerce_agent_kind(agent_kind: AgentKind | str) -> AgentKind:
    return agent_kind if isinstance(agent_kind, AgentKind) else AgentKind(agent_kind)


def policy_for_tool(agent_kind: AgentKind | str, tool_name: str) -> ToolPolicy:
    agent = _coerce_agent_kind(agent_kind)
    capability = capability_for_tool(agent, tool_name)
    if capability is None:
        raise AgentPolicyError(f"{agent.value} agent is not allowed to call tool {tool_name!r}")
    return ToolPolicy(
        agent_kind=agent,
        tool_name=tool_name,
        capability_id=capability.id,
        access=capability.access,
    )


def require_tool_allowed(agent_kind: AgentKind | str, tool_name: str) -> ToolPolicy:
    return policy_for_tool(agent_kind, tool_name)


def require_read_only_tool(agent_kind: AgentKind | str, tool_name: str) -> ToolPolicy:
    policy = policy_for_tool(agent_kind, tool_name)
    if policy.access != AccessMode.READ:
        raise AgentPolicyError(f"{policy.agent_kind.value}.{tool_name} is {policy.access.value}, not read-only")
    return policy


def require_read_only_toolset(agent_kind: AgentKind | str, tool_names: set[str] | frozenset[str]) -> None:
    for tool_name in sorted(tool_names):
        require_read_only_tool(agent_kind, tool_name)


def agent_can_write(agent_kind: AgentKind | str) -> bool:
    return any(capability.access == AccessMode.WRITE for capability in capabilities_for_agent(agent_kind))
