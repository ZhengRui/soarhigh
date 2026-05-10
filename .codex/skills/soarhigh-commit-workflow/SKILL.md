---
name: soarhigh-commit-workflow
description: Project-specific commit workflow for SoarHigh. Use when the user asks to commit changes, inspect commit readiness, or handle the recurring pre-commit mypy issue; this repo expects commits to run with the backend virtualenv on PATH.
---

# SoarHigh Commit Workflow

Use this workflow for commits in this repository.

## Before Staging

Inspect the exact scope:

```bash
git status --short
git diff --stat
git log -3 --format=%B
```

Stage only files that belong to the requested change. Do not include unrelated
user edits.

## Validation

Run focused checks for the files touched. Common backend commands:

```bash
cd backend
PYTHONPATH=. uv run pytest <relevant-tests>
uv run ruff check <relevant-python-files>
PYTHONPATH=. uv run mypy <relevant-python-files>
```

For frontend changes, rely on staged-file hooks when the change is narrow; run
broader `bun` checks when the risk justifies it.

## Commit Environment

Before `git commit`, activate the backend virtualenv from the repo root:

```bash
source backend/.venv/bin/activate
which mypy
git commit ...
```

The backend pre-commit config invokes bare `mypy` with `language: system`:

```text
cd backend && mypy .
```

Activating `backend/.venv` puts the project-installed `mypy`, `ruff`, and other
Python tools on `PATH`, avoiding the recurring `mypy: command not found` hook
failure.

If the hook still fails only with `mypy: command not found`, treat that as a
local hook environment issue:

1. Confirm other hook tasks passed or did not report real code errors.
2. Run the equivalent check explicitly:

```bash
cd backend
PYTHONPATH=. uv run mypy <relevant-python-files>
```

3. If `uv run mypy` passes, commit with `--no-verify` and mention in the final
response that the hook infrastructure failed but the project mypy command
passed.

Do not use `--no-verify` to bypass real lint, type, test, or formatting
failures.

## Message Style

Match recent history:

- concise imperative subject, usually scoped, for example
  `feat(agent): add web public assistant`
- blank line, then a useful body
- bullets when multiple behaviors changed
- wrap body lines around 70-72 characters
- end Codex-authored commits with:

```text
Co-Authored-By: OpenAI Codex GPT 5.5 <noreply@openai.com>
```

## After Hook Failures

Hooks may modify staged files with Prettier or formatters. Before retrying,
inspect:

```bash
git status --short
git diff --cached --stat
git diff --stat
```

Re-stage intended formatter changes before retrying the commit.
