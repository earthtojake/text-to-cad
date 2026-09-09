# Project Overview

Hardcore is a local-first, cross-platform Electron app for running multiple AI coding
agents in parallel around CAD artifacts. Each task is isolated in its own Git worktree and
can run locally or over SSH, while the desktop app coordinates provider CLIs, ACP chat
sessions, terminal sessions, the CAD Viewer, diff review, and release packaging.

This directory is `apps/desktop` inside the Text-to-CAD monorepo
(earthtojake/text-to-cad). The repository root's `AGENTS.md` governs the rest of the
repository; this file governs everything under `apps/desktop`. The desktop uses the
repository's canonical CAD resources directly — `apps/viewer`, `packages/cadgen`,
`packages/cadgen-js`, and `skills/` — and never vendors or copies them into this tree.
Read [CAD integration](agents/integrations/cad.md) before changing anything under
`src/main/host/cad/` or `src/core/features/cad/`.

## Repository Structure

This directory is a pnpm workspace of its own. The Electron app lives in
`apps/emdash-desktop/` as `@hardcore/desktop`; shared packages live under
`packages/`. Unless a path is prefixed with `packages/` or another app, app paths
such as `src/...`, `drizzle/`, `scripts/`, and `build/` are relative to
`apps/emdash-desktop/`. All commands below run from `apps/desktop`, not from the
repository root.

Workspace root (`apps/desktop`):

- `.claude/` - Local Claude agent settings for this checkout.
- `agents/` - Agent-facing architecture, workflow, convention, integration, and risk docs.
- `apps/emdash-desktop/` - The Electron desktop app.
- `apps/workspace-server/` - Remote workspace server and its Docker-based dev stack.
- `packages/chat-ui/` - Shared transcript and ACP chat renderer with Storybook coverage.
- `packages/core/` - Transport-agnostic runtime primitives, including ACP session logic.
- `packages/plugins/` - Agent provider plugin definitions, hooks, and ACP adapters.
- `packages/shared/` - Shared primitives such as result types, logging, and markdown helpers.
- `packages/theme/` - Theme token codegen that emits the generated theme CSS.
- `packages/ui/` - Shared React UI components, theme tokens, recipes, and primitives.
- `packages/wire/` - Typed wire protocol contracts shared by app and workspace server.
- `tooling/` - Root scripts, including the CAD setup (`tooling/scripts/setup-cad.mjs`)
  and the pinned CAD dependency lock (`tooling/cad-runtime-constraints.txt`).
- `pnpm-workspace.yaml` - Workspace package globs for `apps/*` and `packages/**`.
- Root config files - `package.json`, `nx.json`, `.nvmrc`, `.oxfmtrc.json`,
  `.oxlintrc.json`, and lockfile/configuration owned at this workspace root.

Inside `apps/emdash-desktop/`:

- `build/` - Electron packaging assets; avoid edits unless working on packaging/signing.
- `drizzle/` - Generated Drizzle SQL migrations and metadata.
- `scripts/` - Release, verification, and build support scripts.
- `src/main/` - Electron main process: bootstrap, Wire gateway, DB, and host services,
  including the CAD adapter under `src/main/host/cad/`.
- `src/entry/` - Electron entry points: `main.ts` (main process) and `preload.ts`, the typed
  preload bridge exposed to the renderer.
- `src/renderer/` - React composition shell, shared browser infrastructure, and tests.
- `src/core/` - Vertical slices with portable APIs, Node implementations, browser UI, and manifests.
- `src/types/` - Ambient and cross-cutting TypeScript declarations.
- `tooling/` - App-level development and test infrastructure not bundled into production.

## Build & Development Commands

The only prerequisite is any `pnpm` on PATH: the root `package.json` pins
`packageManager: pnpm@10.28.2` and `devEngines.runtime` node `24.14.0` with
`onFail: "download"`, so pnpm provisions the pinned toolchain itself (no nvm or
corepack). The committed `mise.toml` is an optional convenience for mise users.
Root scripts are powered by Nx and run package targets in dependency order with
local caching where configured.

Golden-path commands (see [Developer flows](agents/workflows/flows.md) for the
full index — one blessed command per flow, database flows, Storybook,
packaging, remote development, and escape hatches):

