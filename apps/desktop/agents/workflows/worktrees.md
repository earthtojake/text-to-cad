# Worktrees

## Main Files

- `packages/core/src/runtimes/workspace-registry/` (creation pipeline, lifecycle steps, activation)
- `packages/core/src/runtimes/scripts/` (lifecycle script execution)
- `packages/core/src/runtimes/host-settings/` (per-host defaults)
- `src/core/features/workspaces/` (desktop wire controllers and UI)
- `.emdash.json`

## Current Behavior

- task worktrees are created under the project's DB-backed worktree directory setting
- branch prefix defaults to `emdash` and is configurable in app settings
- generated task branch names use the configured prefix plus a random suffix by default; app repository settings can disable only the random suffix
- worktree creation is managed by the project provider pattern
- creation runs a fast foreground pipeline (`inspect → resolve-base → add-worktree → verify`);
  the base ref is fetched only when it is not locally resolvable
- newly created task branches use `git worktree add --no-track`; the selected base ref is a
  starting point, not the branch's upstream
- gitignored files named in `preservePatterns` are copied from the repository into the new
  worktree as a durable background step, using copy-on-write (`cp -c` on APFS,
  `--reflink=auto` on Linux) with a plain-copy fallback; nothing is copied without
  configured patterns
- there are no built-in preserve defaults: the `.env` family is no longer copied
  automatically — projects that relied on it must add `preservePatterns` (behavior
  change in workspace-lifecycle-v2; `excludePatterns` was removed at the same time and
  stale keys are silently ignored)
- branch publication carries the resolved project `pushRemote` as an explicit durable target;
  a successful push establishes that remote's same-named branch as upstream
- branch publication and ref freshening run as durable background steps; a failed push surfaces
  as a "branch not pushed" task state with a manual retry

## `.emdash.json`

`.emdash.json` stores optional shareable project settings. Supported runtime keys:

- `preservePatterns` (gitignored files deliberately carried into new worktrees; empty unless configured)
- `scripts.prepare`
- `scripts.setup`
- `scripts.run`
- `scripts.teardown`
- `shellSetup` (per-workspace override of the host-settings default; the per-project DB
  field was retired)

Base project settings are DB-backed Project Settings, not runtime `.emdash.json` keys:

- `worktreeDirectory`
- `defaultBranch`
- `baseRemote`
- `pushRemote`
- `tmux`

Host-level defaults (`shellSetup`, `worktreeRoot`, `tmux`) live in the host-settings
runtime (`packages/core/src/runtimes/host-settings/`), stored as a JSON file in the
host's emdash data directory and editable from the machines/system settings UI.
Precedence is per-project DB override, then host settings, then app defaults.

## Rules

- do not hardcode worktree paths; use service helpers
- use lifecycle config for repo-specific bootstrap and teardown behavior
- `scripts.prepare` is blocking and runs after the workspace exists but before task providers,
  conversations, setup scripts, or run scripts start; keep it idempotent
- `scripts.prepare`, `scripts.setup`, and `scripts.run` wait for the background artifact copy to
  settle before running, since they may consume preserved files
- `scripts.setup` and `scripts.run` are runtime-triggered after `scripts.prepare` succeeds; they do
  not block task readiness
- lifecycle scripts execute in the dedicated scripts runtime
  (`packages/core/src/runtimes/scripts/`) on the host: PTY-backed, one run per
  (workspace, script), with provenance (`activation`/`manual`/`retry`), per-run timeouts,
  and a stop verb; the workspace registry observes runs and mirrors them into durable
  lifecycle steps for the Activity timeline
- `shellSetup` runs inside each PTY before the interactive shell starts; the workspace's
  `.emdash.json` value overrides the host-settings default
- tmux wrapping has an app level default but is also project-configurable in Project Settings and affects PTY lifecycle behavior.
- `preservePatterns` never copies tracked files or `.emdash.json`
