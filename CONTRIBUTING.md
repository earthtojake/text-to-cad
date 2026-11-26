# Contributing

How to set up a checkout of text-to-cad, work in it and try a change in the agent apps.
[AGENTS.md](AGENTS.md) is the index for everything else: what is where, the rules that hold
everywhere, the one document to read before each kind of change, and the check to run after it.
Report a security problem privately, as [SECURITY.md](SECURITY.md) says, never as an issue or a pull
request.

- [Local Checkout](#local-checkout): Python, JavaScript, Linux with no screen, Windows
- [Work In A Worktree](#work-in-a-worktree): a server of your own
- [Test In Agent Apps](#test-in-agent-apps): this checkout as the plugin
- [Source Boundaries](#source-boundaries) and [Git Hygiene](#git-hygiene): the rules of the tree,
  with what holds each
- [Releases](#releases)

## Local Checkout

Branch from `main` and open the pull request against `earthtojake/text-to-cad:main`: from a branch of
the repository with write access, otherwise from a fork.

### Python

The Python side is a [uv](https://docs.astral.sh/uv/) project: the root `pyproject.toml` is a
workspace whose one member is `packages/cad`, and `uv.lock` pins the development environment for
contributors and CI alike.

```bash
uv sync --python 3.14        # .venv, from uv.lock; again after a pull that changes the lock
uv run cad --version         # `uv run` runs a command in that environment
```

- Python 3.14 is what CI tests on and what the install command installs cad on; uv fetches it when
  it is missing. The floor is `requires-python` in `packages/cad/pyproject.toml`, which CI holds
  before a release ships ([CI](docs/contributing/testing.md#ci), the release tier).
- `uv sync` installs the root `pyproject.toml`'s `dev` group, whose comments say what each entry is
  for: `cad` editable with the extras the suites need, and the repository's tooling. So the `.venv`
  carries the CAD kernel and is its own base environment: the server makes none for a checkout.
- The fea suite's netgen and CalculiX are the `fea` group (`uv sync --group fea`); a plain `uv sync`
  takes them out again. The KiCad and Blender suites make their own environments
  (`scripts/test/test-kicad.sh`, `test-blender.sh`).

### JavaScript

Install Node.js 22, which CI uses, for the viewer, the CAD app, the shared packages and the docs
site. Python-only work needs none until it opens a model's page or runs a test that reads the bundle.

```bash
npm ci                       # every workspace, from the one root lockfile
npm run build:packages       # @cad/core, then @cad/ui: apps consume their dist, so again after editing either
scripts/bundle/bundle.sh     # the viewer's client and the CAD app's page, as the server serves them
```

- Nothing built is committed ([Git Hygiene](#git-hygiene)). Until `bundle.sh` has run, a model's
  page answers 404 (`The viewer client is not built`); building a model needs none of it.
- `npm ci --workspace @cad/core --workspace @cad/ui --workspace @cad/web` installs only the
  workspaces named, as each CI job does. Never add a nested lockfile, or link `node_modules` from
  another checkout.
- The browser tests need a browser each, of revisions that can differ (on Linux, add `--with-deps`):

  ```bash
  npx --no-install playwright install chromium       # the UI's and the web app's tests, the browser suite
  uv run playwright install --only-shell chromium    # the viewer's launch smoke test (Python Playwright)
  ```

- `git config core.hooksPath .githooks` turns on the checked-in pre-commit hook, which runs
  `scripts/bundle/bundle.sh --check` when a commit touches `packages`, `apps`, `skills` or
  `scripts/bundle`.
- Developing the viewer's client with hot reload against a running engine is
  [apps/web's Launching](apps/web/README.md#launching). Each runner's options are in
  [scripts/README.md](scripts/README.md).

### Linux with no screen

A snapshot is drawn by OCCT in an OpenGL context, which on Linux needs an X display
([The viewer and the snapshot](packages/cad/src/cad_server/engine/docs/viewer-and-snapshot.md) says
where the engine finds one). On a server or in a container, install Xvfb, Mesa's software GL and the
font the stills set their text in, and run the package suites under `xvfb-run`, as CI does: they draw
in the test process too.

```bash
sudo apt-get install -y xvfb libgl1-mesa-dri fonts-dejavu-core
xvfb-run -a -s "-screen 0 1920x1080x24 +extension GLX" scripts/test/test-python.sh --select cadgen
```

### Windows

Run Python and npm commands in PowerShell, and the repository's `.sh` entry points through Git Bash,
which Git for Windows installs and Windows CI uses. The runners find `.venv\Scripts\python.exe`
themselves.

```powershell
uv sync --python 3.14
$gitBash = 'C:\Program Files\Git\bin\bash.exe'    # Git for Windows' default place
& $gitBash scripts/bundle/bundle.sh
& $gitBash scripts/test/test-python.sh tests/python/packages/cad/test_urdf_source.py
```

On WSL, set the checkout up inside the distribution: a `.venv` or `node_modules` made on Windows
does not work across the boundary.

## Work In A Worktree

Iterate inside the worktree, on its own environment and its own server. A worktree is a checkout of
its own, set up as [Local Checkout](#local-checkout) says, with its own `.venv` (its own
`packages/cad`, editable), `_runtime`, `node_modules` and server. Worktrees share only uv's download
cache, which uv locks, so several can be worked in at once.

A checkout's `cad` (`uv run cad`) reaches the computer's one server unless it is given folders of its
own, and a server is told apart by its release, never by its checkout. At the `VERSION` of the cad
installed on the computer, a worktree's commands are served by the installed server, which runs
other code, with nothing to say so, and its `cad server start` joins that server, saying only that
the server is already running. So give every command its own engine, state and cache folders, under
`tmp/` (gitignored), and keep its server from looking for a newer release:

```bash
export CAD_ENGINE_DIR=$PWD/tmp/cad/engine CAD_STATE_DIR=$PWD/tmp/cad/state \
       CAD_CACHE_DIR=$PWD/tmp/cad/cache CAD_UPDATE_CHECK=0
uv run cad server start
uv run python models/examples/src/l_bracket.py    # builds on this worktree's server, prints its id and page
uv run cad viewer                                 # the home, served from this worktree's bundle
```

On Windows, in PowerShell:

```powershell
$env:CAD_ENGINE_DIR = "$PWD\tmp\cad\engine"; $env:CAD_STATE_DIR = "$PWD\tmp\cad\state"
$env:CAD_CACHE_DIR = "$PWD\tmp\cad\cache"; $env:CAD_UPDATE_CHECK = "0"
uv run cad server start
```

- An export lasts only in its shell. Where each command runs in a fresh shell (an agent's), set the
  variables in the same command as each `cad` command, from the worktree's root.
- Plain `cad`, without `uv run`, is the installed command, whatever folder the shell is in.
- The server keeps the code it started with. After editing `packages/cad/src`, run
  `uv run cad server stop` (with the same variables, so it stops this worktree's), then start it
  again. Between edits of a model script leave it running: a build of the same script reuses its
  warm worker.
- Stop the server when the worktree is done, and never stop one you did not start.
- The test runners need none of this: each test file gets a server and folders of its own.
- A checkout's cad is a development build, which sends no telemetry by default
  (`cad_server/_internal/editable.py`).
- A checkout serves its own web build; `CAD_VIEWER_DIST` and `CAD_MCP_APP_DIR` name another, for a
  test or a build elsewhere.

## Test In Agent Apps

No agent app can be driven by a test, so a change to the skills, the plugin, the server or the CAD
app is tried by hand in Claude Code, Codex and Cursor before it ships. Test what users get: the
plugin, with the computer's `cad` and its server. One script installs this checkout into the agent
apps as the install command would ([scripts/README.md](scripts/README.md), `install/`), with the
checkout in place of PyPI and GitHub:

```bash
npm ci && scripts/bundle/bundle.sh             # first: the viewer's and the CAD app's pages come from the bundle
scripts/install/dev_install.py                 # every app found here
scripts/install/dev_install.py claude codex    # these apps alone (`--help` lists the names)
scripts/install/dev_install.py --release       # back to the published release, in every app
```

- This is the computer's global install, so one worktree at a time owns it: the last to run the
  script is the computer's `cad`, and the agent apps'. Iterating needs none of it
  ([Work In A Worktree](#work-in-a-worktree)).
- It installs the checkout's cad as the `cad` uv tool, editable, with automatic updates off (an
  update would put the release in its place). It writes the plugin into `tmp/dev-plugin/text-to-cad`
  as version `<VERSION>-dev.<time>`, so each app takes it as new, in the catalog `earthtojake-dev`,
  with Codex's CAD server running `cad mcp`. Then it installs that folder in each app with the app's
  own command, and only then removes the published copy of ours there.
- An app that cannot install from a folder is skipped and says so. Claude Code's copy also serves
  Cursor and Grok Build, which load Claude Code's plugins.
- After a change to a skill or the plugin, run it again and start a new session in the app. After a
  change to the viewer or the CAD app, bundle again. After a change to Python alone, run
  `cad server stop`: a running server keeps the code it started with and outlives the app, and the
  next `cad server start` runs the new code.
- The app menu of every view names the build it shows: any build but a release's own reads
  `v<VERSION>-dev.<commit>`, with `-dirty` when the checkout had uncommitted changes.
- Keep one copy of the plugin per app: two show every skill twice. The scripts replace only our own
  copies, never a plugin store's (Codex's directory, claude.ai's): remove that one in the app before
  testing there.
- `--release` uninstalls the editable tool and runs the install script as it is: the newest release
  of cad, then that cad's own `cad plugin install`, which puts every app back on the GitHub copy,
  then automatic updates on.

**To add an agent app, or correct one**, change its row of `APPS`, cad's one table of apps
(`packages/cad/src/cad_server/plugin/apps.py`), and say in the row's comment how its commands were
checked: the vendor's documentation (its address), the CLI's own `--help`, or a run. Change its test
in `tests/python/packages/cad_server/plugin/test_apps.py`, which runs the command against stand-in
app commands (`tests/python/support/agent_apps.py`), and its entry in
[docs/install.md](docs/install.md) (install, update and remove by hand); a new app is also named in
the README and the homepage's copy. Every test of the command runs it in a temporary home (the
`PluginRuns` test case gives one): run against your own home, it installs the plugin into your apps.
The correction ships in the next release of cad and reaches a computer when its cad updates.

In Codex, the one app given the CAD server, the server's output is in Codex's log database,
`~/.codex/logs_2.sqlite`, in lines starting `MCP server stderr`. What the CAD app is and how each
host presents it is [apps/mcp/README.md](apps/mcp/README.md). Its inline cards, which no app is
offered, are reached with the development switch `CAD_MCP_PRESENTATION=inline` in the environment of
`cad mcp` (`tabs` and `text` force the others): in a server added to Cursor by hand, or in the MCP
Apps reference host (`basic-host`, from `modelcontextprotocol/ext-apps`), which speaks Streamable
HTTP and so needs a local bridge to the stdio server.

## Source Boundaries

| Boundary | Why | Held by |
| --- | --- | --- |
| A skill imports no other skill and nothing of the repository, and puts neither on a lookup path (`sys.path`, `PYTHONPATH`, `NODE_PATH`) | An installer copies `skills/<name>` alone: what resolves in a checkout is not there | `tests/python/global/test_skill_self_containment.py`, `scripts/github-workflows/check-builds.sh` |
| Markdown in a Python distribution (`packages/cad`, each alias under `packages/aliases`) names nothing outside it, and a skill's links stay inside the skill | Each ships alone (law 13), its README its PyPI page. Name the bundled thing ("the @cad/core runtime bundled at build time"), never the repository path of its source, and put repository guidance here | `tests/python/global/test_package_boundaries.py` |
| Apps import the shared packages by their public exports; no app imports another, and no package imports an app | The rule and its reasons are [packages/README.md](packages/README.md)'s | `npm run check:boundaries`; for `apps/web`, `apps/web/scripts/selfContained.test.mjs`; for the Python distribution, `test_package_boundaries.py` |

## Git Hygiene

Git holds source only. The repository root is the plugin: every manifest sits at the root and the
plugin's skills are `skills/` itself, so an install that names no branch copies `main` as it is, and
the install branches are built from the same files
([The install branches](docs/contributing/releases.md#the-install-branches)). The `static` job checks
the tracked tree on every change, with `scripts/github-workflows/check-builds.sh --tree-only` and the
policy tests under `tests/python/global/`:

| Never tracked | Why | Held by |
| --- | --- | --- |
| A symlink | Installers disagree about symlinks, and Codex's `plugin add` drops them with no error: the skill ships with files missing | `check-builds.sh` |
| A `.gitattributes` rule that changes a file on its way to a user: `filter` (so no Git LFS), `ident`, `working-tree-encoding`, `export-ignore`, `export-subst` | Installers clone without git-lfs and would get pointer files, and claude.ai's plugin directory validates files as stored and refuses a plugin whose installs could differ | `check-builds.sh` |
| A file of 5 MiB or more | Every clone carries it, and claude.ai's directory stops validating at 5 MiB | `check-builds.sh` |
| A CAD or mesh file (a STEP, STL, GLB, 3MF, DXF, XBF, `.blend` and the like) | It costs every clone and drifts from the code that makes it. A test makes what it needs in a temporary folder, and a sample exports on request into its project's gitignored `STEP/`, `STL/`, `GLB/`, `3MF/`, `DXF/` or `XBF/` | `test_no_cad_assets_tracked.py`, which lists the few tiny fixtures kept, each with the reason no test can make it |
| A KiCad file a sample's scripts write | It is build output, made again by the sample's `cad run build.py`; a board no script makes is source | `test_generated_kicad_files_untracked.py`, which lists both |
| The built runtime, `packages/cad/src/cad_server/_runtime/` | `scripts/bundle/bundle.sh` builds it and only the wheel ships it ([Build artifacts live in the wheel, never in git](docs/contributing/releases.md#build-artifacts-live-in-the-wheel-never-in-git)) | `.gitignore`; the `packaging` job builds it from clean |
| An environment file, a key or a certificate; a local environment, cache or `tmp/` | Secrets and local state are no one else's | `.gitignore`, `test_secret_files_ignored.py` |

## Releases

A pull request that changes `VERSION` is a release. How one is made, what it may change, how it
reaches a computer and how the install branches are written is
[docs/contributing/releases.md](docs/contributing/releases.md).
