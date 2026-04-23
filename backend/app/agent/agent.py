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
