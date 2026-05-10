"""AgentPublic runtime deps."""

from typing import Any, Optional

from pydantic import BaseModel

from app.agents.runtime.skill_registry import SkillRegistry


class GeneralPublicDeps(BaseModel):
    """Per-turn dependency context for AgentPublic tools."""

    session_id: str
    current_user_message: str = ""
    today: str = ""
    skill_registry: SkillRegistry
    meeting_pool_cache: Optional[list[dict]] = None
    meeting_pool_lock: Any = None

    model_config = {"arbitrary_types_allowed": True}
