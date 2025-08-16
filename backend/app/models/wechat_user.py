from typing import Optional

from pydantic import BaseModel, Field


class WeChatUser(BaseModel):
    """WeChat miniapp user model."""

    wxid: str = Field(description="WeChat openid")
    attendee_id: Optional[str] = Field(default=None, description="Linked attendee ID if bound to meeting participant")


class WeChatLoginRequest(BaseModel):
    """Request model for WeChat login."""

    wx_code: str = Field(description="Temporary code from wx.login()")


class WeChatLoginResponse(BaseModel):
    """Response model for WeChat login."""

    success: bool = Field(description="Whether login was successful")
    access_token: str = Field(description="JWT access token for subsequent API calls")


class TokenRefreshResponse(BaseModel):
    """Response model for token refresh."""

    success: bool = Field(description="Whether refresh was successful")
    access_token: str = Field(description="New JWT access token")
