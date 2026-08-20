# AGENTS.md

This repo is a workbench for CAD-related agent skills. Treat `skills/` as the
product and `models/` as the shared fixture/artifact area.

## Branch And Layout First

Before changing code, branch from `develop`, not `main`; PRs should target `develop`.
Do not start development work from `main`. The `develop` branch intentionally uses
symlinks across generated runtime and viewer-local package paths. When a path is
symlinked, follow the link and edit the source target.
Use `main` as the production clone/release branch only. `main` is publish-only:
do not open PRs to `main` or push it directly.

## Release Workflow

Do not bump the canonical release version in `VERSION` during
normal development work. Ship releases only through the single `Release`
GitHub Actions workflow, which handles the version bump, release PR, publish
commit to `main`, `cadgen` PyPI publish, docs deploy, semver tag, and GitHub
Release in one run.

When asked to publish, make, or ship a release, dispatch `Release` with its
defaults: build from `develop` (`base_branch=develop`), publish to `main`
(`target_branch=main`), and publish the GitHub Release (`publish=true`, not a
draft). Never pick the semver bump yourself: if the request does not name
patch, minor, major, or an exact version, ask which one before dispatching.
Use `target_branch=build-test` only when the user explicitly asks to test
CI/CD or build-pipeline changes — never by default and never as part of a
requested release, and pair it with `bump=none` so a rehearsal does not consume
a version number. `bump=none` publishes `base_branch` as it stands and is also
how you resume a failed publish; it is never a release setting.

The standalone `Deploy Docs` workflow redeploys the docs site without running a
release. It deploys a source ref (defaulting to `develop`), never `main`: the
publish tree drops `docs/` and `packages/`, which the docs app builds against.
The CAD Viewer is a local-filesystem app with no hosted deployment, but each
release mirrors `viewer/` into the standalone `earthtojake/cad-viewer` repo
through the `Sync CAD Viewer Repo` workflow, which `Release` calls after
publishing and which can also be dispatched on its own. Both of those read the
release SOURCE commit, because `main` carries only what installs.
`main` is publish-only; pushing `develop` runs tests but
never publishes. See the Releases section in `CONTRIBUTING.md` for the full
flow, CI/CD-testing and resume options, and local/manual fallbacks.

## Repo Map

- `skills/`: agent skills and their references/scripts.
- `.claude-plugin/`, `.codex-plugin/`: agent plugin manifests. The repository
  root is the plugin package; its skills are `skills/` directly.
- `models/`: sample and durable CAD/robot-description fixtures.
- `viewer/`: editable CAD Viewer source app.
- `packages/cadjs`: shared JS CAD/render/runtime code, UI-framework agnostic.
- `packages/implicitjs`: standalone JS implicit CAD model, shader render,
  snapshot, mesh sampling, and export runtime.
- `packages/cadgen`: shared Python STEP/GLB/topology artifact code.
- `docs/`: documentation site.
- `tests/`: root-owned test suites for skills, packages, viewer services, and
  repo-wide policy.
- `scripts/`: durable repo commands grouped by purpose.

## Repo Rules

- Keep root guidance short. Put domain workflows, CLI details, and validation
  policy in the relevant `skills/<skill>/SKILL.md` or `references/` file.
- Keep relevant Markdown docs current when changing behavior, commands, or repo
  layout, but do not bloat `AGENTS.md`; use it only for durable repo-level
  rules and pointers.
- Read `CONTRIBUTING.md` before committing, rebasing, resolving generated-file
  conflicts, or bumping release versions.
- Keep the primary local `develop` checkout in symlink layout with
  `scripts/dev/setup-symlinks.sh`. Do not auto-repair that layout from
  Codex or Claude Code startup hooks in linked worktrees.
- Each skill must be self-contained and independent at runtime. A skill must
  not refer to or import or depend on code from another skill, from `skills/`
  root, or from repository-root modules. Do not add `skills/`, the repository
  root, or sibling skill directories to `sys.path`, `PYTHONPATH`, `NODE_PATH`,
  or similar runtime lookup paths. Shared runtime helpers must live under
  `packages/` as the source of truth and be vendored/generated from there into
  each consuming skill runtime; do not keep shared helper modules directly under
  `skills/`.
- Edit the source reached by the `develop` symlink layout first, then regenerate
  explicit derived outputs when a production-output task requires it.
- Write all test, sample, permanent, and generated CAD/robot-description
  artifacts under `models/`, including STEP/STP, STL, GLB, DXF, URDF, SRDF,
  and SDF outputs. Do not create ad hoc artifact directories elsewhere.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- Development symlinks mark generated or copied paths. If a file is under a
  symlinked runtime or viewer package path, edit the symlink target/source path
  instead of treating the copy as independent.
- When source changes affect generated runtimes, refresh or check them with the
  master bundle wrapper, `scripts/bundle/bundle.sh`. Use lower-level bundle
  scripts only when debugging the wrapper itself.