```bash
pnpm install        # complete setup from apps/desktop — nothing else needed
pnpm cad:setup      # Python runtime, apps/viewer client build, provider plugins
pnpm run doctor     # report-only environment health check
pnpm run dev        # full workspace dev (apps/desktop); app-only from apps/emdash-desktop/
pnpm run build      # build all workspace projects
pnpm run check      # full merge gate: format, lint, typecheck, test
pnpm cad:test       # Jake's selected CAD suites plus the desktop's generate/validate smoke
```

The four gate commands also run individually from the repo root:

```bash
pnpm run format
pnpm run lint
pnpm run typecheck
pnpm run test
```

Use an isolated development database for schema or migration work:

```bash
EMDASH_DB_FILE=/tmp/emdash-scratch.db pnpm run dev
```

Run focused database validation from `apps/emdash-desktop/`:

```bash
pnpm run db:fixtures
pnpm run test:migrations
```

Deploy releases only when explicitly asked to do release work:

```bash
gh workflow run release-prod.yml --ref main -f arch=both
gh workflow run release-canary.yml --ref main -f arch=both
gh workflow run release-workspace-server.yml --ref main -f channel=stable
```

Production releases publish artifacts to GitHub Releases and Cloudflare R2. Canary
releases currently publish to R2 only. See
[workspace-server packaging](apps/workspace-server/docs/packaging.md) for its independent release
and channel rules.

## Code Style & Conventions

- Use `pnpm`; do not introduce npm or yarn lockfile churn.
- Format with `oxfmt`; config is `.oxfmtrc.json`.
- Keep formatted lines near the configured `printWidth` of 100 characters.
- Use 2 spaces, semicolons, single quotes in TS, double quotes in JSX, LF endings,
  trailing commas where valid in ES5, and sorted imports.
- Lint with `oxlint`; config is `.oxlintrc.json` with correctness, TypeScript, React
  hooks, and local repo rules enabled.
- TypeScript strict mode is enabled; app targets share `apps/emdash-desktop/tsconfig.json`.
- Avoid `any`; if a registry or boundary needs it, keep the escape local and documented.
- Use top-level `import` statements; do not use `require()`.
- Never re-export as a shortcut; import from the original source.
- Components use `PascalCase`; hooks use `useX` camelCase or an existing local pattern.
- Tests use `*.test.ts` or `*.test.tsx`.
- Slice Wire controllers live in `src/core/features/<feature>/node/` and are aggregated by
  `src/core/manifests/node/controllers.ts`; they delegate to imported operation or service
  functions.
- Renderer-main calls go through Wire via the seeded connection seam in
  `src/core/primitives/wire/browser/connection.ts`: the renderer bootstrap seeds it once at
  startup, and each slice exposes a typed domain client from its `api/` (for example
  `getMcpClient()`) built on `domainClient`.
- Feature UI lives under `src/core/features/<feature>/browser/`; the editor slice owns Monaco and
  file rendering under `src/core/features/editor/browser/`; portable browser primitives (modals,
  views, navigation, commands, scoped stores) live under `src/core/primitives/`; the thin
  renderer host shell lives under `src/renderer/lib/`.
- New feature modals and views must be exposed through the owning slice's `contributions/browser.ts`
  and aggregated by `src/core/manifests/browser/browser-contributions.ts`.
- New task tabs contribute providers through `src/core/features/<feature>/contributions/tabs.ts`,
  aggregated by `src/core/manifests/browser/task-tab-contributions.ts`; the workbench registry
  lives at `src/core/features/workbench/api/browser/task-tab-registry.ts`.
- New commands are defined with `defineCommand` (`src/core/primitives/commands/`) in the owning
  slice's `contributions/commands.ts`, aggregated by
  `src/core/manifests/shared/command-catalog.ts`; view scopes
  (`src/core/primitives/view-scopes/`) bind availability and implementation.
- Commit messages should follow Conventional Commits:

```text
<type>(<scope>): <short imperative summary>

Examples:
fix(opencode): change initialPromptFlag from -p to --prompt for TUI
feat(docs): add changelog tab with GitHub releases integration
```

## Architecture Notes

