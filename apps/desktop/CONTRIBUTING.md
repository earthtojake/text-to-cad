# Contributing to Emdash

Thanks for your interest in contributing. We favor small, focused PRs with clear
intent. This guide covers the local development setup, the commands that matter,
and the conventions contributors should follow before opening a PR.

## Quick Start

### Prerequisites

- Git
- Any reasonably recent `pnpm` (install via Homebrew, `npm install -g pnpm`, or
  `curl -fsSL https://get.pnpm.io/install.sh | sh -`)
- Optional, but useful for integration work:
  - GitHub CLI (`gh`)
  - At least one supported coding agent CLI
  - Docker, when working on remote development infrastructure

That is the whole toolchain requirement. `package.json` pins both the package
manager (`packageManager: pnpm@10.28.2`) and the Node runtime
(`devEngines.runtime` with `onFail: "download"`), so any pnpm on PATH swaps
itself to the pinned version and provisions the pinned Node — checksummed in
`pnpm-lock.yaml` — when it runs in this repo. You do not need nvm, corepack, or
a preinstalled Node of the right version.

If you use [mise](https://mise.jdx.dev) for toolchain auto-switching, the
committed `mise.toml` pins node and pnpm for you; it is optional and required
by nothing. `.nvmrc` remains as a compatibility hint for other version
managers.

### Get The Source

Fork the repository on GitHub, then clone your fork:

```bash
git clone https://github.com/<you>/emdash.git
cd emdash
```

### Install

From the repo root:

```bash
pnpm install
```

This single command provisions the pinned pnpm and Node if needed, installs
dependencies, and prepares the native modules — after it succeeds the machine
is ready for every dev flow.

This repository is a pnpm workspace. The Electron app is in
`apps/emdash-desktop/`, and shared workspace packages live in `packages/`.

### Start Development

For normal app development, run the full workspace dev command from the repo root:

```bash
pnpm run dev
```

The root `dev` command now does two things:

1. Builds all packages under `packages/`.
2. Starts package watch builds and the Electron desktop app in parallel.

Use this command when you are changing code in `packages/` or when you want the
same startup path a fresh contributor will use.

If you are only working inside `apps/emdash-desktop/`, you can run the Electron
dev server directly:

```bash
cd apps/emdash-desktop
pnpm run dev
```

Important distinction:

- `pnpm run dev` from the repo root starts the workspace package watchers and the
  app together.
- `pnpm run dev` from `apps/emdash-desktop/` starts only `electron-vite dev` for
  the desktop app.
- If app code imports changed package output, prefer the root command so package
  `dist/` files stay current.

Renderer changes usually hot reload. Main-process changes under
`apps/emdash-desktop/src/main/` may require restarting the Electron dev app.

## Repository Layout

This is a pnpm workspace monorepo.

- `apps/emdash-desktop/` - Electron desktop app package
- `apps/emdash-desktop/src/main/` - Electron main process, RPC controllers,
  services, database, PTY, SSH, Git, GitHub, updates, and integrations
- `apps/emdash-desktop/src/preload/` - typed Electron preload bridge
- `apps/emdash-desktop/src/renderer/` - React composition shell and shared browser infrastructure
- `apps/emdash-desktop/src/core/` - vertical slices with APIs, Node implementations, browser UI,
  contributions, and manifests
- `apps/emdash-desktop/drizzle/` - generated Drizzle migrations and metadata
- `apps/emdash-desktop/scripts/` - release, verification, and build scripts
- `packages/core/` - transport-agnostic core runtime primitives
- `packages/shared/` - shared workspace primitives
- `packages/ui/` - shared UI components and theme system
- `packages/plugins/` - plugin interfaces and helpers
- `agents/` - architecture, workflow, convention, integration, and risk docs

Root scripts are aggregate workspace scripts. Most app-specific commands live in
`apps/emdash-desktop/package.json`.

## Common Commands

Run these from the repo root unless noted. Root scripts run through Nx, which
builds projects in dependency order and caches results locally. A second run
of any cached target (`build`, `test`, `typecheck`, `lint`, `format:check`)
replays instantly if inputs have not changed.

```bash
pnpm run dev            # build packages, watch packages, and start the Electron app
pnpm run build          # build every workspace package
pnpm run format         # format with oxfmt
pnpm run format:check   # check formatting without writing
pnpm run lint           # lint with oxlint
pnpm run typecheck      # run TypeScript checks
pnpm run test           # run workspace tests
pnpm run affected       # lint, typecheck, and test only projects changed vs. main
pnpm run graph          # open the Nx project graph in the browser
```

Individual project targets are addressable from the root without `cd`:

```bash
nx package:mac @emdash/emdash-desktop
nx db:reset @emdash/emdash-desktop
nx build:theme @emdash/ui
```

See `agents/workflows/nx.md` for a full explanation of the Nx setup.

Useful app-local commands from `apps/emdash-desktop/`:

```bash
pnpm run dev            # start electron-vite dev for the desktop app only
pnpm run dev:debug      # start with debug logging
pnpm run dev:main       # watch the Electron main process
pnpm run dev:renderer   # watch the renderer
pnpm run build          # build the Electron app
pnpm run build:main     # build main process only
pnpm run build:renderer # build renderer only
pnpm run package        # build and package desktop artifacts
pnpm run rebuild        # rebuild native Electron dependencies
pnpm run reset          # clean app dependencies and reinstall
```

Useful package-local commands from a package under `packages/`:

```bash
pnpm run dev            # watch-build that package with tsdown
pnpm run build          # build that package with tsdown
pnpm run test
pnpm run typecheck
```

## Local Validation

Before opening or merging a PR, run the local merge gate:

```bash
pnpm run format
pnpm run lint
pnpm run typecheck
pnpm run test
```

There are no pre-commit hooks. CI enforces format:check, typecheck, lint, and
test via `nx affected` — only projects touched by the PR are checked. The
Playwright-backed `browser` Vitest projects are skipped in CI, so the full
local suite is still expected before merging.

## Development Workflow

1. Create a feature branch:

```bash
git checkout -b feat/<short-slug>
```

2. Keep PRs small and focused.

Update docs when behavior changes. Include screenshots or short recordings for UI
changes where they help reviewers understand the result.

3. Run validation locally.

Use the full merge gate above for broad changes. For narrow work, it is fine to
run focused tests while iterating, then run the full gate before opening or
merging the PR.

4. Commit using Conventional Commits:

```text
fix(opencode): change initialPromptFlag from -p to --prompt for TUI
feat(docs): add changelog tab with GitHub releases integration
```

5. Open a pull request.

Describe the change, the reason for it, and the validation you ran. Link related
issues when relevant.

## Code Style

- Use TypeScript strict mode.
- Use top-level `import` statements, not `require()`.
- Do not introduce npm or yarn lockfiles.
- Use `pnpm`.
- Format with `oxfmt`.
- Lint with `oxlint`.
- Keep lines near the configured `printWidth` of 100 characters.
- Use 2 spaces, semicolons, single quotes in TypeScript, double quotes in JSX, LF
  endings, and trailing commas where valid in ES5.
- Avoid `any`. If a boundary requires it, keep the escape local and document why.
- Do not re-export as a shortcut. Import from the original source.

## App Architecture Conventions

The app follows this high-level flow:

```text
Renderer -> typed RPC client -> preload bridge -> Electron main -> controllers -> services
```

Main process:

- RPC handlers live in `src/main/core/*/controller.ts`.
- Controllers should delegate to imported operation or service functions.
- Expected failures should use the `Result<T, E>` pattern from
  `src/main/lib/result.ts`.
- Prefer `execFile` over `exec`.
- Treat shell escaping, PTY spawning, SSH commands, and worktree paths as
  security-sensitive.
- Preserve secret redaction in logging and telemetry code.

Renderer:

- Feature UI lives under `src/core/features/<feature>/browser/`.
- Shared renderer primitives, stores, hooks, commands, PTY, Monaco, modal
  infrastructure, and UI live under `src/renderer/lib/`.
- Renderer RPC calls go through `rpc` from `src/renderer/lib/ipc.ts`.
- New modals must be registered in `src/renderer/app/modal-registry.ts`.
- New views must be registered in `src/renderer/app/view-registry.ts`.
- New commands should use `src/renderer/lib/commands/registry.ts` and view-level
  `commandProvider` hooks when possible.
- Components use `PascalCase`; hooks use `useX` camelCase or an existing local
  pattern.

State and stores:

- Access task managers through `getTaskManagerStore(projectId)`, not
  `project.taskManager`.
- Access available Project contexts through `asAvailableProject(getProjectStore(id))`.
- Never use `asProvisioned(...)!` or `asAvailableProject(...)!`; use explicit null checks.
- State guards should check `kind !== 'ready'` rather than enumerate non-ready
  states.
- Task selectors live in
  `src/core/features/tasks/browser/stores/task-selectors.ts`.
- Project selectors live in
  `src/core/features/projects/browser/stores/project-selectors.ts`.

## Database And Migrations

Development database paths use Electron `app.getPath('userData')`.

- macOS: `~/Library/Application Support/emdash-dev/emdash4.db`
- Linux: `~/.config/emdash-dev/emdash4.db`
- Windows: `%APPDATA%\emdash-dev\emdash4.db`

Use an isolated scratch database when working on schema or migration changes.
From the repo root:

```bash
EMDASH_DB_FILE=/tmp/emdash-scratch.db pnpm run dev
```

For app-only development, change into `apps/emdash-desktop/` first so this starts
only `electron-vite dev`:

```bash
cd apps/emdash-desktop
EMDASH_DB_FILE=/tmp/emdash-scratch.db pnpm run dev
```

Reset dev databases from `apps/emdash-desktop/`:

```bash
pnpm run db:reset
```

Database rules:

- Do not hand-edit numbered Drizzle migrations or `drizzle/meta/`.
- Use `pnpm run db:generate` for new migrations.
- Update fixtures and migration tests when schema behavior changes.
- Run focused database validation from `apps/emdash-desktop/` when relevant:

```bash
pnpm run db:fixtures
pnpm run test:migrations
```

Read `agents/risky-areas/database.md` before changing database internals.

## Worktrees, PTY, SSH, And Providers

Emdash orchestrates coding agents in Git worktrees and PTY sessions. These areas
are high impact.

- Do not delete worktree folders manually unless you know the matching Git state.
  Prefer in-app cleanup or `git worktree prune` from the main repository.
- Do not weaken shell quoting, spawn behavior, environment allowlists, or secret
  redaction.
- PTY environment passthrough must use the allowlist in
  `src/main/core/pty/pty-env.ts`.
- Provider changes may need updates to shared provider metadata, dependency
  detection, PTY behavior, hooks/plugins, renderer assumptions, and tests.

Read the relevant risk or integration doc before touching these areas:

- `agents/risky-areas/pty.md`
- `agents/risky-areas/ssh.md`
- `agents/integrations/providers.md`
- `agents/integrations/mcp.md`

## Testing Notes

- Unit tests use Vitest.
- Main database integration tests run in the `main-db` Vitest project.
- Migration tests run in the `migrations` project.
- Fixture generation runs in the `fixtures` project.
- Renderer browser tests use Playwright-backed `@vitest/browser-playwright`.
- Main-process tests are colocated under `src/main/core/**/*.test.ts`.
- Renderer unit tests live under `src/renderer/tests/`.
- Renderer browser tests live under `src/renderer/tests/browser/`.
- Integration-style tests create temporary repos and worktrees in `os.tmpdir()`.

From `apps/emdash-desktop/`, the app test command is:

```bash
pnpm run test
```

It runs the app Vitest projects:

```text
node, main-db, migrations, browser, scripts
```

## Native Dependencies

After native dependency changes, rebuild Electron native modules from
`apps/emdash-desktop/`:

```bash
pnpm run rebuild
```

This is especially relevant for `better-sqlite3` and `node-pty`.

## Remote Development Stack

The workspace-server stack (`apps/workspace-server/docker-compose.yaml`) is the
only Docker-backed remote-dev stack. When working on SSH/remote development
infrastructure, start it from `apps/workspace-server/`:

```bash
pnpm run run:docker-remote
```

Read `agents/workflows/remote-development.md` and `agents/risky-areas/ssh.md`
before making SSH behavior changes.

## Issue Reports And Feature Requests

Use GitHub Issues. Include:

- Operating system
- Emdash version or commit SHA
- Node and pnpm versions, if development-related
- Steps to reproduce
- Expected behavior
- Actual behavior
- Relevant logs, terminal output, or screenshots

Do not include secrets, tokens, private keys, local app databases, or private
repository content in public issues.

## Release Process For Maintainers

Do not dispatch release workflows, publish packages, or upload artifacts unless
you are explicitly doing release work.

The app version lives in `apps/emdash-desktop/package.json`. For release version
bumps, run these from `apps/emdash-desktop/`:

```bash
pnpm version patch
pnpm version minor
pnpm version major
```

This updates `package.json` and `pnpm-lock.yaml`, creates a version commit, and
creates a tag.

Production releases are dispatched through GitHub Actions:

```bash
gh workflow run release-prod.yml --ref main -f arch=both
```

Canary releases are dispatched through:

```bash
gh workflow run release-canary.yml --ref main -f arch=both
```

Workspace-server releases have an independent version and channel:

```bash
gh workflow run release-workspace-server.yml --ref main -f channel=stable
```

See [`apps/workspace-server/docs/packaging.md`](apps/workspace-server/docs/packaging.md) before
bumping or publishing a workspace-server version.

Production releases publish artifacts to GitHub Releases as the primary update
feed and Cloudflare R2 as fallback. Canary releases currently publish to R2 only.

## Further Reading

- `agents/README.md`
- `agents/quickstart.md`
- `agents/architecture/overview.md`
- `agents/architecture/main-process.md`
- `agents/architecture/renderer.md`
- `agents/conventions/ipc.md`
- `agents/conventions/main-patterns.md`
- `agents/conventions/renderer-patterns.md`
- `agents/conventions/typescript.md`
- `agents/workflows/nx.md`
- `agents/workflows/testing.md`
- `agents/workflows/worktrees.md`
