# Knowledge Base

This directory stores **reusable, human-readable, git-backed** knowledge for this project.

## Purpose

Capture knowledge that future contributors and agents can find and use.
Task-local working notes belong in `.sisyphus/notepads/`. Promote into this
directory only when the information is likely to be reused.

## Directory Layout

- `architecture/` — design constraints, rationale, system boundaries
- `patterns/` — reusable coding or workflow patterns
- `tooling/` — environment, build, CI/CD, CLI, automation
- `troubleshooting/` — bugs, failure modes, concrete fixes

## Entry Standard

Every entry must follow this structure:

```md
# Title

## Context
## Problem
## Solution
## Why It Works
## Side Effects / Tradeoffs
## Evidence
## Related Files
## Tags
```

## Promotion Rule

Promote a note here only if it is:
1. reusable,
2. evidence-backed,
3. narrowly scoped,
4. likely to help a future task.

## Usage

Use the `knowledge-capture` skill (in `.opencode/skills/knowledge-capture.md`)
to manually write and validate entries after completing relevant tasks.