- Never let a symlink reach the published tree. Agent installers disagree about
  symlinks and one loses data silently: the Skills CLI dereferences them, Claude
  Code preserves them, and Codex `plugin add` drops them with no error, shipping
  a skill with missing files. `scripts/github-workflows/check-builds.sh` enforces
  this; do not relax it.
- `viewer/` must stay self-contained: nothing under it may reference a path,
  command, or document above it, because it is mirrored verbatim into the
  standalone `cad-viewer` repo with no rewriting step. Keep repo-level tooling
  in `scripts/`, not under `viewer/`.
  `viewer/scripts/selfContained.test.mjs` enforces this.
- `packages/cadjs` must stay reusable/non-React; app UI and workflow state
  belong in `viewer/`.
- `packages/implicitjs` must stay reusable/non-React and independent of
  `packages/cadjs` (`implicitjs` must never import `cadjs`). The dependency
  flows one way: `cadjs` depends on `implicitjs` and re-exports its shared
  render/export APIs under `cadjs/implicit/*`, so consumers (CAD Viewer,
  snapshot tools) install and import `cadjs` alone rather than depending on
  `implicitjs` directly or duplicating implicit CAD logic. Shared primitives
  that both packages need live in `implicitjs` as the single source of truth
  and are re-exported from `cadjs` (e.g. `cadjs/common/camera.js`).
- `packages/cadgen` owns reusable Python artifact generation; skills should use
  bundled package code, not sibling skill imports.
- Create lightweight shared Python packages under `packages/` when a helper
  should not inherit heavier package dependencies.
- Use path-targeted search, validation, and `git status`; avoid broad scans over
  generated CAD/LFS artifacts unless the task requires them.
- Treat `VERSION` as the canonical release version. Do not hand-edit duplicate
  package, plugin, lockfile, or Python `pyproject.toml` versions; release
  preparation and `scripts/bundle/bundle.sh` stamp them from the canonical
  version.

## Environments

- Prefer `./.venv/bin/python` for CAD Python work.
- Keep new branch checkouts and git worktrees lightweight by default. Do not
  copy `.venv/` or `models/` through `.worktreeinclude`; recreate `.venv/`
  inside the worktree only when Python dependencies are needed for the workflow.
- In Codex or Claude Code worktrees, prefer the skill instructions and scripts
  under the current worktree's `skills/` directory over globally installed
  skill symlinks from another checkout.
- If a worktree explicitly needs the development symlink layout, run
  `scripts/dev/setup-symlinks.sh --check` and then
  `scripts/dev/setup-symlinks.sh` intentionally in that worktree.
- Hydrate `models/` only when the user asks for it or when the task targets
  specific files under `models/`. In a new worktree, make the relevant model
  paths real before using them, preferring the local Git LFS cache with
  `git lfs checkout <path>` or `git lfs checkout models`. Download missing LFS
  objects only when explicitly requested or required after confirming the local
  cache is missing them.
- Install dependencies only for the workflow being changed.
- Do not commit `.venv/`, `node_modules/`, caches, `tmp/`, local credentials, or
  printer config.

## Checks

Run the smallest path-targeted check that covers the change. Use broad wrappers
when touching shared surfaces or before handoff:

- Code tests: `scripts/test/test.sh`
  - In GitHub Actions, `test.yml` checks the canonical release version in a
    separate job so code tests still run when version metadata is wrong; its
    test job verifies the `develop` symlink layout, checks generated outputs
    against their sources, bundles temporary production outputs, and runs docs
    and code tests against that bundle. `main` writes are validated by the
    `Release` workflow's publish job; GitHub branch settings should block PRs
    and direct pushes to `main`.
- Focused test runners: `scripts/test/test-js.sh`,
  `scripts/test/test-docs.sh`, `scripts/test/test-python.sh`,
  `scripts/test/test-global.sh`
- Development symlink layout: `scripts/dev/setup-symlinks.sh --check`
- Canonical release version: `scripts/release/check-version.sh`
- Generated runtime freshness: `scripts/bundle/bundle.sh --check`
- CAD Viewer, `packages/cadjs`, or `packages/implicitjs`:
  `npm --prefix packages/cadjs test`, `npm --prefix packages/implicitjs test`,
  `npm --prefix viewer run test`, `npm --prefix viewer run build`
- Docs site: `npm --prefix docs run check`
- Targeted Python tests: `./.venv/bin/python -m unittest <changed test paths>`

When a task intentionally writes production outputs locally, run
`scripts/bundle/bundle.sh`, rerun `scripts/bundle/bundle.sh --check`, and restore
the development symlink layout afterward if you are continuing on `develop`.

## CAD Viewer

A Viewer URL's PATH is the absolute directory it opens, exactly as in a `file://`
URL, and `?file=` selects one artifact within it:

```text
http://127.0.0.1:3245/absolute/model/root?file=path/relative/to/that/root
```

