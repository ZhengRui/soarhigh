import httpx
from fastapi import HTTPException

from ..config import WECHAT_APP_ID, WECHAT_APP_SECRET


async def exchange_wx_code_for_openid(wx_code: str) -> str:
    """
    Exchange WeChat code for openid using WeChat API.

    Args:
        wx_code: Temporary code from wx.login()

    Returns:
        openid (wxid) string

    Raises:
        HTTPException: If WeChat API fails or returns error
    """
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "js_code": wx_code,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if "errcode" in data:
                raise HTTPException(status_code=502, detail=f"WeChat API error: {data.get('errmsg', 'Unknown error')}")

            if "openid" not in data:
                raise HTTPException(status_code=502, detail="WeChat API response missing openid")

            return data["openid"]

        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to WeChat API: {e!s}")
