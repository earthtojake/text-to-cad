# AGENTS.md

This repo is a workbench for CAD-related agent skills. Treat `skills/` as the
product and `models/` as the shared fixture/artifact area.

## Branch And Layout First

Before changing code, branch from `develop`, not `main`; PRs should target `develop`.
Do not start development work from `main`. The `develop` branch intentionally uses
symlinks across generated runtime, viewer-local package, and plugin package
paths. When a path is symlinked, follow the link and edit the source target.
Use `main` as the production clone/release branch only. `main` is publish-only:
do not open PRs to `main` or push it directly.

## Release Workflow

Normal development work targets `develop` and should not bump the canonical release
version in `plugins/cad/VERSION`. To start a release, run the `Prepare Release`
workflow with `base_branch=develop`; it creates a `release/<version>` branch,
updates `plugins/cad/VERSION` and derived version metadata, and opens a PR back
to `develop`. The `Test` workflow checks version metadata and runs a production
bundle job on `develop` and PRs to `develop`, so production-output issues are
caught before publishing. After a release PR merges, run `Publish` manually from
the `develop` workflow ref with `source_ref=develop`; it ships only when the
source version is newer than `main` and the latest semver tag, bundles real
generated outputs, validates and tests that production layout, writes the
publish merge commit on top of the previous publish target with the release
source as the second parent for release-note attribution, creates the semver git
tag, and opens a draft GitHub Release. Use `target_branch=main` only for a real
release and `target_branch=build-test` for publish rehearsals. Pushing
`develop` runs tests but does not publish `main`.
Use `scripts/release/bump-version.sh` and
`scripts/release/publish-github-release.sh` only as local/manual fallbacks for
the GitHub workflows.

## Repo Map

- `skills/`: agent skills and their references/scripts.
- `plugins/`: versioned agent plugin packages that bundle repo skills.
- `models/`: sample and durable CAD/robot-description fixtures.
- `viewer/`: editable CAD Viewer source app.
- `packages/cadjs`: shared JS CAD/render/runtime code, UI-framework agnostic.
- `packages/implicitjs`: standalone JS implicit CAD model, shader render,
  snapshot, mesh sampling, and export runtime.
- `packages/cadpy`: shared Python STEP/GLB/topology artifact code.
- `packages/cadpy_metadata`: dependency-free Python metadata helpers vendored
  into generated URDF/SRDF/SDF skill runtimes.
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
- Keep the `develop` checkout in symlink layout with
  `scripts/dev/setup-symlinks.sh`.
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
  SDF, and G-code outputs. Do not create ad hoc artifact directories elsewhere.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- Development symlinks mark generated or copied paths. If a file is under a
  symlinked runtime, viewer package, or plugin package path, edit the symlink
  target/source path instead of treating the copy as independent.
- When source changes affect generated runtimes or plugin packages, refresh or
  check them with the master bundle wrapper, `scripts/bundle/bundle.sh`. Use
  lower-level bundle scripts only when debugging the wrapper itself.
- `packages/cadjs` must stay reusable/non-React; app UI and workflow state
  belong in `viewer/`.
- `packages/implicitjs` must stay reusable/non-React and independent of
  `packages/cadjs`; CAD Viewer and snapshot tools should consume its shared
  render/export APIs instead of duplicating implicit CAD logic.
- `packages/cadpy` owns reusable Python artifact generation; skills should use
  bundled package code, not sibling skill imports.
- Create lightweight shared Python packages under `packages/cadpy_*` when a
  helper should not inherit heavier package dependencies.
- Use path-targeted search, validation, and `git status`; avoid broad scans over
  generated CAD/LFS artifacts unless the task requires them.
- Treat `plugins/cad/VERSION` as the canonical release version. Do not hand-edit
  duplicate package, plugin, lockfile, or Python `pyproject.toml` versions;
  release preparation and `scripts/bundle/bundle.sh` stamp them from the
  canonical version.

## Environments

- Prefer `./.venv/bin/python` for CAD Python work.
- When creating a new branch checkout or git worktree for CAD work, copy the
  installed `.venv/` from the source checkout into the new checkout as a
  bootstrap cache, then run the branch's dependency install/sync for the
  workflow being changed so dependency changes are reconciled locally.
- Install dependencies only for the workflow being changed.
- Do not commit `.venv/`, `node_modules/`, caches, `tmp/`, local credentials, or
  printer config.

## Checks

Run the smallest path-targeted check that covers the change. Use broad wrappers
when touching shared surfaces or before handoff:

- Code tests: `scripts/test/test.sh`
  - In GitHub Actions, `test.yml` checks the canonical release version as a
    separate non-blocking job, verifies the `develop` symlink layout on `develop`,
    and runs a temporary production bundle check plus docs checks for `develop`.
    `main` writes are validated by `publish.yml`; GitHub branch settings should
    block PRs and direct pushes to `main`.
- Focused test runners: `scripts/test/test-js.sh`,
  `scripts/test/test-docs.sh`, `scripts/test/test-python.sh`,
  `scripts/test/test-global.sh`
- Development symlink layout: `scripts/dev/setup-symlinks.sh --check`
- Canonical release version: `scripts/release/check-version.sh`
- Generated runtime and plugin freshness: `scripts/bundle/bundle.sh --check`
- CAD Viewer, `packages/cadjs`, or `packages/implicitjs`:
  `npm --prefix packages/cadjs test`, `npm --prefix packages/implicitjs test`,
  `npm --prefix viewer run test`, `npm --prefix viewer run build`
- Docs site: `npm --prefix docs run check`
- Targeted Python tests: `./.venv/bin/python -m unittest <changed test paths>`

When a task intentionally writes production outputs locally, run
`scripts/bundle/bundle.sh`, rerun `scripts/bundle/bundle.sh --check`, and restore
the development symlink layout afterward if you are continuing on `develop`.

## CAD Viewer

When reviewing repo fixtures in CAD Viewer, point the Viewer at the repo
`models/` directory with an absolute `?dir=` path; keep any permanent or
generated CAD/robot-description files in `models/` so the viewer catalog and
artifacts stay in one place.

Start or reuse the Viewer through the `cad-viewer` skill launcher and use the
base URL it prints. The launcher owns port selection, reuses a compatible live
Viewer for the same worktree/branch, and uses the source app in Vite dev mode
when the skill viewer path is a development symlink.

Run from `skills/cad-viewer`:

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --shutdown-after 12h
```

Every returned Viewer URL must include `?dir=<absolute-model-root>`, commonly
`<repo>/models`, and `file=<path>` values must be relative to `?dir=`. Do not
manually choose or increment ports, do not rely on session-storage `?dir=`
fallbacks, and do not stop an existing Viewer server unless the user asks.

Packaged Viewer runtime and handoff details belong in the `cad-viewer` skill
instructions. Treat packaged Viewer checks as generated-output checks and use
the master bundle wrapper unless you are debugging a lower-level script.

## Git And LFS

CAD exchange files, generated render/topology assets, `assets/**`, and
`benchmarks/**` may be LFS-tracked. Never disable LFS filters for `git add`,
commits, or other object-writing operations. Local hooks live in `.githooks` and
delegate build checks through `scripts/git-hooks/pre-commit`.
