# AGENTS.md

This repo is a workbench for CAD-related agent skills. Treat `skills/` as the
product and `models/` as the shared fixture/artifact area.

## Repo Map

- `skills/`: agent skills and their references/scripts.
- `plugins/`: versioned agent plugin packages that bundle repo skills.
- `models/`: sample and durable CAD/robot-description fixtures.
- `viewer/`: editable CAD Viewer source app.
- `packages/cadjs`: shared JS CAD/render/runtime code, UI-framework agnostic.
- `packages/cadpy`: shared Python STEP/GLB/topology artifact code.
- `packages/cadpy_metadata`: dependency-free Python metadata helpers vendored
  into generated URDF/SRDF/SDF skill runtimes.
- `docs/`: documentation site.
- `scripts/`: durable repo commands grouped by purpose, with compatibility
  wrappers at the top level.

## Repo Rules

- Keep root guidance short. Put domain workflows, CLI details, and validation policy in the relevant `skills/<skill>/SKILL.md` or `references/` file.
- Keep relevant Markdown docs current when changing behavior, commands, or repo
  layout, but do not bloat `AGENTS.md`; use it only for durable repo-level
  rules and pointers.
- Read `COMMIT.md` before committing, rebasing, resolving generated-file
  conflicts, or bumping release versions.
- Before committing release metadata for a PR, fetch the base branch and ensure
  the branch version is greater than the latest base version; use `COMMIT.md`
  for the exact workflow.
- Each skill must be self-contained and independent at runtime. A skill must
  not refer to or import or depend on code from another skill, from `skills/` root, or from
  repository-root modules. Do not add `skills/`, the repository root, or sibling
  skill directories to `sys.path`, `PYTHONPATH`, `NODE_PATH`, or similar runtime
  lookup paths. Shared runtime helpers must live under `packages/` as the source
  of truth and be vendored/generated from there into each consuming skill
  runtime; do not keep shared helper modules directly under `skills/`.
- Edit sources first, then regenerate explicit derived outputs. Do not hand-edit generated skill runtimes or bundled package copies.
- Write all test, sample, permanent, and generated CAD/robot-description
  artifacts under `models/`, including STEP/STP, STL, GLB, DXF, URDF, SRDF,
  SDF, and G-code outputs. Do not create ad hoc artifact directories elsewhere.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- `viewer/`, `packages` are the source of truth for CAD Viewer and shared CAD runtime behavior. Duplicate files under skills such as `skills/cad-viewer/scripts/viewer`, `skills/cad-viewer/scripts/packages/`, `skills/cad/scripts/packages/`, and snapshot runtimes are generated copies that should not be edited.
- When changing skill behavior that uses `packages/cadjs`, `packages/cadpy`, or `skills/cad-viewer/scripts/viewer`, edit the root source in `packages/*` or `viewer/*`, then rebuild the generated skill copies. Never patch the copies as the lasting fix.
- `plugins/cad/skills/` is a generated, materialized plugin package copy of
  the root `skills/` sources. Edit `skills/*` first, then run
  `scripts/build/build-plugin.sh` to refresh the plugin copy; do not hand-edit
  plugin skill copies.
- `viewer/packages/*` contains generated viewer-local package copies for
  standalone viewer deployments. Edit `packages/*` first, then run
  `scripts/build/build-viewer.sh` to refresh the copies.
- `packages/cadjs` must stay reusable/non-React; app UI and workflow state belong in `viewer/`.
- `packages/cadpy` owns reusable Python artifact generation; skills should use bundled package code, not sibling skill imports.
- Create new packages like `packages/cadpy_metadata` when it doesn't make sense to bundle heavy requirements of other cadpy skills (prefix new packages with `cadpy_*`).
- Use path-targeted search, validation, and `git status`; avoid broad scans over generated CAD/LFS artifacts unless the task requires them.
- Keep release versioning in lockstep: the git tag, plugin manifests and
  `plugins/*/VERSION`, package manifests/locks, Python `pyproject.toml` files,
  and any other repo-owned release version numbers should all match. The
  current release version is `0.1.12`. Use `scripts/release/bump-version.sh`
  for version bumps as described in `COMMIT.md`.

## Environments

- Prefer `./.venv/bin/python` for CAD Python work.
- Install dependencies only for the workflow being changed.
- Do not commit `.venv/`, `node_modules/`, caches, `tmp/`, local credentials, or
  printer config.

## Checks

Run the smallest path-targeted check that covers the change. Use broad wrappers
when touching shared surfaces or before handoff:

- Full repo validation: `scripts/test.sh`
- All generated runtime freshness: `scripts/build.sh --check`
- CAD skill or `packages/cadpy`: `scripts/build/build-cad-skill.sh --check`
- Root Viewer package copies: `scripts/build/build-viewer.sh --check`
- CAD Viewer or `packages/cadjs`: `npm --prefix packages/cadjs test`, `npm --prefix viewer run test`, `npm --prefix viewer run build`, `scripts/build/build-cad-viewer-skill.sh --check`
- URDF/SRDF/SDF `cadpy_metadata` runtimes: `scripts/build/build-urdf-skill.sh --check`, `scripts/build/build-srdf-skill.sh --check`, `scripts/build/build-sdf-skill.sh --check`
- Plugin packages: `scripts/build/build-plugin.sh --check`, then
  `scripts/check/validate-plugins.sh`
- Docs site: `npm --prefix docs run check`
- Python skill scripts: `./.venv/bin/python -m pytest <changed test paths>`

When changing generated outputs, run the matching build script without
`--check`, then rerun it with `--check`.

## CAD Viewer

When reviewing repo fixtures in CAD Viewer, point the Viewer at the repo
`models/` directory with an absolute `?dir=` path; keep any permanent or
generated CAD/robot-description files in `models/` so the viewer catalog and
artifacts stay in one place.

For root dev-server iteration, use the URL printed by Viewer commands; do not
assume a fixed dev port unless you pass Vite's standard `--port` flag.

When modifying Viewer behavior, always run the root source app in dev mode for iteration;
do not run the generated viewer from the cad-viewer skill while developing.

```bash
npm --prefix viewer run dev -- --host 127.0.0.1
```

For packaged skill runtime review:

```bash
npm --prefix skills/cad-viewer/scripts/viewer run serve -- --host 127.0.0.1 --port 4178 --shutdown-after 12h
```

For cad-viewer skill handoffs, probe port `4178` first and reuse it when
`/__cad/server` reports `app: "cad-viewer"`, `dynamicRoot: true`, and
`serverApiVersion >= 2`; use `viewerVersion` in that response to sanity-check
the running build. If a legacy root-bound Viewer or non-Viewer process occupies
the port, try the next port. Return links with an absolute `?dir=` on every URL
and an absolute `?file=...` for each requested file.

## Git And LFS

CAD exchange files, generated render/topology assets, `assets/**`, and
`benchmarks/**` may be LFS-tracked. Never disable LFS filters for `git add`,
commits, or other object-writing operations. Local hooks live in `.githooks` and
delegate build checks through `scripts/git-hooks/pre-commit`.
