---
description: Create a git commit with auto-generated message (context-light)
argument-hint: [--amend] [optional message or instructions]
context: fork
agent: general-purpose
---

## Usage
```
/commit [--amend] [optional message or instructions]
```

## Examples
```
/commit
/commit fix auth bug
/commit --amend
/commit --amend update error handling
```

## Flags

- `--amend` – amend the previous commit instead of creating a new one. Can optionally include a new message hint; if not provided, reuses/refines the existing commit message.

## Instructions

1. **Receive context from main session**:
   - Main session provides a brief summary of current task/goal
   - Use this to understand what the user has been working on

2. **Check for --amend flag**:
   - If `--amend` is present, this will modify the previous commit
   - Run `git log -1 --oneline` to see the current commit being amended

3. **Stage changes intelligently** (no user prompts):
   - Run `git status` to see all changes
   - If changes are already staged, use those
   - If nothing staged, decide what to stage based on context and message:
     - If user message hints at specific files/features, stage only relevant files
     - If context suggests working on specific area, stage files in that area
     - Otherwise, stage all changes with `git add -A`
   - If nothing to commit and not amending, inform user and exit

4. **Generate commit message**:
   - If user provided a message/hint, use it as guidance
   - If `--amend` with no new hint, keep or refine the existing message
   - Otherwise, analyze the diff and session context to generate a conventional commit message
   - Format: `<type>(<scope>): <short description>`
   - Types: feat, fix, docs, style, refactor, test, chore

5. **Execute directly** (no confirmation needed):
   - Normal: `git commit -m "<message>"`
   - Amend: `git commit --amend -m "<message>"`

6. **Return brief confirmation**:
```
Committed: feat(auth): add JWT token refresh logic
2 files changed, 45 insertions(+), 12 deletions(-)
```
or
```
Amended: feat(auth): add JWT token refresh logic
2 files changed, 45 insertions(+), 12 deletions(-)
```

## Key Requirements

- Keep output minimal
- Use conventional commit format
- Don't explain the changes in detail—just commit and confirm
