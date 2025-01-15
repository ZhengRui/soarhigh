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
