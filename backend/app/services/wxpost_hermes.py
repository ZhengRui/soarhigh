"""Focused Hermes Agent calls used by the authenticated WxPost editor."""

from __future__ import annotations

from typing import Any

import httpx


class HermesUnavailableError(RuntimeError):
    """Hermes could not accept or finish the requested editorial turn."""


class HermesResponseError(RuntimeError):
    """Hermes returned a response that cannot be used by the editor."""


def _editorial_context(context: dict[str, Any]) -> str:
    manifest = context.get("manifest")
    editorial = manifest.get("editorial") if isinstance(manifest, dict) else None
    if not isinstance(editorial, dict):
        return "No additional workspace context."

    article_type = str(editorial.get("customArticleType") or editorial.get("articleType") or "unspecified")
    guidance = str(editorial.get("writingGuidance") or "").strip()
    voice_tone = editorial.get("voiceTone")
    selected: list[str] = []
    if isinstance(voice_tone, dict):
        presets = voice_tone.get("presets")
        if isinstance(presets, list):
            selected.extend(str(item) for item in presets)
        custom_profiles = voice_tone.get("customProfiles")
        if isinstance(custom_profiles, list):
            selected.extend(
                str(profile.get("name"))
                for profile in custom_profiles
                if isinstance(profile, dict) and profile.get("selected") is True
            )

    lines = [f"Article type: {article_type}."]
    if guidance:
        lines.append(f"Writing guidance: {guidance}")
    if selected:
        lines.append(f"Already selected voice and tone profiles: {', '.join(selected)}.")
    return "\n".join(lines)


async def suggest_voice_tone_instruction(
    *,
    hermes_url: str,
    service_token: str,
    profile_name: str,
    workspace_context: dict[str, Any],
) -> str:
    """Ask Hermes for one editable, workspace-local voice instruction."""

    if not hermes_url or not service_token:
        raise HermesUnavailableError("Hermes is not configured.")

    system_prompt = (
        "You are Hermes, SoarHigh's editorial assistant. This turn only proposes "
        "one reusable writing instruction for a custom Voice & tone profile. "
        "Do not call tools, read or write files, or modify the workspace. Return "
        "only the instruction text: one or two concise imperative sentences, "
        "20 to 60 words, with no heading, quotation marks, bullets, or commentary."
    )
    user_prompt = (
        f'Custom profile name: "{profile_name}"\n'
        f"{_editorial_context(workspace_context)}\n"
        "Write a practical instruction that explains how the article should sound. "
        "Avoid repeating the profile name as a heading."
    )
    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            response = await client.post(
                f"{hermes_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {service_token}"},
                json={
                    "model": "hermes-agent",
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
    except httpx.HTTPError as error:
        raise HermesUnavailableError("Hermes request failed.") from error

    if response.status_code >= 400:
        raise HermesUnavailableError("Hermes rejected the request.")
    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise HermesResponseError("Hermes returned an invalid response.") from error
    if not isinstance(content, str):
        raise HermesResponseError("Hermes returned an invalid response.")
    instruction = content.strip()
    if not instruction or len(instruction) > 1000:
        raise HermesResponseError("Hermes returned an invalid instruction.")
    return instruction
