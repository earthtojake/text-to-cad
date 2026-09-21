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
environment needs Git LFS and Python 3.11 or newer. Install Node.js 22 for the
packaged runtime, Viewer, `cadgen-js`, or documentation site; Python-only work
can defer Node until a selected test needs a generated runtime stage.

### Linux, macOS, and WSL

Use the POSIX shell. On WSL, install dependencies inside the distribution; do
not reuse a Windows `.venv` or `node_modules` directory across the boundary.

```bash
git lfs install
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
git lfs install
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

Install `requirements-dev.txt`, not a skill's `requirements.txt`: the skill
files pin `cadgen==<VERSION>` (the release PR stamps them, and they are what an
installer resolves from PyPI). The editable install reports that same version,
so the pin is satisfied in a checkout — but `pip install -r skills/<s>/requirements.txt`
on its own would fetch the previous RELEASE from PyPI over your working copy.

`packages/cadgen/src/cadgen/_runtime/` is BUILT, not committed — the whole
directory is gitignored, and the wheel is the only place those files ship. A
fresh clone therefore has no Node builders, no snapshot browser bundle and no
Viewer client until `scripts/bundle/bundle.sh` runs, and cadgen says so by name
the first time it reaches for one. `scripts/test/test-python.sh` and
`scripts/test/test-global.sh` build the two stages they read if they are
missing, so this step is about having the whole thing, including the Viewer
client the wheel carries.

For CAD Viewer development:

```bash
npm --prefix apps/viewer install
```

The skills ship no launcher scripts: every operational verb is a `cadgen`
subcommand (`cadgen <verb>`, or `python -m cadgen.cli <verb>` when the console
script is not on PATH), and `python <model>.py` builds a model through the `__main__` call at the end of its script.
The robot validators used to be the exception, running on bare `python3` while
their logic lived under `skills/`; that logic is `cadgen.{urdf,sdf,srdf}_*` now,
so they need cadgen like everything else.

## Link Skills Into Your Agent

For local development, symlink this checkout's supported skill directories into
your agent. Do not copy skill directories into your agent: symlinks keep edits
in this checkout visible immediately.

Use the installer from the repository root:

```bash
scripts/install/install-skills.sh --agent codex
```

To see supported agents and resolved destination directories:

```bash
scripts/install/install-skills.sh --list-agents
```

The installer discovers each directory under `skills/` that contains
`SKILL.md`, creates one symlink per skill, and leaves existing non-symlink paths
untouched.

Supported local-development agent destinations:

| Agent flag  | Destination                                       |
| ----------- | ------------------------------------------------- |
| `codex`     | `${CODEX_HOME:-$HOME/.codex}/skills`              |
| `claude`    | `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills`      |
| `gemini`    | `$HOME/.gemini/skills`                            |
| `universal` | `${XDG_CONFIG_HOME:-$HOME/.config}/agents/skills` |
| `project`   | `.agents/skills` in this repository               |

`claude-code`, `gemini-cli`, `agents`, and `repo` are accepted aliases. Use
`--all` to install into every destination above, or repeat `--agent` for a
smaller set:

```bash
scripts/install/install-skills.sh --agent codex --agent claude
```

Restart or reload the agent after linking so it rescans available skills.

To remove this checkout's skill links while testing provider behavior:

```bash
scripts/install/uninstall-skills.sh --agent codex
```

The uninstaller removes only symlinks that point back at this checkout and
prunes empty destination directories unless `--keep-empty-dirs` is passed.

## Test From This Repository

Automated tests are self-contained. They must not read, enumerate, build, or
import sample models from this repository's `models/` directory. Generate the
smallest fixture needed in a fresh temporary directory, or use a tiny fixture
committed with the tests; do not rely on existing outputs or LFS downloads.
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

`test.yml` is one job per thing that has to work, each conditional on the
changes that can break it. `AGENTS.md` has the job table; this is why.

**Jobs are split by condition, not by size.** Two tests belong in the same job
unless they should run under different conditions — a different set of paths,
or a different operating system. So the cadgen package suite is one job (one
per platform), every skill suite plus the policy gates is one job, and there
are no shards: each job parallelises internally (`unittest_files.py --jobs`,
`node --test` concurrency) instead of across machines.

**The conditions encode the dependency graph.** `packages/cadgen` is the engine
everything downstream runs — the skills are thin entrypoints over its CLIs, the
viewer is served by `cadgen.viewer`, the docs site documents its commands, the
wheel packages it — so a cadgen change runs the cadgen, viewer, skills, docs and
packaging jobs. `packages/cadgen-js` is bundled into the runtime cadgen
executes and imported by the viewer and the docs hero, so it fans out the same
way plus its own unit tests. A viewer-client change runs the viewer and
packaging jobs; a docs change runs docs; a skills change runs skills and docs
(the site mirrors the skills' frontmatter). `scripts/`, `.github/` and the
version metadata can break any job, so they run all of them. The one direction
that does NOT fan out is up: the viewer client, the skills and the docs cannot
break cadgen, so touching them never runs the cadgen suite.

**Only prose skips everything.** Root `*.md`, `notes/`, `models/`, `LICENSE`
and issue templates are read by no test, so a pull request touching only those
runs Version Check and nothing else. Markdown under `skills/` and
`packages/cadgen/` is test input — `test_documented_commands` runs the command
forms a SKILL.md teaches, `test_skill_requirements` reads a skill's prose for
the extras it reaches, `test_package_boundaries` reads the package's own
markdown — and is therefore not in that class.

**Windows runs the cadgen suite and nothing else.** What has to be proven on
Windows is the platform-facing code: paths, locks, subprocesses, file URLs, the
daemon, the CAD Viewer backend — all of it in `packages/cadgen`, all of it
covered by that one suite (four of the last five user-reported bugs were
Windows-only bugs whose coverage existed and never ran there). Bundling,
packaging, the policy gates and the skill suites are properties of the tree;
the JS suites are properties of a browser or of Node; none of them has a
Windows failure mode the cadgen suite does not already exercise, so none of
them buys a Windows runner. Windows runs `--keep-going` so one round trip
reports every failing suite.

**Every job is a required check.** `main` requires all eight names; a job
skipped by its own condition satisfies its check, which is what lets a prose
pull request merge. Adding a job means adding its name to branch protection
(the `gh api` command is in the runbook below); renaming one likewise.

**The packaged runtime is built per job**, not built once and passed between
them: `ensure_packaged_runtime` takes ~13 s, and an artifact would serialise
every test job behind a bundle job for longer than that.

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

## Source Boundaries

A skill must not import another skill or a repository-root module at runtime, and
must not put `skills/`, the repository root, or a sibling skill directory on
`sys.path`, `PYTHONPATH`, `NODE_PATH`, or any similar lookup path. Skills are
independent of *each other*.

They are not independent of `cadgen`. Each skill's `requirements.txt` names that
distribution, and a skill's `scripts/<tool>` is a thin entrypoint whose parser and
behaviour live in `cadgen.cli` — so what a published skill needs is an install, not
a copy. Skills used to vendor cadgen and its Node builders into
`skills/*/scripts/packages/`; six copies of one runtime is what that cost, and it
is gone. cadgen now carries the JavaScript it executes as well as the Python.

Canonical source directories are:

- `skills/*` for skill instructions, references, and the thin entrypoints.
- `apps/viewer/` for the CAD Viewer's React client. Its backend is
  `cadgen.viewer` (in `packages/cadgen`), and its built `dist/` ships inside the
  cadgen wheel as `cadgen/_runtime/viewer` — built at release time, never
  committed.
- `packages/*` for the shared runtimes. `packages/cadgen` is the published
  distribution; `packages/cadgen-js` is its JS build input, and the client's.

One source tree ships whole and must work in isolation outside this repo — the
ships-alone law, enforced by the markdown-isolation check in
`tests/python/global/test_package_boundaries.py`: `packages/cadgen` builds into
the PyPI wheel with cadgen-js and the viewer client bundled in at build time; its
README is the PyPI long description. Markdown under it must be true and
actionable with this repo gone: name the bundled thing ("the cadgen-js runtime
bundled at build time"), never the repo path to its source, and keep commands
relative to the package itself. Repo-development guidance belongs here, not in
the package. `apps/viewer` is a client package with a boundary of its own
(`apps/viewer/scripts/selfContained.test.mjs`): it imports cadgen-js by name and
nothing else from outside its directory.

## Working On cadgen In This Repo

- `scripts/test/test-python.sh` (or path-targeted `unittest`) for the engine;
  `tests/python/global/` holds the policy gates that enforce the design laws in
  `packages/cadgen/README.md`.
- Editing anything the bundlers consume? Run `scripts/bundle/bundle.sh` and
  there is nothing to commit: all of `_runtime/` is gitignored, so a JS edit
  shows up in the diff as the cadgen-js source it was made in and reaches a user
  as the wheel the release builds. A rebundle used to add ~1.3 MB of
  `snapshot-render.js` to every commit that touched the renderer.
- `VERSION` at the repo root is canonical; release tooling stamps every
  duplicate. Never hand-edit versions under `packages/`.

## Viewer Development In This Repo

`apps/viewer/README.md` keeps the app-facing half (launcher contract, dev vs
prod, behaviours worth knowing, testing); everything below is workbench-only
and deliberately lives here.

The backend is `cadgen viewer` — the `cadgen.viewer` package, so the
interpreter that has cadgen is the server. The served directory is the cwd
(there is no directory flag), so `cd` into the worktree's `models/` first. From
a lightweight worktree, use the primary checkout's venv with the WORKTREE's
cadgen sources on `PYTHONPATH`, or the worktree exercises the main checkout's
cadgen. The client resolves to `apps/viewer/dist` in a checkout (`npm run
build` there first); `--dist` or `CADGEN_VIEWER_DIST` point elsewhere:

```bash
cd <worktree>/models && \
PYTHONPATH=<worktree>/packages/cadgen/src \
<main>/.venv/bin/python -m cadgen.viewer --host 127.0.0.1 --json
```

The self-contained browser regression suite checks supported formats, picking,
placement, and Inspect/Render quality transitions. It creates tiny inputs and
starts its own viewer with an isolated cache; no sample builds are needed.
Bundle the client first and install Playwright Chromium from the development
requirements:

```bash
scripts/test/test-viewer-browser.sh --ci                # ~2 min: format, pick, kinematics, camera (the CI job)
scripts/test/test-viewer-browser.sh                     # ~4 min: every gate
scripts/test/test-viewer-browser.sh --only kinematics   # one gate while working on it
```

Mesh exports (`@stl`/`@3mf`/`@glb`) and DXF previews run the checkout's live
`packages/cadgen-js/bin` builders in Node, which import `three` and friends
from `packages/cadgen-js/node_modules`. A fresh worktree has none, and cadgen
refuses with an error naming this paragraph rather than letting the child die
with `ERR_MODULE_NOT_FOUND`. Symlink both `node_modules` directories from the
primary checkout (they are gitignored) or `npm install` in each package:

```bash
ln -s <main>/packages/cadgen-js/node_modules <worktree>/packages/cadgen-js/node_modules
mkdir <worktree>/apps/viewer/node_modules
for e in <main>/apps/viewer/node_modules/* <main>/apps/viewer/node_modules/.bin; do
  [ "$(basename "$e")" = cadgen-js ] || ln -s "$e" <worktree>/apps/viewer/node_modules/
done
ln -s <worktree>/packages/cadgen-js <worktree>/apps/viewer/node_modules/cadgen-js
```

Do NOT symlink the Viewer's `node_modules` directory whole. Its `cadgen-js`
entry is a RELATIVE link (`../../../packages/cadgen-js`) that resolves against
the primary checkout, so the worktree's Viewer tests and dev server would run
the primary checkout's cadgen-js and silently ignore every cadgen-js edit in
the worktree. Link the entries individually and point `cadgen-js` at the
worktree's package, as above.

For `npm run dev`, set `VIEWER_PYTHON` the same way — it defaults to `python3`,
which is usually wrong here: on macOS `python3` is still 3.9, BELOW the
server's floor and refused at startup with a message naming the version and
this variable, and a `python3` without cadgen has no server to run at all. The
dev plugin logs the interpreter it resolved:

```bash
VIEWER_PYTHON=<main>/.venv/bin/python \
PYTHONPATH=<worktree>/packages/cadgen/src \
npm --prefix <worktree>/apps/viewer run dev
```

`npm run dev` needs no `npm run build` first: the plugin spawns the backend with
`--api-only`, and Vite serves the client. Production is the opposite — no built
`dist/`, no start.

The backend's tests live at `tests/python/packages/cadgen/viewer/` and run with
the cadgen package suite (`scripts/test/test-python.sh`, on Linux through
`test.sh` and directly in the Windows CI job); `npm run test` covers the client's
`src/` and `scripts/` only. `test_module_boundaries.py` holds the one structural
law: nothing in `cadgen.viewer` imports the CAD kernel at module scope, so
`cadgen viewer` starts as fast as `cadgen --help` and the kernel loads only in
the compile worker.

Launcher reuse keys on realpath(root) × identity token (the cadgen version plus
a content digest of every cadgen Python runtime file and the exact built client
selected for the launch), so another checkout's instance can never be handed
back for a worktree's root, `--dist` cannot reuse a different client, and a
resident instance running pre-pull or pre-rebuild code fails the match. A
resident that sees those files change refuses new model-data requests with a
restart-required response while leaving its existing process and view alone.

Worktrees deliberately carry no `node_modules`; link them from the primary
checkout before building. cadgen-js needs all three of its runtime
dependencies linked — `three-mesh-bvh` included, which an earlier version of
this recipe omitted:

```bash
# apps/viewer/node_modules: per-entry links with cadgen-js pointing at THIS
# worktree -- see "Viewer Development In This Repo" above for why not one link.
mkdir -p packages/cadgen-js/node_modules
for dep in three three-mesh-bvh meshoptimizer; do
  ln -s <main>/packages/cadgen-js/node_modules/$dep packages/cadgen-js/node_modules/$dep
done
npm --prefix apps/viewer run build
```

Do not extend the trick to the docs app: Turbopack rejects a symlinked
`apps/docs/node_modules`, so the docs app needs a real install in any checkout
that builds it.

Never let a symlink reach the published tree (see Branch Layouts):
`scripts/github-workflows/check-builds.sh` enforces symlink-free publishes.

Production-output checks are intentionally centralized. `--clean` removes the
`_runtime` tree first, so a renamed stage or output cannot survive into the
wheel; `--check` builds and then asserts every file each stage owes:

```bash
scripts/bundle/bundle.sh --clean
scripts/bundle/bundle.sh --check
```

Do not call `scripts/bundle/cadgen-runtime.sh` directly as part of routine
iteration; its per-stage flags (`scripts/README.md`) are for debugging a
production-output check.

## Branch Layout

`main` is the source tree, what installers clone, and what releases are cut
from. There is no development symlink layout and no generated publish tree:
every path is the real file, and the repository root is itself the agent plugin
package (`.claude-plugin/` and `.codex-plugin/` hold the manifests; the plugin's
skills are `skills/` directly), so whatever is on `main` is what agent
installers copy.

Three consequences are enforced by `scripts/github-workflows/check-builds.sh`
on every push:

- **No tracked symlink, anywhere.** The installers disagree about symlinks and
  one loses data silently: the Skills CLI dereferences them, Claude Code
  preserves them, and Codex `plugin add` drops them with no error at all,
  publishing a skill whose files are simply missing at runtime.
- **No LFS-tracked path under `skills/`.** Installers clone without git-lfs and
  receive pointer files. `models/` and `assets/` stay LFS: nothing installs
  them, `.lfsconfig` excludes them from default fetches (a fresh clone is ~27 MB
  with `models/` as pointers), and `.gitattributes` export-ignores `models/`
  from archives.
- **No skill reaching into a repo root.** `packages/` being present is not
  permission to import from it: the Skills CLI installs `skills/<name>` alone,
  so `../../../packages/` would work in a checkout and break on the first
  `npx skills add`. `tests/python/global/test_skill_self_containment.py` and
  `test_package_boundaries.py` hold the same law.

Skill `requirements.txt` files pin `cadgen==<VERSION>` in the tree. The release
PR stamps them with the bump, and `scripts/release/check-version.sh` asserts
every pin equals `VERSION` — so a bare `cadgen` line or a stale pin fails the
`Version Check` job.

The `Test` workflow runs on pushes to `main` and PRs against it: it runs
`scripts/bundle/bundle.sh --clean` to produce the runtime, checks the layout
without rebuilding it, runs documentation checks, and runs the code tests
against that generated output. `main` commits no generated runtime at all —
cadgen's Node builders, its snapshot bundle and the Viewer client are built from
`packages/cadgen-js` and `apps/viewer` on demand, and ship only inside the
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
`_runtime/browser`, and the CAD Viewer client under `_runtime/viewer` — is
gitignored and produced by `scripts/bundle/bundle.sh`. Nothing built is ever
committed: a rebundle used to add a megabyte of history per commit, and a
committed bundle can drift from the source that claims to produce it.

Where the built things live instead:

- **CI** builds the runtime at the start of every `Test` run and tests against
  that build (`bundle.sh --check` now means "the runtime builds and is
  complete", not a diff against a committed copy).
- **The wheel** is the release artifact. `Publish Release` bundles, builds the
  wheel and sdist, asserts the wheel carries `_runtime/`, installs and
  exercises it, keeps the distribution as a workflow artifact, uploads it to
  PyPI (the install channel every skill pins against), and attaches that same
  wheel and sdist to the GitHub Release as the provenance copy of what shipped.
- **A checkout** builds its own: run `scripts/bundle/bundle.sh` once after
  cloning (and after pulling changes to `packages/cadgen-js`); a missing runtime
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
metadata (`sync-version.mjs`) and every skill's `cadgen==` pin
(`pin-cadgen-requirements.sh`), commits on `release/<version>`, opens the PR,
merges it through the API (the PAT, as before — no "allow auto-merge" setting
is involved) and deletes the branch. The merged commit is THE release commit.

`Publish Release`, on that push:

1. `check-version.sh`, then the gate: `VERSION` must be past the latest release
   tag (either spelling — `scripts/release/release-tags.sh` is the one place
   that knows `v0.5.0` and the bare `0.4.28` before it, and it compares
   versions, not tag strings), or equal to it with the tag missing.
2. `bundle.sh --clean` — which is where cadgen's whole runtime comes into
   existence, Node builders, snapshot bundle and Viewer client alike, because
   the release commit carries none of it — then `check-builds.sh`, the docs and
   code tests, the wheel-contents check, `python -m build`, and an `unzip -l`
   assertion that the wheel about to ship really holds `_runtime/node`,
   `_runtime/browser` and `_runtime/viewer`.
3. Install test: the built wheel into a fresh venv — `cadgen --help`, `cadgen
   viewer --help`, `cadgen doctor skills/cad-viewer` — then
   `scripts/test/test-installed.sh`; the distribution is uploaded as a workflow
   artifact (`cadgen-<version>`).
4. **On `main` only:** PyPI upload (`skip-existing`, so a rerun is a no-op),
   `Deploy Docs`, then the `v<VERSION>` tag and the GitHub Release, with the
   wheel and sdist from that same artifact attached as release assets (PyPI
   stays the install channel; the release page is the provenance copy). Nothing is
   committed or pushed to `main` after the release PR merge: the tag points at
   the source commit, and `git describe` on `main` is meaningful.

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
scripts/release/pin-cadgen-requirements.sh
scripts/release/check-version.sh --incremented-from "refs/tags/$(source scripts/release/release-tags.sh && latest_release_tag)"
node scripts/release/sync-version.mjs --check
```

`scripts/release/publish-github-release.sh` is the manual fallback for the tag
and GitHub Release step. Unlike `Publish Release`, the script creates a
draft release unless `--publish` is passed.

### Repository settings

`main` requires a PR with every `test.yml` job as a status check — `Version
Check`, `cadgen (Linux)`, `cadgen (Windows)`, `cadgen-js`, `viewer`, `skills`,
`docs`, `packaging` — strict (up to date with `main`), squash merges only, a
linear history, no force pushes and no deletions. A job skipped by its path
condition satisfies its check, so a prose pull request merges on Version Check
alone. Adding or renaming a job means changing this list — the rules `develop`
carried before the cutover, with the job names updated. `Prepare
Release`'s PR merges through the same checks via the API (no "allow auto-merge"
repository setting is needed). `build-test` needs no protection: the
irreversible steps never run there. Keep the repository tag
ruleset (extend its pattern to cover `v[0-9]*.[0-9]*.[0-9]*` beside the bare
form) and immutable releases.

Dependency updates arrive as Dependabot PRs (`.github/dependabot.yml`: weekly,
one grouped PR per ecosystem for minor + patch bumps, labelled `dependencies`
so they land in the release notes' Maintenance category).

### Cutover runbook (one time, manual)

`main` today holds the OLD publish tree: 29 generated commits, each with the
release source commit as its second parent, whose trees carry the materialized
skill runtime and no `models/`. The last is `0e94cd1d Publish 0.4.28 from develop
to main`. A plain merge of the source branch into it conflicted on every path
the publish transformation touched, so the source branch recorded that history
as an ancestor instead: `release/0.5.0` carries `git merge -s ours origin/main`
(dc4f501d), a merge whose tree is the source tree unchanged. Since then PR #273
(`release/0.5.0` → `main`) is an ordinary pull request: the required checks run
on it, and merging it lands the source history on `main` with the old publish
commits reachable as ancestors. Nothing is force-pushed.

Steps, in order (none of these are run by the workflow). Steps 1, 2 and 4 were
done on 2026-09-04; `develop`'s protection is still in place until step 5.

1. Record the current rules (read-only):
   ```bash
   gh repo view --json defaultBranchRef --jq .defaultBranchRef.name     # main
   gh api repos/earthtojake/text-to-cad/branches/develop/protection
   gh api repos/earthtojake/text-to-cad/rulesets
   ```
2. Retire the `main publish only` ruleset (it blocked updates, deletions and
   non-fast-forward pushes and required linear history, which would refuse
   every PR merge). Done: ruleset 17058028 deleted.
3. Land the history: merge PR #273 once its required checks are green. Done
   2026-09-04 as a squash (`gh pr merge 273 --squash`, `main` = 3eb1f9b8); the
   granular source history is kept at `history/0.5.0-source`.
4. Protect `main` the way `develop` was protected (done; the classic
   branch-protection API):
   ```bash
   gh api --method PUT repos/earthtojake/text-to-cad/branches/main/protection \
     --input - <<'JSON'
   {"required_status_checks":{"strict":true,"contexts":["Version Check","cadgen (Linux)","cadgen (Windows)","cadgen-js","viewer","skills","docs","packaging"]},
    "enforce_admins":false,
    "required_pull_request_reviews":{"dismiss_stale_reviews":false,"require_code_owner_reviews":false,"required_approving_review_count":0},
    "restrictions":null,"allow_force_pushes":false,"allow_deletions":false,"required_linear_history":true}
   JSON
   ```
5. Delete the retired branches once nothing references them:
   ```bash
   gh api --method DELETE repos/earthtojake/text-to-cad/branches/develop/protection
   git push origin --delete develop release/0.5.0
   git branch -r | sed -n 's#^ *origin/\(release/.*\)#\1#p' | xargs -n1 git push origin --delete
   ```
6. Archive the mirror and drop its secret: `gh repo archive earthtojake/cad-viewer`
   and `gh secret delete CAD_VIEWER_SYNC_TOKEN`. `BUILD_TEST_PUSH_TOKEN` is
   unused too and can go.
7. Create `build-test` from `main` (`git push origin main:build-test`) so the
   rehearsal target exists; optionally rehearse first with
   `gh workflow run release-prepare.yml --ref main -f bump=minor -f target=build-test`.
8. Re-point PyPI trusted publishing at the new workflow file. A trusted
   publisher is bound to the workflow FILENAME, and the upload used to run from
   `release.yml`; it now runs from `release-publish.yml`. On pypi.org → project
   `cadgen` → Publishing, add a publisher for `earthtojake/text-to-cad`,
   workflow `release-publish.yml` (no environment), then remove the
   `release.yml` one. Skipping this makes the first real upload fail with an
   OIDC "invalid publisher" error after every other gate has passed; the
   rehearsal on `build-test` cannot catch it because it never uploads.
9. The first release after the cutover is an ordinary
   `gh workflow run release-prepare.yml --ref main -f bump=minor` (0.5.0). The
   gate compares against the latest tag (`0.4.28`, bare) and creates `v0.5.0`.

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
npm --prefix apps/viewer run test        # the Viewer's CLIENT half only
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

For fast CAD Viewer source iteration, run the root viewer app in dev mode. Do
not run the packaged viewer from an installed cadgen while modifying Viewer
behavior. Run it from the DIRECTORY YOU WANT SERVED — the dev backend has no
directory flag, so the served root is npm's `INIT_CWD`, and `apps/viewer` is
excluded from that choice on purpose:

```bash
npm --prefix apps/viewer run dev -- --host 127.0.0.1
```

The dev server serves ONE root, fixed at startup; the page is the bare origin
and `?file=` names the artifact relative to that root:
`http://127.0.0.1:<port>/?file=models/thang010146/STEP/gear_rack_gripper.step`.
Do not assume a fixed dev port unless you pass
Vite's standard `--port` flag. Packaged Viewer runtime checks are
production-output checks; use `scripts/README.md` when you specifically need
that path.

## Git Hygiene

Do not commit local environments, dependency folders, caches, or temp files such
as `.venv/`, `node_modules/`, `.vite/`, `dist/`, `tmp/`, or local credentials.
Generated runtime changes should come from the production-output workflow, not
manual edits inside generated runtime folders.

CAD exchange files, generated render/topology assets, and `assets/**` may be
LFS-tracked. Never disable LFS filters for `git add`, commits, or other
object-writing operations.

`assets/**` holds heavyweight demo GIFs and is excluded from default LFS pulls,
so lightweight clones do not fetch it. Hydrate it only when you need the demo
assets locally:

```bash
git lfs pull --include="assets/**"
```
