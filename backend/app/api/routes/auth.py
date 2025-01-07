from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from ...config import SUPABASE_JWT_SECRET
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
    return [
        User(uid="a1", username="john", full_name="John Smith"),
        User(uid="a2", username="sarah", full_name="Sarah Johnson"),
        User(uid="a3", username="michael", full_name="Michael Chen"),
        User(uid="a4", username="emily", full_name="Emily Brown"),
    ]
