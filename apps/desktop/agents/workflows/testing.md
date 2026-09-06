# Testing And Validation

All paths are relative to `apps/emdash-desktop/`.

## Core Local Gate

Run these before merging (from the repo root or `apps/emdash-desktop/`):

```bash
pnpm run format
pnpm run lint
pnpm run typecheck
pnpm run test
```

## Test Layout

- main-process tests: colocated in `src/main/core/**/*.test.ts`
- renderer unit tests: `src/renderer/tests/`
- renderer browser tests: `src/renderer/tests/browser/` (run via Playwright)

## Current Setup

- Vitest config is in `vitest.config.ts` (separate from the build config in `electron.vite.config.ts`).
- Five test projects:
  - `node` — `src/**/*.test.ts` excluding `_*` dirs, browser tests, migration tests, `*.db.test.ts`
  - `main-db` — `src/main/core/**/*.db.test.ts` against real SQLite
  - `fixtures` — fixture generator, run via `pnpm run db:fixtures`
  - `migrations` — `src/main/db/tests/migrations/**`, run via `pnpm run test:migrations`
  - `browser` — `src/renderer/tests/browser/**/*.test.{ts,tsx}` via Playwright
- `pnpm run test` runs every project except `fixtures` (`node`, `main-db`,
  `migrations`, `scripts`, and `browser`). Setting `EMDASH_TEST_SKIP_BROWSER=1`
  omits the Playwright-backed `browser` project locally; CI omits it automatically.
- Tests use per-file `vi.mock()` setup.
- Integration-style tests create temporary repos and worktrees in `os.tmpdir()`.

## CI Notes

- `.github/workflows/code-consistency-check.yml` uses `nx affected` to enforce
  format:check, typecheck, lint, and test only for projects touched by the PR. Nx
  computes the affected set using `nrwl/nx-set-shas` and the PR base/head SHAs.
- CI installs with `--ignore-scripts`, so the workflow explicitly installs the
  native side project (`pnpm --dir apps/emdash-desktop/tooling/node-deps install`)
  for the DB-backed Vitest projects. It also rebuilds and load-checks `node-pty`
  from `@emdash/core`, a workspace that declares the dependency. Vitest omits the
  Playwright-backed `browser` projects (app and chat-ui) when it detects CI until
  browser provisioning is proven stable there.
- The full suite (including `browser` projects) is still expected locally before merging.

## Focused Validation

- after IPC/RPC changes: rerun the affected Vitest file and confirm the controller is wired in `src/main/rpc.ts`
- after worktree or PTY changes: rerun the closest `src/main/core/` test files
- after schema changes: run `pnpm run db:fixtures` and `pnpm run test:migrations`
