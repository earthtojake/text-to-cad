---
name: knowledge-capture
description: Manually capture reusable project knowledge into docs/knowledge markdown for Phase 1 validation.
---

# Knowledge Capture Skill

Use this skill to manually write a knowledge entry after completing a task.

## Triggers

- "Capture project knowledge"
- "Document this task as knowledge"
- "Write a knowledge entry"
- "Summarize this fix into docs"
- "整理成知識庫"
- "把這次任務寫成 knowledge"

---

## When To Use

Use only when the work is done and at least one is true:
- the task revealed a non-obvious fix,
- the task exposed a repeated pitfall,
- the task established a reusable pattern,
- the task clarified a design decision,
- the task produced a decision future contributors will need.

Do **not** use for trivial edits, obvious refactors, or one-off experiments.

---

## Required Inputs

Before writing, gather from the completed task:
- task summary,
- changed files,
- validation evidence (tests, diagnostics, build result, observed behavior),
- the key problem,
- the actual solution,
- any tradeoffs or side effects.

---

## Output Location Rules

- `docs/knowledge/troubleshooting/` — bug fixes, incident patterns
- `docs/knowledge/patterns/` — reusable implementation patterns
- `docs/knowledge/architecture/` — design constraints or rationale
- `docs/knowledge/tooling/` — environment, build, CI/CD, CLI

If no file exists for the topic, create a new kebab-case markdown file.

---

## Required Document Format

```
# <Title>

## Context
## Problem
## Solution
## Why It Works
## Side Effects / Tradeoffs
## Evidence
## Related Files
## Tags
```

---

## Writing Rules

- Prefer facts over summaries.
- Prefer short paragraphs and bullets over long prose.
- Preserve concrete terms exactly: error text, env vars, commands, paths, versions.
- Keep one file focused on one reusable lesson.
- Merge into an existing file if the lesson is the same concept.
- If the knowledge is task-local and not reusable, leave it in `.sisyphus/notepads/`.

---

## Validation Checklist

After drafting, verify:
1. **Reusable** — future tasks could benefit.
2. **Scoped** — one concept, not a task dump.
3. **Evidence-backed** — every claim is traceable.
4. **Readable** — a human can skim it.
5. **Non-duplicative** — no unnecessary repeat of existing entries.

---

## Rules

- Never write knowledge before the task is complete.
- Never record guesses as facts.
- Never dump raw transcripts into `docs/knowledge/`.
- Never create a giant catch-all file.
- If evidence is missing, stop and ask.
