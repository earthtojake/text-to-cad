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

The Python side is a [uv](https://docs.astral.sh/uv/) project: the root `pyproject.toml` is a
workspace whose one member is `packages/cad`, and `uv.lock` beside it pins every package the
development environment holds, for contributors and CI alike. Install uv, then run `uv sync`
once in the checkout (and again after a pull that changes the lock); `uv run <command>` runs a
command in that environment, `.venv`. Use Python 3.14, the Python the server's installations run
on (`uv sync --python 3.14`, which fetches it when it is missing); the packages' floor is 3.11
(`requires-python`), which CI holds with the library's, the server's and the transport's suites on
it before a release ships ([CI](docs/contributing/testing.md#ci), the release tier). Install Node.js 22 for the
packaged runtime, Viewer, `@cad/core`, or documentation site; Python-only work
can defer Node until a selected test needs a generated runtime stage.

### Linux, macOS, and WSL

Use the POSIX shell. On WSL, install dependencies inside the distribution; do
not reuse a Windows `.venv` or `node_modules` directory across the boundary.

```bash
uv sync --python 3.14
uv run scripts/test/test.sh
```

Build the packaged runtime when the work needs it, and run CLI calls in the
environment:

```bash
scripts/bundle/bundle.sh
uv run cad xbf snapshot --help
uv run cad urdf validate --help
```

The engine draws CAD snapshots with OCCT in an OpenGL context; a native KiCad board's
snapshot is painted with Pillow and needs no display. On Linux that context is an X
server's: the OCP wheels we pin draw through GLX alone (no EGL, no OSMesa), so there is no
off-screen context without one. A snapshot draws on the request's `DISPLAY`, else on the
engine's: the daemon's own, else an Xvfb the daemon starts itself where `Xvfb` is on PATH
(`cad_server/engine/display.py`). With no screen (a server, a container, CI) install Xvfb,
Mesa's software GL and the font the stills set their text in; the package suites draw in the
test process too, so run them under `xvfb-run`, as CI's Linux job does. With neither a
display nor Xvfb a snapshot fails, naming what to install.

```bash
sudo apt-get install -y xvfb libgl1-mesa-dri fonts-dejavu-core
xvfb-run -a -s "-screen 0 1920x1080x24 +extension GLX" uv run scripts/test/test-python.sh --select cadgen
```

### Native Windows

Use PowerShell for Python and npm commands. Git for Windows supplies Git Bash,
which runs the repository's checked-in `.sh` entry points just as Windows CI
does.

```powershell
uv sync --python 3.14
```

Invoke repository scripts through Git Bash. The default installation path is
shown here; adjust it if Git is installed elsewhere. The runners discover the
Windows `.venv\Scripts\python.exe` layout automatically.

```powershell
$gitBash = 'C:\Program Files\Git\bin\bash.exe'
& $gitBash scripts/bundle/bundle.sh
& $gitBash scripts/test/test-python.sh --select cadgen
```

Use `uv run` for direct CLI calls, and the runner for a focused test, so the file
builds on an engine daemon of its own:

```powershell
uv run cad xbf snapshot --help
& $gitBash scripts/test/test-python.sh tests/python/packages/cad/test_urdf_source.py
```

### Development dependencies

`uv sync` installs the root `pyproject.toml`'s `dev` group: the source package from
`packages/cad` and the repository's own tooling (Playwright, `build`, distlib, Pyrefly). It
installs `cad` editable, with its `build123d` extra (OCP, build123d and the rest), so the
checkout's `.venv` carries the CAD kernel and is its own base environment: the server
makes no base for it (`cad_server/_internal/base.py`; an installed cad makes its own on first
need). The library comes with its `trimesh` extra too, so `cad
<type> dfm --process` measures in the `.venv` and the server makes no `cad[trimesh]` environment for
it (`cad_server/_internal/integration_env.py`). `cad run` of a program whose imports use another set of
cad's integrations than build123d alone (none, or kicad), or that names packages of its own, runs in an
environment uv makes from the checkout's source tree, editable (`cad_server/_internal/extras.py`), from
uv's cache where it holds it. The editable
library installs `cad-lazy-kernel.pth` into the venv's site-packages as its wheel
does (`packages/cad/setup.py`), so `import build123d` defers the kernel and a
`python model.py` from a checkout costs what a user's does; a venv installed before
that has no such file until it is synced again (`uv sync --reinstall-package cad`). This is
the default Python environment for broad repo checks and source-checkout
development. The fea job's netgen and CalculiX are the `fea` group (`uv sync --group fea`);
a plain `uv sync` takes them out again. After pulling, run `uv sync` to refresh the
editable-install metadata: `cad.__version__` reports the installed
dist-info by design — it is release-grained, so dev code is always newer than
its number — and nothing behavioral consults it, but stale metadata makes the
reported number drift further from the code than it has to.

Skills run plain `cad` commands, with no version in them, through the `cad` command uv installs.
A model script starts no server of its own: it reaches the computer's one server, and where none
runs it says so in one line. To run your working copy in the agent apps, install it as the `cad`
tool with `scripts/install/dev_install.py` (see [Test In Agent Apps](#test-in-agent-apps)).

`packages/cad/src/cad_server/_runtime/` is BUILT, not committed — the whole
directory is gitignored, and the wheel is the only place those files ship. A
fresh clone therefore has no Viewer client or CAD app page until
`scripts/bundle/bundle.sh` runs, and the server says so by name the
first time it reaches for one. Building a model needs none of it.

For CAD Viewer development:

```bash
npm ci
npm run build:packages
```

### The engine server

Every build, export and snapshot runs in the engine server, a daemon: one per computer, started by
`cad server start` (or `cad mcp`, which Codex's plugin line runs) and running until
`cad server stop` (no timer stops it). A command that needs it and finds none says so in one line.
A checkout's `.venv` reaches the same server as any client: to run a worktree's own engine, give it
its own `CAD_ENGINE_DIR` and `CAD_STATE_DIR` ([Work In A Worktree](#work-in-a-worktree)). The engine folder, its door (a named pipe; on Windows,
a port file) and lock live in `cad-engine` in `$XDG_RUNTIME_DIR`, else in the per-user temporary
folder (on macOS the system's `/var/folders/...` one, whatever `$TMPDIR` a sandbox sets; else a
per-user `$TMPDIR`), else in `/tmp/cad-<uid>` (Windows: the temporary folder); `CAD_ENGINE_DIR` moves
them, which gives a test, a benchmark or an experiment a daemon to itself. `cad server status` lists
its workers, one per model script, each with its memo, and what each is building; `cad server stop`
stops it (`cad server start --foreground` runs one in the foreground); a running `cad mcp` holds it
until its host quits. A running daemon keeps the engine code it started with: after editing
`packages/cad/src`, stop the daemon you started so the next build runs the new code. Never stop one
you did not start. Set `CAD_UPDATE_CHECK=0` for a server you start by hand, so it never updates
itself.

Every environment variable cad reads is declared once, in `cad._internal.environment`
(`packages/cad/src/cad/_internal/environment.py`), with who sets it: the public ones a person may
set (the server's README lists them), the development ones for tests and experiments
(`CAD_ENGINE_MESH=processes|inline`, `CAD_ENGINE_STANDBY=0`, `CAD_VIEWER_WARM=0` and the like), the
internal ones cad's processes hand each other, and the deprecated ones. A variable is the last resort
(law 31): add one by declaring it there first, with its tier, and
`tests/python/global/test_environment_variables.py` fails on a name the source reads and the table
lacks. What the
engine builds is written beside a project only as the files models declare or a command
exports. Beside the person's settings, in the data folder (`CAD_STATE_DIR`, else `cad` in the
platform's place for state), it keeps one record per model or opened file
(`documents/<uuid>/document.json`: the script and function that build it, or the file's path; never
geometry). In the cache folder (`CAD_CACHE_DIR`, else the platform's: `~/.cache/cad`) it keeps each
model document's bytes as last built, `documents/<uuid>/document.xbf`, regenerable and wiped at no
loss, so a restart reopens every document without a build, under `pycache/` the bytecode the daemon
and its workers compile of the libraries they load (`PYTHONPYCACHEPREFIX`), and under `homes/` the
private settings folders `cad run` hands Blender's module in place of a person's own; it touches
nothing else in that folder but the environments it makes (`base/`). `cad cache dir|prune|clean`
manages that folder; nothing else of cad deletes a past release's files. Releases before 0.10 kept theirs in `~/.cache/cadgen`, which no build reads. Tests point both folders at temporary ones
(`scripts/test/unittest_files.py` does).

The skills ship no launcher scripts: every operational verb is a `cad`
subcommand (`cad <document_type> <operation>` or `cad <verb>`, or `python -m cad_server.cli ...` when the console
script is not on PATH), and `python <model>.py` builds the models its Python control flow explicitly calls.
The robot validators used to be the exception, running on bare `python3` while
their logic lived under `skills/`; that logic is the library's now (`cad.urdf`, `cad.sdf`, `cad.srdf`), run
by `cad urdf|sdf|srdf validate`, so they need the server like everything else.

## Work In A Worktree

Iterate inside the worktree, on its own environment and its own server; install globally only to test
end to end in an agent app ([Test In Agent Apps](#test-in-agent-apps)), one worktree at a time. Several
worktrees can iterate at once: each has its own `.venv` (its own `packages/cad`, editable), `_runtime`,
`node_modules` and server, and they share only uv's download cache, which uv locks.

A worktree's `cad` (`uv run cad ...`, `.venv`'s) reaches the computer's one server unless it is given
folders of its own, and a server is told apart by its release, never by its checkout: a worktree at
0.11.12 and the published 0.11.12 are the same release, so its commands are served by the global
server (the published code, or the code of whichever checkout last ran `dev_install.py`), and its
`cad server start` joins that server rather than starting one. So give each worktree its own engine,
state and cache folders (under `tmp/`, which is gitignored), and keep the server you start from
updating itself:

```bash
uv sync --python 3.14
npm ci && scripts/bundle/bundle.sh       # only for the CAD Viewer or the CAD app page
export CAD_ENGINE_DIR=$PWD/tmp/engine CAD_STATE_DIR=$PWD/tmp/state CAD_CACHE_DIR=$PWD/tmp/cache CAD_UPDATE_CHECK=0
uv run cad server start
uv run python models/<model>/model.py    # builds on this worktree's server and prints its page
uv run cad viewer                        # the home, served from this worktree's bundle
```

On Windows, in PowerShell:

```powershell
uv sync --python 3.14
$env:CAD_ENGINE_DIR = "$PWD\tmp\engine"; $env:CAD_STATE_DIR = "$PWD\tmp\state"
$env:CAD_CACHE_DIR = "$PWD\tmp\cache"; $env:CAD_UPDATE_CHECK = "0"
uv run cad server start
```

An export lasts only in the shell it ran in. Where each command runs in a fresh shell (an agent's
commands), set the variables in the same command as each `cad` command, from the worktree's root;
a command without them reaches the computer's global server, which runs other code, and says nothing:

```bash
export CAD_ENGINE_DIR=$PWD/tmp/engine CAD_STATE_DIR=$PWD/tmp/state CAD_CACHE_DIR=$PWD/tmp/cache CAD_UPDATE_CHECK=0 && uv run cad server start
```

The server keeps the Python it started with: after editing `packages/cad/src`, run
`uv run cad server stop` (with the same variables, so it stops this worktree's), and the next command
starts the new code. Leave it running between edits of a model script: a build of the same script
reuses its warm worker. Stop it when the worktree is done. Never stop a server you did not start.

The test runners need none of this: `uv run scripts/test/test-python.sh <files>` gives each test file
a server and folders of its own. Run plain `cad` (not `uv run cad`) and you get the global command,
whatever the shell's folder.

## Test In Agent Apps

A person installs text-to-cad with the install command
(`curl -fsSL https://texttocad.dev/install.sh | sh`; on Windows
`irm https://www.texttocad.dev/install.ps1 | iex`): `scripts/install/install.sh` and `install.ps1`
make sure uv is there, then download and run `scripts/install/install.py`, which installs cad as a uv
tool (PyPI's newest) only where none is installed or the one there does not start, installs the
plugin from the `latest` branch in each agent app it finds with that app's own command, removes our
own older copies, puts cad's folder on the PATH with `uv tool update-shell`, and, wherever cad is
there, turns on `cad plugin update auto`, telling cad whether its run is ending with exit status 0
(`CAD_INSTALL_FAILED`). It has no modes and reads no feed:
`cad plugin update` runs the same script. Its `APPS` table is the one list of apps; `docs/install.md` is the same list for people.
`tests/python/global/test_install_script.py` runs it against stand-in app commands in a home of its
own.

Test the skills the way users get them: as the plugin, with CAD's server. This is the global
install, so one worktree at a time owns it: the last to run the script is the computer's `cad`, and
the agent apps' (iterating needs none of it: [Work In A Worktree](#work-in-a-worktree)). One script installs
this checkout into the agent apps, with the same table and each app's own command, the checkout
in place of PyPI and GitHub:

```bash
scripts/install/dev_install.py                 # every app found here
scripts/install/dev_install.py claude codex    # these apps alone (install.py's APPS keys)
scripts/install/dev_install.py --release       # back to the published release, in every app
```

It installs the checkout's cad as the `cad` uv tool, editable, and turns cad's automatic updates
off, since an update would put the release in its place. It writes the plugin into
`tmp/dev-plugin/text-to-cad`: its manifests name the version `<VERSION>-dev.<time>`, so each app
takes it as new; Codex's CAD server (the one app given one) runs `cad mcp`, the editable tool's
command; and its catalog is `earthtojake-dev`. Then it installs that folder in each app and only then
removes the published copy of ours there. Run it again after a change, and start a new session in
the app. Run `npm ci` and `scripts/bundle/bundle.sh` once first: the viewer's page and the CAD app's
page come from the bundle (without it a model's link answers 404). An app that cannot install from a
folder is skipped and says so; Claude Code's copy also serves Cursor and Grok Build, which load
Claude Code's plugins.

`--release` uninstalls the editable tool, then runs the install script as it is: the newest release
of cad, every app moved back to the GitHub copy (the development copies among the old ones it
removes), automatic updates on.

A running server keeps the Python it started with and outlives the app: after a Python-only change
run `cad server stop`, and the next `cad server start` runs the new code. The app menu of every view
says which build it shows: any build but the release's own reads `v<VERSION>-dev.<commit>` (`-dirty`
when the checkout had uncommitted changes).

Keep one copy of the plugin per app: two copies show every skill twice. The scripts replace only
our own copies; a copy from a plugin store (Codex's directory, claude.ai's) is never touched, so
remove it in the app before testing there.

Where the server's output goes:

- Codex, the one app given the CAD server: its log database, `~/.codex/logs_2.sqlite` (lines
  starting `MCP server stderr`)

What the CAD app is and how hosts present it is in
[apps/mcp/README.md](apps/mcp/README.md). No agent app can be driven by a test,
so the standard path is also checked in the MCP Apps reference host
(`basic-host` from `modelcontextprotocol/ext-apps`): it speaks Streamable HTTP,
so a local bridge to the stdio server is needed, and the server offers tools to
the Codex app alone, so start it with the development switch
`CAD_MCP_PRESENTATION=inline` (`tabs` or `text` force the others). To try the
cards in Cursor, add the server to Cursor by hand with that switch in its
environment.

## Testing

The rules, what runs where, how to add a test or a CI job, what to do when a run is red, and the
other ways this repository is tested (by hand in agent apps, the manual models, the benchmarks and
the timing table a performance change opens its pull request with) are
[docs/contributing/testing.md](docs/contributing/testing.md). The commands are
[Common Dev Checks](#common-dev-checks).

## Document Types And Integrations

A file cad shows is a document type, and a third-party tool our code calls is an integration; a file
cad only writes or checks is its tool's integration's, with no type (an MJCF, MuJoCo's). The words and
laws are `packages/cad/README.md`'s. Start from
[Adding an integration](docs/contributing/adding-an-integration.md#start-from-the-tool), which asks what
the tool already does and what is missing, then
[Adding a document type](docs/contributing/adding-a-document-type.md) where the tool's file is one. Each
is a record of what the tools so far needed and a checklist for the ones like them, not a template: a
tool that does not fit is thought through on its own terms: the change says where it departs and why,
and the guide and the laws are amended with it where they should read differently.

## Source Boundaries

A skill must not import another skill or a repository-root module at runtime, and
must not put `skills/`, the repository root, or a sibling skill directory on
`sys.path`, `PYTHONPATH`, `NODE_PATH`, or any similar lookup path. Skills are
independent of *each other*.

They are not independent of cad. Each skill that uses it runs the `cad` command, and what a
skill would script is a `cad` command whose parser and behaviour live in `cad_server.cli` — so
what a published skill needs is an install, not a copy. Skills used to vendor the runtime and its JavaScript builders into
`skills/*/scripts/packages/`; six copies of one runtime is what that cost, and it
is gone. The server now carries the JavaScript it executes as well as the Python.

Canonical source directories are:

- `skills/*` for skill instructions and references.
- `apps/web/` for the CAD Viewer's React client. Its backend is
  `cad_server.viewer` (in `packages/cad`), and its built `dist/` ships inside the
  wheel as `cad_server/_runtime/viewer` — built at release time, never
  committed.
- `apps/mcp/` for the CAD app agent hosts render (MCP Apps: the Codex app's tabs). Its
  server is the engine's MCP endpoint (`cad_server/mcp`), which `cad mcp` (`cad_mcp`)
  carries a host's requests to, and its one-file
  build ships inside the wheel as `cad_server/_runtime/mcp` — built at
  release time, never committed.
- `apps/docs/` for the site.
- `apps/api/` for `api.texttocad.dev`, the version feed and the telemetry receiver
  the server talks to: a Vercel project of its own, with no dependencies.
- `packages/cad/` for the one Python distribution, `cad`: the library (`src/cad`), the server and
  the `cad` command with its bundled runtime assets (`src/cad_server`), and the transport an agent
  app starts (`src/cad_mcp`); and `packages/aliases/` for `cad-server`, `cad-mcp` and `cadgen`, empty
  aliases every release still publishes, each installing `cad` at the same release.
- `packages/core/` for non-React CAD/client code.
- `packages/ui/` for FileViewer, renderers, controls and shared styles.

The distributions ship whole and must each work in isolation outside this repo — the
ships-alone law, enforced by the markdown-isolation check in
`tests/python/global/test_package_boundaries.py`: `packages/cad` (with @cad/core and the viewer
client bundled in at build time) and each alias under `packages/aliases` build into a PyPI wheel
whose README is its long description. Markdown under it must be true and
actionable with this repo gone: name the bundled thing ("the @cad/core runtime
bundled at build time"), never the repo path to its source, and keep commands
relative to the package itself. Repo-development guidance belongs here, not in
the package. `apps/web` is a client package with a boundary of its own
(`apps/web/scripts/selfContained.test.mjs`): it imports @cad/core and @cad/ui by their public exports; relative
imports remain inside its directory.

## Working On The Packages In This Repo

- `scripts/test/test-python.sh` (or path-targeted `unittest`) for the engine
  (`tests/python/packages/cad/engine/`, `tests/python/packages/cad_server/engine/`);
  `tests/python/global/` holds the policy
  gates that enforce the design laws in `packages/cad/README.md`.
- Editing anything the bundlers consume? Run `scripts/bundle/bundle.sh` and
  there is nothing to commit: all of `_runtime/` is gitignored, so a JS edit
  shows up in the diff as the shared package source it was made in and reaches a user
  as the wheel the release builds.
- `VERSION` at the repo root is canonical; release tooling stamps every
  duplicate. Never hand-edit versions under `packages/`.

## Viewer Development In This Repo

The npm apps are `docs`, `web` and `mcp` (`apps/api` is a Vercel project of its own, with no
dependencies). Framework-independent CAD code lives
in `@cad/core`; `@cad/ui` owns the complete FileViewer and injectable
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
npm ci --workspace @cad/core
npm run build --workspace @cad/core
# Viewer and shared UI work:
npm ci --workspace @cad/core --workspace @cad/ui --workspace @cad/web
npm run build:packages
# Docs work:
npm ci --workspace @cad/core --workspace cad-skills-docs
npm run build:docs
```

There is one root lockfile. Do not create nested lockfiles or symlink dependency
trees from another checkout. Rebuild shared packages after editing them;
Vite and Next consume their `dist` exports. `npm ci` without a
workspace filter installs the whole workspace.

Create this worktree's `.venv` with `uv sync` when Python is needed, and give it a server
of its own ([Work In A Worktree](#work-in-a-worktree)). For web development, invoke Vite from a folder of models (the home shows it):

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

Vite announces itself to the device's engine with an API-only launch.
Closing Vite leaves that engine and its other clients running. `VIEWER_PYTHON`
must name an interpreter that satisfies the packages' Python floor and imports this
checkout. The backend opens any file by its absolute path. The web app owns
URL/history and browser preferences. FileViewer
state is scoped by file and renderer; each CAD render session owns its
cache provider and worker lease.

`cad viewer [FILE ...]` reaches the running engine (`cad server start` starts it), opens its one
page -- each FILE's at `/<id>`, else the home -- and exits. `--json` prints the authenticated launch record
without opening a browser. Each launch's folder becomes the folder the home shows.
An explicit `--host` or `--port` pins the engine listener; a conflict with an
already-running engine fails. The engine's default port is 3245, rolled past when another
program holds it (`cad server status` says which); there is no viewer process of its own.
A checkout serves its local web build; `CAD_VIEWER_DIST` and
`CAD_MCP_APP_DIR` are explicit asset overrides. A wheel resolves its
bundled assets without the repository. Run `scripts/bundle/bundle.sh` after
editing build inputs to refresh all packaged outputs.

The self-contained browser suite creates tiny inputs and owns its project,
viewer and cache. It never reads the sample-model corpus. The server itself needs no
browser: OCCT draws its snapshots, and the wheel depends on no Playwright. The
tests do: the UI/web tests and the browser suite drive npm Playwright's Chromium,
and the viewer's launch smoke test (`scripts/test/test-viewer-launch.sh`) drives
Python Playwright's headless shell, the one Python package the `dev` group
installs for a browser. Install both; their revisions can differ:

```bash
npx --no-install playwright install chromium                  # UI/web tests, browser suite
uv run playwright install --only-shell chromium               # the launch smoke test
scripts/bundle/bundle.sh
scripts/test/test-viewer-browser.sh
scripts/test/test-viewer-browser.sh --only camera
scripts/test/test-viewer-launch.sh
```

Use `--with-deps` when installing browsers on Linux. The browser suite runs
exactly what CI runs: every load path (STEP, STL, DXF, URDF) and the camera
across modes and a saved revision, through the real backend (picking and
kinematics are the `packages/ui` browser specs' on every PR). Backend tests live in
`tests/python/packages/cad_server/viewer` and are selected with
`scripts/test/test-python.sh --select viewer`. Client tests do not cover them.
Nothing in `cad_server.viewer` imports the CAD kernel at module scope.

There is one engine per computer (or per `CAD_ENGINE_DIR`), so the CLI, the page and each host's
`cad mcp` share it. There is one page per engine, every document at `/<id>`, and no page sessions. Python
source edits require restarting your test engine with `cad server stop`; it does not
re-execute under active pages. Never stop an instance you did not start. See
`apps/web/README.md` for the launcher contract and catalog/link behavior.

Production outputs are centralized and ignored by Git:

```bash
scripts/bundle/bundle.sh --clean
scripts/bundle/bundle.sh --check
```

`--clean` removes old runtime outputs before building. `--check` builds and
asserts the required outputs (the Viewer client's and the CAD app's
`index.html`, and the `THIRD_PARTY_LICENSES.txt` each build writes beside its page of the
packages it inlines); wheel validation checks the complete packaged runtime too
(`scripts/release/check-wheel-contents.sh`). Per-stage `cadgen-runtime.sh` flags are for
debugging; normal iteration goes through `bundle.sh`. The wheel carries no plugin and no skill.

## Branch Layout

`main` is the source tree, what installers clone, and what releases are cut
from. There is no development symlink layout and no generated publish tree:
every path is the real file, and the repository root is itself the agent plugin
package (`.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `gemini-extension.json`
and the other apps' `.<app>-plugin/` folders hold the manifests; the plugin's skills are
`skills/` directly), so whatever is on `main` is what agent installers copy.

Four consequences are enforced by `scripts/github-workflows/check-builds.sh`
on every push:

- **No tracked symlink, anywhere.** The installers disagree about symlinks and
  one loses data silently: a copied skills folder dereferences them, Claude Code
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
  permission to import from it: the install script copies `skills/<name>` alone
  into an agent's skills folder, so `../../../packages/` would work in a checkout
  and break there. `tests/python/global/test_skill_self_containment.py` and
  `test_package_boundaries.py` hold the same law.

Every mention of the release's own in the tree — the four `pyproject.toml`s and the aliases'
`cad==` pins, Codex's server line (`cad@<VERSION>`) and the release each skill's Setup block names —
names `VERSION`. `scripts/release/bump-version.sh` stamps them with the bump (`sync-version.mjs`),
and `scripts/release/check-version.sh` asserts they all equal `VERSION` — so a stale one fails the
`static` job's version check.

The `Test` workflow runs on PRs against `main` and pushes to it, selecting
the jobs each change can break ([CI](docs/contributing/testing.md#ci)); a push whose tree its pull request
already tested runs nothing again, and the `packaging` job builds the runtime
from clean with `scripts/bundle/bundle.sh --clean` and checks the layout and the
wheel. `main` commits no generated runtime at all —
the Viewer client and the CAD app page are built from `packages/core`,
`packages/ui`, `apps/web` and `apps/mcp` on demand, and ship only inside the wheel. What IS
committed and therefore checked for freshness is the version
metadata derived from `VERSION`, asserted by the `static` job's version check
(`scripts/release/check-version.sh` and `sync-version.mjs --check`).

## Releases

A pull request that changes `VERSION` is a release, and merging it ships it. Everything about releases
is in [docs/contributing/releases.md](docs/contributing/releases.md): which number a release bumps and
what counts as breaking, how a release reaches a computer, shipping one, the install branches, the
version feed, resuming, rehearsing and the repository's settings.

## Decisions

Why text-to-cad is installed, run and updated the way it is -- two layers with one direction of
knowledge, one cad per computer, the feed saying when, who updates which copy, forward only, the
30-day rule, the install script, the bridge -- is
[docs/contributing/decisions.md](docs/contributing/decisions.md). Read it before changing the
install script, cad's update, the manifests or the skills' setup text.

## Writing A Skill

What earns a line in a skill, the size budget, where each kind of content goes and how a change is
tested A/B are [Writing a skill](docs/contributing/writing-a-skill.md). Read it before editing
anything under `skills/`. Then test the skill in an agent app
([Test In Agent Apps](#test-in-agent-apps)).

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
npm --prefix apps/api test               # api.texttocad.dev, no install needed
```

Use [`AGENTS.md`](AGENTS.md) or [`scripts/README.md`](scripts/README.md) for path-specific validation when you are
working in a particular package, skill, docs site, or production-output
path.

For targeted Python tests, run the relevant test files through the runner, which
gives each file an engine daemon of its own (a bare `python -m unittest` would build
on your own daemon), for example:

```bash
scripts/test/test-python.sh tests/python/packages/cad/test_urdf_source.py
```

Repo-owned Python tests live under `tests/python/`, grouped by tested surface:
`skills/<skill>`, `packages/<package>`, and `global`. The CAD Viewer backend's
suite is `tests/python/packages/cad_server/viewer/`, part of the server's package suite.

For fast CAD Viewer source iteration, build the shared packages, then invoke
the web app in dev mode from a folder of models (outside `apps/web`). The app
consumes source with HMR while shared packages resolve to their compiled exports:

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

The spawned backend opens any file by its absolute path; the folder it starts
in is only the folder the home shows. Its resolver takes `INIT_CWD`, then
the process working directory, skipping either when it is inside `apps/web`. Vite's
fallback is `<checkout>/apps`. npm sets `INIT_CWD` to the invocation directory,
so `--prefix` selects the app while keeping your folder. The page is the bare
origin, the home; a document's page is `/<id>` (`http://127.0.0.1:5173/<id>`), a file's id
given by `cad viewer FILE --json` or by opening it from the home.

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
shipping contract above), so heavyweight media never goes in the tree. It holds code,
never CAD or mesh assets: a test makes the STEP, GLB or mesh it needs in a temporary
folder, a sample exports on request into its project's gitignored `STEP/`, `STL/`,
`GLB/`, `3MF/`, `DXF/` or `XBF/`, and `tests/python/global/test_no_cad_assets_tracked.py`
fails on any tracked CAD or mesh file but the few tiny fixtures it lists, each with the
reason no test can make it. The KiCad files an electronics sample's scripts write (its board,
schematic, project and libraries) are build output in the same way: gitignored, made again by
the sample's `cad run build.py`, and held untracked by
`tests/python/global/test_generated_kicad_files_untracked.py`, which lists what each build writes
and the few KiCad files beside it that no script makes. A board no script makes is source.

A security problem is reported privately, as [SECURITY.md](SECURITY.md) says, never as an
issue or a pull request.