```mermaid
flowchart LR
  User[User] --> Renderer[React renderer]
  Renderer --> Clients[Typed Wire domain clients]
  Clients --> Seam[Seeded wire connection seam]
  Seam --> Preload[Preload wire port]
  Preload --> Main[Electron main process]
  Main --> Gateway[Desktop Wire gateway]
  Gateway --> Controllers[Slice Wire controllers]
  Controllers --> Services[Domain services]
  Services --> DB[(SQLite via Drizzle)]
  Services --> Runtime[Runtime services]
  Runtime --> PTY[PTY sessions]
  Runtime --> ACP[ACP sessions]
  Runtime --> SSH[SSH and SFTP]
  Services --> VCS[Git, GitHub, GitLab, PRs]
  Services --> MCP[MCP and skills]
  ACP --> CoreAcp[@emdash/core ACP runtime]
  ACP --> Plugins[@emdash/plugins providers]
  Renderer --> ChatUI[@emdash/chat-ui]
  Main --> Events[Live models and typed events]
  Events --> Renderer
```

The app boots from `src/entry/main.ts`, which runs the phased bootstrap in
`src/main/bootstrap/` (environment, database, window creation, recovery). Renderer-main
traffic is served by the desktop Wire gateway (`src/main/gateway/desktop-wire.ts`) from the
contract assembled in `src/core/manifests/shared/desktop-wire-contract.ts` and the controllers
aggregated in `src/core/manifests/node/controllers.ts`. The preload bridge
(`src/entry/preload.ts`) exposes only `requestWirePort` and `getPathForFile`. The renderer is
a React app that calls typed Wire domain clients, subscribes to live models and typed events,
and coordinates views, tabs, modals, commands, project state, terminal state, and task
workflows.

Task execution has two runtime paths. Legacy/TUI conversations run through PTY
services under `packages/core/src/services/pty/` and the terminal/TUI runtimes under
`packages/core/src/runtimes/terminals/` and `packages/core/src/runtimes/tui-agents/`.
Structured chat conversations use ACP: provider plugins in `packages/plugins/` expose
ACP behavior, `packages/core/src/runtimes/acp/` owns protocol/session state, terminal
management, and process hosting, the desktop launches that runtime as a Wire component worker
from `src/main/gateway/entries/acp.ts` (`src/main/core/acp/` bridges agent status), and
`src/core/features/conversations/browser/acp/` maps updates into `@emdash/chat-ui`.

Main-process adapter domains live under `src/main/core/`: ACP, agent status, app,
dependencies, file search, files, Git, provider accounts, runtime,
shared, terminal shell, and utils. Portable domain logic lives in vertical slices
under `src/core/` and in `packages/core/` (for example PTY services under
`packages/core/src/services/pty/` and resource monitoring under
`packages/core/src/runtimes/resource-usage/`). Expected failures should use the
`Result<T, E>` pattern from `@emdash/shared` or the app-local result helpers.

## Testing Strategy

Local merge gate:

```bash
pnpm run format
pnpm run lint
pnpm run typecheck
pnpm run test
```

- Root `pnpm run test` uses Nx to run every workspace package test target.
- App tests run with Vitest projects in `apps/emdash-desktop/vitest.config.ts`.
- App `node` tests cover `src/**/*.test.ts` except DB, migration, and browser tests.
- App `main-db` tests cover main-process integration tests that need real SQLite.
- App `fixtures` tests generate DB fixtures via `pnpm run db:fixtures`.
- App `migrations` tests validate Drizzle migrations via `pnpm run test:migrations`.
- App `scripts` tests cover release and support scripts under `scripts/**/*.test.ts`.
- App `browser` tests use Playwright-backed `@vitest/browser` for renderer behavior.
- `packages/core` has ACP, dependency, plugin helper, Git, FS, and runtime unit tests.
- `packages/chat-ui` has node, browser, perf, and benchmark test targets.
- `packages/ui`, `packages/shared`, and `packages/plugins` run their package-local tests.
- Integration-style tests create temporary repos and worktrees in `os.tmpdir()`.
- The monorepo's GitHub workflows do not run this workspace yet; the former fork's
  `code-consistency-check.yml` (`nx affected` for `format:check`, `typecheck`, `lint`,
  and `test`) is the template for adding it. Until then every gate runs locally before
  merge.

