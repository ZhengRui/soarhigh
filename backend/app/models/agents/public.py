from pydantic import BaseModel


class AgentTurnPublicRequest(BaseModel):
    """Per-turn request payload for AgentPublic."""

    session_id: str
    user_message: str
