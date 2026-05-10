"""AgentPublic tool implementations."""

from typing import Literal

from pydantic_ai import RunContext

from app.agents.general.models_public import GeneralPublicDeps
from app.services import meeting_lookup


async def apply_view_skill_public(ctx: RunContext[GeneralPublicDeps], name: str) -> str:
    """Return the full body of an allowed public skill."""
    return ctx.deps.skill_registry.view(name)


async def apply_lookup_meeting_public(
    ctx: RunContext[GeneralPublicDeps],
    no: int | None = None,
    theme_substring: str | None = None,
    introduction_substring: str | None = None,
    type_filter: Literal["Regular", "Workshop", "Custom"] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 5,
) -> dict:
    """Find published meetings by public-safe filters.

    Delegates to the shared meeting_lookup service, whose user_id=None DB
    path returns published meetings only.
    """
    return await meeting_lookup.apply_lookup_meeting(
        ctx,
        no=no,
        theme_substring=theme_substring,
        introduction_substring=introduction_substring,
        type_filter=type_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
