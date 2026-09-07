# AGENTS.md — apps/desktop

Read `README.md` first: dev, checks, packaging and the layout tree are there.

## The plan is not in this repository

Hardcore's design document lives outside the checkout, at
`~/robots/text-to-cad-notes/design/desktop-app.md` (user policy: design notes
are never committed). Section numbers in the comments here — "plan §3", "plan
§9" — point at it. If you cannot read it, ask; do not reconstruct it from the
code and do not write a copy into this tree.

## Directory ownership per phase

One phase owns a directory. A folder that is a stub with a comment naming its
phase is not an oversight — it is the seam.

| Phase | Owns |
| --- | --- |
| P0 (done) | the project itself, `src/shared`, `src/preload`, `src/main/{index,menu,window-state,telemetry,updater}.ts`, `src/main/db`, `src/main/ipc`, the shell, the command palette, Settings' frame, `tests/` |
| P1 (done) | `src/main/agents`, `src/main/acp`, `src/shared/acp`, `src/shared/agents.ts`, `src/shared/ipc/{acp,agents}.ts`, `src/main/ipc/{acp,agents}.ts`, `src/renderer/state/{acp,agents}.ts`, `scripts/acp-harness.mjs`, `tests/fake-agent`, `tests/fixtures/acp` |
| P2 | `src/renderer/features/session` — the transcript, activity rows, composer chips, permissions, plan card — plus what the model and effort chips are drawn from before a session exists: `src/shared/acp/options.ts`, `src/{shared,main}/ipc/agent-options.ts`, `src/main/acp/agent-options.ts`, `src/renderer/state/agent-options.ts` |
| P3 (done) | `src/main/explorer`, `src/main/ipc/{explorer,cad}.ts`, `src/shared/ipc/{explorer,cad}.ts`, `src/renderer/features/explorer` — file tab, tree, Monaco, review, browser, terminal |
| P4 (done) | `apps/viewer`'s `CadFileView` and its `viewerOrigin` threading; P3's file tab renders it |
| P5 (done) | `src/main/cad/`, `src/main/ipc/{cad,runtime,plugins}.ts`, `resources/`, `skills/hardcore-app-use`, `scripts/{build,build-plugin,build-mcp,cad-resources,bundle-runtime}.mjs`, `src/renderer/state/cad-commands.ts`, the `reveal` field of the explorer store and tree |
| P6 | `src/renderer/features/settings` — the pages' contents |
| P7 (done) | `src/main/projects/{git,workspace}.ts`, `src/shared/ipc/git.ts`, `src/main/ipc/git.ts`, `src/renderer/lib/git-mode.ts`, the review tab's scopes and commit popover, Git & Worktrees' per-project cards, `tests/e2e/git.spec.ts` |
| P8 (done) | `electron-builder.yml`, `build/`, `resources/`, `scripts/{package,make-icons}.mjs`, `updater.ts`, `telemetry.ts`, `src/{shared,main}/ipc/app.ts`, the CI jobs |

Work outside your phase's directories only where the seam requires it — a new
IPC branch in `src/shared/ipc/<branch>.ts`, spread into `src/shared/ipc/index.ts`,
with its handlers in `src/main/ipc/<branch>.ts` spread into
`src/main/ipc/index.ts`, is expected; reshaping the shell to fit one feature is
not.

## Rules that are easy to break here

- **The renderer imports from `src/main` never, and from `src/shared` types
  only.** Its one way off the page is `window.hardcore`, built from the
  contract in `src/shared/ipc/index.ts`.
- **Every IPC channel is declared once**, as a request schema and a response
  schema. `registerIpc` validates both and refuses to start if a channel has no
  handler. Do not add an `ipcMain.handle` outside it. A branch is its own module
  under `src/shared/ipc/`, spread into the contract; `invoke` comes from
  `./define`, because importing `../ipc` from a branch is a load-time cycle.
- **`node_modules` here is installed, never symlinked.** electron-builder walks
  the tree by real path: a symlinked `node_modules` resolves every transitive
  dependency to `undefined`, packages an app missing half its modules, and does
  not fail while doing it. The viewer's worktree trick does not apply.
- **Nothing reads `process.env` for a build-time secret.** The Aptabase key is
  compiled in as `__APTABASE_KEY__` (`electron.vite.config.ts`); a packaged app
  has no build environment, and a key the launcher can set is a key anyone can
  redirect.
- **Every path from the renderer arrives with the project it is relative to,
  and optionally a root within it.** Main resolves the pair against that
  project's directory — or, when the request names a `root`, against one of
  that project's own worktrees, and nothing else (`rootOf` in
  `src/main/ipc/explorer.ts`, `resolveProjectRoot` in
  `src/main/projects/workspace.ts`) — after `realpath`, so a symlink is not a
  door — and refuses anything outside. A channel that took a bare path would
  be a channel that reads any file on the machine.
- **`src/renderer/components/{ui,ai-elements}` is vendored**, from the shadcn
  and AI Elements registries. It is excluded from eslint (not from the
  typechecker). Three deliberate edits are in it: the `ai` package's types are
  replaced by `./types` (`components/ai-elements/types.ts`), about nine
  index accesses are guarded for `noUncheckedIndexedAccess`, and `shimmer.tsx`
  sweeps a foreground-coloured band rather than a background-coloured one
  (the stock band erases the letters it passes over). Re-vendoring a
  component means redoing those.
- **The CAD runtime ships inside the app.** `resources/runtime/<os>-<arch>/`
  is a complete Python with cadgen installed (`scripts/bundle-runtime.mjs`),
  resolved right after an explicit override; a packaged app downloads and
  installs nothing, and `scripts/package.mjs` refuses to package without it.
  Do not add a first-launch install, a progress state, or a Settings page for
  it back: a runtime that is not there is a failure the CAD tab reports with
  the interpreter's words, not a state the person is asked to fix.
- **`package.json` stays at version `0.0.0`.** The repository's `VERSION` is
  the canonical release version; `scripts/app-version.mjs` reads it and both
  the build and `scripts/package.mjs` stamp it. Do not hand-edit it.
- **Exact dependency versions, no ranges.** Everything the later phases need is
  already installed, so a phase should not have to touch `package.json`.
- **No symlinks, ever** (repo-wide law: installers disagree about them and one
  drops them silently).
- **No bottom panel.** The terminal is a fourth explorer tab kind. Everything
  secondary lives in the one strip.
- **The explorer strip belongs to the project, not to a session.** A person
  with a file, a terminal and a review open is looking at a directory; closing
  a thread must not take those away. `explorer_tabs` is keyed by `project_id`
  (migration 2). What *does* follow the session is the strip's **root** (README,
  "The explorer's root"): a worktree thread makes new tabs open in, and the
  tree list, its worktree; every tab keeps the root it was opened in.
- **The renderer never picks a session's working directory.** It sends a git
  mode; main resolves it (`src/main/projects/workspace.ts`), creates the
  worktree, and writes `cwd`, `branch` and `worktreePath` onto the row. The one
  exception is Settings' `New chat in this worktree`, which names a directory
  that already exists — and main checks it is the project or one of that
  project's own worktrees before running anything in it.
- **A review's `Last turn` and `This session` are revisions, not times.** Main
  records HEAD when a session is created and again at the start of every turn
  (`sessions.sessionHead` / `turnHead`); the renderer sends the scope's *name*
  and main resolves it. Two commits can share a second, and `--before=` picks a
  commit rather than a moment, so a timestamp cannot do this job.
