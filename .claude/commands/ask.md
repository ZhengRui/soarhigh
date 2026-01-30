---
description: Ask a question about the repo or codebase (context-light)
argument-hint: [--with-context] <question>
context: fork
agent: Explore
---

## Usage
```
/ask [--with-context] <question>
```

## Flags

- `--with-context` – include a brief summary of current session goal/task for questions that relate to what you're working on

## Examples
```
/ask how does the auth flow work?
/ask where is the database connection configured?
/ask what does the useAuth hook do?
/ask list all API endpoints
/ask why is this project using pnpm instead of npm?
/ask what testing framework is used?
/ask how many components are in src/components?
/ask --with-context does this approach fit our current design?
/ask --with-context am I missing any edge cases?
/ask --with-context what existing utilities can I reuse?
```

## Instructions

1. **Parse arguments**:
   - Check for `--with-context` flag
   - Remaining text is the question

2. **Gather context if requested**:
   - If `--with-context`: the main session will provide a 2-3 sentence summary of the current goal/task and approach
   - Use this to make the answer more relevant to current work

3. **Assess the question**:
   - If it's about code structure, files, or implementation → search the codebase
   - If it's about project setup, config, or tooling → check config files (package.json, tsconfig, etc.)
   - If it's a general/simple question that doesn't need codebase context → just answer directly

4. **Explore as needed**:
   - Use Glob to find relevant files
   - Use Grep to search for patterns, function names, keywords
   - Use Read to examine file contents
   - Be efficient—don't read everything, focus on what's relevant

5. **Answer naturally**:
   - Be concise for simple questions
   - Be detailed for complex questions
   - Include file paths when referencing code
   - Include short code snippets if helpful (not entire files)
   - If `--with-context` was used, relate the answer back to the current work

## Key Requirements

- **No rigid output format** – respond naturally based on question complexity
- **Be efficient** – don't over-explore for simple questions
- **Cite locations** – mention file paths when relevant
- **Stay read-only** – this is for questions, not changes
