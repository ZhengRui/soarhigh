from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROFILE_NAME = "wxpost"
PROFILE_DESCRIPTION = "Dedicated SoarHigh WxPost writing and editing assistant."
LEGACY_PLUGIN_NAME = "soarhigh-wxpost-card"
LEGACY_MCP_SERVER_NAME = "soarhigh-wxpost"
LEGACY_SKILL_NAME = "soarhigh-wxpost-authoring"
NAVIGATION_PLUGIN_NAME = "soarhigh-wxpost-navigation"
CURRENT_TOOLSET_NAME = "wxpost_current"
NAVIGATION_TOOLSET_NAME = "wxpost_navigation"
FULL_MCP_SERVER_NAME = "soarhigh-wxpost"
BASE_TOOLSETS = ["skills", "browser", "vision"]
WEB_SEARCH_BACKEND = "tavily"
DISABLED_TOOLSETS = [
    "terminal",
    "file",
    "code_execution",
    "video",
    "image_gen",
    "video_gen",
    "x_search",
    "tts",
    "todo",
    "memory",
    "context_engine",
    "session_search",
    "project",
    "clarify",
    "delegation",
    "kanban",
    "cronjob",
    "homeassistant",
    "spotify",
    "yuanbao",
    "computer_use",
]


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        yaml.safe_dump(value, sort_keys=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _enabled_toolsets() -> list[str]:
    toolsets = list(BASE_TOOLSETS)
    if os.environ.get("TAVILY_API_KEY", "").strip():
        toolsets.insert(1, "web")
    return toolsets


def _replace_directory(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(source, temporary)
    if destination.exists():
        shutil.rmtree(destination)
    os.replace(temporary, destination)


def _remove_legacy_default_profile_state(
    root_home: Path,
    default_config: dict[str, Any],
) -> None:
    """Remove WxPost integrations superseded by the managed profile.

    The default profile remains the source of shared model and platform
    settings. Only the old WxPost-specific entries and installed copies are
    removed; unrelated default-profile configuration is preserved.
    """

    changed = False
    mcp_servers = default_config.get("mcp_servers")
    if isinstance(mcp_servers, dict) and LEGACY_MCP_SERVER_NAME in mcp_servers:
        del mcp_servers[LEGACY_MCP_SERVER_NAME]
        changed = True
        if not mcp_servers:
            del default_config["mcp_servers"]

    plugins = default_config.get("plugins")
    if isinstance(plugins, dict):
        for key in ("enabled", "disabled"):
            values = plugins.get(key)
            if isinstance(values, list) and LEGACY_PLUGIN_NAME in values:
                plugins[key] = [
                    value for value in values if value != LEGACY_PLUGIN_NAME
                ]
                changed = True
        entries = plugins.get("entries")
        if isinstance(entries, dict) and LEGACY_PLUGIN_NAME in entries:
            del entries[LEGACY_PLUGIN_NAME]
            changed = True

    if changed:
        _write_yaml(root_home / "config.yaml", default_config)

    for legacy_path in (
        root_home / "plugins" / LEGACY_PLUGIN_NAME,
        root_home / "skills" / "domain" / LEGACY_SKILL_NAME,
    ):
        if legacy_path.exists():
            shutil.rmtree(legacy_path)


def configure_profile(
    *,
    root_home: Path,
    source_skill: Path,
    source_soul: Path,
    source_plugin: Path,
) -> Path:
    default_config_path = root_home / "config.yaml"
    default_env_path = root_home / ".env"
    if not default_config_path.is_file():
        raise RuntimeError(f"missing default Hermes config: {default_config_path}")
    if not default_env_path.is_file():
        raise RuntimeError(f"missing default Hermes environment: {default_env_path}")
    if not (source_skill / "SKILL.md").is_file():
        raise RuntimeError(f"missing WxPost authoring skill: {source_skill}")
    if not source_soul.is_file():
        raise RuntimeError(f"missing WxPost profile identity: {source_soul}")
    if not (source_plugin / "plugin.yaml").is_file():
        raise RuntimeError(f"missing WxPost navigation plugin: {source_plugin}")

    loaded = yaml.safe_load(default_config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("default Hermes config must be a YAML mapping")
    config = deepcopy(loaded)

    # Hermes toolsets are additive, so the allow-list alone is not a boundary.
    # Keep web search, browser navigation, and image understanding, then
    # explicitly disable the general-purpose capabilities that WxPost
    # authoring does not use. MCP tools are configured separately below.
    enabled_toolsets = _enabled_toolsets()
    config["toolsets"] = enabled_toolsets
    if "web" in enabled_toolsets:
        config["web"] = {
            "backend": WEB_SEARCH_BACKEND,
            "search_backend": WEB_SEARCH_BACKEND,
            "extract_backend": WEB_SEARCH_BACKEND,
        }
    else:
        config.pop("web", None)
    agent_config = config.setdefault("agent", {})
    agent_config["disabled_toolsets"] = DISABLED_TOOLSETS
    # gpt-5.6-luna supports OpenAI priority processing. Keep the dedicated
    # WxPost profile in fast mode without changing the user's default Hermes
    # profile or requiring a per-session `/fast` command.
    agent_config["service_tier"] = "fast"
    # Keep Hermes' text image route for its built-in visual description. The
    # managed Feishu plugin separately preserves official cache paths so the
    # Feishu-only import tool can copy the exact attached files.
    agent_config["image_input_mode"] = "text"
    # Use the same provider and model as the WxPost profile's main agent for
    # image understanding. This avoids an unnecessary auxiliary-provider
    # attempt before Hermes falls back to the main Codex model. Keep the
    # auxiliary timeouts inherited from the default profile, but do not carry
    # provider-specific credentials or transport overrides across providers.
    model_config = config.get("model")
    if isinstance(model_config, dict):
        main_provider = str(model_config.get("provider", "")).strip()
        main_model = str(model_config.get("default", "")).strip()
        if main_provider and main_model:
            vision_config = config.setdefault("auxiliary", {}).setdefault("vision", {})
            vision_config.update(
                {
                    "provider": main_provider,
                    "model": main_model,
                    "base_url": "",
                    "api_key": "",
                }
            )
            for key in ("key_env", "api_key_env", "api_mode"):
                vision_config.pop(key, None)
    config.setdefault("skills", {})["always_load"] = []
    config.setdefault("memory", {})["memory_enabled"] = False
    config.setdefault("memory", {})["user_profile_enabled"] = False
    config.setdefault("curator", {})["enabled"] = False
    config.setdefault("delegation", {})["orchestrator_enabled"] = False
    # Keep Hermes' native confirmation flow for destructive conversation
    # commands such as /new. Feishu renders the confirmation with its native
    # interaction rather than routing the command through the language model.
    config.setdefault("approvals", {})["destructive_slash_confirm"] = True

    # The earlier Feishu card experiment is intentionally not part of the
    # current architecture. This official in-process plugin exists only to
    # read the current Feishu session identity safely; article authoring stays
    # on the controller MCP.
    config["plugins"] = {
        "enabled": [NAVIGATION_PLUGIN_NAME],
        "disabled": [],
        "entries": {},
    }
    common_mcp_env = {
        "PYTHONPATH": "/opt/soarhigh",
        "WXPOST_WORKSPACE_ROOT": "/workspace",
        "WXPOST_UPLOAD_CACHE_ROOTS": (
            "/opt/data/cache:/opt/data/profiles/wxpost/cache"
        ),
        "SOARHIGH_API_BASE_URL": "${SOARHIGH_API_BASE_URL}",
        "WXPOST_SERVICE_TOKEN": "${WXPOST_SERVICE_TOKEN}",
    }
    config["mcp_servers"] = {
        FULL_MCP_SERVER_NAME: {
            "command": "/opt/hermes/.venv/bin/python",
            "args": ["-m", "wxpost_controller.mcp_server"],
            "env": dict(common_mcp_env),
            "enabled": True,
        },
    }
    config["platform_toolsets"] = {
        # The Web Draft Assistant uses task-local in-process tools. ``no_mcp``
        # is deliberate: Hermes registers MCP servers globally, and duplicate
        # full/draft tool names can otherwise leak the cross-workspace surface
        # into API sessions despite the platform allow-list.
        "api_server": [*enabled_toolsets, "no_mcp", CURRENT_TOOLSET_NAME],
        "feishu": [
            *enabled_toolsets,
            FULL_MCP_SERVER_NAME,
            NAVIGATION_TOOLSET_NAME,
        ],
    }
    # Hermes enables newly discovered plugin toolsets on every platform until
    # each platform has acknowledged them. Mark this managed toolset as known
    # so its explicit Feishu membership is authoritative and it cannot leak
    # workspace navigation into the Web Draft Assistant.
    config["known_plugin_toolsets"] = {
        "api_server": [CURRENT_TOOLSET_NAME, NAVIGATION_TOOLSET_NAME],
        "feishu": [CURRENT_TOOLSET_NAME, NAVIGATION_TOOLSET_NAME],
    }

    profile_home = root_home / "profiles" / PROFILE_NAME
    profile_home.mkdir(parents=True, exist_ok=True)
    _write_yaml(
        profile_home / "profile.yaml",
        {"description": PROFILE_DESCRIPTION, "description_auto": False},
    )
    _write_yaml(profile_home / "config.yaml", config)
    (profile_home / "SOUL.md").write_text(
        source_soul.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (profile_home / ".no-bundled-skills").write_text(
        "Managed by SoarHigh; do not seed bundled Hermes skills.\n",
        encoding="utf-8",
    )

    profile_env_path = profile_home / ".env"
    if profile_env_path.exists() or profile_env_path.is_symlink():
        profile_env_path.unlink()
    profile_env_path.symlink_to(default_env_path)

    with tempfile.TemporaryDirectory(dir=profile_home) as temporary_directory:
        staged_skills = Path(temporary_directory)
        shutil.copytree(
            source_skill,
            staged_skills / "soarhigh-wxpost-authoring",
        )
        _replace_directory(staged_skills, profile_home / "skills")

    with tempfile.TemporaryDirectory(dir=profile_home) as temporary_directory:
        staged_plugins = Path(temporary_directory)
        shutil.copytree(
            source_plugin,
            staged_plugins / NAVIGATION_PLUGIN_NAME,
        )
        _replace_directory(staged_plugins, profile_home / "plugins")

    _remove_legacy_default_profile_state(root_home, loaded)

    return profile_home


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-home", type=Path, required=True)
    parser.add_argument("--source-skill", type=Path, required=True)
    parser.add_argument("--source-soul", type=Path, required=True)
    parser.add_argument("--source-plugin", type=Path, required=True)
    args = parser.parse_args()
    configure_profile(
        root_home=args.root_home,
        source_skill=args.source_skill,
        source_soul=args.source_soul,
        source_plugin=args.source_plugin,
    )


if __name__ == "__main__":
    main()
