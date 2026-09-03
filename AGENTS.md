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
release. It deploys a source ref (defaulting to `develop`), not `main`: the site
is built from the commit a release was cut from.
`main` is `develop` with the skill bundles materialized, versions stamped, skill
requirements pinned, and ONLY `models/` removed — `apps/`, `packages/`, and
`tests/` ship (source discoverability), and `packages/` being present is not
permission for a skill to import from it; `scripts/github-workflows/check-publish-tree.sh`
enforces the contract (no symlink, no LFS path outside `assets/`, no skill
reaching into a repo root) before the publish commit.
The CAD Viewer is a local-filesystem app with no hosted deployment: the
cad-viewer skill bundles the built client + Python server, and each release mirrors
`apps/viewer/` into the standalone `earthtojake/cad-viewer` repo through the
`Sync CAD Viewer Repo` workflow (which `Release` calls after publishing and which
can also be dispatched on its own; it reads the release SOURCE commit, because
`main` carries only what installs). `Deploy Docs` also reads the release SOURCE
commit.
`main` is publish-only; pushing `develop` runs tests but
never publishes. See the Releases section in `CONTRIBUTING.md` for the full
flow, CI/CD-testing and resume options, and local/manual fallbacks.

## Repo Map

- `skills/`: agent skills and their references/scripts.
- `.claude-plugin/`, `.codex-plugin/`: agent plugin manifests. The repository
  root is the plugin package; its skills are `skills/` directly.
- `models/`: sample and durable CAD/robot-description fixtures.
- `apps/viewer/`: the CAD Viewer's React client (its backend is `cadgen.viewer`).
- `packages/cadgen-js`: shared JS CAD/render/runtime code, UI-framework agnostic.
- `packages/cadgen`: the published distribution — STEP/GLB/topology generation,
  the skill CLI parsers, the CAD Viewer backend + client, and the Node/browser
  runtimes it executes.
- `apps/docs/`: documentation site.
- `tests/`: root-owned test suites for skills, packages, viewer services, and
  repo-wide policy.
- `scripts/`: durable repo commands grouped by purpose.

## Repo Rules

- Boundaries and design laws live in each package's README: read
  `packages/cadgen/README.md` (the laws), `packages/cadgen-js/README.md`,
  `apps/viewer/README.md`, and `apps/docs/README.md` before changing
  generation, rendering, storage, layout, or public interfaces.
- Ships-alone law: `packages/cadgen` (the built PyPI wheel) works in isolation
  outside this repo, so its markdown must not refer to anything outside the
  package — enforced by `tests/python/global/test_package_boundaries.py`.
  Repo-development guidance for it goes in `CONTRIBUTING.md`.

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
- A skill must not import another skill, a `skills/` root module, or a
  repository-root module, and must not add `skills/`, the repository root, or a
  sibling skill directory to `sys.path`, `PYTHONPATH`, `NODE_PATH`, or any other
  runtime lookup path. Skills are independent of each other, not of everything.
- Shared runtime comes from the **`cadgen` distribution**. A skill that uses it
  names it in its `requirements.txt` — unpinned on `develop` so the editable
  install in `requirements-dev.txt` satisfies it, pinned to the release at
  publish. Skills do not vendor it: a skill script is a thin entrypoint whose
  parser and behaviour live in `cadgen.cli`, and which fails with the
  `pip install -r requirements.txt` hint when cadgen is missing. cadgen carries
  the JavaScript it executes too (Node builders, the snapshot browser bundle,
  the CAD Viewer client), so a skill ships no runtime of its own. Not every
  skill needs cadgen (bambu-labs, dfam-check, gcode, sendcutsend, step-parts
  are cadgen-free); do not add the dependency to a skill that never invokes it.
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
- The CAD Viewer is `cadgen viewer`: the server is `cadgen.viewer` (Python, in
  `packages/cadgen`), the React client's source is `apps/viewer/` and its build
  ships in the wheel at `cadgen/_runtime/viewer` (gitignored; a checkout serves
  `apps/viewer/dist`). The cad-viewer skill is instructions over that verb.
  Nothing in `cadgen.viewer` imports the CAD kernel at module scope — the one
  kernel action, importing a foreign STEP, runs in a worker the server owns.
  Keep repo-level tooling in `scripts/`, not under `apps/viewer/`.
- `packages/cadgen-js` must stay reusable/non-React; app UI and workflow state
  belong in `apps/viewer/`. It holds the shared CAD render/runtime code: one package,
  one copy of each shared primitive.
- `packages/cadgen` is the whole distribution, not just the Python: artifact
  generation, the CLI parsers behind every skill command (`cadgen/cli`), the warm
  build daemon (`cadgen/daemon`), and
  the JS/SPA assets it executes (`cadgen/_runtime`, built by
  `scripts/bundle/skills/bundle-cadgen-runtime.sh`). Skills consume it as an
  installed distribution.
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
- CAD Viewer or `packages/cadgen-js`:
  `npm --prefix packages/cadgen-js test`,
  `npm --prefix apps/viewer run test`, `npm --prefix apps/viewer run build`.
  The Viewer is two languages and `npm run test` covers only the client — the
  backend's suite is `tests/python/packages/cadgen/viewer`, run by
  `scripts/test/test-python.sh`. Touching `cadgen/viewer/` means running that.
- Docs site: `npm --prefix apps/docs run check`
- Targeted Python tests: `./.venv/bin/python -m unittest <changed test paths>`

When a task intentionally writes production outputs locally, run
`scripts/bundle/bundle.sh`, rerun `scripts/bundle/bundle.sh --check`, and restore
the development symlink layout afterward if you are continuing on `develop`.

## CAD Viewer

The app-facing playbook lives in `apps/viewer/README.md`: launcher contract
(reuse, ports, `--new`), dev vs prod, and the catalog/link-verification
gotchas. The repo-side half — the lightweight-worktree recipe and
node_modules linking — lives in `CONTRIBUTING.md` under "Viewer Development
In This Repo". Read them before starting, stopping, or debugging a Viewer.
Never stop an instance you did not start; packaged-runtime checks go
through `scripts/bundle/bundle.sh`.

## Git And LFS

CAD exchange files, generated render/topology assets, and `assets/**` may be
LFS-tracked. Never disable LFS filters for `git add`, commits, or other
object-writing operations. Local hooks live in `.githooks` and
delegate build checks through `scripts/git-hooks/pre-commit`.
