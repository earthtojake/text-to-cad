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
real file. Installers follow `latest`, claude.ai's directory `claude-plugin` and
Codex's `codex-plugin`: the plugin alone, one commit per release,
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
  `main`'s and stamps the derived metadata and every mention of the release's own
  (`cad==`, `cad@`) with it.

Releases follow Semantic Versioning: a breaking change, which always comes with a migration guide,
bumps the minor below 1.0 and the major from 1.0, and `Test`'s version check refuses a new migration
guide in a release that must break nothing: a patch below 1.0, a patch or a minor from 1.0 (an existing
guide may be corrected in any release). Which releases install themselves is a second rule: cad installs
every newer release of its own major by itself, so below 1.0 a minor that breaks too (this is a beta); a
new major never arrives by itself, only by `cad update --major` ([decisions](docs/contributing/decisions.md)). A command
the skills used keeps working for 30 days after they stop using it, which CI checks; otherwise a
command, option or tool may change or go in any release. What breaks is law 15's tiers and the short
list of what must stay the same
([CONTRIBUTING.md, "Which number a release bumps"](CONTRIBUTING.md#which-number-a-release-bumps)).

Merge a release pull request only on the user's explicit word, once its checks
pass: the merge is the release. `Test` runs every job for a `VERSION` change (the
installer rehearsals and the Python 3.11 floor among them), and its `static` job
vets the bump (a branch of this repository only, a version past
`main`'s and the latest tag, every stamp in step). `Publish Release`
(`release-publish.yml`) runs on the merge: it builds the plugin ZIP, the bundle
and the wheel and sdist of each of the release's four projects on PyPI (`cad`, and its
empty aliases `cad-server`, `cad-mcp` and `cadgen`), uploads
them `cad` first, then `cad-server` and `cad-mcp` together, then `cadgen`, waiting until PyPI lists each,
and only then writes the install branches (`latest`, `claude-plugin`, `codex-plugin`), deploys
the docs site, tags `v<VERSION>` and publishes the GitHub Release. A run that
stopped partway is finished by dispatching `Publish Release` on `main`;
`build-test` is the rehearsal branch, used only when the user asks to test the
pipeline; the standalone `Deploy Docs` workflow redeploys the docs site from a
ref without a release. The full flow, the resume path, the rehearsal and the
local fallbacks are [CONTRIBUTING.md's Releases](CONTRIBUTING.md#releases).

People install text-to-cad with one command, `curl -fsSL https://texttocad.dev/install.sh | sh`
(Windows: `irm https://www.texttocad.dev/install.ps1 | iex`). It takes no options, carries no
version and has one behaviour, whoever runs it: the bootstrap in `scripts/install/` makes sure uv is
there and runs `install.py`, which installs cad as a uv tool only where none is installed or the one
there does not start, installs the plugin from `latest` in each agent app it finds with that app's own
command (its `APPS` table is the one list of apps), removes our own older copies, puts cad's folder on
the PATH with `uv tool update-shell`, and turns on `cad plugin update auto`, keeping its release as the one
it is up to date for only where it ends well. It never starts the server. cad alone is installed by one
promised line, `uv tool install cad`, which is what every skill's Setup block runs; no skill runs the install
command. A global install updates itself to every newer release of its own major version, on by default
(`cad update auto`), never to a higher major; `cad update` updates it now inside its major, and `cad update
--major` to the newest of all. Where `cad plugin update auto` is on and
cad is newer than the release the install command last ended well for, however it got newer, cad's
server runs `cad plugin update` (the install command) once. A
store updates its own copy. cad knows no app or skill, and of plugins only `cad plugin`
([decisions](docs/contributing/decisions.md)).

text-to-cad is one Python distribution, `cad`, at one `VERSION`: the library (import `cad`, the CAD
kernel as its `build123d` extra), the server and the `cad` command (import `cad_server`: the engine
and its daemon, the commands, the viewer's server) and the stdio transport an agent app starts
(import `cad_mcp`, run as `cad mcp`), all in `packages/cad/src`. `cad-server`, `cad-mcp` and `cadgen`
are empty aliases published at every release so older installs keep working; `cadgen` is the
library's deprecated name. New text and examples name `cad`. A computer has one cad, installed
globally (`uv tool install cad`), and one server, started only by `cad server start` or `cad mcp`
(Codex's plugin line, `uvx --no-config --managed-python --python 3.14 cad@<VERSION> mcp`, which
installs cad globally where the computer has none, the newest of `<VERSION>`'s major, and uses that cad's
server; no server runs from
uv's cache). cad runs on Python 3.11 and newer. Skills run plain `cad` commands, no version in them. The server installs `cad[build123d]` at its own release, with uv, on first need,
into the base environment its kernel processes run in (`cad_server._internal.base`); `cad run` is
`uv run` with the library pinned at that release and the integrations a program's imports use
(`cad_server._internal.extras`). A test or an experiment gets a server of its own with its own
`CAD_STATE_DIR` and `CAD_ENGINE_DIR`. In a checkout, `uv sync` makes `.venv` from `uv.lock` (the root
`pyproject.toml`, a uv workspace: cad editable, with its kernel, its own base; CI installs the same lock with
`uv sync --locked`), `uv run ...` runs in it, and you test in agent apps with `scripts/install/dev_install.py [APP...]`,
which installs the checkout as the `cad` tool, editable (`--release` goes back).

## Repo Map

- `skills/`: agent skills and their references. They ship in the plugin alone, never in a wheel.
- `.claude-plugin/`, `.codex-plugin/` (the one naming a CAD server, `codex.mcp.json`: browser
  first, every other app gets the skills alone), `.cursor-plugin/`, `.grok-plugin/`,
  `.antigravity-plugin/`, `.kimi-plugin/`, `.devin-plugin/`, `.muse-plugin/` and `gemini-extension.json`:
  agent plugin manifests (no root `plugin.json`: Codex would read it in place of its own). The repository root
  is the plugin package; its skills are
  `skills/` directly. Installers take it from the `latest` branch, claude.ai's directory
  from `claude-plugin` (the skills alone, pinned `@claude`) and Codex's from `codex-plugin`
  (pinned `@codex`), which `scripts/release/plugin_branch.py` builds at each release.
- `models/` ([README](models/README.md)): the corpus of models, plain files, each
  built with `python model.py`; nothing installs it.
- `docs/install.md`: the install command, installing by hand app by app, updating and removing;
  `docs/contributing/`: [decisions](docs/contributing/decisions.md) (why install and updates work
  as they do), [testing](docs/contributing/testing.md) (the rules, adding a test or a CI
  job, a red run), [writing a skill](docs/contributing/writing-a-skill.md),
  [adding a document type](docs/contributing/adding-a-document-type.md) and
  [adding an integration](docs/contributing/adding-an-integration.md);
  `docs/migrations/`: the hand-migration guides between releases
  ([0.10 to 0.11](docs/migrations/migrating-0.10-to-0.11.md),
  [0.8 to 0.10](docs/migrations/migrating-0.8-to-0.10.md),
  [0.7 to 0.8](docs/migrations/migrating-0.7-to-0.8.md), 0.4 to 0.5).
- `apps/web/` ([README](apps/web/README.md)): the viewer's React client (the server
  hosts `cad_server.viewer`'s HTTP app).
- `apps/mcp/` ([README](apps/mcp/README.md)): the CAD app the Codex app renders as tabs, the one
  host given it (started by `cad mcp`); its cards are reached only by a development switch.
- `packages/` ([README](packages/README.md)): the published distribution and the shared JS
  packages. `packages/cad` ([README](packages/cad/README.md), the laws) is `cad`: the library
  (`src/cad`: models built into documents and the files written from them, the worker every build
  runs in, exports, the OCCT stills, the client every command reaches the server by, the formats and
  validators), the server ([README](packages/cad/src/cad_server/README.md): the daemon and its
  registry, the `cad` command line, the viewer server, the CAD app's server half, and the JS assets
  they serve in `_runtime`, built by `scripts/bundle/cadgen-runtime.sh`) and the transport
  ([README](packages/cad/src/cad_mcp/README.md)). `packages/aliases/` holds the three empty aliases.
  `packages/core` ([README](packages/core/README.md)) is `@cad/core`, shared
  CAD/runtime/client code without React; `packages/ui` ([README](packages/ui/README.md))
  is `@cad/ui`, the shared FileViewer, renderers, controls and styles.
- `apps/docs/` ([README](apps/docs/README.md)): the site, texttocad.dev: the homepage and the
  documentation under `/docs`, which shows the install and migration guides of `docs/` as they are
  and its own pages (`apps/docs/content/`: a page per skill, the `cad` command, contributing).
- `apps/api/` ([README](apps/api/README.md)): `api.texttocad.dev`, its own Vercel project:
  the version feed (read from PyPI) and the CAD app's consented analytics.
- `tests/`: root-owned test suites for skills, packages, viewer services, and
  repo-wide policy.
- `scripts/` ([README](scripts/README.md)): durable repo commands grouped by purpose.
- [SECURITY.md](SECURITY.md): the trust boundary (the server's door, the page's
  credentials) and how a vulnerability is reported.

## Repo Rules

- Claude Code, Codex and Cursor are the first-class integrations, and supporting them comes first:
  a change that touches the plugin, the skills, CAD's server or the CAD app keeps all three
  working, and is tested in each before it ships. Browser first: only Codex gets the CAD server
  (its tab is the one verified view); the others show models in their browser (the host table in
  [`apps/mcp/README.md`](apps/mcp/README.md)). Other hosts are best effort.
- Boundaries and design laws live in each package's README: read
  [`packages/cad/README.md`](packages/cad/README.md) (the laws),
  [`packages/core/README.md`](packages/core/README.md),
  [`packages/ui/README.md`](packages/ui/README.md),
  [`apps/web/README.md`](apps/web/README.md), [`apps/docs/README.md`](apps/docs/README.md)
  and [`apps/api/README.md`](apps/api/README.md) before changing generation, rendering,
  storage, layout, or public interfaces.
- The laws and the how-to guides record what the tools so far needed; they are not a template for the
  next one. When adding a feature, a document type, an integration or a command, take them with a
  grain of salt and think from first principles about what is best for that tool: what it already
  does, who looks at its files, and what is missing without us. Where that leads away from a law or a
  guide, do not force the fit: say which and why in the change, and where the law itself should read
  differently, amend it in the same change (an MJCF has no document type, and law 27 changed with
  it). What stays wrong is departing from one without saying so.
- No superficial wrappers. Everything added around a tool, a helper in the library or a `cad` command
  alike, is added because something is missing without it: a result shape, a safety guarantee, a fact
  the tool does not report. Never to rename or re-expose what the tool already does: that is used as
  the tool's own, its Python API in the script and its command line through `cad run`
  ([`packages/cad/README.md`](packages/cad/README.md), laws 25 and 29).
- A README holds the laws; the mechanism each law constrains lives one link
  away, and the README names the link. Read the README, then follow the one
  link — not the tree. Where the mechanisms are: the engine's README
  (`packages/cad/src/cad_server/engine/README.md`: models, the daemon and its workers,
  documents, exports, the mesh, references, the build closure), `packages/core/docs/`,
  `packages/ui/docs/` (`settings-ui.md` is BINDING for any settings control) and
  `apps/web/docs/`; each README's table says what every document there is for.
- Ships-alone law: each distribution (`packages/cad` and the aliases under `packages/aliases`: a
  built PyPI wheel) works in isolation outside this repo, so its
  markdown must not refer to anything outside its own package — enforced by
  `tests/python/global/test_package_boundaries.py`.
  Repo-development guidance for it goes in `CONTRIBUTING.md`.
- The README and the docs site's homepage (its copy: `apps/docs/src/lib/content.ts`)
  share their structure, install commands, summary, the apps they name (those `docs/install.md`
  lists), the link to `docs/install.md` and Contributing: change them together. The per-app installs, updates and reinstalls live in
  `docs/install.md` alone: the docs app shows that file as it is, at `/docs/install`, and never
  keeps a copy (`apps/docs/README.md`).
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
- cad knows no app or skill: it never names, installs, removes, updates or carries them (the MCP
  server may read which app connected). Of plugins it knows one command, `cad plugin`, which runs
  the hosted install command (`cad plugin update`, and once where cad is newer than the release it
  last ended well for and `cad plugin update auto` is on). Knowledge of the apps lives in the plugin and
  `scripts/install/install.py`.
- Shared runtime comes from the **`cad` distribution**. A skill that uses it runs plain `cad`
  commands, with no version, and says how to get cad in its SKILL.md's Setup block (the same in
  each); no skill installs cad any other way (no `requirements.txt` naming it), because a second
  installation is one the Setup block never names, and no skill names or runs the install command. A command the skills used keeps working for 30
  days after they stop using it (`tests/python/global/test_released_commands_still_parse.py`).
  Skills do not vendor cad, and ship no scripts (claude.ai's plugin
  directory refuses a program): what a skill would script is a `cad` command whose parser
  and behaviour live in `cad_server.cli` (print3d's presets are `cad orcaslicer`). The
  server draws every snapshot with OCCT, so no skill has a browser step. The server carries
  the JavaScript it serves too (the viewer client, the CAD app page), so a skill ships no
  runtime of its own. Every skill runs `cad` today; one that never invokes it carries no
  setup block.
- Keep samples and manual CAD/robot-description validation artifacts under
  `models/`. Automated tests must not read, build or import that sample corpus:
  generate small fixtures in fresh temporary directories or use tiny test-owned
  fixtures, with their own server daemon (`CAD_ENGINE_DIR`) and cleanup. Repo `tmp/` is fine.
  Enforced by `tests/python/global/test_tests_are_self_contained.py`.
- Every test runs in CI. Each test file is reached by a runner under
  `scripts/test/`, every runner is called by a `test.yml` job on the changes that
  can break it (the release tier, the Python floor and the installer rehearsals, on a
  full run: before a release ships, and nightly), and a collector that finds nothing
  fails the run rather than reporting a group that never ran. A test no CI job runs
  is dead: wire it in or delete it. There are no manual-only test gates. Enforced by
  `tests/python/global/test_ci_workspace_selection.py`.
- Tests and CI are short and succinct. Test a contract, a user flow or a fixed bug,
  once, at the cheapest level that exercises the real path: a unit or jsdom test
  first, a real browser (WebGL) only for what needs one. Await the condition, never
  a fixed sleep or a wall-clock bound; a flaky test is fixed or deleted, never
  retried. CI time is a budget: each `js-ui` job stays within 7 minutes, a test file
  within 120 seconds on Linux CI (240 on Windows; one that outgrows it is split), and a
  change that lengthens any job says what it costs and why in its PR.
- Benchmarks under `scripts/bench/` are manual and their output is never
  committed: reports, logs, profiles and screenshots go to an ignored `tmp/`.
  Only their pure helper units run in a test runner.
- The Python floor is `requires-python` in `packages/cad/pyproject.toml` and
  nowhere else (every other `pyproject.toml` declares the same). Every source of the
  distribution, and every test, is parsed against that floor, so syntax
  newer than it fails here rather than at `pip install` time on a user's
  interpreter; raising the declared minimum relaxes the check automatically.
  The floor (3.11, so cad installs on the older Python a person may already have) is
  older than the Python the server's installations run on (3.14, `cad_server._internal.launch.PYTHON`):
  a call the floor's standard library lacks parses and fails only when it runs, so CI
  runs the library's, the server's and the transport's suites on the floor too
  (`scripts/test/test-floor.sh`), on every full run: before a release ships, and nightly.
- Reserve `scripts/` for durable repo commands. Do not write temporary,
  one-off, or local-only helper scripts there; use `tmp/` or `/tmp` instead.
- The server's packaged runtime (`_runtime/viewer` and `_runtime/mcp`) is BUILT,
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
  symlinks and one loses data silently: a copied skills folder dereferences them, Claude
  Code preserves them, and Codex `plugin add` drops them with no error, shipping
  a skill with missing files. The shipping contract (Git, below) enforces this;
  do not relax it.
- The viewer is `cad viewer`: the server hosts `cad_server.viewer` (Python, in
  `packages/cad`), the React client's source is `apps/web/` and its build
  ships in the server's wheel at `cad_server/_runtime/viewer` (built, never committed; a
  checkout serves `apps/web/dist`). Every skill that shows a model (CAD, PCB, robot simulation) documents that verb directly.
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

- Prefer `uv run` (the checkout's `.venv`, made by `uv sync`) for CAD Python work.
- Keep new branch checkouts and git worktrees lightweight by default. Do not
  copy `.venv/` or `models/` through `.worktreeinclude`; run `uv sync` inside
  the worktree only when Python dependencies are needed for the workflow.
- In Codex or Claude Code worktrees, prefer the skill instructions and scripts
  under the current worktree's `skills/` directory over globally installed
  skills or plugins from another checkout.
- Iterate inside a worktree on its own server, never on a global install (that is for end-to-end tests alone,
  below): `CAD_ENGINE_DIR`, `CAD_STATE_DIR`, `CAD_CACHE_DIR` and `CAD_UPDATE_CHECK=0`, set in every command
  ([CONTRIBUTING.md, "Work In A Worktree"](CONTRIBUTING.md#work-in-a-worktree)).
- Test skills and the plugin in an agent app with
  `scripts/install/dev_install.py [APP...]` ([CONTRIBUTING.md, "Test In Agent
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
  `--print-weights`; `test-js.sh` takes `--select core|ui|ui-units|ui-browser|web|mcp|all`. See
  [`scripts/README.md`](scripts/README.md).
- In GitHub Actions, `test.yml` runs one job per concern, each whole on its one
  flag and only when the change reaches it: `scripts/github-workflows/select_checks.py`
  maps every changed path to its component (the packages, the UI, an app, a suite), a
  component to the jobs that run it, and a changed test file to itself
  ([docs/contributing/testing.md](docs/contributing/testing.md#ci)); an unknown path, `VERSION`, `packages/core`, the
  lockfiles and the test machinery run everything, as do a manual dispatch and the
  nightly run. `main` requires one check, `CI`, which fails when any job did, so a
  job is added, renamed or sharded without a branch-protection change.
- Canonical release version: `scripts/release/check-version.sh`
- Packaged runtime builds and is complete: `scripts/bundle/bundle.sh --check`
- Viewer or shared packages: build exports with `npm run build:packages`,
  then `npm --prefix packages/core test`, `npm --prefix packages/ui test`,
  `npm --prefix apps/web run typecheck`, `npm --prefix apps/web run test`,
  `npm --prefix apps/web run build` (`scripts/test/test-js.sh` runs all but the web build,
  which `scripts/bundle/bundle.sh` runs).
  The viewer is two languages and `npm run test` covers only the client — the
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

## Viewer

The app-facing playbook lives in [`apps/web/README.md`](apps/web/README.md): launcher contract
(reuse, ports, `/<id>` pages), dev vs prod, and the catalog/link-verification
gotchas. The repo-side half — the lightweight-worktree recipe and
root workspace dependencies — lives in [CONTRIBUTING.md under "Viewer Development
In This Repo"](CONTRIBUTING.md#viewer-development-in-this-repo). Read them before starting,
stopping, or debugging a viewer. Never stop an instance you did not start;
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
allowlist, a reason and a size cap each. KiCad files a sample's scripts write are build output
too, gitignored and made by its `cad run build.py`; a board no script makes is source
(`tests/python/global/test_generated_kicad_files_untracked.py`). Local hooks live in
`.githooks` and delegate build checks through `scripts/git-hooks/pre-commit`.
