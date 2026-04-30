"""Shared agent runtime contracts.

These models are intentionally small and transport-oriented. Specialist
agents can keep their local tool shapes, while the router/orchestrator gets a
stable vocabulary for decisions and cross-agent handoff.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

JsonObject = dict[str, Any]


class AgentKind(str, Enum):
    ROUTER = "router"
    MEETING = "meeting"
    STATISTICS = "statistics"


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"


class RouteKind(str, Enum):
    SPECIALIST = "specialist"
    CLARIFY = "clarify"
    HANDOFF = "handoff"
    REFUSE = "refuse"
    DIRECT_ANSWER = "direct_answer"


class HandoffPayload(BaseModel):
    """Structured facts passed from one specialist to another.

    Handoffs are not tool calls. They are orchestrator-owned payloads that
    preserve which agent produced the facts, which agent may act on them, and
    whether the user must confirm before a write-capable specialist mutates
    anything.
    """

    source_agent: AgentKind
    target_agent: AgentKind
    intent: str
    facts: list[JsonObject] = Field(default_factory=list)
    references: list[JsonObject] = Field(default_factory=list)
    constraints: JsonObject = Field(default_factory=dict)
    requires_confirmation: bool = True

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _validate_agents(self) -> Self:
        if self.source_agent == self.target_agent:
            raise ValueError("handoff source_agent and target_agent must be different")
        if self.source_agent == AgentKind.ROUTER or self.target_agent == AgentKind.ROUTER:
            raise ValueError("handoff endpoints must be specialist agents, not the router")
        return self


class RouterDecision(BaseModel):
    """Persistable router/orchestrator decision for a user turn."""

    route: RouteKind
    intent: str
    reason: str
    agent_kind: AgentKind | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    clarification_question: str | None = None
    direct_response: str | None = None
    handoff: HandoffPayload | None = None
    metadata: JsonObject = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _validate_route_shape(self) -> Self:
        if self.route == RouteKind.SPECIALIST:
            if self.agent_kind not in {AgentKind.MEETING, AgentKind.STATISTICS}:
                raise ValueError("specialist route requires agent_kind meeting or statistics")
            if self.handoff is not None:
                raise ValueError("specialist route must not include handoff payload")
        elif self.route == RouteKind.CLARIFY:
            if not (self.clarification_question or "").strip():
                raise ValueError("clarify route requires clarification_question")
            if self.handoff is not None:
                raise ValueError("clarify route must not include handoff payload")
        elif self.route == RouteKind.HANDOFF:
            if self.handoff is None:
                raise ValueError("handoff route requires handoff payload")
        elif self.route == RouteKind.REFUSE:
            if not (self.reason or "").strip():
                raise ValueError("refuse route requires reason")
            if self.handoff is not None:
                raise ValueError("refuse route must not include handoff payload")
        elif self.route == RouteKind.DIRECT_ANSWER:
            if not (self.direct_response or "").strip():
                raise ValueError("direct_answer route requires direct_response")
            if self.handoff is not None:
                raise ValueError("direct_answer route must not include handoff payload")
            if self.agent_kind is not None:
                raise ValueError("direct_answer route must not include agent_kind")
        return self
