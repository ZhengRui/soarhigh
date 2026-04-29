"""Statistics agent runtime deps. Mirrors meeting_agent's AgendaDeps in
shape so the Pydantic AI scaffolding (RunContext, message_history) works
the same way, but is intentionally simpler: there's no draft to mutate."""

from typing import Any, Optional

from pydantic import BaseModel


class StatsDeps(BaseModel):
    """Per-turn dependency context passed to every stats tool.

    `current_user_message` is mostly informational (the actual
    user_message is also embedded in the prompt), kept here for
    consistency with the meeting agent's deps shape.

    `meeting_pool_cache` / `meeting_pool_lock` mirror the per-turn pool
    cache from `meeting_agent.AgendaDeps` so cross-language
    `lookup_meeting` fan-out within a stats turn (e.g. theme + intro
    parallel calls) shares one Supabase fetch."""

    session_id: str
    current_user_message: str = ""
    today: str = ""
    meeting_pool_cache: Optional[list[dict]] = None
    meeting_pool_lock: Any = None

    model_config = {"arbitrary_types_allowed": True}
