from os import environ

from starlette.config import Config

config = Config(environ.get("DOTENV_PATH", ".env"))

SUPABASE_URL = config("SUPABASE_URL", cast=str)
SUPABASE_ANON_KEY = config("SUPABASE_ANON_KEY", cast=str)
SUPABASE_SERVICE_ROLE_KEY = config("SUPABASE_SERVICE_ROLE_KEY", cast=str)
SUPABASE_JWT_SECRET = config("SUPABASE_JWT_SECRET", cast=str)
