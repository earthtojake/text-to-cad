# PROTOTYPE — creation pipeline baseline timing (throwaway, do not ship)

Answers ticket
[05 — instrumentation plan and baseline measurements](../../../../../.scratch/workspace-activation-speed/issues/05-instrumentation-baseline.md):
per-stage timings of the CURRENT `executeCreateWorktree` pipeline, invoked directly
(the production function, `pushBranch: false`, scratch worktrees cleaned up).

Run it (from the repo root):

```bash
pnpm exec tsx --tsconfig packages/core/tsconfig.json \
  apps/emdash-desktop/tooling/prototypes/creation-baseline/run.ts --runs 2
```

Results (2026-08-06, M-series Mac, APFS, real network) are recorded in the ticket's
Answer. Headline: fetch and copy-preserved-files dominate emdash's creation
(~3–5s total); checkout dominates vscode's (~3.6–14s total).
