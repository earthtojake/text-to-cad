# AGENTS.md

Installing text-to-cad rather than developing it? Follow the Quickstart in
[README.md](README.md).

This repo is a workbench for CAD-related agent skills. Treat `skills/` as the
product and `models/` as the shared fixture/artifact area. Read this file, then
[CONTRIBUTING.md](CONTRIBUTING.md) for the workflows it points at; every other
document is one link from the README of the tree it belongs to (Repo Map).

## Branch First

`main` is the only branch you develop on: the source tree, and what releases
are cut from. Branch from `main` and open PRs against `main`; never push it
directly. There is no development symlink layout — every path in the tree is the
real file. Installers follow `latest`, and claude.ai's directory
`claude-plugin`: the plugin alone, one commit per release,
written only by `Publish Release` once the release is on PyPI (see below); never
commit to them. `main` stays an installable plugin too: every manifest and MCP
config lives at its root.

## Release Workflow

A pull request that changes `VERSION` is a release, and merging it releases it.
Never bump during normal development work, and never pick the bump yourself: if
a request to make or ship a release does not name patch, minor, major, or an
exact version, ask which one. A release pull request comes one of two ways:

- **Its own pull request**, for a release of what `main` already has — what
  "make a release" means unless the user names a pull request to carry it:
  dispatch `Prepare Release`
  (`gh workflow run release-prepare.yml --ref main -f bump=<patch|minor|major>`,
  or `-f set_version=X.Y.Z`). It opens `release/X.Y.Z` with the bump and never
  merges it.
- **On the pull request that should carry it**: on its branch,
  `scripts/release/bump-version.sh <patch|minor|major|X.Y.Z>` sets `VERSION` past
  `main`'s and stamps the derived metadata and every pin of the release's own
  (`cad==`, `cad-server==`, `cad-mcp==`) with it.

