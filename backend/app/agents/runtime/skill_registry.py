"""Skill registry: scan a skills/ directory at startup, expose its
markdown contents to agents at runtime.

A skill is a directory containing a single SKILL.md file. The file has
YAML frontmatter (name, description, optionally always) followed by a
markdown body. See plans/2026-05-06-skills-and-general-qa-agent-design.md
for the design rationale.

Three runtime affordances:

- `render_manifest()`: a markdown bullet list of (name — description) for
  injection into the agent's system prompt. The agent reads this to
  decide whether any skill is relevant to the current turn.
- `render_always_loaded()`: full bodies of skills marked `always: true`,
  concatenated. Reserve for tiny mandatory framing — knowledge content
  should NOT use this.
- `view(name)`: full body of a named skill. The agent calls this via the
  `view_skill` tool when it judges a skill relevant. Raises
  `pydantic_ai.ModelRetry` (NOT a plain exception) when the name is
  unknown so the model can self-correct (typo, hyphen vs underscore)
  instead of crashing the turn into agent_error. Mirrors the pattern in
  `agents/statistics/tools.py` (~15 ModelRetry call sites).

Errors at construction time fail loud: a malformed SKILL.md is a config
error, not something to defer until first use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai import ModelRetry

# Mirrors how Nanobot strips frontmatter (single regex, no third-party
# frontmatter library). Matches a leading `---\n...\n---\n` block.
_FRONTMATTER_RE = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?",
    re.DOTALL,
)


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    body: str
    always: bool
    path: Path


class SkillRegistry:
    """Loads skill markdown files from `<skills_dir>/<name>/SKILL.md`.

    Read-only after construction. Construction is cheap (one filesystem
    walk + per-file YAML parse) and intended to run once at process
    start.
    """

    def __init__(self, skills_dir: Path) -> None:
        self._dir = skills_dir
        self._skills: dict[str, SkillEntry] = self._scan(skills_dir)

    @staticmethod
    def _scan(skills_dir: Path) -> dict[str, SkillEntry]:
        if not skills_dir.exists():
            return {}
        if not skills_dir.is_dir():
            raise ValueError(f"skills_dir must be a directory: {skills_dir}")

        skills: dict[str, SkillEntry] = {}
        # Sort for deterministic manifest ordering across processes.
        for child in sorted(skills_dir.iterdir(), key=lambda p: p.name):
            if not child.is_dir():
                continue
            md_path = child / "SKILL.md"
            if not md_path.is_file():
                continue
            entry = _parse_skill_file(md_path)
            if entry.name != child.name:
                raise ValueError(
                    f"{md_path}: frontmatter `name` ({entry.name!r}) "
                    f"does not match directory name ({child.name!r})."
                )
            # Filesystem prevents same-name dirs, so duplicates here would
            # require a name/dir mismatch — already caught above. Keep the
            # check defensive in case _parse_skill_file is ever loosened.
            if entry.name in skills:
                raise ValueError(f"Duplicate skill name: {entry.name}")
            skills[entry.name] = entry
        return skills

    def render_manifest(self) -> str:
        """Markdown bullet list of (name — description) for system-prompt
        injection. Excludes always-loaded skills (their bodies are already
        in the prompt; no need to advertise twice). Empty string if there
        is nothing to advertise.
        """
        on_demand = [s for s in self._skills.values() if not s.always]
        if not on_demand:
            return ""
        lines = ["# Available Skills (load with view_skill if relevant)"]
        for skill in on_demand:
            lines.append(f"- `{skill.name}` — {skill.description}")
        return "\n".join(lines) + "\n"

    def render_always_loaded(self) -> str:
        """Concatenated bodies of `always: true` skills. Empty if none."""
        always = [s for s in self._skills.values() if s.always]
        if not always:
            return ""
        return "\n\n".join(skill.body for skill in always)

    def view(self, name: str) -> str:
        """Return the full markdown body of a named skill.

        Raises `pydantic_ai.ModelRetry` on unknown name, with valid names
        listed so the LLM can self-correct on the next iteration.
        """
        skill = self._skills.get(name)
        if skill is None:
            valid = sorted(self._skills.keys())
            raise ModelRetry(
                f"Unknown skill name {name!r}. Valid names: {valid}. "
                f"Pick one of these or skip view_skill if no skill matches."
            )
        return skill.body

    def all_names(self) -> list[str]:
        """Sorted list of skill names. For tests/debug; agents should not
        rely on iterating this."""
        return sorted(self._skills.keys())

    def __len__(self) -> int:
        return len(self._skills)


def _parse_skill_file(path: Path) -> SkillEntry:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        raise ValueError(f"{path}: missing YAML frontmatter (expected leading `---` block).")
    frontmatter_text = match.group(1)
    body = raw[match.end() :].strip()

    try:
        meta = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML frontmatter: {exc}") from exc

    if not isinstance(meta, dict):
        raise ValueError(f"{path}: frontmatter must be a YAML mapping, got {type(meta).__name__}.")

    name = meta.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{path}: frontmatter `name` is required and must be a non-empty string.")

    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{path}: frontmatter `description` is required and must be a non-empty string.")

    always = bool(meta.get("always", False))

    return SkillEntry(
        name=name.strip(),
        description=description.strip(),
        body=body,
        always=always,
        path=path,
    )
