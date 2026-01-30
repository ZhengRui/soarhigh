---
description: Create a git commit with auto-generated message (context-light)
argument-hint: [optional message or flags]
context: fork
agent: general-purpose
---

## Usage
```
/commit [optional message or instructions]
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

1. **Check for --amend flag**:
   - If `--amend` is present, this will modify the previous commit
   - Run `git log -1 --oneline` to see the current commit being amended

2. **Check staged changes**: run `git diff --staged`
   - If nothing staged and not amending, run `git diff` to see unstaged changes
   - If unstaged changes exist, ask user if they want to stage all (`git add -A`) or abort
   - If amending with no new staged changes, that's fine (user may just want to change the message)

3. **Generate commit message**:
   - If user provided a message/hint, use it as guidance
   - If `--amend` with no new hint, keep or refine the existing message
   - Otherwise, analyze the diff and generate a conventional commit message
   - Format: `<type>(<scope>): <short description>`
   - Types: feat, fix, docs, style, refactor, test, chore

4. **Show the proposed commit**:
```
   Staged files:
   - file1.ts
   - file2.ts

   Proposed commit message:
   feat(auth): add JWT token refresh logic

   [amending previous: feat(auth): add JWT token logic]  # if --amend
```

5. **Execute**:
   - Normal: `git commit -m "<message>"`
   - Amend: `git commit --amend -m "<message>"`

6. **Return brief confirmation**:
```
   ✓ Committed: feat(auth): add JWT token refresh logic
     2 files changed, 45 insertions(+), 12 deletions(-)
```
   or
```
   ✓ Amended: feat(auth): add JWT token refresh logic
     2 files changed, 45 insertions(+), 12 deletions(-)
```

## Key Requirements

- Keep output minimal
- Use conventional commit format
- Don't explain the changes in detail—just commit and confirm
