"""General Q&A agent runtime deps. Mirrors StatsDeps in shape so the
Pydantic AI scaffolding (RunContext, message_history) works the same way,
but carries a SkillRegistry handle so the `view_skill` tool can pull
skill bodies on demand.

The registry itself is module-level (built at import time in
`agents/general/agent.py`); deps just hand a reference to each turn so
tests can swap in a fixture registry."""

from typing import Any

from pydantic import BaseModel

from app.agents.runtime.skill_registry import SkillRegistry


class GeneralDeps(BaseModel):
    """Per-turn dependency context passed to every general-agent tool."""

    session_id: str
    current_user_message: str = ""
    today: str = ""
    skill_registry: SkillRegistry

    model_config = {"arbitrary_types_allowed": True}

    # Allow Any-typed arbitrary objects for forward extension (e.g. a
    # future club-archive cache); mirrors StatsDeps.meeting_pool_cache
    # convention.
    extras: dict[str, Any] = {}
