"""Pydantic AI registration for AgentPublic.

Public read-only assistant for non-member visitors. Tool surface is
deliberately separate from the member General agent so member-only skills do
not appear in the public manifest or schema.
"""

import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.agents.general import tools_public as _tools
from app.agents.general.models_public import GeneralPublicDeps
from app.agents.general.prompts_public import (
    GENERAL_PUBLIC_SYSTEM_PROMPT,
    LOAD_SKILL_PUBLIC_INSTRUCTION,
)
from app.agents.runtime.model_settings import build_model_settings
from app.agents.runtime.skill_registry import SkillRegistry
from app.config import (
    DEEPSEEK_API_KEY,
    GENERAL_AGENT_MODEL,
    GENERAL_THINKING_LEVEL,
    GOOGLE_API_KEY,
    OPENAI_API_KEY,
)

os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")
os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY or "not-configured")
os.environ.setdefault("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY or "not-configured")

SKILLS_DIR = Path(__file__).parent / "skills"

PUBLIC_SKILL_NAMES = (
    "meeting-protocol",
    "soarhigh-bylaws",
    "soarhigh-faq",
    "soarhigh-officer-election",
    "soarhigh-quick-links",
    "toastmasters-evaluation",
    "toastmasters-pathways",
    "toastmasters-role-scripts",
    "toastmasters-roles",
)

skill_registry_public = SkillRegistry(SKILLS_DIR).restricted(PUBLIC_SKILL_NAMES)

SkillNamePublic = Literal[
    "meeting-protocol",
    "soarhigh-bylaws",
    "soarhigh-faq",
    "soarhigh-officer-election",
    "soarhigh-quick-links",
    "toastmasters-evaluation",
    "toastmasters-pathways",
    "toastmasters-role-scripts",
    "toastmasters-roles",
]
SkillNamePublicArg = Annotated[
    SkillNamePublic,
    Field(description="Exact installed public skill name from the enum. Do not invent aliases."),
]

USAGE_LIMITS_PUBLIC = UsageLimits(request_limit=10, total_tokens_limit=300_000)


def compose_system_prompt_public() -> str:
    parts = [GENERAL_PUBLIC_SYSTEM_PROMPT]
    always = skill_registry_public.render_always_loaded()
    if always:
        parts.append(always)
    manifest = skill_registry_public.render_manifest()
    if manifest:
        parts.append(manifest)
        parts.append(LOAD_SKILL_PUBLIC_INSTRUCTION)
    return "\n\n".join(parts)


agent_public = Agent(
    GENERAL_AGENT_MODEL,
    system_prompt=compose_system_prompt_public(),
    deps_type=GeneralPublicDeps,
    retries=2,
    model_settings=build_model_settings(GENERAL_AGENT_MODEL, thinking_level=GENERAL_THINKING_LEVEL),
)


@agent_public.tool
async def view_skill_public(ctx: RunContext[GeneralPublicDeps], name: SkillNamePublicArg) -> str:
    """Return the full markdown body of a named public skill."""
    return await _tools.apply_view_skill_public(ctx, name=name)


@agent_public.tool
async def lookup_meeting_public(
    ctx: RunContext[GeneralPublicDeps],
    no: int | None = None,
    theme_substring: str | None = None,
    introduction_substring: str | None = None,
    type_filter: Literal["Regular", "Workshop", "Custom"] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 5,
) -> dict:
    """READ-ONLY. Find published meetings by public-safe filters.

    Use this for public meeting discovery: "情感相关的会议", "今年上半年
    的 workshop", "#451 是哪次会议". This searches published meeting
    number, theme, introduction, type, and date range. It does NOT expose
    member attendance, role counts, awards matrices, draft meetings, or
    private dashboards.

    Topic search convention:
    - When the user gives a topic keyword without saying which field to
      search, fan out to BOTH theme_substring and introduction_substring.
    - Also fan out across the likely bilingual keyword. Chinese topic ->
      English translation; English topic -> Chinese translation. For
      example, "情感相关" should call theme/introduction searches for
      "情感", "emotion", "emotional", "relationship", and "relationships";
      "emotion" should also search "情感".
    - Keep field/keyword searches as separate calls. Then group or
      de-duplicate matches in the reply and explain whether they came from
      the theme or the introduction.
    - If the user explicitly says theme/title only, use theme_substring.
      If the user explicitly says introduction/description only, use
      introduction_substring.
    """
    return await _tools.apply_lookup_meeting_public(
        ctx,
        no=no,
        theme_substring=theme_substring,
        introduction_substring=introduction_substring,
        type_filter=type_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
