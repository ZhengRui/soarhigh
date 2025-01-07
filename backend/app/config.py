from os import environ

from starlette.config import Config

config = Config(environ.get("DOTENV_PATH", ".env"))

SUPABASE_URL = config("SUPABASE_URL", cast=str)
SUPABASE_KEY = config("SUPABASE_KEY", cast=str)
SUPABASE_JWT_SECRET = config("SUPABASE_JWT_SECRET", cast=str)
