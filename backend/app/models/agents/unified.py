from pydantic import BaseModel

from app.agents.meeting.models import Agenda


class AgentTurnRequest(BaseModel):
    """Unified agent turn request.

    `agenda_snapshot` is required only when the router selects the meeting
    specialist. Statistics turns are read-only and do not need current-draft
    state.
    """

    session_id: str
    user_message: str
    agenda_snapshot: Agenda | None = None