On Windows the drive is part of that path, after the leading slash and with
forward slashes: `D:\project\models` is `.../3245/D:/project/models`.

The Viewer is not started against a directory — it opens whatever a URL names, so
one instance serves any folder **under its own served root**. That qualifier
matters in a worktree: an instance started from another checkout resolves paths
against ITS root, so an absolute path into a different clone is simply not found
and the pane reports it as outside this viewer's root. If a Viewer from another
checkout already holds the default port, start one for this workspace on a free
port (`--port <n>`) rather than pointing the running one at your path.

When reviewing repo fixtures, use the repo
`models/` directory as the path and keep permanent or generated
CAD/robot-description files there so the catalog and artifacts stay in one place.
Always use an absolute path: the Viewer runs from an arbitrary working directory,
so a relative one resolves against the wrong place. Do not stop another Viewer
unless the user asks.

Editing `viewer/` or `packages/cadjs` source and not seeing the change? Vite's
server-side transform cache can outlive both HMR and a hard reload — the browser
keeps serving the old module while the file on disk is already correct. Restart
the dev server and delete `viewer/node_modules/.vite`.

### Dev by default, prod only for e2e

Iterate with the **dev** server — Vite serves the client from source with HMR, so
your `viewer/`, `packages/cadjs`, and `packages/implicitjs` edits show up live:

```bash
npm --prefix viewer run dev -- --host 127.0.0.1 --port <n>
# then open http://127.0.0.1:<port><repo>/models?file=<path>
```

Use the **prod** path only for end-to-end tests against the shipped bundle, or
when explicitly asked to test prod. It serves the built `dist/` via the Python
backend (the `cad-viewer` skill's `start` command), so build first:

```bash
npm --prefix viewer run build
npm --prefix viewer run start -- --host 127.0.0.1 --port <n>
# then open http://127.0.0.1:<port><repo>/models?file=<path>
```

### Ports

Both `dev` and `start` listen on `--port`, defaulting to `3245`. Neither rolls to
another port: if the port is taken they exit with an error, so a Viewer is always
on the port you asked for. Pass `--port <n>` to run more than one at a time.

Packaged Viewer runtime and handoff details live in the `cad-viewer` skill.
Treat packaged Viewer checks as generated-output checks via the master bundle
wrapper unless you are debugging a lower-level script.

### Starting the Viewer from a lightweight worktree

The `cad-viewer` skill documents the PRODUCTION runtime and assumes a hydrated
checkout. In a lightweight worktree its one-liner fails four times in a row, each
with an error that does not name the real cause, because worktrees deliberately
carry no `node_modules` and no built bundle:

1. `npm --prefix skills/cad-viewer/scripts/viewer run start` dies with
   `Cannot find package 'cadjs'`. `skills/cad-viewer/scripts/viewer` is a symlink
   to `viewer/`, so the "packaged" runtime still needs the worktree's modules.
2. With those linked, the server starts and the CAD API answers but `/` returns
   404: `start` serves a prebuilt bundle and there is no `viewer/dist` yet. A live
   backend with no front end looks like a broken link, not a missing build.
3. `npm --prefix viewer run build` then fails one bare specifier at a time —
   `implicitjs`, `three`, `meshoptimizer` — each from `packages/cadjs/src/...`.
4. `meshoptimizer` is not under `packages/cadjs/node_modules` anywhere; the only
   copy in the repo is `docs/node_modules/meshoptimizer`.

From the worktree root, with `<main>` the primary checkout:

```bash
ln -s <main>/viewer/node_modules viewer/node_modules
mkdir -p packages/cadjs/node_modules
ln -s ../../implicitjs                                packages/cadjs/node_modules/implicitjs
ln -s <main>/packages/cadjs/node_modules/three        packages/cadjs/node_modules/three
ln -s <main>/docs/node_modules/meshoptimizer          packages/cadjs/node_modules/meshoptimizer
npm --prefix viewer run build
npm --prefix skills/cad-viewer/scripts/viewer run start -- --host 127.0.0.1 --port <n>
```

Use an explicit free `--port`: a Viewer already running from another checkout
resolves paths against ITS root, so it will never find a model in this worktree.

Two behaviours worth knowing before you conclude a model is broken:

- **The catalog scan skips dot-directories.** A buildable entry under `.review/`
  or any other dotted path resolves by a direct `?dir=` query but never appears
  in a scan from the project root, and the Viewer reports that the file does not
  exist. Keep buildable entries out of dotted directories.
- **Verify a Viewer link by loading the page**, not by curling `/__cad/asset`.
  That route serves raw files; a generated entry's render package is served by a
  different route, so probing it returns 404 whether or not anything is wrong.

## Git And LFS

CAD exchange files, generated render/topology assets, and `assets/**` may be
LFS-tracked. Never disable LFS filters for `git add`, commits, or other
object-writing operations. Local hooks live in `.githooks` and
delegate build checks through `scripts/git-hooks/pre-commit`.
