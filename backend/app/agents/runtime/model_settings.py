"""Shared Pydantic AI model_settings builder.

Each agent (router / meeting / statistics) tunes thinking effort
independently via its own *_THINKING_LEVEL env var. The helper maps a
single normalized level (MINIMAL / LOW / MEDIUM / HIGH) onto whatever
the underlying provider accepts:

* Gemini 3.x family — `thinking_level` enum (MINIMAL / LOW / MEDIUM /
  HIGH). Includes gemini-3.1-flash-lite, which IS a thinking model
  (default MINIMAL).
* Gemini 2.5 family — `thinking_budget` int. Has no level enum to map
  to, so we always pass `-1` (dynamic) and ignore the input level.
  gemini-2.5-flash-lite does NOT support thinking; intentionally
  excluded.
* OpenAI o-series + gpt-5 — `openai_reasoning_effort` (lowercase
  minimal/low/medium/high). Non-reasoning OpenAI models (gpt-4, gpt-4o,
  gpt-3.5-turbo) return None.

Returns None for any model that doesn't expose thinking — Pydantic AI
then uses the provider default.
"""

from __future__ import annotations

from typing import Literal

ThinkingLevel = Literal["MINIMAL", "LOW", "MEDIUM", "HIGH"]


def build_model_settings(model_spec: str, *, thinking_level: str = "MINIMAL"):
    """Return provider-specific model_settings, or None for non-thinking models."""
    level = (thinking_level or "MINIMAL").upper()

    if "gemini-3" in model_spec:
        from pydantic_ai.models.google import GoogleModelSettings

        return GoogleModelSettings(
            google_thinking_config={
                "thinking_level": level,  # type: ignore[typeddict-item]
                "include_thoughts": True,
            },
        )

    if "gemini-2.5" in model_spec and "flash-lite" not in model_spec:
        from pydantic_ai.models.google import GoogleModelSettings

        return GoogleModelSettings(
            google_thinking_config={
                "thinking_budget": -1,
                "include_thoughts": True,
            },
        )

    if _is_openai_reasoning_model(model_spec):
        from pydantic_ai.models.openai import OpenAIChatModelSettings

        return OpenAIChatModelSettings(
            openai_reasoning_effort=level.lower(),  # type: ignore[typeddict-item]
        )

    return None


def _is_openai_reasoning_model(model_spec: str) -> bool:
    """Detect OpenAI reasoning models by name. Conservative — only matches
    known reasoning families (o-series, gpt-5).

    Examples that match:
        openai:o4-mini, openai:o3, o1-mini, openai:gpt-5, gpt-5-turbo
    Examples that don't:
        openai:gpt-4o, gpt-4-turbo, gpt-3.5-turbo, anthropic:claude-..."""
    name = model_spec.split(":", 1)[-1].lower() if ":" in model_spec else model_spec.lower()
    if len(name) >= 2 and name[0] == "o" and name[1].isdigit():
        return True
    if name.startswith("gpt-5"):
        return True
    return False
