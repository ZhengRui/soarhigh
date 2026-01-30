---
description: Ask a question about the repo or codebase (context-light)
argument-hint: [--with-context:level] <question>
context: fork
agent: Explore
---

## Usage
```
/ask [--with-context[:brief|medium|comprehensive]] <question>
```

## Flags

- `--with-context` – include session context for questions that relate to what you're working on
  - `--with-context:brief` (default) – 2-3 sentence summary of current goal
  - `--with-context:medium` – paragraph summary including approach and key decisions
  - `--with-context:comprehensive` – detailed context including recent changes, challenges, and full task scope

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
/ask --with-context:medium am I missing any edge cases?
/ask --with-context:comprehensive what existing utilities can I reuse for this refactor?
/ask what's the latest best practice for React Server Components?
```

## Instructions

1. **Parse arguments**:
   - Check for `--with-context` flag and its level (brief/medium/comprehensive, default: brief)
   - Remaining text is the question

2. **Gather context if requested**:
   - If `--with-context:brief` or `--with-context`: main session provides 2-3 sentence summary
   - If `--with-context:medium`: main session provides paragraph with approach and key decisions
   - If `--with-context:comprehensive`: main session provides detailed context including recent changes and challenges
   - Use this context to make the answer more relevant to current work

3. **Assess the question**:
   - If it's about code structure, files, or implementation → search the codebase
   - If it's about project setup, config, or tooling → check config files (package.json, tsconfig, etc.)
   - If it's about external topics, best practices, or current trends → use web search
   - If it's a general/simple question that doesn't need codebase context → just answer directly

4. **Explore as needed**:
   - Use Glob to find relevant files
   - Use Grep to search for patterns, function names, keywords
   - Use Read to examine file contents
   - Use WebSearch for external knowledge, best practices, library docs, or current information
   - Be efficient—don't read everything, focus on what's relevant

5. **Answer naturally**:
   - Be concise for simple questions
   - Be detailed for complex questions
   - Include file paths when referencing code
   - Include short code snippets if helpful (not entire files)
   - Include source URLs when citing web search results
   - If `--with-context` was used, relate the answer back to the current work

## Key Requirements

- **No rigid output format** – respond naturally based on question complexity
- **Be efficient** – don't over-explore for simple questions
- **Cite locations** – mention file paths when relevant
- **Cite sources** – include URLs when using web search results
- **Stay read-only** – this is for questions, not changes
