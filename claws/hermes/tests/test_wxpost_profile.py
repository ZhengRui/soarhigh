from pathlib import Path

import yaml

from wxpost_profile.configure import (
    BASE_TOOLSETS,
    DISABLED_TOOLSETS,
    LEGACY_MCP_SERVER_NAME,
    LEGACY_PLUGIN_NAME,
    LEGACY_SKILL_NAME,
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
    )

    config = yaml.safe_load((profile_home / "config.yaml").read_text())
    assert config["model"] == {"provider": "example", "default": "model"}
    assert config["toolsets"] == BASE_TOOLSETS
    assert "browser" in config["toolsets"]
    assert "browser" not in config["agent"]["disabled_toolsets"]
    assert "web" not in config
    assert config["agent"]["disabled_toolsets"] == DISABLED_TOOLSETS
    assert config["agent"]["service_tier"] == "fast"
    assert config["skills"]["always_load"] == []
    assert config["memory"] == {
        "memory_enabled": False,
        "user_profile_enabled": False,
    }
    assert config["curator"]["enabled"] is False
    assert config["delegation"]["orchestrator_enabled"] is False
    assert config["plugins"] == {"enabled": [], "disabled": [], "entries": {}}
    assert list(config["mcp_servers"]) == ["soarhigh-wxpost"]
    assert (profile_home / ".env").resolve() == root_home / ".env"
    assert (profile_home / "SOUL.md").read_text() == source_soul.read_text()
    assert (
        profile_home / "skills" / "soarhigh-wxpost-authoring" / "SKILL.md"
    ).read_text() == "# WxPost\n"
    assert not (profile_home / "plugins").exists()

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
    )

    assert (stale_skill / "SKILL.md").read_text() == "current\n"
    assert not unrelated_skill.exists()
    assert not (profile_home / "plugins").exists()
