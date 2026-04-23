import os

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.agent import tools as _tools
from app.agent.models import AgendaDeps
from app.agent.prompts import ROUTER_SYSTEM_PROMPT_MINIMAL
from app.config import AGENT_MODEL, GOOGLE_API_KEY

# Ensure the provider can construct at import time even when no real key is set
# (tests that use TestModel override never hit the provider; missing-key errors
# should surface at request time, not import time).
os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")

USAGE_LIMITS = UsageLimits(request_limit=15, total_tokens_limit=50_000)

agent = Agent(
    AGENT_MODEL,
    system_prompt=ROUTER_SYSTEM_PROMPT_MINIMAL,
    deps_type=AgendaDeps,
    retries=2,
)


@agent.tool
def set_role(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    new_role_taker: str,
) -> dict:
    """Unilateral: set who takes a role in ONE segment. Pass empty string to clear."""
    return _tools.apply_set_role(ctx, segment_id=segment_id, new_role_taker=new_role_taker)


@agent.tool
def set_type(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    new_type: str,
) -> dict:
    """Unilateral: rename ONE segment's type/title (e.g. 'Prepared Speech' -> 'Ice Breaker').
    Keeps id, duration, position, role_taker, and buffers unchanged."""
    return _tools.apply_set_type(ctx, segment_id=segment_id, new_type=new_type)


@agent.tool
def set_duration(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    new_duration_min: int,
) -> dict:
    """Unilateral: set the duration (in minutes) of ONE segment.
    Downstream segment start times recompute automatically."""
    return _tools.apply_set_duration(ctx, segment_id=segment_id, new_duration_min=new_duration_min)


@agent.tool
def set_buffer(
    ctx: RunContext[AgendaDeps],
    segment_id: str,
    buffer_min: int,
) -> dict:
    """Set the buffer (gap/间隔) minutes BEFORE a segment. A buffer is the time gap
    between the previous segment ending and this segment starting - NOT a separate
    segment. Downstream start times recompute."""
    return _tools.apply_set_buffer(ctx, segment_id=segment_id, buffer_min=buffer_min)


@agent.tool
def set_meta(
    ctx: RunContext[AgendaDeps],
    field: str,
    value: str,
) -> dict:
    """Change a meeting-level field. Supported: theme, location, date, start_time, no,
    manager, introduction. end_time is derived and cannot be set directly."""
    return _tools.apply_set_meta(ctx, field=field, value=value)
