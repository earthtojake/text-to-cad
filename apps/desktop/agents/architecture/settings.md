# Settings Ownership And Precedence

This page is the authoritative map for settings that affect project and workspace execution.
Do not introduce another merged project-settings bag. Read raw values from the owning domain and
use the named resolver listed below when a field has multiple layers.

"Personal" means **host-local personal config**: data stored by the workspace registry on that
machine. It is not an account-wide user profile, is not shared with the team, and is not synced to
other machines. "Team" means a repository or working-directory `.emdash.json` that can be
committed and shared.

## Field Ownership

| Field | Owning store | Effective precedence | Resolver | Main execution consumers |
| --- | --- | --- | --- | --- |
| `scripts.prepare` | Workspace registry host-local personal config; team `.emdash.json` | host-local personal > that workspace's team file > unset | `resolveProjectConfig()` in `packages/core/src/runtimes/workspace-registry/node/project-config.ts` | Workspace registry creation/lifecycle sequencing in `packages/core/src/runtimes/workspace-registry/node/runtime.ts` |
| `scripts.setup` | Workspace registry host-local personal config; team `.emdash.json` | host-local personal > that workspace's team file > unset | `resolveProjectConfig()` | Workspace registry activation and lifecycle sequencing |
| `scripts.run` | Workspace registry host-local personal config; team `.emdash.json` | host-local personal > that workspace's team file > unset | `resolveProjectConfig()` | Workspace registry activation and lifecycle sequencing |
| `scripts.teardown` | Workspace registry host-local personal config; team `.emdash.json` | host-local personal > that workspace's team file > unset | `resolveProjectConfig()` | Workspace registry deactivation and lifecycle sequencing |
| `autoRunSetup` | Workspace registry host-local personal config | host-local personal > built-in `true` | `resolveProjectConfig()` | Workspace registry activation gate and lifecycle sequencing |
| `autoRunRun` | Workspace registry host-local personal config | host-local personal > built-in `false` | `resolveProjectConfig()` | Workspace registry activation gate and lifecycle sequencing |
| `preservePatterns` | Workspace registry host-local personal config; team `.emdash.json` | host-local personal > that workspace's team file > built-in `[]`; arrays replace | `resolveProjectConfig()` | Worktree create/update copy-artifact steps |
| `shellSetup` | Team `.emdash.json`; host settings JSON | that workspace's team file > host default > unset | `resolveProjectConfig()` | Workspace lifecycle script launches, task conversations, and terminal hydration |
| `tmux` | Desktop project-settings DB override; host settings JSON; desktop app setting `project.tmuxByDefault` | stored project override > host default > app default | `resolveTmux()` in `apps/emdash-desktop/src/core/primitives/project-settings/api/effective-settings.ts` | Task conversation assembly, terminal hydration, and project-session teardown |
| `worktreeRoot` | Desktop project-settings DB override; host settings JSON; built-in host path | stored project override > host default > `<host-home>/emdash/worktrees` | `resolveWorktreeRoot()` in `apps/emdash-desktop/src/core/primitives/project-settings/api/effective-settings.ts` | `WorkspacePlacementResolver`, task creation, and destination previews |
| `defaultBranch` | Desktop project-settings DB; live repository facts | valid stored branch > remote HEAD > well-known remote branch > well-known local branch > unavailable | `resolveEffectiveSettings()` / `resolveEffectiveGitSettings()` in `apps/emdash-desktop/src/core/primitives/project-settings/api/effective-settings.ts` | Task and terminal environment, task creation, automation deployment, source-control UI |
| `baseRemote` | Desktop project-settings DB; live repository facts | valid stored remote > `origin` > sole remote > first remote alphabetically > unavailable | `resolveEffectiveSettings()` / `resolveEffectiveGitSettings()` | Git fetch, task creation, automation deployment, source-control UI |
| `pushRemote` | Desktop project-settings DB; effective base remote | valid stored remote > effective base remote > unavailable | `resolveEffectiveSettings()` / `resolveEffectiveGitSettings()` | Push and pull-request flows, automation deployment, source-control UI |
| `githubAccount` | Desktop project-settings DB; connected provider accounts; repository remote host | stored account/explicit none > matching default account > sole host-matching account > none; stale or host-mismatched pins fail closed | `resolveEffectiveSettings()` | GitHub issues and pull requests, Git credentials, GitHub account UI |
| `agentGitCredentials` | Desktop project-settings DB | stored project choice > built-in `effective-account` | `getStoredGitSettings()` plus `DEFAULT_AGENT_GIT_CREDENTIALS` | `createGitCredentialsService()` for TUI, terminal, and source-control session credentials |
| `watcherExclude` | Local desktop app settings for the local worker; host settings JSON for remote workspace servers | worker-specific stored value > shared built-in exclusion list. With “Sync local settings” enabled, the desktop value is copied to the remote host (last writer wins; this is synchronization, not a precedence layer). | Files runtime construction in `apps/emdash-desktop/src/main/gateway/desktop-workers.ts` and `apps/workspace-server/src/gateway/workspace-workers.ts` | Files runtime watchers and file-search exclusion policy |

## Domain Boundaries

- `ProjectSettingsProvider` exposes stored Git identity, stored placement, placement context, and
  resolver-backed tmux. It does not expose a merged `get()` or `update()` API.
- Desktop DB JSON stores only explicit project overrides. `tmuxDefaultMigrated` is one-time lazy
  migration metadata, not a user setting.
- Project settings pages are self-contained domain snapshots. Forms patch only touched fields;
  `null` removes an explicit value and restores inheritance.
- The workspace registry is the sole resolver for lifecycle and file-handling config. The scripts
  runtime receives already-resolved `command` and `shellSetup` values and does not read config.
- Git/GitHub and placement previews must use the same portable resolvers as execution.

## Deferred And Deliberate Legacy Behavior

- The desktop `shareableProjectSettingsJson` column remains temporarily as a migration source and
  completion-marker carrier. Retiring that column is deferred to a future migration-train step;
  current production reads and writes must not treat it as an active settings owner.
- Historical desktop/project `shellSetup` values are deliberately dropped. They are not imported
  into host-local personal config. Current `shellSetup` comes only from `.emdash.json` or the host
  settings JSON chain above.
