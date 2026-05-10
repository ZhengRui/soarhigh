from os import environ, path
from typing import List

from starlette.config import Config

# main.py sets ENV_FILE=.env.bak when --backup is passed; defaults to .env.
env_path = environ.get("ENV_FILE", ".env")
config = Config(env_path if path.exists(env_path) else None)

SUPABASE_URL = config("SUPABASE_URL", cast=str)
SUPABASE_ANON_KEY = config("SUPABASE_ANON_KEY", cast=str)
SUPABASE_SERVICE_ROLE_KEY = config("SUPABASE_SERVICE_ROLE_KEY", cast=str)
SUPABASE_JWT_SECRET = config("SUPABASE_JWT_SECRET", cast=str)


def parse_cors_origins(v: str) -> List[str]:
    return [origin.strip() for origin in v.split(",")]


CORS_ORIGINS = config("CORS_ORIGINS", cast=parse_cors_origins, default="*")

OPENAI_API_KEY = config("OPENAI_API_KEY", cast=str)

# Meeting Agent (Pydantic AI). Prefixed meeting_* for consistency with the
# meeting_agent module / meeting_agent_sessions table — future agents
# (blog, vote) can add their own MODEL env vars without collision.
MEETING_AGENT_MODEL = config("MEETING_AGENT_MODEL", cast=str, default="google-gla:gemini-3.1-flash-lite-preview")
# Router classifier (Pydantic AI). Tiny prompt, structured output, no tools —
# kept independent of MEETING_AGENT_MODEL so router latency / cost can be
# tuned (or downgraded to a smaller model) without touching the specialists.
ROUTER_AGENT_MODEL = config("ROUTER_AGENT_MODEL", cast=str, default="google-gla:gemini-3.1-flash-lite-preview")
# Statistics agent (Pydantic AI). Read-only analytics over historical
# meetings. Kept independent of MEETING_AGENT_MODEL so stats can be tuned
# upward (e.g. gemini-2.5-flash/pro for richer aggregation reasoning) without
# affecting meeting-edit latency.
STATISTICS_AGENT_MODEL = config("STATISTICS_AGENT_MODEL", cast=str, default="google-gla:gemini-3.1-flash-lite-preview")
# General Q&A agent (Pydantic AI). Knowledge-driven, near-zero tool surface
# (one view_skill tool). Kept independent so we can downgrade to a smaller
# model: this agent's main cost is loading skill markdown into the prompt,
# not heavy reasoning.
GENERAL_AGENT_MODEL = config("GENERAL_AGENT_MODEL", cast=str, default="google-gla:gemini-3.1-flash-lite-preview")
# Per-agent thinking effort. Mapped onto provider-specific knobs by
# app/agents/runtime/model_settings.py: thinking_level for Gemini 3.x,
# thinking_budget=-1 (dynamic; level ignored) for Gemini 2.5, and
# openai_reasoning_effort for OpenAI o-series / gpt-5.
ROUTER_THINKING_LEVEL = config("ROUTER_THINKING_LEVEL", cast=str, default="MINIMAL")
MEETING_THINKING_LEVEL = config("MEETING_THINKING_LEVEL", cast=str, default="MINIMAL")
STATISTICS_THINKING_LEVEL = config("STATISTICS_THINKING_LEVEL", cast=str, default="MINIMAL")
GENERAL_THINKING_LEVEL = config("GENERAL_THINKING_LEVEL", cast=str, default="MINIMAL")
# Inner OpenAI model for converting pasted registration text into a structured
# Meeting. Kept separate from MEETING_AGENT_MODEL so we can compare planner
# quality/latency independently of the outer Pydantic AI router.
MEETING_TEXT_PLANNER_MODEL = config("MEETING_TEXT_PLANNER_MODEL", cast=str, default="o4-mini")
MEETING_TEXT_PLANNER_REASONING_EFFORT = config("MEETING_TEXT_PLANNER_REASONING_EFFORT", cast=str, default="low")
# Accept either name; google-genai SDK itself checks both.
GOOGLE_API_KEY = config("GOOGLE_API_KEY", cast=str, default="") or config("GEMINI_API_KEY", cast=str, default="")
DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", cast=str, default="")

# WeChat Configuration
WECHAT_APP_ID = config("WECHAT_APP_ID", cast=str)
WECHAT_APP_SECRET = config("WECHAT_APP_SECRET", cast=str)
WECHAT_JWT_SECRET = config("WECHAT_JWT_SECRET", cast=str)

# Public Agent visitor identity / rate limiting.
# The visitor secret signs the future Web public visitor cookie. Defaulting to
# WECHAT_JWT_SECRET keeps local/test imports working, but production should set
# a dedicated value.
AGENT_PUBLIC_VISITOR_SECRET = config("AGENT_PUBLIC_VISITOR_SECRET", cast=str, default=WECHAT_JWT_SECRET)
AGENT_PUBLIC_LIMIT_PER_MINUTE = config("AGENT_PUBLIC_LIMIT_PER_MINUTE", cast=int, default=10)
AGENT_PUBLIC_LIMIT_PER_DAY = config("AGENT_PUBLIC_LIMIT_PER_DAY", cast=int, default=80)

# AliCloud OSS Configuration
ALICLOUD_ACCESS_KEY_ID = config("ALICLOUD_ACCESS_KEY_ID", cast=str)
ALICLOUD_ACCESS_KEY_SECRET = config("ALICLOUD_ACCESS_KEY_SECRET", cast=str)
ALICLOUD_OSS_BUCKET = config("ALICLOUD_OSS_BUCKET", cast=str)
ALICLOUD_OSS_ENDPOINT = config("ALICLOUD_OSS_ENDPOINT", cast=str)
ALICLOUD_OSS_MEETING_MEDIA_PREFIX = config("ALICLOUD_OSS_MEETING_MEDIA_PREFIX", cast=str, default="public/meetings")
