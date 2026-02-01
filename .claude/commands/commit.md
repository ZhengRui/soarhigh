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
   - Run `git log -1 --format=%B` to get the FULL existing commit message (not just oneline)
   - You MUST preserve the context from the previous commit message when amending

3. **Stage changes intelligently** (no user prompts):
   - Run `git status` to see all changes
   - If changes are already staged, use those
   - If nothing staged, decide what to stage based on context and message:
     - If user message hints at specific files/features, stage only relevant files
     - If context suggests working on specific area, stage files in that area
     - Otherwise, stage all changes with `git add -A`
   - If nothing to commit and not amending, inform user and exit

4. **Generate commit message** with multi-line format:
   - If user provided a message/hint, use it as guidance
   - If `--amend`: Update the commit message to reflect the FINAL state of the commit
     - Read the previous message and the new diff to understand what changed
     - The new message should accurately describe what the commit does NOW
     - Add bullet points for new additions, remove bullets for reverted changes, update bullets for modifications
   - Otherwise, analyze the diff and session context to generate the message
   - Types: feat, fix, docs, style, refactor, perf, test, chore

   **Commit message format:**
   ```
   <type>[(<scope>)]: <short description in lowercase>

   <paragraph explaining what was added/changed and why>

   - <bullet point detail 1>
   - <bullet point detail 2>
   - <bullet point detail N>

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
   ```

   **Example:**
   ```
   feat: add segment checkin indicator with timer reset capability

   Add visual indicator showing when someone has checked in for a segment,
   with special reset functionality for the Timer role. Members can see
   all checkins and reset Timer assignments when needed.

   - Backend: Add /checkins/reset endpoint and supporting DB functions
   - Frontend: Add CheckinIndicator component with portal-based tooltip
   - Uses hover on desktop, click on mobile for tooltip interaction
   - Includes confirmation dialog before reset to prevent accidents

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
   ```

5. **Execute directly** (no confirmation needed):
   - Use HEREDOC format to preserve multi-line message:
   ```bash
   git commit -m "$(cat <<'EOF'
   <full multi-line message here>
   EOF
   )"
   ```
   - For amend: `git commit --amend -m "$(cat <<'EOF' ... EOF)"`

6. **Return brief confirmation**:
```
Committed: feat(auth): add JWT token refresh logic
2 files changed, 45 insertions(+), 12 deletions(-)
```

## Key Requirements

- Use multi-line commit message format with description paragraph and bullet points
- Use conventional commit type prefix with optional scope, e.g. `feat:` or `feat(auth):`
- Always include Co-Authored-By line
- Don't explain the changes verbally—just commit and confirm
