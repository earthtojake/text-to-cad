# Developer flows

The index of every first-class developer flow, one blessed command each.
Conventions that apply throughout:

- **One blessed command per flow.** Aliases that duplicated a flow (`d`,
  `db:setup`, `run:docker-ssh`) no longer exist.
- **Root vs app dir:** run workspace-wide flows from the repo root, app-scoped
  flows from `apps/emdash-desktop/`, package-local flows from that package.
- **Environment preflight is owned by the doctor.** When a flow lists a
  prerequisite, the check for it is `pnpm run doctor` (root) — report-only,
  every failing line names the fixing command.
- **Build ordering is wired, not documented.** Flows that bypass Nx task
  orchestration (app-only dev, Storybook) start with
  `tooling/scripts/ensure-packages-built.mjs`, which builds the workspace
  packages through Nx and no-ops when the flow is already running as an Nx
  task. Both orderings are verified to work on a fresh clone that never built
  anything; warm re-runs are Nx cache hits and cost about a second.

## Setup

| Flow | Command | Where |
| --- | --- | --- |
| Bootstrap | `pnpm install` | root |
| Environment health | `pnpm run doctor` | root |

`pnpm install` is the whole setup: any pnpm on PATH provisions the pinned pnpm
and Node itself (see [quickstart](../quickstart.md)), installs dependencies,
builds the isolated system-Node better-sqlite3 side project, and rebuilds the
app's better-sqlite3 for the Electron ABI. Playwright browsers for the app's
browser test project are the one extra step, only needed for tests:
`pnpm exec playwright install` (the doctor checks it).

## Development

| Flow | Command | Where |
| --- | --- | --- |
| Full workspace dev | `pnpm run dev` | root |
| App-only dev | `pnpm run dev` | `apps/emdash-desktop/` |
| App dev, verbose Vite logs | `pnpm run dev:debug` | `apps/emdash-desktop/` |
| Main-only / renderer-only watch | `pnpm run dev:main` / `pnpm run dev:renderer` | `apps/emdash-desktop/` |
| One package in isolation | `pnpm run dev` | that `packages/*` dir |
| Storybook (ui) | `pnpm --filter @emdash/ui run storybook` (port 6006) | root |
| Storybook (chat-ui) | `pnpm --filter @emdash/chat-ui run storybook` (port 6007) | root |
| Theme codegen | `pnpm run build:theme` / `pnpm run watch:theme` | `packages/theme/` |

Notes:

- App dev scripts hardcode `LOG_LEVEL=debug` and write the main-process log to
  `apps/emdash-desktop/.emdash-logs/emdash.log`.
- Root `pnpm run dev` already includes every package watcher; the per-package
  watch flow is only for working on one package in isolation.
- Nx starts a background daemon that lingers after dev sessions; stop it with
  `pnpm exec nx daemon --stop` if task results ever look stale (the doctor
  reports a running daemon).
- Theme codegen normally runs as an Nx build dependency; invoke it manually
  only when iterating on the token codegen itself.

## Database

| Flow | Command | Where |
| --- | --- | --- |
| Generate a migration | `pnpm run db:generate <schema>` | `apps/emdash-desktop/` |
| Regenerate fixture DBs | `pnpm run db:fixtures` | `apps/emdash-desktop/` |
| Validate migrations | `pnpm run test:migrations` | `apps/emdash-desktop/` |
| Reset dev databases | `pnpm run db:reset` | `apps/emdash-desktop/` |

The `db:generate` dispatcher covers all five Drizzle schemas in the repo and
prints the follow-up obligations (fixtures, migration tests) after generating:

| Schema | Owner | Migrations directory |
| --- | --- | --- |
| `app` | `apps/emdash-desktop` | `apps/emdash-desktop/drizzle/` |
| `automations` | `packages/core` | `packages/core/src/runtimes/automations/node/persistence/migrations/` |
| `conversations` | `packages/core` | `packages/core/src/runtimes/conversations/node/persistence/migrations/` |
| `file-search` | `packages/core` | `packages/core/src/runtimes/file-search/node/storage/migrations/` |
| `workspace-registry` | `packages/core` | `packages/core/src/runtimes/workspace-registry/node/persistence/migrations/` |

