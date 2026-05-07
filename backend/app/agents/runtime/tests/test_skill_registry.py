from pathlib import Path

import pytest
import yaml
from pydantic_ai import ModelRetry

from app.agents.runtime.skill_registry import SkillRegistry


def _write_skill(skills_dir: Path, name: str, body: str = "Body content.\n", **frontmatter: object) -> Path:
    """Build a SKILL.md fixture under skills_dir/<name>/.

    Uses yaml.safe_dump so values containing reserved characters (colons,
    quotes) round-trip correctly.
    """
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = {"name": name, "description": f"Test skill - {name}", **frontmatter}
    md_path = skill_dir / "SKILL.md"
    md_path.write_text(
        "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n" + body,
        encoding="utf-8",
    )
    return md_path


# ---------------------------------------------------------------------------
# Construction / scanning
# ---------------------------------------------------------------------------


def test_nonexistent_directory_yields_empty_registry(tmp_path):
    registry = SkillRegistry(tmp_path / "does-not-exist")
    assert len(registry) == 0
    assert registry.all_names() == []
    assert registry.render_manifest() == ""
    assert registry.render_always_loaded() == ""


def test_empty_directory_yields_empty_registry(tmp_path):
    registry = SkillRegistry(tmp_path)
    assert len(registry) == 0


def test_directory_passed_as_a_file_raises(tmp_path):
    file_path = tmp_path / "some-file.txt"
    file_path.write_text("not a directory")
    with pytest.raises(ValueError, match="must be a directory"):
        SkillRegistry(file_path)


def test_skill_dirs_without_skill_md_are_skipped(tmp_path):
    (tmp_path / "no-md-here").mkdir()
    (tmp_path / "no-md-here" / "README.md").write_text("not a SKILL.md")
    _write_skill(tmp_path, "valid-one")

    registry = SkillRegistry(tmp_path)
    assert registry.all_names() == ["valid-one"]


def test_loose_files_in_skills_dir_are_ignored(tmp_path):
    (tmp_path / "stray.md").write_text("---\nname: stray\n---\nbody")
    _write_skill(tmp_path, "real-skill")

    registry = SkillRegistry(tmp_path)
    assert registry.all_names() == ["real-skill"]


def test_skills_loaded_in_sorted_order(tmp_path):
    _write_skill(tmp_path, "zulu")
    _write_skill(tmp_path, "alpha")
    _write_skill(tmp_path, "mike")

    registry = SkillRegistry(tmp_path)
    assert registry.all_names() == ["alpha", "mike", "zulu"]


# ---------------------------------------------------------------------------
# Frontmatter validation (fail-loud at construction)
# ---------------------------------------------------------------------------


def test_missing_frontmatter_raises(tmp_path):
    skill_dir = tmp_path / "no-frontmatter"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Just a body, no frontmatter.\n")

    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        SkillRegistry(tmp_path)


def test_invalid_yaml_frontmatter_raises(tmp_path):
    skill_dir = tmp_path / "bad-yaml"
    skill_dir.mkdir()
    # Unbalanced brackets — YAML parser will reject.
    (skill_dir / "SKILL.md").write_text("---\nname: [unclosed\n---\nbody\n")

    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        SkillRegistry(tmp_path)


def test_frontmatter_must_be_mapping_not_list(tmp_path):
    skill_dir = tmp_path / "list-frontmatter"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\n- one\n- two\n---\nbody\n")

    with pytest.raises(ValueError, match="must be a YAML mapping"):
        SkillRegistry(tmp_path)


def test_missing_name_field_raises(tmp_path):
    skill_dir = tmp_path / "no-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: x\n---\nbody\n")

    with pytest.raises(ValueError, match="`name` is required"):
        SkillRegistry(tmp_path)


def test_missing_description_field_raises(tmp_path):
    skill_dir = tmp_path / "no-desc"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\nbody\n")

    with pytest.raises(ValueError, match="`description` is required"):
        SkillRegistry(tmp_path)


def test_empty_string_name_raises(tmp_path):
    skill_dir = tmp_path / "empty-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text('---\nname: ""\ndescription: x\n---\nbody\n')

    with pytest.raises(ValueError, match="`name` is required"):
        SkillRegistry(tmp_path)


def test_name_must_match_directory(tmp_path):
    skill_dir = tmp_path / "dir-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: different-name\ndescription: x\n---\nbody\n")

    with pytest.raises(ValueError, match="does not match directory name"):
        SkillRegistry(tmp_path)


# ---------------------------------------------------------------------------
# Manifest rendering
# ---------------------------------------------------------------------------


