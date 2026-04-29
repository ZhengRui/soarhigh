from pydantic import BaseModel

from app.agents.meeting.models import Agenda


class MeetingAgentTurnRequest(BaseModel):
    session_id: str
    user_message: str
    agenda_snapshot: Agenda


class MeetingAgentRevertRequest(BaseModel):
    session_id: str
    # Revert to BEFORE this turn ran: load agenda_before of target_seq, then
    # delete all turns >= target_seq. target_seq=1 rewinds to the very start.
    target_seq: int
