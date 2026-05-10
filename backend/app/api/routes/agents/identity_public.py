"""Identity resolution for AgentPublic.

Member Agent routes use auth.users.id ownership. AgentPublic uses a public
identity tuple: (channel, visitor_key). Mini App guests resolve from wxid;
future Web visitors resolve from a signed server-issued cookie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Request, Response, status
from jose import ExpiredSignatureError, JWTError, jwt

from ....config import AGENT_PUBLIC_VISITOR_SECRET
from ....models.users import User
from ....models.wechat_user import WeChatUser

PublicChannel = Literal["miniapp", "web"]
VISITOR_COOKIE_PUBLIC = "agent_visitor_public"
_VISITOR_TOKEN_TYPE = "agent_public_visitor"
_VISITOR_MAX_AGE_SECONDS = 60 * 60 * 24 * 365


@dataclass(frozen=True)
class AgentIdentityPublic:
    channel: PublicChannel
    visitor_key: str


def _encode_visitor_token(visitor_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "type": _VISITOR_TOKEN_TYPE,
        "visitor_id": visitor_id,
        "iat": now,
        "exp": now + timedelta(seconds=_VISITOR_MAX_AGE_SECONDS),
    }
    return jwt.encode(payload, AGENT_PUBLIC_VISITOR_SECRET, algorithm="HS256")


def _decode_visitor_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, AGENT_PUBLIC_VISITOR_SECRET, algorithms=["HS256"])
    except (ExpiredSignatureError, JWTError):
        return None
    if payload.get("type") != _VISITOR_TOKEN_TYPE:
        return None
    visitor_id = payload.get("visitor_id")
    return visitor_id if isinstance(visitor_id, str) and visitor_id else None


def ensure_visitor_cookie_public(request: Request, response: Response) -> str:
    """Return a valid visitor id, issuing/replacing the signed cookie if needed."""
    token = request.cookies.get(VISITOR_COOKIE_PUBLIC)
    visitor_id = _decode_visitor_token(token) if token else None
    if visitor_id is None:
        visitor_id = str(uuid4())
        token = _encode_visitor_token(visitor_id)
        response.set_cookie(
            VISITOR_COOKIE_PUBLIC,
            token,
            max_age=_VISITOR_MAX_AGE_SECONDS,
            httponly=True,
            secure=True,
            samesite="lax",
        )
    return visitor_id


def resolve_identity_public(request: Request, user: User | WeChatUser | None) -> AgentIdentityPublic:
    """Resolve the public owner for /agent-public/turn.

    Mini App v1 must pass a WeChat session token that resolves to
    `WeChatUser`. Bound members resolve to `User` and must use the member
    Agent instead. Future Web public calls use the signed visitor cookie.
    """
    if isinstance(user, WeChatUser):
        return AgentIdentityPublic(channel="miniapp", visitor_key=user.wxid)
    if isinstance(user, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AgentPublic is for public visitors. Bound members should use the member assistant.",
        )

    visitor_token = request.cookies.get(VISITOR_COOKIE_PUBLIC)
    visitor_id = _decode_visitor_token(visitor_token) if visitor_token else None
    if visitor_id:
        return AgentIdentityPublic(channel="web", visitor_key=visitor_id)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="AgentPublic requires a Mini App guest token or a public visitor cookie.",
    )
