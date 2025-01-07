from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from ...config import SUPABASE_JWT_SECRET
from ...db.core import get_members
from ...models.users import User

http_scheme = HTTPBearer()
auth_router = r = APIRouter()

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid token",
    headers={"WWW-Authenticate": "Bearer"},
)

expired_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Token expired",
    headers={"WWW-Authenticate": "Bearer"},
)


def verify_access_token(token: str, jwt_secret: str = SUPABASE_JWT_SECRET) -> dict:
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"], audience="authenticated")
        return payload
    except ExpiredSignatureError:
        raise expired_exception
    except JWTError:
        raise credentials_exception


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_scheme)) -> User:
    token = credentials.credentials
    payload = verify_access_token(token)
    return User(
        uid=payload["sub"],
        username=payload["user_metadata"]["username"],
        full_name=payload["user_metadata"]["full_name"],
    )


@r.get("/whoami")
async def whoami(user: User = Depends(get_current_user)) -> User:
    return user


@r.get("/members")
async def members(user: User = Depends(get_current_user)) -> List[User]:
    members = get_members()
    return [User(uid=member["id"], username=member["username"], full_name=member["full_name"]) for member in members]
