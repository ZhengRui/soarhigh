from pathlib import Path

import yaml

from wxpost_profile.configure import (
    BASE_TOOLSETS,
    CURRENT_TOOLSET_NAME,
    DISABLED_TOOLSETS,
    FULL_MCP_SERVER_NAME,
    LEGACY_MCP_SERVER_NAME,
    LEGACY_PLUGIN_NAME,
    LEGACY_SKILL_NAME,
    NAVIGATION_PLUGIN_NAME,
    NAVIGATION_TOOLSET_NAME,
    _enabled_toolsets,
    configure_profile,
)


def test_configure_profile_keeps_only_wxpost_capabilities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    root_home = tmp_path / "hermes"
    root_home.mkdir()
    (root_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {"provider": "example", "default": "model"},
                "auxiliary": {
                    "vision": {
                        "provider": "old-provider",
                        "model": "old-model",
                        "base_url": "https://old.example/v1",
                        "api_key": "old-key",
                        "api_mode": "chat_completions",
                        "timeout": 120,
                        "download_timeout": 30,
                    }
                },
                "toolsets": ["hermes-cli"],
                "agent": {"disabled_toolsets": ["existing"]},
                "memory": {
                    "memory_enabled": True,
                    "user_profile_enabled": True,
                },
                "curator": {"enabled": True},
                "delegation": {"orchestrator_enabled": True},
                "plugins": {
                    "enabled": [LEGACY_PLUGIN_NAME, "unrelated"],
                    "disabled": [LEGACY_PLUGIN_NAME],
                    "entries": {
                        LEGACY_PLUGIN_NAME: {"enabled": True},
                        "unrelated": {"enabled": True},
                    },
                },
                "mcp_servers": {
                    LEGACY_MCP_SERVER_NAME: {"enabled": True},
                    "unrelated": {"enabled": True},
                },
            }
        ),
        encoding="utf-8",
    )
    (root_home / ".env").write_text("FEISHU_APP_ID=test\n", encoding="utf-8")
    source_skill = tmp_path / "skill"
    source_skill.mkdir()
    (source_skill / "SKILL.md").write_text("# WxPost\n", encoding="utf-8")
    source_soul = tmp_path / "SOUL.md"
    source_soul.write_text("SoarHigh Club's AI Assistant\n", encoding="utf-8")
    source_plugin = tmp_path / "navigation-plugin"
    source_plugin.mkdir()
    (source_plugin / "plugin.yaml").write_text(
        f"name: {NAVIGATION_PLUGIN_NAME}\n", encoding="utf-8"
    )
    (source_plugin / "__init__.py").write_text("plugin = True\n", encoding="utf-8")
    legacy_plugin = root_home / "plugins" / LEGACY_PLUGIN_NAME
    legacy_plugin.mkdir(parents=True)
    (legacy_plugin / "plugin.yaml").write_text("name: stale\n", encoding="utf-8")
    legacy_skill = root_home / "skills" / "domain" / LEGACY_SKILL_NAME
    legacy_skill.mkdir(parents=True)
    (legacy_skill / "SKILL.md").write_text("stale\n", encoding="utf-8")

    profile_home = configure_profile(
        root_home=root_home,
        source_skill=source_skill,
        source_soul=source_soul,
        source_plugin=source_plugin,
    )

    config = yaml.safe_load((profile_home / "config.yaml").read_text())
    assert config["model"] == {"provider": "example", "default": "model"}
    assert config["toolsets"] == BASE_TOOLSETS
    assert "browser" in config["toolsets"]
    assert "browser" not in config["agent"]["disabled_toolsets"]
    assert "web" not in config
    assert config["agent"]["disabled_toolsets"] == DISABLED_TOOLSETS
    assert config["agent"]["service_tier"] == "fast"
    assert config["agent"]["image_input_mode"] == "text"
    assert config["auxiliary"]["vision"] == {
        "provider": "example",
        "model": "model",
        "base_url": "",
        "api_key": "",
        "timeout": 120,
        "download_timeout": 30,
    }
    assert config["skills"]["always_load"] == []
    assert config["memory"] == {
        "memory_enabled": False,
        "user_profile_enabled": False,
    }
    assert config["curator"]["enabled"] is False
    assert config["delegation"]["orchestrator_enabled"] is False
    assert config["approvals"]["destructive_slash_confirm"] is True
    assert config["plugins"] == {
        "enabled": [NAVIGATION_PLUGIN_NAME],
        "disabled": [],
        "entries": {},
    }
    assert list(config["mcp_servers"]) == [FULL_MCP_SERVER_NAME]
    assert config["platform_toolsets"] == {
        "api_server": [*BASE_TOOLSETS, "no_mcp", CURRENT_TOOLSET_NAME],
        "feishu": [
            *BASE_TOOLSETS,
            FULL_MCP_SERVER_NAME,
            NAVIGATION_TOOLSET_NAME,
        ],
    }
    assert config["known_plugin_toolsets"] == {
        "api_server": [CURRENT_TOOLSET_NAME, NAVIGATION_TOOLSET_NAME],
        "feishu": [CURRENT_TOOLSET_NAME, NAVIGATION_TOOLSET_NAME],
    }
    for server in config["mcp_servers"].values():
        assert server["env"]["WXPOST_UPLOAD_CACHE_ROOTS"] == (
            "/opt/data/cache:/opt/data/profiles/wxpost/cache"
        )
    assert (profile_home / ".env").resolve() == root_home / ".env"
    assert (profile_home / "SOUL.md").read_text() == source_soul.read_text()
    assert (
        profile_home / "skills" / "soarhigh-wxpost-authoring" / "SKILL.md"
    ).read_text() == "# WxPost\n"
    assert (
        profile_home / "plugins" / NAVIGATION_PLUGIN_NAME / "__init__.py"
    ).read_text() == "plugin = True\n"

    default_config = yaml.safe_load((root_home / "config.yaml").read_text())
    assert default_config["mcp_servers"] == {"unrelated": {"enabled": True}}
    assert default_config["plugins"] == {
        "enabled": ["unrelated"],
        "disabled": [],
        "entries": {"unrelated": {"enabled": True}},
    }
    assert not legacy_plugin.exists()
    assert not legacy_skill.exists()


