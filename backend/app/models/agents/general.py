from pydantic import BaseModel


class GeneralAgentTurnRequest(BaseModel):
    """Per-turn request payload for the General Q&A agent.

    No agenda_snapshot — the general agent is read-only knowledge Q&A
    and never inspects or mutates an agenda. session_id is per-user
    convention `<user_id>:general` from the frontend.
    """

    session_id: str
    user_message: str
    # Set by the unified /agent/turn dispatcher so the persisted turn carries
    # the routing context. Standalone callers leave it empty.
    router_decision: dict | None = None
