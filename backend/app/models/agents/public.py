from typing import Annotated

from pydantic import BaseModel, Field

PublicSessionId = Annotated[
    str,
    Field(
        min_length=20,
        max_length=160,
        pattern=r"^agent-public:(miniapp|web):[A-Za-z0-9._:-]+$",
    ),
]

PublicUserMessage = Annotated[
    str,
    Field(min_length=1, max_length=4000),
]


class AgentTurnPublicRequest(BaseModel):
    """Per-turn request payload for AgentPublic."""

    session_id: PublicSessionId
    user_message: PublicUserMessage
