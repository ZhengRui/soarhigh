---
description: Code review using a subagent - WIP changes (default) or full codebase
argument-hint: [--scope:diff|full] [--focus:areas]
context: fork
agent: general-purpose
---

## Usage
```
/review-wip [context options] [--scope:diff|full] [--focus:areas]
```

## Scope Options

- `--scope:diff` – review only code changes from git diff (default)
- `--scope:full` – review the full codebase (ignores git diff, explores project structure)

## Context Options (combine any)

- `--summary` – auto-generate a brief summary of the current session goal/task
- `--goal:"<description>"` – manually specify the goal
- `--file:<path>` – read context from a plan/spec file (e.g., `--file:docs/plan.md`)

If no context options provided, default to `--summary`.

## Focus Options (comma-separated)

`--focus:` followed by one or more of:
- `bugs` – logic errors, edge cases, potential runtime failures
- `design` – architecture, patterns, abstractions, trade-offs
- `correctness` – does implementation match stated goal?
- `understanding` – explain what the code does and why
- `security` – vulnerabilities, input validation, auth issues
- `all` – comprehensive review (default if `--focus` not specified)

## Examples
```
/review-wip --summary --focus:design
/review-wip --goal:"add retry logic to API client" --focus:bugs,correctness
/review-wip --summary --file:docs/feature-spec.md --focus:all
/review-wip --focus:understanding
/review-wip --scope:full --focus:design
/review-wip --scope:full --goal:"authentication system" --focus:security
```

## Instructions

1. **Parse arguments** to determine scope, context sources, and focus areas.

2. **Gather context**:
   - If `--summary`: generate a 2-4 sentence summary of the current session's goal and approach
   - If `--goal:"..."`: use the provided description
   - If `--file:<path>`: read the specified file
   - Combine all provided context sources

3. **Gather code to review** based on scope:
   - If `--scope:diff` (default): run `git diff` (unstaged) and `git diff --staged` (staged)
   - If `--scope:full`: explore the full codebase structure, read key files, understand architecture (ignore git diff)

4. **Review the code** against the context, focusing on the specified areas.

5. **Return findings** in the output format below.

## Output Format
```
## Overview
Brief assessment (2-3 sentences): what was reviewed, overall impression.

## At a Glance

### Issue Distribution (if bugs/correctness/security focus)
Critical  ███░░░░░░░  N
Major     █████░░░░░  N
Minor     ██░░░░░░░░  N
Nit       █░░░░░░░░░  N

### File Hotspots (if multiple files affected)
file1.ts   ████████  N issues
file2.ts   ████      N issues
...

## Findings

| # | Severity | Location | Issue (brief) |
|---|----------|----------|---------------|
| 1 | Critical | file:line | Short description |
| 2 | Major    | file:line | Short description |
...

### 1. <Issue title> (<Severity>) – <file:line>

**What's happening:**
Detailed explanation of the issue...

**Why it matters:**
Impact, risks, edge cases...

**Suggestion:**
Concrete fix with reasoning, code snippet if helpful...

---

### 2. <Issue title> (<Severity>) – <file:line>

...

## Design Observations (if --focus includes design)

Detailed discussion of architecture, patterns, trade-offs, alternatives...

## Understanding Summary (if --focus includes understanding)

Explanation of what the code does, how it fits together, key decisions...

## Summary Chart (optional, if helpful)

Use ASCII diagrams for:
- Dependency relationships
- Data flow
- Component interactions
```

## Key Requirements

- **Be comprehensive**: don't sacrifice detail for brevity
- **Be scannable**: use tables and charts for quick orientation
- **Be actionable**: every issue should have a concrete suggestion
- **Sort by severity**: critical issues first
- **Link to locations**: always include file:line references