## Security & Compliance

- The project is licensed under Apache-2.0; see `LICENSE.md`.
- Do not commit secrets, tokens, private keys, app databases, logs, build artifacts,
  generated dependency folders, or release artifacts.
- Application secrets are stored through encrypted app secret services and Electron
  safe storage; SSH credentials are managed through SSH services and OS-backed storage.
- Release secrets live in GitHub Actions secrets, including PostHog, Cloudflare R2,
  Apple signing/notarization, Azure Trusted Signing, and Cachix credentials.
- Telemetry must remain optional; users can disable it with `TELEMETRY_ENABLED=false`
  or in app settings.
- File logging must preserve redaction of common secret patterns.
- PTY environment construction must go through `packages/core/src/services/pty/api/terminal-env.ts`.
- Treat ACP process spawning, SSH command construction, shell escaping, PTY spawning,
  and worktree paths as security-sensitive.
- Do not bypass path-safety, shell escaping, or validation helpers.
- Use `pnpm-lock.yaml` for dependency integrity and review dependency changes.
- This checkout does not define repo-local Dependabot config, CODEOWNERS, or SECURITY.md;
  do not assume extra repository-owned security automation beyond the workflows present
  in `.github/workflows/`.
- Dependency changes must keep `pnpm-lock.yaml` in sync, preserve `packageManager` and
  `pnpm.onlyBuiltDependencies`, and avoid introducing new install scripts or native
  builds without explicit review.
- CI installs with `pnpm install --frozen-lockfile --ignore-scripts` in
  `.github/workflows/code-consistency-check.yml`; changes that rely on install-time
  side effects need clear justification.
- Prefer existing dependencies and workspace packages over adding new third-party
  packages. When adding a dependency, document why the existing stack is insufficient
  and check license/security posture before committing the lockfile change.

## Agent Guardrails

- Start with this file for repo-wide context and required commands.
- Load only the relevant `agents/` topic page for the area you are changing.
- Prefer updating the smallest applicable `agents/` page over expanding this file.
- If nested `AGENTS.md` files are added later, the closest file to the edited path wins.
- Explicit user or maintainer instructions override this file.
- Do not hand-edit numbered Drizzle migrations or `drizzle/meta/`.
- Use `pnpm run db:generate` for new migrations, then update fixtures and migration tests.
- Avoid editing `dist/`, `release/`, `out/`, `build/`, and generated package artifacts
  unless the task is explicitly about packaging, signing, or release behavior.
- Do not dispatch release workflows, publish packages, upload artifacts, or trigger
  external deployments unless the user explicitly asks for release work.
- Treat `src/main/core/acp/`, `packages/core/src/services/pty/`,
  `src/core/services/ssh/`, `src/main/db/`, updater code, and provider process
  spawning as high risk.
- Read the matching `agents/risky-areas/` page before touching database, PTY, SSH, or
  updater code.
- Never copy, vendor, or stage `apps/viewer`, `packages/cadgen`, or `skills/` into this
  tree; resolve them through `src/main/host/cad/text-to-cad-layout.ts`. Never script the
  CAD Viewer's DOM from the desktop.
- Do not weaken shell quoting, spawn behavior, env allowlists, path validation, or
  secret redaction casually.
- Prefer existing service, provider, plugin, Wire, modal, view, tab, and store patterns
  over new abstractions.
- New Wire procedures belong in the owning slice's `api/` contract with a controller in
  `node/`, registered through `src/core/manifests/shared/desktop-wire-contract.ts` and
  `src/core/manifests/node/controllers.ts`.
- Keep renderer-main calls on typed Wire contracts, live models, and typed events. The preload
  bridge should stay small; add direct `window.electronAPI` surface only when an
  Electron/browser primitive cannot fit the Wire path.
- Access task and Project MobX stores through selectors and task view hooks:
  `getTaskStore`, `asProvisioned`, `taskViewKind`, `getTaskManagerStore`,
  `getProjectStore`, `asAvailableProject`, `getProjectHostAccess`, `useTaskViewKind`, `useWorkspace`,
  `useWorkspaceId`, `useWorkspaceViewModel`, `useConversations`,
  and `useTerminals`.