`db:reset` honors `EMDASH_DB_FILE`: when set it deletes that database family
(main file plus the derived `-file-search` / `-automations` / `-operations`
siblings and SQLite `-wal`/`-shm` sidecars); otherwise it deletes the default
dev databases in the platform user-data dir. Use `EMDASH_DB_FILE` isolation for
schema work: `EMDASH_DB_FILE=/tmp/emdash-scratch.db pnpm run dev`.

## Checks and tests

| Flow | Command | Where |
| --- | --- | --- |
| Full merge gate | `pnpm run check` | root |
| Individual gates | `pnpm run format` / `lint` / `typecheck` / `test` | root |
| CI-style scoping | `pnpm run affected` | root |
| One app Vitest project | `pnpm exec vitest run --project <name>` | `apps/emdash-desktop/` |
| chat-ui perf / bench | `pnpm run test:perf` / `pnpm run test:bench` | `packages/chat-ui/` |
| Remote WSS integration test | `pnpm run test:workspace-server-remote` | `apps/emdash-desktop/` |

- `pnpm run check` runs the four gate commands in order and is exactly
  equivalent to running them by hand.
- App Vitest projects: `node`, `main-db`, `fixtures`, `migrations`, `scripts`,
  `browser`. The browser project needs Playwright browsers — run the doctor.
- CI (`code-consistency-check.yml`) gates `format:check`, `typecheck`, `lint`,
  and `test` via `nx affected`. The Playwright-backed `browser` projects (app
  and chat-ui) are skipped when Vitest detects CI until browser provisioning is
  proven stable there.
- The remote WSS test requires Docker and the workspace-server stack
  (`pnpm run run:docker-remote` from `apps/workspace-server/`) and sets
  `EMDASH_TEST_REMOTE_WSS=1` itself. Run the doctor first; it reports Docker
  reachability.

## Remote development

| Flow | Command | Where |
| --- | --- | --- |
| Workspace-server dev | `pnpm run dev` / `dev:remote` / `dev:remote-app` | `apps/workspace-server/` |
| Docker remote stack | `pnpm run run:docker-remote` | `apps/workspace-server/` |

The workspace-server stack is the only remote-dev stack. Prerequisite: Docker
running (doctor reports it). See
[remote development](remote-development.md) for the full workflow and the
`EMDASH_WS_*` env family.

## Packaging and maintenance

| Flow | Command | Where |
| --- | --- | --- |
| Local packaging | `pnpm run package` / `package:mac` / `package:linux` / `package:win` | `apps/emdash-desktop/` |
| Rebuild native deps | `pnpm run rebuild` | `apps/emdash-desktop/` |
| Lint-infra allowlists | `pnpm run prune:boundary-allowlists` | root |
| Task graph | `pnpm run graph` | root |
| Releases (maintainers) | `gh workflow run release-prod.yml` / `release-canary.yml` / `release-workspace-server.yml` | — |

- Local packaging without signing identities still produces installable
  artifacts; mac builds are unsigned/un-notarized and Gatekeeper will warn.
- `rebuild` force-rebuilds better-sqlite3 for the installed Electron version
  (auto-detected). node-pty is never rebuilt — its N-API prebuild serves both
  runtimes. Offline fallback: append `--build-from-source`.
- Run `prune:boundary-allowlists` after fixing boundary violations; root lint
  fails while the allowlists carry stale entries. The allowlists are
  shrink-only — the script removes entries that no longer violate and never
  adds new ones.
- Releases are maintainer-only and run only when explicitly asked
  (see AGENTS.md guardrails).

## Escape hatches

Environment variables that intentionally deviate from the default setup. The
doctor lists any that are active.

| Variable | Effect |
| --- | --- |
| `EMDASH_DB_FILE` | Point the app (and `db:reset`) at an isolated database file |
| `EMDASH_SKIP_ELECTRON_REBUILD=1` | Skip the Electron-ABI rebuild in postinstall (CI sets this implicitly via `--ignore-scripts`) |
| `EMDASH_DISABLE_NATIVE_DB=1` | Run without the native better-sqlite3 (also skips its rebuild) |
| `EMDASH_DISABLE_PTY=1` | Run without PTY support |
| `EMDASH_TEST_SKIP_BROWSER=1` | Omit the Playwright-backed `browser` Vitest projects locally |
| `EMDASH_FORCE_BOOT_FAILURE=1` | Force the boot-failure path for recovery testing |
| `TELEMETRY_ENABLED=false` | Disable telemetry |
| `CODEX_SANDBOX_MODE`, `CODEX_APPROVAL_POLICY` | Override Codex provider sandbox/approval behavior |