def test_enabled_toolsets_adds_web_only_with_tavily_key(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert _enabled_toolsets() == BASE_TOOLSETS

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    assert _enabled_toolsets() == ["skills", "web", "browser", "vision"]


def test_configure_profile_replaces_stale_managed_content(tmp_path: Path) -> None:
    root_home = tmp_path / "hermes"
    root_home.mkdir()
    (root_home / "config.yaml").write_text("model: {}\n", encoding="utf-8")
    (root_home / ".env").write_text("TOKEN=test\n", encoding="utf-8")
    source_skill = tmp_path / "skill"
    source_skill.mkdir()
    (source_skill / "SKILL.md").write_text("current\n", encoding="utf-8")
    source_soul = tmp_path / "SOUL.md"
    source_soul.write_text("current identity\n", encoding="utf-8")
    source_plugin = tmp_path / "navigation-plugin"
    source_plugin.mkdir()
    (source_plugin / "plugin.yaml").write_text(
        f"name: {NAVIGATION_PLUGIN_NAME}\n", encoding="utf-8"
    )
    (source_plugin / "__init__.py").write_text("current plugin\n", encoding="utf-8")
    profile_home = root_home / "profiles" / "wxpost"
    stale_skill = profile_home / "skills" / "soarhigh-wxpost-authoring"
    stale_skill.mkdir(parents=True)
    (stale_skill / "SKILL.md").write_text("stale\n", encoding="utf-8")
    unrelated_skill = profile_home / "skills" / "unrelated"
    unrelated_skill.mkdir()
    (unrelated_skill / "SKILL.md").write_text("unrelated\n", encoding="utf-8")
    stale_plugin = profile_home / "plugins" / "soarhigh-wxpost-card"
    stale_plugin.mkdir(parents=True)

    configure_profile(
        root_home=root_home,
        source_skill=source_skill,
        source_soul=source_soul,
        source_plugin=source_plugin,
    )

    assert (stale_skill / "SKILL.md").read_text() == "current\n"
    assert not unrelated_skill.exists()
    assert not stale_plugin.exists()
    assert (
        profile_home / "plugins" / NAVIGATION_PLUGIN_NAME / "__init__.py"
    ).read_text() == "current plugin\n"
