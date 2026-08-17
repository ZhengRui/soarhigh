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


class DraftOperationInProgress(WorkspaceError):
    """Another Draft operation is already running for this workspace."""

    code = "draft_operation_in_progress"


class DraftTurnInterrupted(WorkspaceError):
    """The member stopped the Draft turn before it saved anything."""

    code = "draft_turn_interrupted"


class PublicationOperationNotFound(WorkspaceError):
    """The opaque publication operation identifier does not resolve."""

    code = "publication_operation_not_found"
