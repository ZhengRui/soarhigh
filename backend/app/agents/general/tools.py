"""General Q&A agent tool implementations.

Tool surface is intentionally tiny: just `view_skill`, which pulls a
skill markdown body from the registry on the deps. Future tools (e.g.
`search_meeting_archive`, `lookup_member_info`) plug in here.

Following the meeting/statistics convention, the actual logic lives in
`apply_*` helpers — `agent.py` imports and registers thin wrappers via
`@agent.tool`. This split keeps the agent module's import side effects
(Agent construction) separable from tool unit-testing.
"""

from pydantic_ai import RunContext

from app.agents.general.models import GeneralDeps


async def apply_view_skill(ctx: RunContext[GeneralDeps], name: str) -> str:
    """Return the full markdown body of a named skill.

    The registry's `view()` raises pydantic_ai.ModelRetry on unknown
    name (with valid names listed); we let it propagate so Pydantic AI
    feeds the retry back to the model on the next iteration.
    """
    return ctx.deps.skill_registry.view(name)
