from pydantic import BaseModel

from app.agent.models import Agenda


class AgentTurnRequest(BaseModel):
    session_id: str
    user_message: str
    agenda_snapshot: Agenda
