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
    config.setdefault("skills", {})["always_load"] = []
    config.setdefault("memory", {})["memory_enabled"] = False
    config.setdefault("memory", {})["user_profile_enabled"] = False
    config.setdefault("curator", {})["enabled"] = False
    config.setdefault("delegation", {})["orchestrator_enabled"] = False

    # The earlier Feishu card experiment is intentionally not part of the
    # current architecture. The normal Hermes Feishu channel and WxPost MCP
    # server are the only integration surfaces in this profile.
    config["plugins"] = {"enabled": [], "disabled": [], "entries": {}}
    config["mcp_servers"] = {
        "soarhigh-wxpost": {
            "command": "/opt/hermes/.venv/bin/python",
            "args": ["-m", "wxpost_controller.mcp_server"],
            "env": {
                "PYTHONPATH": "/opt/soarhigh",
                "WXPOST_WORKSPACE_ROOT": "/workspace",
                "SOARHIGH_API_BASE_URL": "${SOARHIGH_API_BASE_URL}",
                "WXPOST_SERVICE_TOKEN": "${WXPOST_SERVICE_TOKEN}",
            },
            "enabled": True,
        }
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

    # A prior development profile may contain the abandoned card plugin.
    # Removing only this managed profile's plugin directory keeps capability
    # discovery deterministic without touching the default Hermes profile.
    profile_plugins = profile_home / "plugins"
    if profile_plugins.exists():
        shutil.rmtree(profile_plugins)

    _remove_legacy_default_profile_state(root_home, loaded)

    return profile_home


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-home", type=Path, required=True)
    parser.add_argument("--source-skill", type=Path, required=True)
    parser.add_argument("--source-soul", type=Path, required=True)
    args = parser.parse_args()
    configure_profile(
        root_home=args.root_home,
        source_skill=args.source_skill,
        source_soul=args.source_soul,
    )


if __name__ == "__main__":
    main()
