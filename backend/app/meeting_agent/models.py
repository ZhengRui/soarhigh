from typing import Any, Optional

from pydantic import BaseModel, Field


class Meta(BaseModel):
    no: Optional[int] = None
    type: Optional[str] = None
    theme: Optional[str] = None
    manager: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: Optional[str] = None
    introduction: Optional[str] = None


class Segment(BaseModel):
    id: str
    type: str
    start_time: str
    duration: int
    role_taker: str = ""
    buffer_before: int = 0


class Agenda(BaseModel):
    meta: Meta
    segments: list[Segment] = Field(default_factory=list)


class AgendaDeps(BaseModel):
    agenda: Agenda
    session_id: str
    current_user_message: str = ""
    image_data: Optional[bytes] = None
    image_content_type: Optional[str] = None
    # Per-turn pool cache for the meeting-lookup service. Deps is built fresh
    # each turn so the cache invalidates naturally at turn boundaries.
    # `meeting_pool_lock` is lazily set to an asyncio.Lock on first lookup
    # call (must bind to the current event loop, not the one that built
    # deps). Multiple parallel `lookup_meeting` tool calls within one turn
    # — e.g. cross-language theme + intro fan-out — share a single DB
    # fetch instead of each hitting Supabase.
    meeting_pool_cache: Optional[list[dict]] = None
    meeting_pool_lock: Any = None

    model_config = {"arbitrary_types_allowed": True}
