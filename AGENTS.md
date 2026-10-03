# AGENTS.md

This repo is a workbench for CAD-related agent skills. Treat `skills/` as the
product and `models/` as the shared fixture/artifact area.

## Branch First

`main` is the only branch you develop on: the source tree, what installers
clone, and what releases are cut from. Branch from `main` and open PRs against
`main`; never push it directly. There is no development symlink layout — every
path in the tree is the real file. `plugin`, the plugin claude.ai's directory
follows (and `claude-plugin`, its old name, until claude.ai's listing moves), is
written only by `Publish Release` (see below); never commit to it. `main` stays
an installable plugin too: every manifest and MCP config lives at its root.

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
  are bare `0.4.x` tags) + GitHub-Releases that same merged commit with the
  wheel and sdist that went to PyPI attached as release assets, plus the
  plugin ZIP that a person uploads to OpenAI's plugin portal, which has no API.
  It also commits the plugin alone (Claude, Cursor and Gemini manifests, icon,
  `claude.mcp.json`, `skills/`, `LICENSE`, README) onto the `plugin` branch,
  which claude.ai's plugin directory follows (`scripts/release/plugin_branch.py`).

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

cadgen runs as ONE launch command everywhere, `uvx --no-config --managed-python
--python 3.13 --from cadgen==<VERSION> <tool>` (`cadgen._internal.launch`): the
plugin server configs and every cadgen skill's SKILL.md carry it, the release
stamps every pin (`sync-version.mjs`), and `scripts/release/check-version.sh`
and the tests assert they all equal `VERSION`. uv keeps one installation per
requirement and cadgen names its warm daemon after that installation, so the
server, every thread and every skill command share one daemon. In a checkout,
install `requirements-dev.txt` (the editable cadgen) and test in agent apps with
`scripts/install/dev_install.py`, which points both at the checkout.
`models/` stays on `main` as plain files; nothing installs it.
`scripts/github-workflows/check-builds.sh` enforces the shipping contract on
every push: no tracked symlink, no `.gitattributes` rule that rewrites files at
checkout or changes the archive (so no Git LFS; claude.ai's plugin directory
refuses them), every tracked file under 5 MiB, no skill reaching into a repo root.
See the Releases section in `CONTRIBUTING.md` for the full flow, the resume
path, the rehearsal, and local/manual fallbacks.

## Repo Map

