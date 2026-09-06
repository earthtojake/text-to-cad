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
| P1 | `src/main/agents`, `src/main/acp`, `src/shared/acp/reduce.ts`, session creation and the session index |
| P2 | `src/renderer/features/session` — the transcript, activity rows, composer chips, permissions, plan card |
| P3 | `src/main/explorer`, `src/renderer/features/explorer` — file tab, tree, Monaco, review, browser, terminal |
| P4 | `src/main/cad/viewer.ts` and the file tab's CAD renderer, against `apps/viewer`'s new `CadFileView` |
| P5 | `src/main/cad/{runtime,plugin,mcp-server}.ts`, `resources/`, `skills/hardcore-app` |
| P6 | `src/renderer/features/settings` — the pages' contents |
| P7 | `src/main/projects/git.ts` and the review tab's actions |
| P8 (done) | `electron-builder.yml`, `build/`, `resources/`, `scripts/{package,make-icons}.mjs`, `updater.ts`, `telemetry.ts`, `src/{shared,main}/ipc/app.ts`, the CI jobs |

Work outside your phase's directories only where the seam requires it — a new
IPC branch in `src/shared/ipc/<branch>.ts`, spread into `src/shared/ipc.ts`,
with its handlers in `src/main/ipc/<branch>.ts` spread into
`src/main/ipc/index.ts`, is expected; reshaping the shell to fit one feature is
not.

## Rules that are easy to break here

- **The renderer imports from `src/main` never, and from `src/shared` types
  only.** Its one way off the page is `window.hardcore`, built from the
  contract in `src/shared/ipc.ts`.
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
- **`src/renderer/components/{ui,ai-elements}` is vendored**, from the shadcn
  and AI Elements registries. It is excluded from eslint (not from the
  typechecker). Two deliberate edits are in it: the `ai` package's types are
  replaced by `./types` (`components/ai-elements/types.ts`), and about nine
  index accesses are guarded for `noUncheckedIndexedAccess`. Re-vendoring a
  component means redoing those.
- **`package.json` stays at version `0.0.0`.** The repository's `VERSION` is
  the canonical release version; `scripts/app-version.mjs` reads it and both
  the build and `scripts/package.mjs` stamp it. Do not hand-edit it.
- **Exact dependency versions, no ranges.** Everything the later phases need is
  already installed, so a phase should not have to touch `package.json`.
- **No symlinks, ever** (repo-wide law: installers disagree about them and one
  drops them silently).
- **No bottom panel.** The terminal is a fourth explorer tab kind. Everything
  secondary lives in the one strip.
