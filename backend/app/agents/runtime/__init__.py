"""Shared runtime contracts and policies for agent orchestration."""

from app.agents.runtime.capabilities import Capability, all_capabilities, capabilities_for_agent, capability_for_tool
from app.agents.runtime.contracts import AccessMode, AgentKind, RouteKind, RouterDecision
from app.agents.runtime.envelopes import ToolCoverage, ToolResultEnvelope, normalize_tool_result
from app.agents.runtime.policy import AgentPolicyError, require_tool_allowed
from app.agents.runtime.store import AgentTurnRecord, agent_turn_store

__all__ = [
    "AccessMode",
    "AgentKind",
    "AgentPolicyError",
    "AgentTurnRecord",
    "Capability",
    "RouteKind",
    "RouterDecision",
    "ToolCoverage",
    "ToolResultEnvelope",
    "agent_turn_store",
    "all_capabilities",
    "capabilities_for_agent",
    "capability_for_tool",
    "normalize_tool_result",
    "require_tool_allowed",
]