- `skills/`: agent skills and their references/scripts.
- `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `gemini-extension.json`:
  agent plugin manifests. The repository root is the plugin package; its skills are
  `skills/` directly.
- `models/`: sample and durable CAD/robot-description fixtures.
- `apps/web/`: the CAD Viewer's React client (its backend is `cadgen.viewer`).
- `apps/mcp/`: the CAD app agent hosts render: tabs in Codex, cards in Claude Desktop (its server is `cadgen mcp`).
- `packages/core`: `@text-to-cad/core`, shared CAD/runtime/client code without React.
- `packages/ui`: `@text-to-cad/ui`, the shared FileViewer, renderers, controls and styles.
- `packages/cadgen`: the published distribution — STEP/GLB/topology generation,
  the skill CLI parsers, the CAD Viewer backend + client, and the Node/browser
  runtimes it executes.
- `apps/docs/`: documentation site, and `api.texttocad.dev` (the CAD app's consented analytics).
- `tests/`: root-owned test suites for skills, packages, viewer services, and
  repo-wide policy.
- `scripts/`: durable repo commands grouped by purpose.

## Repo Rules

- Boundaries and design laws live in each package's README: read
  `packages/cadgen/README.md` (the laws), `packages/core/README.md`, `packages/ui/README.md`,
  `apps/web/README.md`, and `apps/docs/README.md` before changing
  generation, rendering, storage, layout, or public interfaces.
- A README holds the laws; the mechanism each law constrains lives one link
  away, and the README names the link. Read the README, then follow the one
  link — not the tree. What exists:
  - `packages/cadgen/`: `STORE.md` (the store contract — sectioned, with a
    table of contents), `SNAPSHOTS.md` (snapshot `--debug` timings).
  - `packages/core/docs/`: `render-pipeline.md`, `resource-ownership.md`,
    `tube-deformation.md`.
  - `packages/ui/docs/`: `settings-ui.md` (BINDING for any settings control),
    `render-types.md`, `render-mode.md`, `lod.md`, `storage.md`, `backend.md`.
- Ships-alone law: `packages/cadgen` (the built PyPI wheel) works in isolation
  outside this repo, so its markdown must not refer to anything outside the
  package — enforced by `tests/python/global/test_package_boundaries.py`.
  Repo-development guidance for it goes in `CONTRIBUTING.md`.

- The README and the docs site's homepage (its copy: `apps/docs/src/lib/content.ts`)
  are one copy: change them together. `apps/docs/README.md` says where they may differ.
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
  defines `cadgen` and `python` in its SKILL.md as the launch command above,
  pinned to `VERSION` (the release stamps every pin); no skill installs cadgen
  any other way (no `requirements.txt` naming it), because a second installation
  is a second daemon. Skills do not vendor it: a skill script is a thin entrypoint whose
  parser and behaviour live in `cadgen.cli`. Playwright is a cadgen dependency and
  the first snapshot fetches its headless browser, so no skill has a browser step. cadgen carries
  the JavaScript it executes too (Node builders, the snapshot browser bundle,
  the CAD Viewer client), so a skill ships no runtime of its own. Not every
  skill needs cadgen (bambu-labs, cad-mcp-setup, dfam-check, dfm, gcode,
  sendcutsend, step-parts are cadgen-free); do not add the dependency to a skill that never invokes it.
- Keep samples and manual CAD/robot-description validation artifacts under
  `models/`. Automated tests must not read, build or import that sample corpus:
  generate small fixtures in fresh temporary directories or use tiny test-owned
  fixtures, with their own cache stores and cleanup. Repo `tmp/` is fine.
  Enforced by `tests/python/global/test_tests_are_self_contained.py`.
- Every test runs in CI. Each test file is reached by a runner under
  `scripts/test/`, every runner is called by a `test.yml` job on the changes that
  can break it, and a collector that finds nothing fails the run rather than
  reporting a group that never ran. A test no CI job runs is dead: wire it in or
  delete it. There are no manual-only test gates. Enforced by
  `tests/python/global/test_ci_workspace_selection.py`.
- Tests and CI are short and succinct. Test a contract, a user flow or a fixed bug,
  once, at the cheapest level that exercises the real path: a unit or jsdom test
  first, a real browser (WebGL) only for what needs one. Await the condition, never
  a fixed sleep or a wall-clock bound; a flaky test is fixed or deleted, never
  retried. CI time is a budget: the `web` job stays within 7 minutes, and a
  change that lengthens any job says what it costs and why in its PR.
- Benchmarks under `scripts/bench/` are manual and their output is never
  committed: reports, logs, profiles and screenshots go to an ignored `tmp/`.
  Only their pure helper units run in a test runner.
- The Python floor is `requires-python` in `packages/cadgen/pyproject.toml` and
  nowhere else. Every cadgen source is parsed against that floor, so syntax
  newer than it fails here rather than at `pip install` time on a user's
  interpreter; raising the declared minimum relaxes the check automatically.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- cadgen's packaged runtime (`_runtime/node`, `_runtime/browser`,
  `_runtime/viewer`, and the file tracer every build loads, `_runtime/native`)
  is BUILT, never committed: the whole directory is
  gitignored and ships only inside the wheel. Build it with the one bundle
  entry point, `scripts/bundle/bundle.sh`; `bundle.sh --check` builds it and
  asserts every required output. Call `scripts/bundle/cadgen-runtime.sh`
  directly only when debugging one stage.
- Never let a symlink reach the published tree. Agent installers disagree about
  symlinks and one loses data silently: the Skills CLI dereferences them, Claude
  Code preserves them, and Codex `plugin add` drops them with no error, shipping
  a skill with missing files. `scripts/github-workflows/check-builds.sh` enforces
  this; do not relax it.
- The CAD Viewer is `cadgen viewer`: the server is `cadgen.viewer` (Python, in
  `packages/cadgen`), the React client's source is `apps/web/` and its build
  ships in the wheel at `cadgen/_runtime/viewer` (built, never committed; a
  checkout serves `apps/web/dist`). The CAD, DXF and robot-description skills document that verb directly.
  Nothing in `cadgen.viewer` imports the CAD kernel at module scope — the one
  kernel action, importing a foreign STEP, is a compile job in cadgen's build
  pool, never work the server process does.
  Keep repo-level tooling in `scripts/`, not under `apps/web/`.
- `packages/core` stays non-React. Shared FileViewer/renderers belong in
  `packages/ui`; host workflow state belongs in apps. Apps never import another
  app and shared packages never import apps. Root npm workspaces consume compiled
  package exports; do not add source aliases or nested lockfiles. Preserve app
  UI/UX and functionality during restructuring; changes are pure refactors.
- Shared UI must stay platform-agnostic. Apps implement environmental effects;
  shared features use injected capabilities and named extension slots. Before
  extending these interfaces, read [the viewer host contract](packages/ui/docs/viewer-host.md).
- `packages/cadgen` is the whole distribution, not just the Python: artifact
  generation, the CLI parsers behind every skill command (`cadgen/cli`), the warm
  build daemon (`cadgen/daemon`), and
  the JS/SPA assets it executes (`cadgen/_runtime`, built by
  `scripts/bundle/cadgen-runtime.sh`). Skills consume it as an
  installed distribution.
- Create lightweight shared Python packages under `packages/` when a helper
  should not inherit heavier package dependencies.
- Use path-targeted search, validation, and `git status`; avoid broad scans over
  generated CAD artifacts unless the task requires them.
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
  skills or plugins from another checkout.
- Test skills and the plugin in an agent app with
  `scripts/install/dev_install.py <host>` (`CONTRIBUTING.md`, "Test In Agent
  Apps"). One copy of the plugin per app: never the development install beside
  the published plugin, or beside the skills installed loose.
- Install dependencies only for the workflow being changed.
- Do not commit `.venv/`, `node_modules/`, caches, `tmp/`, local credentials, or
  printer config.

## Checks

Run the smallest path-targeted check that covers the change. Use broad wrappers
when touching shared surfaces or before handoff:

- Code tests: `scripts/test/test.sh` (JS, then Python, then policy).
- Focused runners: `scripts/test/test-js.sh`, `scripts/test/test-docs.sh`,
  `scripts/test/test-python.sh`, `scripts/test/test-global.sh`.
  `test-python.sh` takes `--select cadgen|viewer|skills|all` and
  `--print-weights`; `test-js.sh` takes `--select core|ui|web|mcp|all`. See
  `scripts/README.md`.
- In GitHub Actions, `test.yml` runs one conditional job per concern. The graph,
  stable required check names and workspace install recipes are in
  `CONTRIBUTING.md#ci`. Core changes reach all consumers; UI reaches web; app
  changes do not run unrelated apps. Manual dispatch runs all jobs.