- Never use `asProvisioned(...)!` or `asAvailableProject(...)!`; use explicit null checks.
- State guards must check `kind !== 'ready'` rather than enumerating non-ready states.
- Access task managers through `getTaskManagerStore(projectId)`, not `project.taskManager`.
- Access available Project contexts through `asAvailableProject(getProjectStore(id))`, not inline
  guards. Read Host-dependent action state through that context's `host` access interface.
- Task selectors live in `src/core/features/tasks/api/browser/task-state/task-selectors.ts`.
- Project selectors live in `src/core/features/projects/api/browser/stores/project-selectors.ts`.
- For provider changes, update plugin metadata, shared provider metadata, ACP support
  flags, PTY env passthrough if needed, hook integrations, renderer assumptions, and
  tests for non-standard behavior.
- For ACP changes, preserve protocol state-machine behavior in `packages/core/src/runtimes/acp/`,
  keep provider-specific transforms in `packages/plugins/`, and adapt UI payloads at
  app or chat-UI edges.
- For MCP changes, keep canonical data in shared types and adapt provider formats at edges.
- Follow `.github/PULL_REQUEST_TEMPLATE.md`: keep PRs small and focused, self-review
  before handoff, list checks run, attach UI evidence when applicable, and update docs
  and tests when behavior changes.
- Call out high-risk changes explicitly in the PR description or handoff notes,
  especially database, ACP, PTY, SSH, updater, provider spawning, dependency, and
  release-related changes.
- Do not self-approve, merge, assign reviewers, edit branch protection, or change
  workflow permissions unless the user explicitly asks.
- Avoid scripted loops against GitHub, Linear, Jira, GitLab, provider CLIs, or release
  workflows. Use focused queries and respect existing workflow retries; ask before
  adding polling, bulk API calls, or scheduled automation.
- Keep automation scoped to the task. Do not run the full local merge gate repeatedly
  when a focused check is enough during iteration; run broader checks before handoff
  when the change scope justifies it.

## Extensibility Hooks

- Agent provider plugins live in `packages/plugins/src/agents/impl/` and are registered
  in `packages/plugins/src/agents/registry.ts`.
- Provider plugin hosting services live in `packages/core/src/services/agent-plugins/`.
- Agent provider metadata and capabilities live in `packages/plugins/src/agents/registry.ts`
  and `packages/plugins/src/agents/impl/`; renderer-facing DTOs are built by
  `src/core/features/agents/node/agent-payload-builder.ts`.
- ACP support is exposed through plugin ACP capabilities and portable Core ACP APIs.
- Provider detection lives in `src/main/core/dependencies/`.
- Provider PTY behavior and env construction live under `packages/core/src/services/pty/`.
- Provider event hooks and plugins are installed and hosted by
 `packages/core/src/runtimes/tui-agents/`; desktop projection lives under
 `src/main/core/agent-status/`.
- ACP process hosting lives in `packages/core/src/runtimes/acp/`; the desktop launches the
  runtime as a Wire component worker from `src/main/gateway/entries/acp.ts`.
- Feature modal and view definitions are contributed by slices and aggregated in
  `src/core/manifests/browser/browser-contributions.ts`; renderer app registries compose host entries.
- Task tab providers are aggregated through
  `src/core/manifests/browser/task-tab-contributions.ts`.
- MCP server config handling lives in `src/core/features/mcp/node/` (wire controller and
  registration utils), canonical types in `src/core/primitives/mcp/api/`, and UI in
  `src/core/features/mcp/browser/`.
- Skills types and validation live in Core primitives; skills UI and service code live in
  `src/core/features/skills/browser/` and `src/core/features/skills/node/`.
- Team-owned runtime settings live in each workspace's `.emdash.json`:
  `preservePatterns`, `scripts.prepare`, `scripts.setup`, `scripts.run`,
  `scripts.teardown`, and `shellSetup` (a per-workspace override of the host default).
- Project overrides such as `worktreeRoot`, `defaultBranch`, `baseRemote`, `pushRemote`,
  `githubAccount`, `agentGitCredentials`, and `tmux` are DB-backed, not `.emdash.json`. Effective
  tmux resolves through project override > host default > app default; it is not seeded from a
  default at project creation.
