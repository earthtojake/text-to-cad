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

Do not bump the canonical release version in `plugins/cad/VERSION` during
normal development work. Ship releases only through the single `Release`
GitHub Actions workflow, which handles the version bump, release PR, publish
commit to `main`, models upload, web-app deploys, semver tag, and GitHub
Release in one run.

When asked to publish, make, or ship a release, dispatch `Release` with its
defaults: build from `develop` (`base_branch=develop`), publish to `main`
(`target_branch=main`), and publish the GitHub Release (`publish=true`, not a
draft). Never pick the semver bump yourself: if the request does not name
patch, minor, major, or an exact version, ask which one before dispatching.
Use `target_branch=build-test` only when the user explicitly asks to test
CI/CD or build-pipeline changes — never by default and never as part of a
requested release. Rerun `Release` with `set_version` pinned to the current
version to resume a failed publish.

The standalone `Deploy Docs` and `Deploy Viewer` workflows redeploy the
individual web apps from `main`, and the standalone `Upload Models` workflow
uploads the `models/` catalog to Vercel Blob from `develop`, all without
running a release. `main` is publish-only; pushing `develop` runs tests but
never publishes. See the Releases section in `CONTRIBUTING.md` for the full
flow, CI/CD-testing and resume options, and local/manual fallbacks.

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

- Prefer `./.venv/bin/python` for CAD Python work (`.venv/Scripts/python.exe`
  on Windows).
- Cross-platform Python dependencies: PyBullet publishes Linux wheels only;
  on Windows/macOS build it from source, use WSL2, or follow the MuJoCo
  alternative documented in the `sim-test` skill. trimesh, MuJoCo, and
  build123d ship wheels for all three OSes. Engine-dependent tests should
  skip via `pytest.importorskip` so suites collect everywhere.
- Windows checkouts: enable Developer Mode (or run an elevated shell) and
  set `git config core.symlinks true` before cloning, so the `develop`
  symlink layout materializes as real symlinks instead of copies.
  `scripts/bundle/bundle.sh` also needs `rsync`, which Git Bash lacks;
  production bundles are built by CI on Linux, so local Windows development
  does not need it.
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
  - In GitHub Actions, `test.yml` checks the canonical release version as a
    separate non-blocking job; its test job verifies the `develop` symlink
    layout, bundles temporary production outputs, and runs docs and code tests
    against that bundle. `main` writes are validated by the `Release`
    workflow's publish job; GitHub branch settings should block PRs and direct
    pushes to `main`.
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

## Part QA Loop

Part-generation tasks follow a clarify → design → generate → test → review
loop, using the `mesh-qa` and `sim-test` skills as tool guides. Those skills
document APIs and reference values only; the agent running the task decides
which checks are meaningful for each part.

- Clarify: ask one short question only when a request is ambiguous on
  fit-critical, material, or motion requirements. Otherwise proceed with a
  reasonable assumption and state it.
- Design note: for complex or moving parts, write a short design note (part
  purpose, critical tolerances, which QA skills look relevant) before CAD
  generation. Simple static parts may skip this step.
- Generate: produce the part with the `cad` skill, keeping artifacts under
  `models/` per the artifact rules above.
- Test: decide which of `mesh-qa`, `sim-test`, and `gcode` apply, and write
  pytest files under `tests/generated/<part-name>/`. Assert against design
  intent with stated threshold bases, not against current measurements.
  Commit the generated tests; they are durable regression artifacts and are
  kept separate from the repo-owned suites in `tests/python/`.
- Iterate: run the tests, read failures, fix the CAD source, and retry. Stop
  after 3 attempts; when the budget is exhausted, report the current state
  and remaining failures and ask the user for direction.
- Review: after all tests pass, review the part and the tests against the
  design note (missed requirements, superficial assertions) and present a
  short review summary to the user.
- Log: keep `tests/generated/<part-name>/iteration-log.md` current per
  iteration — what passed or failed, what changed, and the review outcome.

This loop does not conflict with the `cad-viewer` skill: visual verification
and automated test verification are separate, complementary layers.

## Git And LFS

CAD exchange files, generated render/topology assets, `assets/**`, and
`benchmarks/**` may be LFS-tracked. Never disable LFS filters for `git add`,
commits, or other object-writing operations. Local hooks live in `.githooks` and
delegate build checks through `scripts/git-hooks/pre-commit`.
