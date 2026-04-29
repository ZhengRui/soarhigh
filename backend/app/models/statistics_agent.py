from pydantic import BaseModel


class StatisticsAgentTurnRequest(BaseModel):
    """Per-turn request payload for the statistics agent.

    No agenda_snapshot — the stats agent is read-only and operates on
    historical data only. session_id is per-user (not per-meeting):
    convention is `<user_id>:stats` from the frontend.
    """

    session_id: str
    user_message: str