Merge a release pull request only on the user's explicit word, once its checks
pass: the merge is the release. `Test` runs every job for a `VERSION` change, and
its Version Check vets the bump (a branch of this repository only, a version past
`main`'s and the latest tag, every stamp in step). `Publish Release`
(`release-publish.yml`) runs on the merge: it builds the plugin ZIP, the bundle
and the wheel and sdist of each of the release's four projects on PyPI (`cad`,
`cad-server`, `cad-mcp`, and the alias `cadgen`), uploads
them one project at a time, the library first, waiting until PyPI lists each,
and only then writes the install branches (`latest`, `claude-plugin`), deploys
the docs site, tags `v<VERSION>` and publishes the GitHub Release. A run that
stopped partway is finished by dispatching `Publish Release` on `main`;
`build-test` is the rehearsal branch, used only when the user asks to test the
pipeline; the standalone `Deploy Docs` workflow redeploys the docs site from a
ref without a release. The full flow, the resume path, the rehearsal and the
local fallbacks are [CONTRIBUTING.md's Releases](CONTRIBUTING.md#releases).

People install text-to-cad with one command, `curl -fsSL https://texttocad.dev/install.sh | sh`
(Windows: `irm https://www.texttocad.dev/install.ps1 | iex`): the bootstrap in
`scripts/install/` runs the newest release's `cad setup` through uvx
(`--from cad-server==<VERSION>`), which installs that release in its own folder
(`<state>/releases/<release>`), sets up the plugin in every agent app on the device (the skills
alone, through the Skills CLI, for the agents without a plugin) and moves the device's server to it,
asking nothing, and, run again, updates them; the update button in the CAD Viewer and the CAD app,
and `cad update`, take the same steps.

text-to-cad is three distributions from this repository at one `VERSION`: the library `cad`
(import `cad`, the CAD kernel as its `build123d` extra; `cadgen` is an import alias of it), the server
`cad-server` (import `cad_server`, command `cad`: the engine and its daemon, the commands, the
CAD Viewer's server) and the shim `cad-mcp` (import `cad_mcp`, command `cad-mcp`: the stdio
transport an agent app starts, the standard library alone). The alias distributions `cadgen` and
`text-to-cad` install the library at the same release. A file's place: imported by a model or run in
a worker, the library; run in the daemon or a command, the server; run inside the host's process,
the shim. The plugin server configs run the shim as ONE uvx command,
`uvx --no-config --managed-python --python 3.14 --from cad-mcp==<VERSION> cad-mcp`, and the
server runs as `uvx ... --from cad-server==<VERSION> cad <verb>` (`cad_server._internal.launch`).
The server installs the library with its `build123d` extra, with uv, into one base environment per
installation that every model and kernel process runs in (`cad_server._internal.base`), a program's
own folder last on its path. That installation registers itself and writes the `cad` command,
`~/.local/bin/cad`; every skill that uses the server runs `cad` (uvx cannot start in an agent's
sandbox, the command can), which runs the current installation, so no skill names a release. Every
requirement on the library names its release exactly (`cad==<VERSION>`, `cad[build123d]==<VERSION>`):
PyPI's `cad` project holds unrelated 1.x releases an open requirement would resolve to. The release
stamps every pin (`sync-version.mjs`), with the installer's fallback release, and
`scripts/release/check-version.sh` and the tests assert they all equal `VERSION`. The device runs one
server, the current installation's (`<state>/installations/current`): the CAD app, every thread and
every skill command share one daemon, and only an update moves it to
another ([CONTRIBUTING.md, "Development dependencies"](CONTRIBUTING.md#development-dependencies)).
A test or an experiment gets a server of its own with its own `CAD_STATE_DIR` and
`CAD_ENGINE_DIR`. In a checkout, install `requirements-dev.txt` (the three editable, the library
with its `build123d` extra: its own base) and test in agent apps with `scripts/install/dev_install.py`,
which points both at the checkout.

## Repo Map

- `skills/`: agent skills and their references/scripts. They ship byte for byte in the server's
  wheel (`cad_server/_runtime/plugin`, with the plugin manifests), from which the server writes the
  plugin folder (`<state>/plugin`) that `cad setup` points every agent app at.
- `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `gemini-extension.json`, and the
  [Agent Plugins](https://agent-plugins.org) standard's `plugin.json` and `mcp.json`:
  agent plugin manifests. The repository root is the plugin package; its skills are
  `skills/` directly. Installers take it from the `latest` branch, which
  `scripts/release/plugin_branch.py` builds from this tree at each release.
- `models/` ([README](models/README.md)): the corpus of models, plain files, each
  built with `python model.py`; nothing installs it.
- `docs/install.md`: installing by hand, app by app, updates, and what the install command does;
  `docs/migrations/`: the hand-migration guides between releases
  ([0.8 to 0.10](docs/migrations/migrating-0.8-to-0.10.md),
  [0.7 to 0.8](docs/migrations/migrating-0.7-to-0.8.md), 0.4 to 0.5).
- `apps/web/` ([README](apps/web/README.md)): the CAD Viewer's React client (the server
  hosts `cad_server.viewer`'s HTTP app).
- `apps/mcp/` ([README](apps/mcp/README.md)): the CAD app agent hosts render: tabs in
  Codex, cards in Claude Desktop (its server is `cad-mcp`).
- `packages/` ([README](packages/README.md)): the published distributions and the shared JS
  packages. `packages/cad` ([README](packages/cad/README.md)) is the library: the
  engine's library half (`cad/engine`: models built into documents, and the XBF, STEP, GLB, STL,
  3MF and DXF files written from them; the worker every build runs in; exports; the OCCT stills;
  the client every command reaches the server by), the formats and validators, and the `cadgen`
  alias. `packages/cad-server` ([README](packages/cad-server/README.md)) is the server:
  the daemon, the supervisor of the processes it declares and its registry (`cad_server/engine`),
  the `cad` command line (`cad_server/cli`), the CAD Viewer server (`cad_server/viewer`), the CAD
  app's server half (`cad_server/mcp`), and the JS assets they serve (`cad_server/_runtime`, built
  by `scripts/bundle/cadgen-runtime.sh`).
  `packages/cad-mcp` ([README](packages/cad-mcp/README.md)) is the shim, and
  `packages/aliases/` the `cadgen` alias. Skills consume the server as an
  installed distribution.
  `packages/core` ([README](packages/core/README.md)) is `@cad/core`, shared
  CAD/runtime/client code without React; `packages/ui` ([README](packages/ui/README.md))
  is `@cad/ui`, the shared FileViewer, renderers, controls and styles.
- `apps/docs/` ([README](apps/docs/README.md)): documentation site.
- `apps/api/` ([README](apps/api/README.md)): `api.texttocad.dev`, its own Vercel project:
  the version feed (read from PyPI) and the CAD app's consented analytics.
- `tests/`: root-owned test suites for skills, packages, viewer services, and
  repo-wide policy.
- `scripts/` ([README](scripts/README.md)): durable repo commands grouped by purpose.
- [SECURITY.md](SECURITY.md): the trust boundary (the server's door, the page's
  credentials) and how a vulnerability is reported.

## Repo Rules

- Boundaries and design laws live in each package's README: read
  [`packages/cad/README.md`](packages/cad/README.md) (the laws),
  [`packages/core/README.md`](packages/core/README.md),
  [`packages/ui/README.md`](packages/ui/README.md),
  [`apps/web/README.md`](apps/web/README.md), [`apps/docs/README.md`](apps/docs/README.md)
  and [`apps/api/README.md`](apps/api/README.md) before changing generation, rendering,
  storage, layout, or public interfaces.
- A README holds the laws; the mechanism each law constrains lives one link
  away, and the README names the link. Read the README, then follow the one
  link — not the tree. Where the mechanisms are: the engine's README
  (`packages/cad-server/src/cad_server/engine/README.md`: models, the daemon and its workers,
  documents, exports, the mesh, references, the build closure), `packages/core/docs/`,
  `packages/ui/docs/` (`settings-ui.md` is BINDING for any settings control) and
  `apps/web/docs/`; each README's table says what every document there is for.
- Ships-alone law: each distribution (`packages/cad`, `packages/cad-server`,
  `packages/cad-mcp`: a built PyPI wheel) works in isolation outside this repo, so its
  markdown must not refer to anything outside its own package — enforced by
  `tests/python/global/test_package_boundaries.py`.
  Repo-development guidance for it goes in `CONTRIBUTING.md`.
- The README and the docs site's homepage (its copy: `apps/docs/src/lib/content.ts`)
  share their structure, install commands, summary, the link to `docs/install.md` and
  Contributing: change them together. The per-app installs, updates and reinstalls live in
  `docs/install.md` alone, never in the docs app (`apps/docs/README.md`).
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
- Shared runtime comes from the **`cad-server` distribution**. A skill that uses it
  runs the `cad` command, names no release, and says how to get the command in its
  SKILL.md's setup block (the same in each); no skill installs the server or the library
  any other way (no `requirements.txt` naming either), because a second installation
  is a second daemon. Skills do not vendor it: a skill script is a thin entrypoint whose
  parser and behaviour live in `cad_server.cli`. The server draws every snapshot with
  OCCT, so no skill has a browser step. The server carries the JavaScript it serves too
  (the CAD Viewer client, the CAD app page), so a skill ships no runtime of its own. Not every
  skill needs the server (bambu-labs, dfam-check, dfm, gcode, sendcutsend and
  step-parts never run it); do not add the dependency to a skill that never invokes it.
- Keep samples and manual CAD/robot-description validation artifacts under
  `models/`. Automated tests must not read, build or import that sample corpus:
  generate small fixtures in fresh temporary directories or use tiny test-owned
  fixtures, with their own server daemon (`CAD_ENGINE_DIR`) and cleanup. Repo `tmp/` is fine.
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
- The Python floor is `requires-python` in `packages/cad/pyproject.toml` and
  nowhere else (every other `pyproject.toml` declares the same). Every source of the three
  distributions is parsed against that floor, so syntax
  newer than it fails here rather than at `pip install` time on a user's
  interpreter; raising the declared minimum relaxes the check automatically.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- The server's packaged runtime (`_runtime/viewer`, `_runtime/mcp` and `_runtime/plugin`) is BUILT,
  never committed: the whole directory is gitignored and ships only inside the
  server's wheel. Build it with the one bundle entry point, `scripts/bundle/bundle.sh`;
  `bundle.sh --check` builds it and asserts every required output. Call
  `scripts/bundle/cadgen-runtime.sh` directly only when debugging one stage.
- Installs always work from `main`. A command that names no branch installs `main`
  as it is, so every manifest, MCP config and the marketplace catalog stay at its
  root, the catalog lists the plugin at `./`, and nothing on `main` points an
  installer at another branch. The documented commands name `latest` instead: the
  plugin alone, one commit per release, never ahead of PyPI
  ([CONTRIBUTING.md, "The install branches"](CONTRIBUTING.md#the-install-branches)).
  `tests/python/global/test_plugin_manifests.py` holds both halves.
- Never let a symlink reach the published tree. Agent installers disagree about
  symlinks and one loses data silently: the Skills CLI dereferences them, Claude
  Code preserves them, and Codex `plugin add` drops them with no error, shipping
  a skill with missing files. The shipping contract (Git, below) enforces this;
  do not relax it.
- The CAD Viewer is `cad viewer`: the server hosts `cad_server.viewer` (Python, in
  `packages/cad-server`), the React client's source is `apps/web/` and its build
  ships in the server's wheel at `cad_server/_runtime/viewer` (built, never committed; a
  checkout serves `apps/web/dist`). The CAD, DXF and robot-description skills document that verb directly.
  Nothing in `cad_server.viewer` imports the CAD kernel at module scope — a STEP or
  `.xbf` it shows is read and meshed by the server's kernel processes (`viewer/documents.py`),
  never by a request's thread.
  Keep repo-level tooling in `scripts/`, not under `apps/web/`.
- `packages/core` stays non-React. Shared FileViewer/renderers belong in
  `packages/ui`; host workflow state belongs in apps. Apps never import another
  app and shared packages never import apps. Root npm workspaces consume compiled
  package exports; do not add source aliases or nested lockfiles. Preserve app
  UI/UX and functionality during restructuring; changes are pure refactors.
- Shared UI must stay platform-agnostic. Apps implement environmental effects;
  shared features use injected capabilities and named extension slots. Before
  extending these interfaces, read [the viewer host contract](packages/ui/docs/viewer-host.md).
- Create lightweight shared Python packages under `packages/` when a helper
  should not inherit heavier package dependencies.
- Use path-targeted search, validation, and `git status`; avoid broad scans over
  generated CAD artifacts unless the task requires them.
- Treat `VERSION` as the canonical release version. Do not hand-edit duplicate
  package, plugin, lockfile, or Python `pyproject.toml` versions;
  `scripts/release/bump-version.sh` and `scripts/bundle/bundle.sh` stamp them
  from the canonical version.

## Environments

- Prefer `./.venv/bin/python` for CAD Python work.
- Keep new branch checkouts and git worktrees lightweight by default. Do not
  copy `.venv/` or `models/` through `.worktreeinclude`; recreate `.venv/`
  inside the worktree only when Python dependencies are needed for the workflow.
- In Codex or Claude Code worktrees, prefer the skill instructions and scripts
  under the current worktree's `skills/` directory over globally installed
  skills or plugins from another checkout.
- Test skills and the plugin in an agent app with
  `scripts/install/dev_install.py <host>` ([CONTRIBUTING.md, "Test In Agent
  Apps"](CONTRIBUTING.md#test-in-agent-apps)). One copy of the plugin per app: never the
  development install beside the published plugin, or beside the skills installed loose.
- Install dependencies only for the workflow being changed.
- Do not commit `.venv/`, `node_modules/`, caches, `tmp/`, local credentials, or
  printer config.

## Checks

Run the smallest path-targeted check that covers the change. Use broad wrappers
when touching shared surfaces or before handoff:

- Code tests: `scripts/test/test.sh` (JS, API, Python, then policy).
- Focused runners: `scripts/test/test-js.sh`, `scripts/test/test-api.sh`, `scripts/test/test-docs.sh`,
  `scripts/test/test-python.sh`, `scripts/test/test-global.sh`.
  `test-python.sh` takes `--select cadgen|viewer|skills|all` and
  `--print-weights`; `test-js.sh` takes `--select core|ui|web|mcp|all`. See
  [`scripts/README.md`](scripts/README.md).
- In GitHub Actions, `test.yml` runs one job per concern, each only when the
  change reaches it: `scripts/github-workflows/select_checks.py` maps every
  changed path to the tests that read it, and the Python jobs run just those
  files. A test that reads a new kind of path gets a rule there
  ([CONTRIBUTING.md#ci](CONTRIBUTING.md#ci)); an unknown path, `VERSION`, `packages/core`, the
  lockfiles and the test machinery run everything, as does a manual dispatch.
  Required check names stay stable.
- Canonical release version: `scripts/release/check-version.sh`
- Packaged runtime builds and is complete: `scripts/bundle/bundle.sh --check`
- CAD Viewer or shared packages: build exports with `npm run build:packages`,
  then `npm --prefix packages/core test`, `npm --prefix packages/ui test`,
  `npm --prefix apps/web run typecheck`, `npm --prefix apps/web run test`,
  `npm --prefix apps/web run build` (`scripts/test/test-js.sh` runs all but the web build,
  which `scripts/bundle/bundle.sh` runs).
  The Viewer is two languages and `npm run test` covers only the client — the
  backend's suite is `tests/python/packages/cad_server/viewer`, run by
  `scripts/test/test-python.sh`. Touching `cad_server/viewer/` means running that.
- Docs site: `npm --prefix apps/docs run check`
- API (`api.texttocad.dev`): `npm --prefix apps/api test`
- Targeted Python tests: `scripts/test/test-python.sh <changed test paths>` (each file
  on a server daemon of its own; `test-global.sh` for
  `tests/python/global`)

When a task changes what the bundlers consume, run `scripts/bundle/bundle.sh`
and confirm the change lands in the built runtime. There is nothing to commit:
`_runtime/` is gitignored end to end, so what a reviewer reads is the source and
what a user gets is the wheel the release builds from it.

## CAD Viewer

The app-facing playbook lives in [`apps/web/README.md`](apps/web/README.md): launcher contract
(reuse, ports, `/<id>` pages), dev vs prod, and the catalog/link-verification
gotchas. The repo-side half — the lightweight-worktree recipe and
root workspace dependencies — lives in [CONTRIBUTING.md under "Viewer Development
In This Repo"](CONTRIBUTING.md#viewer-development-in-this-repo). Read them before starting,
stopping, or debugging a Viewer. Never stop an instance you did not start;
packaged-runtime checks go through `scripts/bundle/bundle.sh`.

## Git

The shipping contract, `scripts/github-workflows/check-builds.sh` on every push:
no tracked symlink, no `.gitattributes` rule that rewrites files at checkout or
changes the archive (so no Git LFS; the repository root is the plugin, and
claude.ai's plugin directory refuses files a filter rewrites), every tracked file
under 5 MiB, no skill reaching into a repo root. Heavyweight media stays out of
the tree. Git holds code, never CAD or mesh assets (a STEP, STL, GLB, 3MF, XBF or DXF is
made at run time, in a temporary folder or a gitignored output folder):
`tests/python/global/test_no_cad_assets_tracked.py` fails on a tracked one but for its short
allowlist, a reason and a size cap each. Local hooks live in `.githooks` and delegate build
checks through `scripts/git-hooks/pre-commit`.
