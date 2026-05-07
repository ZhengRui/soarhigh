"""Pydantic AI agent registration for the General Q&A agent.

Read-only. Knowledge-driven via skill markdown files in `./skills/`.
Tool surface is intentionally minimal (one tool: `view_skill`); the
agent's job is to read the skill manifest in the prompt, decide what
applies, and pull the body.
"""

import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from app.agents.general import tools as _tools
from app.agents.general.models import GeneralDeps
from app.agents.general.prompts import GENERAL_SYSTEM_PROMPT
from app.agents.runtime.model_settings import build_model_settings
from app.agents.runtime.skill_registry import SkillRegistry
from app.config import (
    DEEPSEEK_API_KEY,
    GENERAL_AGENT_MODEL,
    GENERAL_THINKING_LEVEL,
    GOOGLE_API_KEY,
    OPENAI_API_KEY,
)

# Same trick as the meeting / statistics agents: bridge .env values to
# os.environ so Pydantic AI providers find the keys at Agent construction.
os.environ.setdefault("GOOGLE_API_KEY", GOOGLE_API_KEY or "not-configured")
os.environ.setdefault("OPENAI_API_KEY", OPENAI_API_KEY or "not-configured")
os.environ.setdefault("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY or "not-configured")

# Single registry built at process start. Skill content lives next to
# this module so `pip install` / Vercel deploys ship it automatically.
SKILLS_DIR = Path(__file__).parent / "skills"
skill_registry = SkillRegistry(SKILLS_DIR)
SkillName = Literal[
    "meeting-protocol",
    "soarhigh-bylaws",
    "soarhigh-faq",
    "soarhigh-meeting-manager",
    "soarhigh-officer-election",
    "soarhigh-quick-links",
    "toastmasters-evaluation",
    "toastmasters-pathways",
    "toastmasters-role-scripts",
    "toastmasters-roles",
]
SkillNameArg = Annotated[
    SkillName,
    Field(description="Exact installed skill name from the enum. Do not invent aliases or near-matches."),
]


# Conservative limits: knowledge questions rarely need many tool calls
# (one or two view_skill loads is typical). Matches the statistics agent.
USAGE_LIMITS = UsageLimits(request_limit=10, total_tokens_limit=300_000)


agent = Agent(
    GENERAL_AGENT_MODEL,
    system_prompt=GENERAL_SYSTEM_PROMPT,
    deps_type=GeneralDeps,
    retries=2,
    model_settings=build_model_settings(GENERAL_AGENT_MODEL, thinking_level=GENERAL_THINKING_LEVEL),
)


@agent.tool
async def view_skill(ctx: RunContext[GeneralDeps], name: SkillNameArg) -> str:
    """Return the full markdown body of a named skill.

    Use this when the skill manifest in your system prompt advertises a
    skill whose description is relevant to the user's question. You MUST
    load skills via this tool before answering — the manifest descriptions
    are not authoritative on their own.

    The `name` argument is schema-constrained to the installed skill
    names. Pick an exact enum value; never invent aliases such as
    `new-member-faq`.
    """
    return await _tools.apply_view_skill(ctx, name=name)
