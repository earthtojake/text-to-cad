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
`dev` (`CADGEN_INSTALL_CHANNEL`), and a checkout's editable cadgen counts as one
too: neither is ever offered an update. To see the update button, run a server or
a Viewer with `CADGEN_INSTALL_CHANNEL=claude-github` and a `versions.json` in its
state directory (`CADGEN_STATE_DIR`) naming a newer `latest`.

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

`test.yml` runs one job per concern, and a change runs only what can break.
Its first job, `Changed paths`, puts every path the change touches — added,
modified or deleted, against the target branch as it is now — through
`scripts/github-workflows/select_checks.py`: a table of the tests that READ each
path (open it, scan it, import it, build it or run it). A path selects the union
of every rule it matches; the jobs run on the result, and the Python jobs run
only the test files it names. A path the table does not know runs everything,
as do `VERSION` (a release is tested whole), the test machinery (`test.yml`,
`setup-deps`, `select_checks.py`, the runners' shared parts) and the dependency
manifests. A manual dispatch runs every job. Selection is by path, never by
diff content: a comment in a module selects what the module's code would.

| Check | Runs when a change reaches | What it runs |
| --- | --- | --- |
| Version Check | every change | canonical version, derived metadata, cadgen pins, the shipping contract's tree rules; on a pull request, what merging it releases (see [Shipping a release](#shipping-a-release)) |
| cadgen (Linux/Windows) | `packages/cadgen`, `scripts/bundle`, a cadgen test, prose a cadgen test reads | the cadgen package suite, CAD Viewer backend included; for a change confined to the Viewer's backend or the CAD app's server (`cadgen/viewer`, `cadgen/mcp` and the commands that start them), only the tests that name them or read all of cadgen; for a test file, that file |
| core-js | `packages/core` (and with it everything), `test-js.sh` and the dependency checks, `apps/docs/src` (the dependency check walks it), the viewer-memory helpers | `@text-to-cad/core`'s units, the dependency and kit-boundary checks, the benchmark helper units |
| web | `packages/ui`, `apps/web` and the files its Markdown links to, `packages/cadgen` and `scripts/bundle`, `tests/browser`, the viewer scripts | the UI's units and browser specs (ui changes only), the client's units, then the bundle, the launch smoke test and the format/camera gates through the real backend (anything the served client or the backend reads) |
| mcp | `apps/mcp`, `packages/ui`, `test-js.sh` | the CAD app's host-adapter units (jsdom) and its one-file build |
| skills | every change | first, with only Python and Node: the light contracts (every policy test that reads the repository's text, and the gcode, sendcutsend and step-parts suites); then, after the full install, the policy tests that load cadgen or its runtime (`packages/cadgen`, `scripts/bundle`), the cad and dxf suites (the same, and each skill's documented examples), dfm and dfam-check (their skills) |
| docs | `apps/docs`, `scripts/brand`, `test-docs.sh` | `npm --prefix apps/docs run check` (static asset contract, the analytics receiver's tests, lint, Next build, icon verification) and the animated brand marks |
| packaging | `packages/cadgen`, `packages/ui`, `apps/web`, `apps/mcp`, `scripts/bundle`, the wheel and install scripts | clean bundle, layout, wheel contents, installed CLI behavior |

Everything runs for `VERSION`, `package.json`, `package-lock.json`,
`requirements-dev.txt`, `packages/core`, `scripts/build`, `tests/python/support`,
the workflow, `setup-deps`, the selector and the runners' shared parts, and any
path the table does not name. Prose inside a code tree (`packages/**/*.md`,
`apps/**/*.md`) is read by the light contracts alone — except cadgen's README,
the wheel's description, and `apps/web`'s Markdown, whose links its tests
resolve. Root prose, the plugin manifests and configs, the release scripts and
`models/` run the light contracts and nothing else.

Adding a test that reads a new path means adding the path to the test's rule in
`select_checks.py`; `tests/python/global/test_ci_workspace_selection.py` holds
the table to the tree: every policy test that is not a light contract is
selected by some rule, every test path a rule names exists, every rule matches a
tracked file, and the routing of each kind of change is pinned. Each job installs only what its selected tests
need: npm workspaces by job, Python and the two Playwright browsers on request,
and nothing beyond Python and Node for the light contracts (every policy test
but the selector's `HEAVY_POLICY`, and its `LIGHT_SKILL_TESTS`).

Every run records the tree it tested as an artifact, `tested-<tree>-<scope>`
(`scope` is `full` or a digest of the selection). A push to `main` whose tree
its pull request's run already tested with the same selection runs nothing
again — `main` merges only up-to-date branches, so that is every ordinary merge
— and `Publish Release` ships a release commit without re-testing it when a run
here tested its tree in full (`scripts/github-workflows/tested_tree.py`: a
successful run of this repository, never a fork's).

A skipped job satisfies its required check. Renaming a job renames its required
check, so it lands together with a matching branch-protection update.

Every job has a timeout of about twice its slowest recent run, so a hang fails
in minutes. Within a Python suite, a test file still running after 15 minutes
prints every thread's stack and fails by name.

The CAD Viewer's backend and the CAD app's server are leaves of cadgen:
outside them and the commands that start them, nothing in cadgen imports either
but `cadgen.viewer.recents`. `test_viewer_and_mcp_boundary.py` holds that, so a
change confined to one of them can run the cadgen tests that reach it instead of
the whole suite. Windows runs the Python package suite because paths, locks,
subprocesses, file URLs and daemon behavior are platform-sensitive.

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
needed. For web development, invoke Vite from a folder of models (a relative
`?file=` resolves against it):

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

Vite owns its API-only Python backend (`--new`: a port of its own). `VIEWER_PYTHON`
must name an interpreter that satisfies cadgen's Python floor and imports this
checkout. The backend opens any file by its absolute path. The web app owns
URL/history and browser preferences. FileViewer
state is scoped by file and renderer; each CAD render session owns its
cache provider and worker lease.

The standalone launcher is `cadgen viewer`: on port 3245, or the port `--port N`
names, as any web server; on that port a viewer of the same code is reused and one
of other code replaced. A source
checkout can serve the local web build; `CADGEN_VIEWER_DIST`, `CADGEN_NODE_BUILDERS_DIR` and
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
command — names `VERSION`. `scripts/release/bump-version.sh` stamps them with the
bump (`sync-version.mjs`), and `scripts/release/check-version.sh` asserts every
skill pin equals `VERSION` — so a stale pin fails the `Version Check` job.

The `Test` workflow runs on PRs against `main` and pushes to it, selecting
the jobs each change can break ([CI](#ci)); a push whose tree its pull request
already tested runs nothing again, and the `packaging` job builds the runtime
from clean with `scripts/bundle/bundle.sh --clean` and checks the layout and the
wheel. `main` commits no generated runtime at all —
cadgen's Node builders, its snapshot bundle and the Viewer client are built from
`packages/core`, `packages/ui` and `apps/web` on demand, and ship only inside the
wheel. What IS committed and therefore checked for freshness is the version
metadata derived from `VERSION`, asserted by the separate `Version Check` job
(`scripts/release/check-version.sh` and `sync-version.mjs --check`).

## Releases

A pull request that changes `VERSION` is a release: merging it starts `Publish
Release`, which uploads the wheel to PyPI and only then moves the branches
installers follow, so the canonical repo version, the skill pins, the Git tag,
the PyPI wheel and the GitHub Release all describe one commit. Normal
development PRs leave `VERSION` alone. A PR that touches release state must keep
`VERSION`, the derived metadata and the pins valid; `Test`'s Version Check job
checks all three, apart from the code tests, so those still run when they are
wrong.

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
- **The install branches** (`install`, and `claude-plugin` for claude.ai's
  directory) are the plugin alone, the trees installers take. See
  [The install branches](#the-install-branches).
- **A checkout** builds its own: run `scripts/bundle/bundle.sh` once after
  cloning (and after pulling changes to `packages/core`); a missing runtime
  fails with a message that says so.

### Shipping a release

Merging a pull request that changes `VERSION` releases it: `Publish Release`
(`release-publish.yml`) runs on that merge. Installers never take `main` as the
plugin: they follow the `install` branch (see
[The install branches](#the-install-branches)), which `Publish Release` moves
only once PyPI serves the wheel. A cadgen pin must never reach anything an
installer tracks before PyPI has that wheel. When installers took `main`, anyone
who updated between a release's merge and its upload got a CAD server that would
not start (`uvx … --from cadgen==0.7.14` → "there is no version"), for the 25
minutes the release took to reach PyPI.

A release pull request comes one of two ways. Choose the bump deliberately for
every release; if a release request does not specify one, confirm it rather
than assuming.

**Its own pull request**, to release what `main` already has: dispatch
`Prepare Release` (`release-prepare.yml`).

```bash
gh workflow run release-prepare.yml --ref main -f bump=patch     # or minor, major; -f set_version=X.Y.Z
```

It runs `bump-version.sh` on a fresh `release/X.Y.Z` branch from `main` and
opens that pull request with `PREPARE_RELEASE_TOKEN`: a pull request the
workflow's own token opens starts no workflows, so no check would ever run on
it. It never merges anything: merge the pull request once its checks pass, and
that merge releases it. `-f dry_run=true` shows the version changes and opens
nothing.

**On the pull request that should carry it**, a feature branch whose merge
should be the release:

```bash
git fetch origin && git merge origin/main      # the bump is relative to main's VERSION
scripts/release/bump-version.sh patch           # or minor, major, or an exact X.Y.Z
```

`bump-version.sh` sets `VERSION`
past `main`'s and stamps the derived metadata and every `cadgen==` pin
(`sync-version.mjs`: package, plugin and lockfile versions, the plugin server
configs, each skill's launch command). It works from `main`'s version, not the
branch's, so running it twice changes nothing and running it again after `main`
moves moves the bump with it; it refuses a branch that does not contain `main`
yet, whose stamps would conflict.

The pull request's Version Check says what merging it releases, and refuses:

- a bump from a fork — releases come from branches of this repository only, so
  a contributor's pull request can never start one;
- a version that is not past the target branch's and the latest release tag's;
- stamps out of step with `VERSION` (`check-version.sh`,
  `sync-version.mjs --check`).

A `VERSION` change runs every `Test` job (see [CI](#ci)), so the release is
tested whole, Windows included, before it can merge. Merge it once everything is
green: that is the release. `Publish Release`, on the merge commit:

1. **Gate.** `check-version.sh` and `sync-version.mjs --check`, and `VERSION`
   must be past the latest release tag (either spelling —
   `scripts/release/release-tags.sh` is the one place that knows `v0.5.0` and
   the bare `0.4.28` before it, and it compares versions, not tag strings).
2. **Tested?** Every `Test` run records the tree it tested
   (`tested-<tree>-<scope>`), and `scripts/github-workflows/tested_tree.py`
   finds the record of a completed, successful `Test` run of this repository
   (never a fork's) that ran every job on exactly this tree: the pull request's
   own, since `main` merges only an up-to-date pull request. Then nothing is
   tested again. Without one, the workflow calls `test.yml` with `full` on the
   release commit and publishes only if every job passes. No untested tree is
   published either way.
3. **Build.** `scripts/release/plugin_zip.py` builds the plugin ZIP from the
   untouched release commit and checks it against the portal's package rules,
   so a package the portal would refuse stops the release before anything
   irreversible; the ZIP is kept as a workflow artifact
   (`cad-openai-plugin-<version>`). `scripts/release/plugin_branch.py --check`
   does the same for both copies of the plugin the install branches get. Then
   `bundle.sh --clean` — which is where cadgen's whole runtime comes into
   existence, Node builders, snapshot bundle and Viewer client alike, because
   the release commit carries none of it — `check-builds.sh`, the
   wheel-contents check, `python -m build`, and an `unzip -l` assertion that
   the wheel about to ship really holds `_runtime/node`, `_runtime/browser`,
   `_runtime/viewer` and every `_runtime/native` tracer.
4. **Install test.** The built wheel into a fresh venv — `cadgen --help`,
   `cadgen viewer --help`, `cadgen doctor skills/cad` — then
   `scripts/test/test-installed.sh --wheel <built-wheel>`; the distribution is
   uploaded as a workflow artifact (`cadgen-<version>`).
5. **PyPI** (on `main` only), with `skip-existing`, so a rerun is a no-op. Then
   the job waits until PyPI's simple index, which uv resolves a pin through,
   lists the version: usually seconds.
6. **Install branches** (on `main` only). `plugin_branch.py` commits the plugin
   alone onto `install` (and `plugin`, its old name) and `claude-plugin`. Only
   now does an installer see the version.
7. **Announce** (on `main` only), after the branches: `Deploy Docs`, which moves
   the version feed that tells installs a release is out; and the `v<VERSION>`
   tag and the GitHub Release, with the wheel and sdist from that same artifact
   and the plugin ZIP attached as release assets (PyPI stays the install
   channel; the release page is the provenance copy).

`main` has the new pins from the merge on, a few minutes before PyPI has the
wheel. Only an install of `main` itself sees that: the Skills CLI or Grok
without the branch, and the Cursor Marketplace, which takes the repository.

When two pull requests bump at once, the first merged wins. The other then
conflicts on the stamps if it bumped differently (take `main`'s side and run
`bump-version.sh` again) or quietly stops changing `VERSION` if it bumped the
same way — its Version Check then says it releases nothing; bump again to
release it.

### The install branches

Installers clone a branch and take its tree as the plugin. On `main` that tree
is the monorepo: a Claude Code install copied all of it into its plugin cache
and ran an npm install of the workspace, 1 GB per install, and claude.ai's
directory would hold its workflows, lockfile and binaries for a reviewer. `main`
also has a release's pins from the merge on, before PyPI has the wheel. So
installers follow branches only `Publish Release` writes, once the release is on
PyPI: one commit per release whose tree is only the plugin
(`scripts/release/plugin_branch.py`) — `.claude-plugin/plugin.json` and
`icon.png`, `.cursor-plugin/plugin.json`, `gemini-extension.json`, the MCP
configs the manifests name, `skills/`, `LICENSE` and `README.md`, with each
README link to a file outside that tree pointed at the release commit on GitHub.
A release whose plugin did not change adds no commit. There are two copies:

- `install`, for every installer that clones a branch. It also carries the
  marketplace catalog, whose entry names the branch itself, and Codex's manifest
  and config. `plugin`, its old name, gets the same commit, for the Cursor
  installs that cloned `plugin` before `install` existed. `install` grew out of
  `plugin`, so their pulls fast-forward.
- `claude-plugin`, which claude.ai's directory listing tracks. Its
  `claude.mcp.json` names the directory as its channel and marks its copies
  auto-updated (below).

`main` stays an installable plugin, every manifest and MCP config at its root,
for development installs (`scripts/install/dev_install.py`) and for a command
that names no branch. Both trees are checked against claude.ai's file rules
(<https://claude.com/docs/plugins/pre-submission-checklist>) by
`tests/python/global/test_plugin_branch.py` on every pull request and again
before each release.

What each store and installer reads:

| Where | Reads |
| ----- | ----- |
| Claude Code, Codex | the catalog on `main` (`earthtojake/text-to-cad`), whose plugin entry names the `install` branch (`"source": {"source": "url", …, "ref": "install"}`), so the plugin comes from `install`. Claude Code's update fetches the branch. Codex's `marketplace upgrade` reinstalls from it whenever `main` has moved, and its background refresh reinstalls when the catalog's version differs from the installed one, so the catalog keeps its stamped version |
| Grok Build | `install` (`earthtojake/text-to-cad@install`; its registry keeps the ref); `main` without it |
| Gemini CLI | `install` (`--ref install`, kept for its updates). Without the ref, the latest GitHub Release: with no Gemini archive among its assets, it takes the release's source tarball, the whole repository. A release with a single asset would be taken as the extension, so keep shipping the wheel and sdist beside the ZIP |
| Skills CLI and skills.sh | `install` (`earthtojake/text-to-cad#install`; the lock file keeps the ref for updates); `main` without it |
| Cursor, by hand | `install` (`git clone --branch install`) |
| claude.ai's directory | `claude-plugin` |
| Cursor Marketplace | the repository's default branch, `main`: its submission takes a repository, not a branch |
| OpenAI's plugin portal | the plugin ZIP a person uploads from the GitHub Release |

Each plugin's CAD server startup config says where its installs come from, its
install channel, in the server's environment (`CADGEN_INSTALL_CHANNEL`), and adds
`CADGEN_AUTO_UPDATED=1` where something other than the person keeps the copy up to
date: the store that reviewed it, or the app that installed it. The processes the
server starts (the Viewer, the daemon) inherit both. cadgen reports the channel
with analytics and says a new release is out only to a copy that is not
auto-updated (`cadgen/_internal/channel.py`, `cadgen/updates.py`); it never
decides by a channel's name, since its core may not know a host. They are
environment, never flags: an install of `main` pins the last release, and a cadgen
ignores a variable it does not know but refuses a flag, so a new setting would
stop every such server until the next release. Nothing works them out at
runtime, so a plugin that ships somewhere new writes its own, and the analytics
receiver (`apps/docs/src/lib/api/events.mjs`) learns its channel;
`test_plugin_manifests.py`, `test_plugin_branch.py` and `test_plugin_zip.py`
hold each one:

| Package | Server environment | Told of a release | Written by |
| ------- | ------------------ | ----------------- | ---------- |
| `claude.mcp.json` on `main` and `install` (Claude Code, Grok Build, and Cursor through Claude Code's plugins) | `claude-github` | yes | the checked-in file |
| `codex.mcp.json` on `main` and `install` | `codex-github` | yes | the checked-in file |
| `gemini-extension.json` | `gemini-github`, auto-updated | no: Gemini updates it | the checked-in file |
| the README's Claude Desktop config | `claude-desktop` | yes | the README |
| `main`'s `cursor.mcp.json`, which the Cursor Marketplace reads | `cursor-marketplace`, auto-updated | no: its store updates it | the checked-in file |
| `install`'s `cursor.mcp.json`, which a Cursor install by hand clones | `cursor-github` | yes | `plugin_branch.py` |
| `claude-plugin`'s `claude.mcp.json`, which claude.ai's directory follows | `claude-directory`, auto-updated | no: its store updates it | `plugin_branch.py` |
| the OpenAI ZIP's `.mcp.json` | `openai-directory`, auto-updated | no: its store updates it | `plugin_zip.py` |
| a development install | `dev` | no | `dev_install.py` |
| a process no plugin's server started: a skill's command, the Viewer a skill opens | none (`unknown`) | the Viewer: a skills-only install | nothing |

A skill's own `cadgen` command never says a release is out: the same skill files
ship in every plugin, so it cannot tell which one it came with. The CAD app and
the Viewer say it.

**Dev note — `plugin`.** It serves only the Cursor installs that cloned it before
`install` existed. Once those have moved, drop it from the `branches` job's push
in `release-publish.yml` and delete the branch. claude.ai's listing stays on
`claude-plugin`: the portal refuses a tracked-branch change while a reviewer has
the plugin, and that copy is the directory's anyway.

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
names `openai-directory` as its install channel, auto-updated, in the server's
`env`; the portal's acceptance of `env` is confirmed at the first upload that
carries it.

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

A run that stopped — say the upload went through and the branches push failed —
is finished by dispatching it:

```bash
gh workflow run release-publish.yml --ref main            # or -f publish=false for a draft
```

That publishes the commit on `main` that last moved `VERSION` — the release
commit, not whatever merged after it — if that version has no tag yet. The
release commit holds the pull request's tested tree, so its record is found and
nothing is tested again (a run that tested a commit itself records it inside
its own run, which does not count, so a resume of one tests again). A dispatch
uses the workflow file on `main`, so a fix to `release-publish.yml` itself
applies to the resume; a fix anywhere else in the tree ships with a new bump,
since the resume builds the release commit as it was. The PyPI upload is
idempotent. A version whose tag exists skips at the gate. A failed docs deploy
is redeployed on its own (see
[Redeploying the docs site](#redeploying-the-docs-site)).

### Rehearsing on `build-test`

`build-test` is a long-lived branch whose only job is to run `Publish Release`
without side effects: there it builds and installs, uploads and pushes nothing,
and prints what it WOULD have uploaded, deployed and tagged
(`publish-github-release.sh --dry-run`). To rehearse a release, reset the
branch, open a bump against it, and merge that:

```bash
git push --force origin main:build-test     # build-test is throwaway; a past rehearsal leaves it ahead
gh workflow run release-prepare.yml --ref main -f bump=patch -f target=build-test
```

Or bump a branch of `build-test` by hand
(`bump-version.sh patch --base origin/build-test`) and open its pull request
against `build-test`. The gate compares the rehearsal's `VERSION` against the
repository's REAL tags, exactly as `main` would: a rehearsal bump passes the
gate and exercises everything. A rehearsal consumes that version number on
`build-test` only; `main` and the tags are untouched, so the real release
re-uses it.

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

To check a bump locally the way the gate and Version Check will:

```bash
git fetch --tags origin
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
linear history, no force pushes and no deletions. A job its selection skips
satisfies its check, so a prose pull request merges on Version Check and the
light contracts. Changing required check names also requires updating GitHub
branch protection. Strict up-to-date is what makes a merged tree the tree its
pull request's run tested, so the push run and `Publish Release` find that run's
record and test nothing again; a merge that is not up to date is still tested,
by both.
`PREPARE_RELEASE_TOKEN` is a personal access token, so that the release pull
requests `Prepare Release` opens start their checks. It needs Contents and Pull
requests write on this repository; nothing merges with it, so it need not be an
admin's.
`build-test` needs no protection: the irreversible steps never run there, and
neither do the install branches need it: `Publish Release` is their only writer. Keep
the repository tag ruleset (extend its pattern to cover `v[0-9]*.[0-9]*.[0-9]*`
beside the bare form) and immutable releases.

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
the web app in dev mode from a folder of models (outside `apps/web`). The app
consumes source with HMR while shared packages resolve to their compiled exports:

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

The spawned backend opens any file by its absolute path; the folder it starts
in is only where a relative `?file=` resolves. Its resolver takes `INIT_CWD`, then
the process working directory, skipping either when it is inside `apps/web`. Vite's
fallback is `<checkout>/apps`. npm sets `INIT_CWD` to the invocation directory,
so `--prefix` selects the app while keeping your folder. The page is the bare
origin and `?file=` names a file, for example
`http://127.0.0.1:5173/?file=/abs/models/STEP/part.step`, or
`?file=STEP/part.step` from `/abs/models`.

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
