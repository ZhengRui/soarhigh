"""Common tool-result envelope models.

Existing specialist tools do not have to return this model directly. The
schema captures the shared projection the unified route, persistence layer,
and frontend can consume as agent output becomes more uniform.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

JsonObject = dict[str, Any]


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class ToolCoverage(BaseModel):
    status: CoverageStatus
    source: str | None = None
    reason: str | None = None

    model_config = ConfigDict(use_enum_values=True)


class ToolWarning(BaseModel):
    code: str
    message: str
    details: JsonObject = Field(default_factory=dict)


class UnsupportedReason(BaseModel):
    code: str
    message: str
    details: JsonObject = Field(default_factory=dict)


class ToolResultEnvelope(BaseModel):
    value: Any = None
    scope: JsonObject = Field(default_factory=dict)
    coverage: ToolCoverage | None = None
    references: list[JsonObject] = Field(default_factory=list)
    warnings: list[ToolWarning] = Field(default_factory=list)
    requires_confirmation: bool = False
    render_addendum: JsonObject | None = None
    unsupported_reason: UnsupportedReason | None = None
    scanned_count: int | None = Field(default=None, ge=0)

    # Allow specialist-specific additions while the shared protocol settles.
    model_config = ConfigDict(extra="allow")


def normalize_tool_result(raw: Mapping[str, Any]) -> ToolResultEnvelope:
    """Project an existing tool result into the shared envelope.

    Stats tools currently keep checkable references under `value.references`.
    The unified protocol exposes references at the top level, so this helper
    lifts them without changing the specialist tool's returned payload.
    """

    payload = dict(raw)
    if "references" not in payload:
        value = payload.get("value")
        if isinstance(value, Mapping) and isinstance(value.get("references"), list):
            payload["references"] = value["references"]
    return ToolResultEnvelope.model_validate(payload)