def test_manifest_lists_each_on_demand_skill(tmp_path):
    _write_skill(tmp_path, "alpha", description="First skill description")
    _write_skill(tmp_path, "bravo", description="Second skill description")

    registry = SkillRegistry(tmp_path)
    manifest = registry.render_manifest()

    assert "alpha" in manifest
    assert "First skill description" in manifest
    assert "bravo" in manifest
    assert "Second skill description" in manifest
    # Header text appears once.
    assert manifest.count("Available Skills") == 1


def test_manifest_excludes_always_loaded_skills(tmp_path):
    _write_skill(tmp_path, "on-demand", description="Loaded on demand")
    _write_skill(tmp_path, "always-on", description="Always loaded", always=True)

    registry = SkillRegistry(tmp_path)
    manifest = registry.render_manifest()

    assert "on-demand" in manifest
    # always-on must NOT appear — its body is already in the prompt via
    # render_always_loaded(), so advertising it again wastes tokens.
    assert "always-on" not in manifest


def test_manifest_empty_when_only_always_loaded_skills(tmp_path):
    _write_skill(tmp_path, "framing", description="x", always=True)

    registry = SkillRegistry(tmp_path)
    assert registry.render_manifest() == ""


def test_manifest_empty_when_no_skills(tmp_path):
    registry = SkillRegistry(tmp_path)
    assert registry.render_manifest() == ""


# ---------------------------------------------------------------------------
# Always-loaded rendering
# ---------------------------------------------------------------------------


def test_always_loaded_concatenates_only_always_skills(tmp_path):
    _write_skill(tmp_path, "framing-a", body="Framing A body.\n", always=True)
    _write_skill(tmp_path, "framing-b", body="Framing B body.\n", always=True)
    _write_skill(tmp_path, "on-demand", body="On-demand body.\n")

    registry = SkillRegistry(tmp_path)
    rendered = registry.render_always_loaded()

    assert "Framing A body." in rendered
    assert "Framing B body." in rendered
    assert "On-demand body." not in rendered


def test_always_loaded_empty_when_none_marked_always(tmp_path):
    _write_skill(tmp_path, "regular")
    registry = SkillRegistry(tmp_path)
    assert registry.render_always_loaded() == ""


# ---------------------------------------------------------------------------
# view(name) — the LLM-facing entry point
# ---------------------------------------------------------------------------


def test_view_returns_full_body(tmp_path):
    _write_skill(tmp_path, "roles", body="# Roles\n\nDetailed content here.\n")
    registry = SkillRegistry(tmp_path)

    body = registry.view("roles")
    assert "# Roles" in body
    assert "Detailed content here." in body
    # Frontmatter must be stripped out.
    assert "name: roles" not in body
    assert "description:" not in body


def test_view_unknown_name_raises_model_retry(tmp_path):
    _write_skill(tmp_path, "roles")
    _write_skill(tmp_path, "protocol")
    registry = SkillRegistry(tmp_path)

    with pytest.raises(ModelRetry) as exc_info:
        registry.view("rolez")  # typo

    msg = str(exc_info.value)
    assert "rolez" in msg  # echoes the bad input
    # Lists valid names so the model can self-correct.
    assert "roles" in msg
    assert "protocol" in msg


def test_view_unknown_name_in_empty_registry_still_raises_model_retry(tmp_path):
    registry = SkillRegistry(tmp_path)
    with pytest.raises(ModelRetry):
        registry.view("anything")


# ---------------------------------------------------------------------------
# Body content fidelity
# ---------------------------------------------------------------------------


def test_body_preserves_markdown_structure(tmp_path):
    body_text = (
        "# Heading\n\n"
        "Paragraph with **bold** and *italics*.\n\n"
        "## Subheading\n\n"
        "- bullet one\n"
        "- bullet two\n\n"
        "```python\nprint('code block')\n```\n"
    )
    _write_skill(tmp_path, "rich", body=body_text)
    registry = SkillRegistry(tmp_path)

    body = registry.view("rich")
    assert "# Heading" in body
    assert "**bold**" in body
    assert "## Subheading" in body
    assert "- bullet one" in body
    assert "```python" in body


def test_body_handles_unicode(tmp_path):
    body_text = "# 头马角色\n\n## TT\n\n表 Topics 的缩写。\n"
    _write_skill(tmp_path, "cn-skill", body=body_text)
    registry = SkillRegistry(tmp_path)

    body = registry.view("cn-skill")
    assert "头马角色" in body
    assert "Topics 的缩写" in body
