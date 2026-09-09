# AGENTS.md

This repo is a workbench for CAD-related agent skills. Treat `skills/` as the
product and `models/` as the shared fixture/artifact area.

## Branch First

`main` is the only long-lived branch: the source tree, what installers clone,
and what releases are cut from. Branch from `main` and open PRs against `main`;
never push it directly. There is no development symlink layout — every path in
the tree is the real file.

## Release Workflow

Do not bump the canonical release version in `VERSION` during normal
development work; the `Test` workflow refuses a PR that changes `VERSION` from
any branch but `release/*`. Releases are two GitHub Actions workflows:

- `Prepare Release` (`release-prepare.yml`, manual): opens and merges a release
  PR against `main` that bumps `VERSION`, the derived metadata and every
  skill's `cadgen==` pin together.
- `Publish Release` (`release-publish.yml`): fires on the push that merge makes.
  Bundles, tests, builds the `cadgen` wheel, installs and exercises it, keeps
  the distribution as a workflow artifact, then — on `main` only — uploads to
  PyPI, deploys the docs site, and tags (`v<VERSION>`; releases before 0.5.0
  are bare `0.4.x` tags) + GitHub-Releases that same merged commit.

When asked to publish, make, or ship a release, dispatch `Prepare Release` on
`main`. Never pick the semver bump yourself: if the request does not name patch,
minor, major, or an exact version, ask which one before dispatching. To resume a
run that uploaded the wheel but failed before the tag or the docs deploy, or to
republish the current head, dispatch `Publish Release` on `main` (`publish=false`
leaves the GitHub Release as a draft). `target=build-test` on `Prepare Release`
is the rehearsal — the same PR against `build-test`, whose pushes run `Publish
Release` without PyPI, docs or tag — and is never a release; use it only when the
user explicitly asks to test the pipeline.

The standalone `Deploy Docs` workflow redeploys the docs site from a ref
(default `main`, or a release tag) without running a release.

Skill `requirements.txt` files pin `cadgen==<VERSION>` on `main` itself;
`scripts/release/check-version.sh` asserts every pin equals `VERSION`. A
checkout's editable install reports that same version, so the pin is satisfied
in development too — install `requirements-dev.txt`, never a skill's
`requirements.txt` on its own (that fetches the previous release from PyPI).
`models/` stays on `main` as LFS pointers (`.lfsconfig` excludes it from
default fetches; `.gitattributes` export-ignores it from archives); nothing
installs it. `scripts/github-workflows/check-builds.sh` enforces the shipping
contract on every push: no tracked symlink, no LFS path under `skills/`, no
skill reaching into a repo root. See the Releases section in `CONTRIBUTING.md`
for the full flow, the resume path, the rehearsal, and local/manual fallbacks.

## Repo Map

- `skills/`: agent skills and their references/scripts.
- `.claude-plugin/`, `.codex-plugin/`: agent plugin manifests. The repository
  root is the plugin package; its skills are `skills/` directly.
- `models/`: sample and durable CAD/robot-description fixtures.
- `apps/viewer/`: the CAD Viewer's React client (its backend is `cadgen.viewer`).
- `apps/desktop/`: Hardcore, the Electron desktop shell (Claude/Codex threads beside
  the CAD Viewer). A self-contained pnpm workspace with its own `AGENTS.md`; it
  runs on `apps/viewer`, `packages/cadgen`, `packages/cadgen-js`, and `skills/`
  directly and is never a dependency of the skills.
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
- A skill must not import another skill, a `skills/` root module, or a
  repository-root module, and must not add `skills/`, the repository root, or a
  sibling skill directory to `sys.path`, `PYTHONPATH`, `NODE_PATH`, or any other
  runtime lookup path. Skills are independent of each other, not of everything.
- Shared runtime comes from the **`cadgen` distribution**. A skill that uses it
  names it in its `requirements.txt`, pinned to `VERSION` (the release PR
  stamps every pin; the editable install in `requirements-dev.txt` satisfies
  it in a checkout). Skills do not vendor it: a skill script is a thin entrypoint whose
  parser and behaviour live in `cadgen.cli`, and which fails with the
  `pip install -r requirements.txt` hint when cadgen is missing. cadgen carries
  the JavaScript it executes too (Node builders, the snapshot browser bundle,
  the CAD Viewer client), so a skill ships no runtime of its own. Not every
  skill needs cadgen (bambu-labs, dfam-check, gcode, sendcutsend, step-parts
  are cadgen-free); do not add the dependency to a skill that never invokes it.
- Regenerate derived outputs (`scripts/bundle/bundle.sh`) when a change reaches
  what the bundlers consume; `bundle.sh --check` is the freshness gate.
- Write all test, sample, permanent, and generated CAD/robot-description
  artifacts under `models/`, including STEP/STP, STL, GLB, DXF, URDF, SRDF,
  and SDF outputs. Do not create ad hoc artifact directories elsewhere.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- When source changes affect generated runtimes, refresh or check them with the
  one bundle entry point, `scripts/bundle/bundle.sh`. Call
  `scripts/bundle/cadgen-runtime.sh` directly only when debugging one stage.
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
  kernel action, importing a foreign STEP, is a compile job in cadgen's build
  pool, never work the server process does.
  Keep repo-level tooling in `scripts/`, not under `apps/viewer/`.
- `packages/cadgen-js` must stay reusable/non-React; app UI and workflow state
  belong in `apps/viewer/`. It holds the shared CAD render/runtime code: one package,
  one copy of each shared primitive.
- `packages/cadgen` is the whole distribution, not just the Python: artifact
  generation, the CLI parsers behind every skill command (`cadgen/cli`), the warm
  build daemon (`cadgen/daemon`), and
  the JS/SPA assets it executes (`cadgen/_runtime`, built by
  `scripts/bundle/cadgen-runtime.sh`). Skills consume it as an
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
  - In GitHub Actions, `test.yml` (PRs to and pushes of `main`) checks the
    canonical release version and the skill pins in a separate job so code
    tests still run when version metadata is wrong; its test job checks
    generated outputs against their sources, bundles production outputs, and
    runs docs and code tests against that bundle. `Publish Release` repeats
    those checks on the release commit before the wheel ships. GitHub branch
    settings should require a PR for `main`.
- Focused test runners: `scripts/test/test-js.sh`,
  `scripts/test/test-docs.sh`, `scripts/test/test-python.sh`,
  `scripts/test/test-global.sh`
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

When a task changes what the bundlers consume, run `scripts/bundle/bundle.sh`,
rerun `scripts/bundle/bundle.sh --check`, and commit the regenerated
`_runtime/node` and `_runtime/browser` (`_runtime/viewer` is gitignored).

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
