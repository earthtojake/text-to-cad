# Contributing

This repository is a local workbench for CAD-related agent skills. Treat
`skills/` as the product under test and `models/` as the shared
fixture/artifact area.

## Local Checkout

`main` is the only long-lived branch: branch from it and open PRs back to it.

### Repository remotes

Maintainers with write access can clone the upstream repository directly:

```bash
git clone https://github.com/earthtojake/text-to-cad.git
cd text-to-cad
git switch -c my-change
```

External contributors should first fork the repository on GitHub, then keep the
fork as `origin` and the canonical repository as `upstream`:

```bash
git clone https://github.com/<username>/text-to-cad.git
cd text-to-cad
git remote add upstream https://github.com/earthtojake/text-to-cad.git
git fetch upstream main
git switch -c my-change upstream/main
```

Push the branch to `origin` and open the pull request against
`earthtojake/text-to-cad:main`.

### Development environment

Choose the setup for the environment where the tools and tests will run. Every
environment needs Python 3.11 or newer. Install Node.js 22 for the
packaged runtime, Viewer, `@text-to-cad/core`, or documentation site; Python-only work
can defer Node until a selected test needs a generated runtime stage.

### Linux, macOS, and WSL

Use the POSIX shell. On WSL, install dependencies inside the distribution; do
not reuse a Windows `.venv` or `node_modules` directory across the boundary.

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-dev.txt
```

Build the packaged runtime when the work needs it, and use the virtual
environment's interpreter for direct CLI calls:

```bash
scripts/bundle/bundle.sh
./.venv/bin/python -m cadgen.cli step snapshot --help
./.venv/bin/python -m cadgen.cli urdf validate --help
```

### Native Windows

Use PowerShell for Python and npm commands. Git for Windows supplies Git Bash,
which runs the repository's checked-in `.sh` entry points just as Windows CI
does.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Invoke repository scripts through Git Bash. The default installation path is
shown here; adjust it if Git is installed elsewhere. The runners discover the
Windows `.venv\Scripts\python.exe` layout automatically.

```powershell
$gitBash = 'C:\Program Files\Git\bin\bash.exe'
& $gitBash scripts/bundle/bundle.sh
& $gitBash scripts/test/test-python.sh --select cadgen
```

Use the Windows virtual-environment path for direct CLI or focused test calls:

```powershell
.\.venv\Scripts\python.exe -m cadgen.cli step snapshot --help
.\.venv\Scripts\python.exe -m unittest tests/python/skills/urdf/test_cli.py
```

### Development dependencies

`requirements-dev.txt` installs the source packages from `packages/` and the
small set of Python extras mirrored from skill runtime requirements. This is
the default Python environment for broad repo checks and source-checkout
development. After pulling, reinstall `requirements-dev.txt` to refresh the
editable-install metadata: `cadgen.__version__` reports the installed
dist-info by design — it is release-grained, so dev code is always newer than
its number — and nothing behavioral consults it, but stale metadata makes the
reported number drift further from the code than it has to.

Skills run cadgen through their launch command, `uvx ... --from cadgen==<VERSION>`,
which installs the RELEASE from PyPI. To run your working copy, use the checkout's
`.venv` (`requirements-dev.txt`), or `scripts/install/dev_install.py`, which points a
dev install's server and skills at it (see [Test In Agent Apps](#test-in-agent-apps)).

`packages/cadgen/src/cadgen/_runtime/` is BUILT, not committed — the whole
directory is gitignored, and the wheel is the only place those files ship. A
fresh clone therefore has no Node builders, no snapshot browser bundle, no
Viewer client and no file tracer -- so it builds no model -- until
`scripts/bundle/bundle.sh` runs, and cadgen says so by name the first time it
reaches for one. `scripts/test/test-python.sh` and `scripts/test/test-global.sh`
build the stages they read if they are missing (the tracer for this machine
only), so this step is about having the whole thing, including the Viewer client
and every platform's tracer the wheel carries.

For CAD Viewer development:

```bash
npm ci
npm run build:packages
```

The skills ship no launcher scripts: every operational verb is a `cadgen`
subcommand (`cadgen <verb>`, or `python -m cadgen.cli <verb>` when the console
script is not on PATH), and `python <model>.py` builds a model through the `__main__` call at the end of its script.
The robot validators used to be the exception, running on bare `python3` while
their logic lived under `skills/`; that logic is `cadgen.{urdf,sdf,srdf}_*` now,
so they need cadgen like everything else.

## Test In Agent Apps

Test the skills the way users get them: as the plugin, with CAD's server. One
script installs this checkout into an agent app, and running it again replaces
that install with the current checkout:

```bash
scripts/install/dev_install.py claude
```

| Host | What it installs |
| ---- | ---------------- |
| `claude` | Claude Code's plugin, which Cursor and Grok Build also load |
| `codex` | the Codex plugin, shared by the app, the CLI and the IDE extension; `--restart` quits and reopens the app |
| `cursor` | a local Cursor plugin, for Cursor without Claude Code |
| `grok` | Grok Build's plugin, for Grok without Claude Code |
| `gemini` | a linked Gemini CLI extension |
| `claude-desktop` | a `cad-dev` server in Claude Desktop's chat, which takes servers, not plugins |

For an agent without plugins, install the skills alone from the checkout with the
Skills CLI, the way users get them, and run it again after a change:

```bash
npx skills add . -g -a <agent>
```

A plugin host gets `text-to-cad@earthtojake-dev`: this checkout's skills, and
`cadgen mcp` run by this checkout's `.venv` (`CADGEN_PYTHON` overrides it), serving
a copy of the `apps/mcp` page built for that install (`--no-build` reuses the last
build). The copied skills' launch command is rewritten to that same `.venv`, so the
server and the agent's scripts share this checkout's installation and warm daemon;
each worktree is an installation of its own (the daemon is named after it), so
several can be installed side by side, one per app. With `--wheel`, the checkout's
wheel is built as the release builds it (`bundle.sh`, then `uv build`) and the
server and skills run it through `uvx --from <wheel>`: exactly what users get,
each build its own installation. Install again to see a skill or page edit. A page that changed under a
running app would change its URI, and hosts drop the frames already showing it,
which is why each install serves its own copy. A running server keeps the
Python it started with, so restart the app after a Python-only change.
`--uninstall` removes a host's install. Its server names its install channel
`dev` (`--channel dev`), and a checkout's editable cadgen counts as one too:
neither is ever offered an update. To see the update button, run a server with
`--channel claude-github` (a Viewer with `CADGEN_INSTALL_CHANNEL=claude-github`)
and a `versions.json` in its state directory (`CADGEN_STATE_DIR`) naming a newer
`latest`.

Keep one copy of the plugin per app. The script refuses to install where another
copy would load beside it: the published plugin, this one installed through
another host, or this repository's skills installed loose where the app reads
skills. Two copies means every skill twice. Uninstall the published plugin
before testing, and reinstall it afterwards.

Where the server's output goes:

- Codex: its log database, `~/.codex/logs_2.sqlite` (lines starting `MCP server stderr`)
- Claude Code: `claude mcp list` shows whether the server connected
- Claude Desktop: `~/Library/Logs/Claude/mcp-server-cad-dev.log`; the app's
  developer tools (Developer Mode, then Cmd+Option+I) inspect a card's frame
- Cursor: `mcp-server-plugin-*` logs under `~/Library/Application Support/Cursor/logs/`
- Gemini CLI: `gemini mcp list` shows whether the server connected

What the CAD app is and how hosts present it is in
[apps/mcp/README.md](apps/mcp/README.md). No agent app can be driven by a test,
so the standard path is also checked in the MCP Apps reference host
(`basic-host` from `modelcontextprotocol/ext-apps`): it speaks Streamable HTTP,
so a local bridge to the stdio server is needed, and it does not advertise the UI
extension, so start the server with `CADGEN_MCP_PRESENTATION=inline`.

## Test From This Repository

Automated tests are self-contained. They must not read, enumerate, build, or
import sample models from this repository's `models/` directory. Generate the
smallest fixture needed in a fresh temporary directory, or use a tiny fixture
committed with the tests; do not rely on existing outputs.
Repo `tmp/` and system temporary directories are both fine. Give builds their
own cache store and clean up their processes and files. The shared
temporary-directory helper retains the Windows cleanup retries used by the suite.

Keep regression tests focused on observable behavior. Reuse setup within a test
when several assertions concern the same result; do not repeatedly build the
same geometry to test unrelated metadata or duplicate an existing integration
case. Each new test should protect a distinct contract or credible failure not
already covered. Test a shared validator's cases once; callers need wiring
checks, not copies of its full matrix. Avoid pinning private helpers, source
spelling or UI copy when observable behavior already covers the requirement.
Real kernel and browser tests remain necessary for geometry fidelity,
cache reuse, rendering, and process-lifecycle behavior.

The UI's browser specs (`packages/ui/**/*.browser.test.mjs`) run as their own
pass, `UI_BROWSER_TEST_CONCURRENCY` files at a time (4 by default; the CI
`viewer` job sets 1, because Linux renders their WebGL in software and several
at once saturate the runner). `CAD_TEST_SWIFTSHADER=1` makes a macOS run use that same
software renderer, to reproduce a CI-only browser failure locally.

A test's COST is part of its design. A cold `python <model>.py` spends ~2.6 s
importing the CAD kernel before it draws a box, so a file that runs one per
assertion is mostly paying for imports: build a fixture the tests only READ once
for the class and copy it in, keep each test's store, roots and freshness state
private, and add a subprocess only where the subject IS the process. Model runs
in tests are cold (`CADGEN_DAEMON=0`): routing them through a warm daemon was
measured on CI and moved the kernel import into a daemon process rather than
removing it (the runners are CPU-bound at four files), and cost more than it
saved on Windows. `tests/python/support/warm_daemon.py` is for the opposite
purpose — a test that deliberately exercises the WARM path, the production
default, through a daemon private to its module — and only where the test's
subject is what a warm worker does. Repeating a non-deterministic case N times
is not coverage — if the underlying property can be pinned directly, pin it and
run the case once.

`scripts/test/test-python.sh --print-weights` prints what the slow files cost,
the first thing to read when a run is slow.

### CI

`test.yml` selects work from the dependency graph. Each job installs only its
root npm workspaces; Python and the two Playwright browser installations are
requested separately. A manual dispatch runs every job.

| Check | Runs for | Coverage |
| --- | --- | --- |
| Version Check | every change | canonical version, derived metadata, skill pins, the shipping contract's tree rules |
| cadgen (Linux/Windows) | cadgen, core, infrastructure | Python engine, daemon, CLI and viewer backend |
| core-js | core, infrastructure | `@text-to-cad/core` and benchmark helper units |
| web | web, UI, core, cadgen, infrastructure | UI and web units, the UI browser specs, bundled launch, format/camera browser checks through the backend |
| skills | skills or runtime/host contracts | repo policy; skill CLI suites only for skills, cadgen, core or infrastructure |
| codex | codex, UI, core, cadgen, infrastructure | the CAD app's host-adapter units (jsdom) and its one-file build |
| docs | docs, skills, cadgen, core, infrastructure | `npm --prefix apps/docs run check`: static asset contract, the analytics receiver's tests (`npm test`), lint, Next build, icon verification |
| packaging | cadgen, core, UI, web, codex, infrastructure | clean bundle, wheel contents, installed CLI behavior |

Here `cadgen`, `core` and `UI` mean their package directories and tests;
`web`, `codex` and `docs` mean their app directories. Infrastructure includes
`scripts/`, `.github/`, the root lockfile/manifests and version/plugin metadata.
Root prose, manual model changes and `LICENSE` run only Version Check. Skill
and package Markdown is test input and follows its owning component.

A skipped job satisfies its required check. Renaming a job renames its required
check, so it lands together with a matching branch-protection update.

Every job has a timeout of about twice its slowest recent run, so a hang fails
in minutes. Within a Python suite, a test file still running after 15 minutes
prints every thread's stack and fails by name.

A web-only edit does not run the Python engine. A UI edit exercises the web
host. Core changes reach every consumer. Policy checks for a host edit do not
also run every skill CLI suite. Windows runs the Python package suite because
paths, locks, subprocesses, file URLs and daemon behavior are
platform-sensitive.

Viewer browser failures upload bounded renderer-state JSON for three days.
CI sets `VIEWER_TEST_DIAGNOSTICS_DIR` for this evidence; it does not enable the
optional review screenshots produced by `--out`. Capture timing stays in the
job log, so a stalled screenshot still leaves useful state diagnostics.

**The packaged runtime is built per job**, not built once and passed between
them: `ensure_packaged_runtime` takes ~13 s plus the host's file tracer (seconds
with zig's cache warm; setup-deps caches it per zig version), and an artifact would
serialise every test job behind a bundle job for longer than that.

**Flakes are fixed by mechanism or deleted — never skipped, retried, or tuned.**
Classify first: a real bug, a retired behaviour, or a platform problem. Then fix
the mechanism — wait on the event that says the thing happened, not on a clock;
give a test its own daemon, socket and store; assert a condition rather than an
elapsed time. A negative assertion behind a sleep ("it did not exit") is worse
than useless, because a slow runner only ever makes it pass. If a deterministic
unit test already pins the property, delete the racy end-to-end copy instead of
stabilising it.

Keep reusable manual edge-case and debugging models in `models/tests/`, with
reproduction instructions. Despite its name, that folder is never CI input;
see [its manual-validation policy](models/tests/README.md).

For manual skill prompts and model review, work inside this repository and keep
samples and CAD/robot-description artifacts under `models/`. Create a scratch
project in the fixture bucket it belongs in: a standalone part
goes in the `models/examples/` cad-project, an assembly gets its own group in
`models/assemblies/` (`src/<assembly>/`, outputs in `STEP/<assembly>/`), a
drawing goes in `models/drawings/` — script in `src/`, artifact declared into a
format folder. For example:

```bash
$EDITOR models/examples/src/my_test.py     # @step(out="../STEP/my_test.step")
python models/examples/src/my_test.py
```

Then start your agent with `/path/to/text-to-cad` as the working directory and
ask it to write files under that scratch path. This keeps manual model sources,
generated artifacts, and Viewer links together, independently of the automated
test suite.

Review media such as snapshot PNGs are not model artifacts:
render them under `/tmp` and attach them to the pull request instead. `.gitignore`
keeps them out of `models/`.

### Performance changes

A change to cadgen's caching, the store, the rebuild gate, or kernel or publish
performance opens its PR description with a before/after timing table for `main`
and the branch. The table comes from the edit benchmarks in
`scripts/bench/cadgen-performance/` (`agent_edits.py` times these edits end to
end) on representative models, and covers at least a leaf edit, a parent-only
edit, a revert and a no-op. The table names any slowdown as a regression, and a regression merges
only with the repository owner's explicit approval. A change that removes a cache
or a performance mechanism first lists what it made faster. #478 removed the
kernel-op memo for correctness and slowed re-runs (f1's `power_unit` forced
rebuild went from 24 s to 102 s); that cost sat deep in a long PR body instead of
being approved as a trade-off.

## Source Boundaries

A skill must not import another skill or a repository-root module at runtime, and
must not put `skills/`, the repository root, or a sibling skill directory on
`sys.path`, `PYTHONPATH`, `NODE_PATH`, or any similar lookup path. Skills are
independent of *each other*.

They are not independent of `cadgen`. Each cadgen skill's SKILL.md runs that
distribution through the launch command, and a skill's `scripts/<tool>` is a thin
entrypoint whose parser and behaviour live in `cadgen.cli` — so what a published skill
needs is an install, not a copy. Skills used to vendor cadgen and its Node builders into
`skills/*/scripts/packages/`; six copies of one runtime is what that cost, and it
is gone. cadgen now carries the JavaScript it executes as well as the Python.

Canonical source directories are:

- `skills/*` for skill instructions, references, and the thin entrypoints.
- `apps/web/` for the CAD Viewer's React client. Its backend is
  `cadgen.viewer` (in `packages/cadgen`), and its built `dist/` ships inside the
  cadgen wheel as `cadgen/_runtime/viewer` — built at release time, never
  committed.
- `apps/mcp/` for the CAD app agent hosts render (MCP Apps: Codex, Claude Desktop). Its
  server is `cadgen mcp` (`cadgen/mcp` in `packages/cadgen`), and its one-file
  build ships inside the cadgen wheel as `cadgen/_runtime/mcp` — built at
  release time, never committed.
- `apps/docs/` for the site.
- `packages/cadgen/` for the Python distribution and bundled runtime assets.
- `packages/core/` for non-React CAD/client code.
- `packages/ui/` for FileViewer, renderers, controls and shared styles.

One source tree ships whole and must work in isolation outside this repo — the
ships-alone law, enforced by the markdown-isolation check in
`tests/python/global/test_package_boundaries.py`: `packages/cadgen` builds into
the PyPI wheel with @text-to-cad/core and the viewer client bundled in at build time; its
README is the PyPI long description. Markdown under it must be true and
actionable with this repo gone: name the bundled thing ("the @text-to-cad/core runtime
bundled at build time"), never the repo path to its source, and keep commands
relative to the package itself. Repo-development guidance belongs here, not in
the package. `apps/web` is a client package with a boundary of its own
(`apps/web/scripts/selfContained.test.mjs`): it imports @text-to-cad/core and @text-to-cad/ui by their public exports; relative
imports remain inside its directory.

## Working On cadgen In This Repo

- `scripts/test/test-python.sh` (or path-targeted `unittest`) for the engine;
  `tests/python/global/` holds the policy gates that enforce the design laws in
  `packages/cadgen/README.md`.
- Editing anything the bundlers consume? Run `scripts/bundle/bundle.sh` and
  there is nothing to commit: all of `_runtime/` is gitignored, so a JS edit
  shows up in the diff as the shared package source it was made in and reaches a user
  as the wheel the release builds. A rebundle used to add ~1.3 MB of
  `snapshot-render.js` to every commit that touched the renderer.
- `VERSION` at the repo root is canonical; release tooling stamps every
  duplicate. Never hand-edit versions under `packages/`.

## Viewer Development In This Repo

The apps are `docs`, `web` and `codex`. Framework-independent CAD code lives
in `@text-to-cad/core`; `@text-to-cad/ui` owns the complete FileViewer and injectable
renderers. Apps consume compiled public exports. Apps never import another app,
and packages never import apps. `npm run check:boundaries` checks the graph,
including aliases, re-exports and dynamic imports.

Viewer features go in the shared components, so every host receives the same
behavior; apps supply only what the host contract asks of them. The viewer's
tools, sidebars and settings follow the binding design system in
`packages/ui/docs/settings-ui.md`: change it with the chrome, and change the
chrome only through it. Package/app READMEs state the ownership rules.

Install from the repository root, selecting only the workflow being exercised:

```bash
# Python engine/runtime or shared core work:
npm ci --workspace @text-to-cad/core
npm run build --workspace @text-to-cad/core
# Viewer and shared UI work:
npm ci --workspace @text-to-cad/core --workspace @text-to-cad/ui --workspace @text-to-cad/web
npm run build:packages
# Docs work:
npm ci --workspace @text-to-cad/core --workspace cad-skills-docs
npm run build:docs
```

There is one root lockfile. Do not create nested lockfiles or symlink dependency
trees from another checkout. Rebuild shared packages after editing them;
Vite and Next consume their `dist` exports. `npm ci` without a
workspace filter installs the whole workspace.

Create this worktree's `.venv` with `requirements-dev.txt` when Python is
needed. For web development, invoke Vite from the directory you want served:

```bash
cd <the directory to serve>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

Vite owns its API-only Python backend. `VIEWER_PYTHON` must name an interpreter
that satisfies cadgen's Python floor and imports this checkout. The backend's
stable `rootId` identifies a normalized real filesystem root across port
changes. The web app owns URL/history and browser preferences. FileViewer
state is scoped by root, file and renderer; each CAD render session owns its
cache provider and worker lease.

The standalone launcher is `cadgen viewer`. A source checkout can serve the
local web build; `CADGEN_VIEWER_DIST`, `CADGEN_NODE_BUILDERS_DIR` and
`CADGEN_BROWSER_RUNTIME_DIR` are explicit asset overrides. A wheel resolves its
own bundled assets without the repository. Run `scripts/bundle/bundle.sh` after
editing build inputs to refresh all packaged outputs.

The self-contained browser suite creates tiny inputs and owns its project,
viewer and cache. It never reads the sample-model corpus. Install the npm
Playwright Chromium for UI/web tests and Python Playwright's headless shell for
snapshot tests (a snapshot also fetches it on first use); their revisions can differ:

```bash
npx --no-install playwright install chromium
.venv/bin/python -m playwright install --only-shell chromium
scripts/bundle/bundle.sh
scripts/test/test-viewer-browser.sh
scripts/test/test-viewer-browser.sh --only camera
```

Use `--with-deps` when installing browsers on Linux. The browser suite runs
exactly what CI runs: every load path (STEP, STL, DXF, URDF) and the camera
across modes and a saved revision, through the real backend (picking and
kinematics are the `packages/ui` browser specs' on every PR). Backend tests live in
`tests/python/packages/cadgen/viewer` and are selected with
`scripts/test/test-python.sh --select viewer`. Client tests do not cover them.
Nothing in `cadgen.viewer` imports the CAD kernel at module scope.

Launcher reuse keys on realpath(root) and an identity token derived from the
Python runtime and selected built client. Another checkout, a different
`--dist`, or a changed runtime cannot silently reuse a stale instance. A running
instance that detects changed files refuses new model-data requests with a
restart-required response. Never stop an instance you did not start; see
`apps/web/README.md` for ports, reuse and catalog/link behavior.

Production outputs are centralized and ignored by Git:

```bash
scripts/bundle/bundle.sh --clean
scripts/bundle/bundle.sh --check
```

`--clean` removes old runtime outputs before building. `--check` builds and
asserts required Node/browser outputs; wheel validation checks the complete
packaged viewer too. Per-stage `cadgen-runtime.sh` flags are for debugging;
normal iteration goes through `bundle.sh`.

## Branch Layout

`main` is the source tree, what installers clone, and what releases are cut
from. There is no development symlink layout and no generated publish tree:
every path is the real file, and the repository root is itself the agent plugin
package (`.claude-plugin/` and `.codex-plugin/` hold the manifests; the plugin's
skills are `skills/` directly), so whatever is on `main` is what agent
installers copy.

Four consequences are enforced by `scripts/github-workflows/check-builds.sh`
on every push:

- **No tracked symlink, anywhere.** The installers disagree about symlinks and
  one loses data silently: the Skills CLI dereferences them, Claude Code
  preserves them, and Codex `plugin add` drops them with no error at all,
  publishing a skill whose files are simply missing at runtime.
- **No `.gitattributes` rule that changes a file on its way to a user.** No
  `filter`, `ident` or `working-tree-encoding`, which rewrite files at checkout,
  and no `export-ignore` or `export-subst`, which change the archive. So there
  is no Git LFS: installers clone without git-lfs and would receive pointer
  files, and claude.ai's plugin directory validates files as stored and refuses
  a plugin whose installs could differ.
- **Every tracked file under 5 MiB.** Every installer clones the whole
  repository, so a big file costs every user on every install, and claude.ai's
  plugin directory stops validating at 5 MiB; heavyweight media stays out of
  the tree.
- **No skill reaching into a repo root.** `packages/` being present is not
  permission to import from it: the Skills CLI installs `skills/<name>` alone,
  so `../../../packages/` would work in a checkout and break on the first
  `npx skills add`. `tests/python/global/test_skill_self_containment.py` and
  `test_package_boundaries.py` hold the same law.

Every cadgen pin in the tree — the plugin server configs and each skill's launch
command — names `VERSION`. The release PR stamps them with the bump
(`sync-version.mjs`), and `scripts/release/check-version.sh` asserts every skill
pin equals `VERSION` — so a stale pin fails the `Version Check` job.

The `Test` workflow runs on pushes to `main` and PRs against it: it runs
`scripts/bundle/bundle.sh --clean` to produce the runtime, checks the layout
without rebuilding it, runs documentation checks, and runs the code tests
against that generated output. `main` commits no generated runtime at all —
cadgen's Node builders, its snapshot bundle and the Viewer client are built from
`packages/core`, `packages/ui` and `apps/web` on demand, and ship only inside the
wheel. What IS committed and therefore checked for freshness is the version
metadata derived from `VERSION`, asserted by the separate `Version Check` job
(`scripts/release/check-version.sh` and `sync-version.mjs --check`).

## Releases

Normal development PRs should not bump `VERSION`; release versions are reserved
for release PRs so the canonical repo version, the skill pins, the Git tag, the
PyPI wheel and the GitHub Release all describe one commit. PRs that do touch
release state must keep `VERSION`, the derived metadata and the pins valid; the
`Test` workflow checks all three in a separate job so code tests still run when
they are wrong.

### Build artifacts live in the wheel, never in git

`main` is source. Everything cadgen executes that is not Python — the Node
builders and the snapshot browser bundle under `cadgen/_runtime/node` and
`_runtime/browser`, the CAD Viewer client under `_runtime/viewer`, and the file
tracer every build loads under `_runtime/native` (one C file,
`packages/cadgen/native/filetrace.c`, cross-compiled by zig for every platform
into the one wheel; `ziglang` comes with `requirements-dev.txt`) — is
gitignored and produced by `scripts/bundle/bundle.sh`. Nothing built is ever
committed: a rebundle used to add a megabyte of history per commit, and a
committed bundle can drift from the source that claims to produce it.

Where the built things live instead:

- **CI** builds the runtime stages needed by each selected test job and tests
  against that build (`bundle.sh --check` now means "the runtime builds and is
  complete", not a diff against a committed copy).
- **The wheel** is the release artifact. `Publish Release` bundles, builds the
  wheel and sdist, asserts the wheel carries `_runtime/`, installs and
  exercises it, keeps the distribution as a workflow artifact, uploads it to
  PyPI (the install channel every skill pins against), and attaches that same
  wheel and sdist to the GitHub Release as the provenance copy of what shipped.
- **The plugin ZIP** (`cad-openai-plugin-<version>.zip`) is the plugin in the
  layout OpenAI's plugin submission portal takes. It is built from the release
  commit and attached to the GitHub Release beside the wheel. See [Submitting
  the plugin to OpenAI](#submitting-the-plugin-to-openai).
- **The `plugin` branch** is the plugin alone, the folder claude.ai's plugin
  directory follows. See [The plugin branch](#the-plugin-branch).
- **A checkout** builds its own: run `scripts/bundle/bundle.sh` once after
  cloning (and after pulling changes to `packages/core`); a missing runtime
  fails with a message that says so.

### Shipping a release

Two GitHub Actions workflows, one release. `Prepare Release`
(`release-prepare.yml`, manual) is the version bump as a PR; `Publish Release`
(`release-publish.yml`) fires on the push its merge makes and does everything
else to that one commit.

```bash
gh workflow run release-prepare.yml --ref main -f bump=patch
```

`Prepare Release` takes `bump` (`patch|minor|major`), `set_version` (an exact
X.Y.Z instead of a bump), `target` (the branch the PR is opened against —
`main`, or `build-test` to rehearse) and `dry_run`. Choose the bump
deliberately for every release; if a release request does not specify one,
confirm it rather than assuming. It bumps `VERSION`, stamps the derived
metadata and every `cadgen==` pin (`sync-version.mjs`: the plugin server configs
and each skill's launch command), commits on `release/<version>`, opens the PR,
merges it through the API (the PAT, as before — no "allow auto-merge" setting
is involved) and deletes the branch. The merged commit is THE release commit.

`Publish Release`, on that push:

1. `check-version.sh`, then the gate: `VERSION` must be past the latest release
   tag (either spelling — `scripts/release/release-tags.sh` is the one place
   that knows `v0.5.0` and the bare `0.4.28` before it, and it compares
   versions, not tag strings), or equal to it with the tag missing. Then
   `scripts/release/plugin_zip.py` builds the plugin ZIP from the untouched
   release commit and checks it against the portal's package rules, so a
   package the portal would refuse stops the release before anything
   irreversible. The ZIP is kept as a workflow artifact
   (`cad-openai-plugin-<version>`). `scripts/release/plugin_branch.py
   --check` does the same for the tree claude.ai's directory gets.
2. `bundle.sh --clean` — which is where cadgen's whole runtime comes into
   existence, Node builders, snapshot bundle and Viewer client alike, because
   the release commit carries none of it — then `check-builds.sh`, the docs and
   code tests, the wheel-contents check, `python -m build`, and an `unzip -l`
   assertion that the wheel about to ship really holds `_runtime/node`,
   `_runtime/browser`, `_runtime/viewer` and every `_runtime/native` tracer.
3. Install test: the built wheel into a fresh venv — `cadgen --help`, `cadgen
   viewer --help`, `cadgen doctor skills/cad` — then
   `scripts/test/test-installed.sh --wheel <built-wheel>`; the distribution is uploaded as a workflow
   artifact (`cadgen-<version>`).
4. **On `main` only:** PyPI upload (`skip-existing`, so a rerun is a no-op),
   `Deploy Docs`, then the `v<VERSION>` tag and the GitHub Release, with the
   wheel and sdist from that same artifact and the plugin ZIP attached as
   release assets (PyPI stays the install channel; the release page is the
   provenance copy), and the plugin tree committed onto `plugin`.
   Nothing is committed or pushed to `main` after the release PR merge: the tag
   points at the source commit, and `git describe` on `main` is meaningful.

### The plugin branch

`main` is an installable plugin for every host: its root holds every manifest
(`.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `gemini-extension.json`)
and MCP config (`claude.mcp.json`, `codex.mcp.json`, `cursor.mcp.json`), and the
README's install commands use it. claude.ai's plugin directory treats the folder it follows as
the whole plugin, though, so it follows the `plugin` branch instead: on `main`
the monorepo's files, workflows, lockfile and binaries would all be held for a
reviewer, and every install would copy them. `Publish Release` writes `plugin` on
each release: one commit whose tree is `.claude-plugin/plugin.json` and
`icon.png`, `.cursor-plugin/plugin.json`, `gemini-extension.json`,
`claude.mcp.json` and `cursor.mcp.json` (the CAD server the manifests name),
`skills/`, `LICENSE` and `README.md`, with each README link to a file outside
that tree pointed at the release commit on GitHub. A Cursor install by hand
clones this branch too (the README's `git clone --branch plugin`). A release whose plugin did not change adds no commit.
The tree is checked against claude.ai's file rules
(<https://claude.com/docs/plugins/pre-submission-checklist>) by
`tests/python/global/test_plugin_branch.py` on every pull request and again
before each release.

What each store and installer reads:

| Where | Reads |
| ----- | ----- |
| claude.ai's directory | the branch the listing tracks: still `claude-plugin`, the old name, so `Publish Release` pushes the same commit there too |
| Cursor Marketplace | the repository's default branch, `main`: its submission takes a repository, not a branch |
| OpenAI's plugin portal | the plugin ZIP a person uploads from the GitHub Release |
| Claude Code, Codex, Grok Build | `main`, unless the command names a ref (`owner/repo@ref` for Codex and Grok) |
| Gemini CLI | the latest GitHub Release: with no Gemini archive among its assets, it takes the release's source tarball, so a new manifest reaches Gemini with the next release. A release with a single asset would be taken as the extension, so keep shipping the wheel and sdist beside the ZIP |
| Skills CLI and skills.sh | `main` |

Each plugin's CAD server startup command says where its installs come from, its
install channel (`--channel`), and adds `--auto-updated` where something other
than the person keeps the copy up to date: the store that reviewed it, or the app
that installed it. The server hands both on to the processes it starts (the
Viewer, the daemon). cadgen reports the channel with analytics and says a new
release is out only to a copy that is not auto-updated (`cadgen/_internal/channel.py`,
`cadgen/updates.py`); it never decides by a channel's name, since its core may not
know a host. Nothing works them out at runtime, so a plugin that ships somewhere
new writes its own, and the analytics receiver (`apps/docs/src/lib/api/events.mjs`)
learns its channel; `test_plugin_manifests.py`, `test_plugin_branch.py` and
`test_plugin_zip.py` hold each one:

| Package | Startup command says | Told of a release | Written by |
| ------- | -------------------- | ----------------- | ---------- |
| `main`'s `claude.mcp.json` (Claude Code, Grok Build, and Cursor through Claude Code's plugins) | `--channel claude-github` | yes | the checked-in file |
| `main`'s `codex.mcp.json` | `--channel codex-github` | yes | the checked-in file |
| `main`'s `gemini-extension.json` | `--channel gemini-github --auto-updated` | no: Gemini updates it | the checked-in file |
| the README's Claude Desktop config | `--channel claude-desktop` | yes | the README |
| `main`'s `cursor.mcp.json`, which the Cursor Marketplace reads | `--channel cursor-marketplace --auto-updated` | no: its store updates it | the checked-in file |
| the `plugin` branch's `claude.mcp.json`, which claude.ai's directory follows | `--channel claude-directory --auto-updated` | no: its store updates it | `plugin_branch.py` |
| the `plugin` branch's `cursor.mcp.json`, which a Cursor install by hand clones | `--channel cursor-github` | yes | `plugin_branch.py` |
| the OpenAI ZIP's `.mcp.json` | `--channel openai-directory --auto-updated` | no: its store updates it | `plugin_zip.py` |
| a development install | `--channel dev` | no | `dev_install.py` |
| a process no plugin's server started: a skill's command, the Viewer a skill opens | nothing (`unknown`) | the Viewer: a skills-only install | nothing |

A skill's own `cadgen` command never says a release is out: the same skill files
ship in every plugin, so it cannot tell which one it came with. The CAD app and
the Viewer say it.

**Dev note — retire `claude-plugin`.** The portal refuses a tracked-branch change
while a reviewer has the plugin. Once the claude.ai listing is out of review,
set its **Branch or tag** to `plugin` on the Settings tab, then remove the
`claude-plugin` push from `release-publish.yml`'s `plugin-branch` job and delete
the `claude-plugin` branch.

### Submitting the plugin to OpenAI

The plugin directory shared by ChatGPT and Codex takes plugins only through the
web portal at <https://platform.openai.com/plugins>. OpenAI documents no API or
CLI for uploading, submitting or publishing, so CD cannot do it and no secret is
involved. What CD does is build the file to upload: each GitHub Release carries
`cad-openai-plugin-<version>.zip`. It holds the plugin at the archive's root,
each folder with its own entry: `.codex-plugin/` (manifest and icons), `skills/`,
`LICENSE`, and every file the manifest points at. (The portal turned away 0.7.6's
first ZIP, one top-level `cad/` folder with no directory entry of its own, as
holding no plugin.) The portal requires `mcpServers` to resolve to a root
`.mcp.json`, so a server config the checkout keeps under another name is
archived as `.mcp.json`, and the archived manifest points there. That config
names `openai-directory` as its install channel, as its server's `--channel`,
with `--auto-updated`: the directory updates its copies.

For each release, a person with the access below:

1. Downloads `cad-openai-plugin-<version>.zip` from the release page.
2. On the Plugins page, opens the text-to-cad plugin, selects **Upload plugin
   to make changes**, and uploads the ZIP. The first submission uses **Upload
   new or existing plugin** instead.
3. Resolves the automated findings, selects **Submit for review**, and completes
   the policy attestations.
4. After approval, selects **Publish plugin**.

One-time setup, in the OpenAI Platform organization that owns the plugin:
complete individual or business verification under
<https://platform.openai.com/settings/organization/general>. Submitting needs an
organization owner, or a member granted **Apps Management Write**
(`api.apps.write`).

`python3 scripts/release/plugin_zip.py --check` runs the same checks locally;
`--out PATH` also writes the ZIP. `tests/python/global/test_plugin_zip.py` runs
them on every pull request that touches the plugin. The checks are the portal's
documented package rules
([submission errors](https://developers.openai.com/plugins/deploy/submission-errors)),
with the final-submission listing limits, such as 30 characters for the name and
subtitle. A missing `interface.logo` or `interface.composerIcon` is a warning,
not an error, but the portal refuses the upload without them. The portal's own
skill and policy scans still run after upload.

### The version feed

cadgen's daily version check reads `api.texttocad.dev/v1/versions`
(`apps/docs/src/lib/api/versions.mjs`): `latest` is the docs app's version,
which the release PR stamps from `VERSION`, and `Publish Release` deploys the
docs after the PyPI upload, so the feed names a release only once it can be
installed. Only a copy nothing else updates reads it (its channel, "The plugin
branch" above): a store's copy (the Claude or OpenAI directory, the Cursor
Marketplace) and Gemini's extension never check and are never told, since their
store or Gemini updates them. A change to the analytics schema (`schema.sql`) is run on the database
before the deploy that ships it (`apps/docs/README.md`).

### Resuming and republishing

Dispatch `Publish Release` on `main`:

```bash
gh workflow run release-publish.yml --ref main            # or -f publish=false for a draft
```

It runs against the current head. A run that uploaded the wheel and failed
before the tag or the docs deploy is finished this way — the PyPI upload is
idempotent and the tag is still missing, so the gate lets it through. A head
whose version is already tagged skips at the gate. There is no `bump=none`: a
version that needs re-preparing goes through `Prepare Release` again.

### Rehearsing on `build-test`

`build-test` is a long-lived branch whose only job is to run `Publish Release`
without side effects. Every push to it (including a rehearsal release PR merge)
runs the full pipeline through the install test and the artifact upload, then
prints what it WOULD have uploaded, deployed and tagged
(`publish-github-release.sh --dry-run`) and stops. To rehearse a release:

```bash
git push origin main:build-test                                    # or any branch under test
gh workflow run release-prepare.yml --ref main -f bump=patch -f target=build-test
```

The gate compares the rehearsal's `VERSION` against the repository's REAL tags,
exactly as `main` would — that is the intended behaviour: a rehearsal bump
passes the gate and exercises everything, while an unbumped push to
`build-test` (say, a pipeline fix) skips at the gate with the same message
`main` would give. A rehearsal consumes that version number on `build-test`
only; `main` and the tags are untouched, so the real release re-uses it. `Test`
also runs on `build-test` pushes and PRs. `dry_run=true` on `Prepare Release`
stops after printing the version diff, for changes to the preparation itself.

### Redeploying the docs site

`Deploy Docs` (`.github/workflows/deploy-docs.yml`) redeploys without a
release, from a ref that defaults to `main`:

```bash
gh workflow run deploy-docs.yml -f ref=main
gh workflow run deploy-docs.yml -f ref=v0.5.0  # a past release: its tag
```

### Local and manual fallbacks

After bundling, `scripts/release/check-wheel-contents.sh` builds from a clean
temporary package copy and verifies that every bundled runtime file is present
with identical bytes, with no obsolete assets left in the wheel. It leaves the
checkout's build scratch untouched. Set `CADGEN_WHEEL_OUT_DIR` and
`CADGEN_KEEP_WHEEL=1` to retain that checked wheel for an installed smoke test.

For local release preparation, use the same scripts the workflow calls:

```bash
git fetch --tags origin
scripts/release/bump-version.sh patch
node scripts/release/sync-version.mjs
scripts/release/check-version.sh --incremented-from "refs/tags/$(source scripts/release/release-tags.sh && latest_release_tag)"
node scripts/release/sync-version.mjs --check
```

`scripts/release/publish-github-release.sh` is the manual fallback for the tag
and GitHub Release step. Unlike `Publish Release`, the script creates a
draft release unless `--publish` is passed.

### Repository settings

`main` requires a PR with eight stable status checks — `Version
Check`, `cadgen (Linux)`, `cadgen (Windows)`, `core-js`, `web`, `skills`,
`docs`, `packaging` — strict (up to date with `main`), squash merges only, a
linear history, no force pushes and no deletions. A job skipped by its path
condition satisfies its check, so a prose pull request merges on Version Check
alone. Changing required check names also requires updating GitHub branch
protection.
`Prepare Release`'s PR merges through the same checks via the API (no "allow auto-merge"
repository setting is needed). `build-test` needs no protection: the
irreversible steps never run there. Keep the repository tag
ruleset (extend its pattern to cover `v[0-9]*.[0-9]*.[0-9]*` beside the bare
form) and immutable releases.

Dependency updates arrive as Dependabot PRs (`.github/dependabot.yml`: weekly,
one grouped PR per ecosystem for minor + patch bumps, labelled `dependencies`
so they land in the release notes' Maintenance category).

### Source-tree history

Before 0.5.0, `main` held a generated publish tree copied from `develop`.
The source-tree cutover landed on 2026-09-04 in commit `3eb1f9b8a`; the
original granular source history remains at `history/0.5.0-source`.
The old publish transformation and mirror workflow are retired. Use the
current release workflow above for future releases.

## Iteration Loop

1. Edit the relevant skill under `skills/<skill-name>/`.
2. Keep skill instructions narrow and executable: say when the skill applies,
   what inputs it expects, what it produces, and how to validate the work.
3. Prefer small files in `references/` and reusable scripts in `scripts/` over
   long inline instructions.
4. Add or update focused fixtures or tests when skill behavior changes so
   regressions are measurable.
5. Validate with the smallest relevant check before broad repo checks.

Generated artifacts should not become skill logic unless they are intentional
fixtures. Prefer source files plus deterministic regeneration.

## Common Dev Checks

Use path-targeted validation. Common checks from the repo root:

```bash
scripts/test/test.sh
scripts/release/check-version.sh
scripts/bundle/bundle.sh --check          # the packaged runtime builds, whole
npm --prefix apps/web run test        # the Viewer's CLIENT half only
scripts/test/test-python.sh              # includes the Viewer's BACKEND suite
scripts/test/test-python.sh --select viewer   # the Viewer's backend alone (~11 s)
npm --prefix apps/docs run check
```

Use `AGENTS.md` or `scripts/README.md` for path-specific validation when you are
working in a particular package, skill, docs site, or production-output
path.

For targeted Python skill-script tests, run the relevant unittest files with the
repo-local Python runtime, for example:

```bash
./.venv/bin/python -m unittest tests/python/skills/urdf/test_cli.py
```

Repo-owned Python tests live under `tests/python/`, grouped by tested surface:
`skills/<skill>`, `packages/<package>`, and `global`. The CAD Viewer backend's
suite is `tests/python/packages/cadgen/viewer/`, part of the cadgen package suite.

For fast CAD Viewer source iteration, build the shared packages, then invoke
the web app in dev mode from the directory you want to serve (outside
`apps/web`). The app consumes source with HMR while shared packages resolve to
their compiled exports:

```bash
cd <the directory to serve>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

The spawned backend serves one root, fixed at startup. Its resolver accepts an
explicit `directoryRoot` from its caller first, then `INIT_CWD`, then the
process working directory, skipping the latter two when they are inside
`apps/web`. Vite's fallback is `<checkout>/apps`. npm sets `INIT_CWD` to the
invocation directory, so `--prefix` selects the app while retaining your chosen
root. The page is the bare origin and `?file=` names an artifact relative to
that root, for example `http://127.0.0.1:5173/?file=STEP/part.step` when the
served directory contains `STEP/part.step`.

Vite defaults to port 5173 and fails if it is taken; select another with
`--port`. See [the app's launcher contract](apps/web/README.md#launching) for
development and external-backend options. Packaged Viewer runtime checks are
production-output checks; use `scripts/README.md` when you specifically need
that path.

## Git Hygiene

Do not commit local environments, dependency folders, caches, or temp files such
as `.venv/`, `node_modules/`, `.vite/`, `dist/`, `tmp/`, or local credentials.
Generated runtime changes should come from the production-output workflow, not
manual edits inside generated runtime folders.

The repository carries no Git LFS and keeps every file under 5 MiB (see the
shipping contract above), so heavyweight media never goes in the tree.
