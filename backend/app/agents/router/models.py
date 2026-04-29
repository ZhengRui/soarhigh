"""Router-facing model aliases.

The canonical schema lives in app.agents.runtime so policy, persistence, and
the eventual router endpoint share the same contract.
"""

from app.agents.runtime.contracts import RouteKind, RouterDecision

__all__ = ["RouteKind", "RouterDecision"]