- The workspace registry owns lifecycle and file-handling config. Host-local personal config
  (`preservePatterns`, scripts, and auto-run toggles) is versioned JSON on the repository or
  directory project-root record; worktrees resolve against their project root's personal config.
- Read registry-owned config through the keyed `projectConfig` live model or `getProjectConfig`.
  It exposes raw personal/team layers, team-file sources, and one `{ value, from }` result per
  field. Applicable precedence is personal > that workspace's `.emdash.json` > host default >
  built-in; arrays replace rather than merge.
- Per-host defaults (`shellSetup`, `worktreeRoot`, `tmux`) live in the host-settings
  runtime (`packages/core/src/runtimes/host-settings/`), stored as JSON in the host's
  emdash data directory and editable from the machines/system settings UI.
- Desktop project settings compose self-contained domain snapshots: the registry owns
  lifecycle/file handling, while desktop DB and host-settings domains own Git identity and
  placement. Forms edit raw layers with explicit per-domain patches; there is no merged settings
  bag to persist.
- The scripts runtime is a strict executor: callers must provide resolved `command` and
  `shellSetup`; it never reads config files or host defaults. The workspace registry resolves and
  sequences lifecycle commands, then observes runs into durable lifecycle steps.
- Desktop settings migrations are centralized under
  `src/core/features/projects/node/settings/migrations/` and run in order when an attachment is
  established. Legacy schemas and readers stay migration-only; destination markers make imports
  idempotent and retryable.
- Optional environment variables include `TELEMETRY_ENABLED`, `EMDASH_DB_FILE`,
  `EMDASH_DISABLE_NATIVE_DB`, `EMDASH_DISABLE_PTY`,
  `CODEX_SANDBOX_MODE`, and `CODEX_APPROVAL_POLICY`.
- Build-time telemetry configuration may use `VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST`.
- App-internal path aliases are defined in `tsconfig.json` (`@/*`, `@core/*`, `@renderer/*`,
  `@main/*`, `@root/*`, and `@tooling/*`) and mirrored where needed in
  `electron.vite.config.ts`; workspace packages resolve through their `exports` maps with a
  `development` condition, not aliases.
- Versioned JSON column schemas use `defineVersionedSchema()` from
  `@emdash/core/primitives/versioned-schema/api`
 (`packages/core/src/primitives/versioned-schema/api/versioned-schema.ts`) and Drizzle
 `versionedJsonColumn()` from `src/core/services/app-db/node/versioned-column.ts`.

## Further Reading

- [Agent docs map](agents/README.md)
- [Quickstart](agents/quickstart.md)
- [Architecture overview](agents/architecture/overview.md)
- [Settings ownership and precedence](agents/architecture/settings.md)
- [Main process architecture](agents/architecture/main-process.md)
- [Renderer architecture](agents/architecture/renderer.md)
- [Shared modules](agents/architecture/shared.md)
- [Developer flows](agents/workflows/flows.md)
- [Nx task orchestration and caching](agents/workflows/nx.md)
- [Testing workflow](agents/workflows/testing.md)
- [Worktrees workflow](agents/workflows/worktrees.md)
- [Remote development workflow](agents/workflows/remote-development.md)
- [Workspace server architecture](agents/architecture/workspace-server.md)
- [Provider integration](agents/integrations/providers.md)
- [MCP integration](agents/integrations/mcp.md)
- [IPC conventions](agents/conventions/ipc.md)
- [Main-process patterns](agents/conventions/main-patterns.md)
- [Renderer patterns](agents/conventions/renderer-patterns.md)
- [TypeScript and React conventions](agents/conventions/typescript.md)
- [Config file rules](agents/conventions/config-files.md)
- [UI kit conventions](agents/conventions/ui-kit.md)
- [UI styling conventions](agents/conventions/ui-styling.md)
- [Versioned schema conventions](agents/conventions/versioned-schemas.md)
- [Database risk notes](agents/risky-areas/database.md)
- [PTY risk notes](agents/risky-areas/pty.md)
- [SSH risk notes](agents/risky-areas/ssh.md)
- [Updater risk notes](agents/risky-areas/updater.md)
- [Contributing guide](CONTRIBUTING.md)
- [Project README](README.md)
