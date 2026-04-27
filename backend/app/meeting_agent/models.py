from typing import Optional

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

    model_config = {"arbitrary_types_allowed": True}
