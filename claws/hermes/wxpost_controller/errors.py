from __future__ import annotations

from .core import WorkspaceError


class HermesUnavailable(WorkspaceError):
    code = "hermes_unavailable"


class HermesTurnFailed(WorkspaceError):
    code = "hermes_turn_failed"


class DraftSessionStoreUnavailable(HermesTurnFailed):
    """The Controller could not read or persist non-canonical session state."""
