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
    GENERAL = "general"


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"


class RouteKind(str, Enum):
    SPECIALIST = "specialist"
    CLARIFY = "clarify"
    REFUSE = "refuse"
    DIRECT_ANSWER = "direct_answer"


class RouterDecision(BaseModel):
    """Persistable router/orchestrator decision for a user turn."""

    route: RouteKind
    intent: str
    reason: str
    agent_kind: AgentKind | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    clarification_question: str | None = None
    direct_response: str | None = None
    metadata: JsonObject = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @model_validator(mode="after")
    def _validate_route_shape(self) -> Self:
        if self.route == RouteKind.SPECIALIST:
            if self.agent_kind not in {AgentKind.MEETING, AgentKind.STATISTICS, AgentKind.GENERAL}:
                raise ValueError("specialist route requires agent_kind meeting, statistics, or general")
        elif self.route == RouteKind.CLARIFY:
            if not (self.clarification_question or "").strip():
                raise ValueError("clarify route requires clarification_question")
        elif self.route == RouteKind.REFUSE:
            if not (self.reason or "").strip():
                raise ValueError("refuse route requires reason")
        elif self.route == RouteKind.DIRECT_ANSWER:
            if not (self.direct_response or "").strip():
                raise ValueError("direct_answer route requires direct_response")
            if self.agent_kind is not None:
                raise ValueError("direct_answer route must not include agent_kind")
        return self
