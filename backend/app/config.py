from os import path
from typing import List

from starlette.config import Config

# Check if .env file exists first
env_path = ".env"
config = Config(env_path if path.exists(env_path) else None)

SUPABASE_URL = config("SUPABASE_URL", cast=str)
SUPABASE_ANON_KEY = config("SUPABASE_ANON_KEY", cast=str)
SUPABASE_SERVICE_ROLE_KEY = config("SUPABASE_SERVICE_ROLE_KEY", cast=str)
SUPABASE_JWT_SECRET = config("SUPABASE_JWT_SECRET", cast=str)


def parse_cors_origins(v: str) -> List[str]:
    return [origin.strip() for origin in v.split(",")]


CORS_ORIGINS = config("CORS_ORIGINS", cast=parse_cors_origins, default="*")

OPENAI_API_KEY = config("OPENAI_API_KEY", cast=str)

# WeChat Configuration
WECHAT_APP_ID = config("WECHAT_APP_ID", cast=str)
WECHAT_APP_SECRET = config("WECHAT_APP_SECRET", cast=str)
WECHAT_JWT_SECRET = config("WECHAT_JWT_SECRET", cast=str)

# AliCloud OSS Configuration
ALICLOUD_ACCESS_KEY_ID = config("ALICLOUD_ACCESS_KEY_ID", cast=str)
ALICLOUD_ACCESS_KEY_SECRET = config("ALICLOUD_ACCESS_KEY_SECRET", cast=str)
ALICLOUD_OSS_BUCKET = config("ALICLOUD_OSS_BUCKET", cast=str)
ALICLOUD_OSS_ENDPOINT = config("ALICLOUD_OSS_ENDPOINT", cast=str)
ALICLOUD_OSS_MEETING_MEDIA_PREFIX = config("ALICLOUD_OSS_MEETING_MEDIA_PREFIX", cast=str, default="public/meetings")