- Canonical release version: `scripts/release/check-version.sh`
- Packaged runtime builds and is complete: `scripts/bundle/bundle.sh --check`
- CAD Viewer or shared packages: build exports with `npm run build:packages`,
  then `npm --prefix packages/core test`, `npm --prefix packages/ui test`,
  `npm --prefix apps/web run test`, `npm --prefix apps/web run build`.
  The Viewer is two languages and `npm run test` covers only the client — the
  backend's suite is `tests/python/packages/cadgen/viewer`, run by
  `scripts/test/test-python.sh`. Touching `cadgen/viewer/` means running that.
- Docs site: `npm --prefix apps/docs run check`
- Targeted Python tests: `./.venv/bin/python -m unittest <changed test paths>`

When a task changes what the bundlers consume, run `scripts/bundle/bundle.sh`
and confirm the change lands in the built runtime. There is nothing to commit:
`_runtime/` is gitignored end to end, so what a reviewer reads is the source and
what a user gets is the wheel the release builds from it.

## CAD Viewer

The app-facing playbook lives in `apps/web/README.md`: launcher contract
(reuse, ports, `--new`), dev vs prod, and the catalog/link-verification
gotchas. The repo-side half — the lightweight-worktree recipe and
root workspace dependencies — lives in `CONTRIBUTING.md` under "Viewer Development
In This Repo". Read them before starting, stopping, or debugging a Viewer.
Never stop an instance you did not start; packaged-runtime checks go
through `scripts/bundle/bundle.sh`.

## Git

No Git LFS, and every file under 5 MiB: the repository root is the plugin, and
claude.ai's plugin directory refuses files a filter rewrites at checkout, so
heavyweight media stays out of the tree. Local hooks live in `.githooks` and
delegate build checks through `scripts/git-hooks/pre-commit`.
