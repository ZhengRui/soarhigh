from __future__ import annotations

from .core import WorkspaceError


class HermesUnavailable(WorkspaceError):
    code = "hermes_unavailable"


class HermesTurnFailed(WorkspaceError):
    code = "hermes_turn_failed"


class DraftStoreUnavailable(WorkspaceError):
    """The Controller could not read or persist Draft Assistant state."""

    code = "draft_store_unavailable"


class DraftOperationNotFound(WorkspaceError):
    code = "draft_operation_not_found"
