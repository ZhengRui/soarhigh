from datetime import datetime, timedelta
from typing import List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from ...config import SUPABASE_JWT_SECRET, WECHAT_JWT_SECRET
from ...db.core import get_attendee_id_by_wxid, get_members, get_user_by_wxid
from ...db.supabase import supabase
from ...models.users import User
from ...models.wechat_user import (
    TokenRefreshResponse,
    WeChatLoginRequest,
    WeChatLoginResponse,
    WeChatUser,
)
from ...utils.wechat import exchange_wx_code_for_openid

http_scheme = HTTPBearer()
http_scheme_optional = HTTPBearer(auto_error=False)
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


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_scheme_optional),
) -> Optional[User]:
    """
    Returns the current user if authenticated, or None if not authenticated.
    Unlike get_current_user, this function does not raise an exception for unauthenticated requests.

    This is useful for endpoints that have different behavior for authenticated vs. unauthenticated users.
    """
    if not credentials:
        return None

    try:
        user = get_current_extended_user(credentials)
        if isinstance(user, User):
            return user
        else:
            return None
    except (HTTPException, JWTError, ExpiredSignatureError):
        return None


def create_wechat_access_token(wxid: str) -> str:
    """Create a JWT access token for WeChat user with embedded user data for performance."""
    # Get user data and embed it in the token to avoid DB queries on each request
    user_data = get_user_by_wxid(wxid)
    attendee_id = get_attendee_id_by_wxid(wxid)

    payload = {
        "type": "wechat_session",
        "wxid": wxid,
        "exp": datetime.utcnow() + timedelta(days=1),
        "iat": datetime.utcnow(),
    }

    if user_data:
        # WeChat user bound to member
        payload.update(
            {
                "user_type": "member",
                "user_data": {
                    "uid": user_data["uid"],
                    "username": user_data["username"],
                    "full_name": user_data["full_name"],
                    "attendee_id": attendee_id,
                },
            }
        )
    else:
        # Unbound WeChat user
        payload.update({"user_type": "guest", "user_data": {"attendee_id": attendee_id}})

    return jwt.encode(payload, WECHAT_JWT_SECRET, algorithm="HS256")


def verify_extended_access_token(token: str) -> dict:
    """Verify JWT token - handles both Supabase and WeChat tokens."""
    try:
        # Try WeChat token first
        payload = jwt.decode(token, WECHAT_JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") == "wechat_session":
            return payload
    except (ExpiredSignatureError, JWTError):
        pass

    # Try Supabase token
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        return payload
    except ExpiredSignatureError:
        raise expired_exception
    except JWTError:
        raise credentials_exception


def get_current_extended_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_scheme),
) -> Union[User, WeChatUser]:
    """
    Get current authenticated user from JWT token - supports both Supabase and WeChat authentication.

    This function handles two types of JWT tokens:
    1. Supabase tokens (from webapp): Returns User object with member information
    2. WeChat tokens (from miniapp): Uses embedded user data for optimal performance,
       with fallback to DB queries for legacy tokens

    The function automatically detects token type and applies appropriate parsing logic.
    For WeChat tokens, it prioritizes embedded data over DB queries for performance.

    Args:
        credentials: HTTP Authorization header with Bearer token

    Returns:
        Union[User, WeChatUser]: User object for members, WeChatUser for unbound WeChat users

    Raises:
        HTTPException: If token is invalid, expired, or malformed
    """
    token = credentials.credentials
    payload = verify_extended_access_token(token)

    # Check token type
    if payload.get("type") == "wechat_session":
        # WeChat token - use embedded data for performance
        wxid = payload["wxid"]

        # Check if token has embedded user data (optimized path)
        if "user_type" in payload and "user_data" in payload:
            user_type = payload["user_type"]
            user_data = payload["user_data"]

            if user_type == "member":
                # Return User object from embedded data
                return User(
                    uid=user_data["uid"],
                    username=user_data["username"],
                    full_name=user_data["full_name"],
                )
            else:
                # Return WeChatUser from embedded data
                return WeChatUser(wxid=wxid, attendee_id=user_data.get("attendee_id"))
        else:
            # Fallback to DB queries for legacy tokens
            user_data = get_user_by_wxid(wxid)
            if user_data:
                # Return User object for bound members
                return User(**user_data)
            else:
                # Return WeChatUser for unbound users
                attendee_id = get_attendee_id_by_wxid(wxid)
                return WeChatUser(wxid=wxid, attendee_id=attendee_id)
    else:
        # Supabase token
        return User(
            uid=payload["sub"],
            username=payload["user_metadata"]["username"],
            full_name=payload["user_metadata"]["full_name"],
        )


def get_optional_extended_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_scheme_optional),
) -> Optional[Union[User, WeChatUser]]:
    """Get current user - returns User for members or WeChatUser for WeChat users.
    Unlike get_current_extended_user, this function does not raise an exception for unauthenticated requests.
    """
    if not credentials:
        return None

    try:
        return get_current_extended_user(credentials)
    except (HTTPException, JWTError, ExpiredSignatureError):
        return None


@r.get("/whoami")
async def whoami(user: User = Depends(get_current_user)) -> User:
    return user


@r.get("/is-admin")
async def is_admin(user: User = Depends(get_current_user)) -> bool:
    """
    Checks if the current authenticated user is an admin
    Returns a dict with a boolean indicating admin status
    """
    # Query the members table to check admin status
    result = supabase.table("members").select("is_admin").eq("id", user.uid).execute()
    is_admin = False
    if result.data and len(result.data) > 0:
        is_admin = result.data[0].get("is_admin", False)
    return is_admin


@r.get("/members")
async def members(user: User = Depends(get_current_user)) -> List[User]:
    members = get_members()
    return [User(uid=member["id"], username=member["username"], full_name=member["full_name"]) for member in members]


@r.post("/wechat-login", response_model=WeChatLoginResponse)
async def wechat_login(login_data: WeChatLoginRequest):
    """Login via WeChat miniapp - exchange wx_code for access token."""
    try:
        # Exchange wx_code for wxid (openid)
        wxid = await exchange_wx_code_for_openid(login_data.wx_code)

        # Create access token
        access_token = create_wechat_access_token(wxid)

        return WeChatLoginResponse(success=True, access_token=access_token)

    except HTTPException as e:
        # Re-raise WeChat API errors
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {e!s}")


@r.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(current_user: Union[User, WeChatUser] = Depends(get_current_extended_user)):
    """Refresh access token for authenticated users."""
    try:
        if isinstance(current_user, WeChatUser):
            # Refresh WeChat token
            access_token = create_wechat_access_token(current_user.wxid)
        else:
            # For User (Supabase) tokens, we don't handle refresh here
            # Supabase handles its own token refresh on the frontend
            raise HTTPException(status_code=400, detail="Supabase tokens should be refreshed via Supabase client")

        return TokenRefreshResponse(success=True, access_token=access_token)

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {e!s}")
