# Contributing

This repository is a local workbench for CAD-related agent skills. Treat
`skills/` as the product under test and `models/` as the shared
fixture/artifact area.

## Local Checkout

`main` is the only long-lived branch: branch from it and open PRs back to it.

```bash
git clone https://github.com/earthtojake/text-to-cad.git
cd text-to-cad
git switch -c my-change
```

Create the repo-local Python development environment:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-dev.txt
```

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

Install the runtime's JavaScript workspaces, then build cadgen's packaged
runtime once:

```bash
npm ci --workspace packages/core --workspace packages/ui --workspace apps/web
scripts/bundle/bundle.sh
```

`packages/cadgen/src/cadgen/_runtime/` is BUILT, not committed — the whole
directory is gitignored, and the wheel is the only place those files ship. A
fresh clone therefore has no Node builders, no snapshot browser bundle and no
Viewer client until the bundler runs, and cadgen says so by name (naming this
command) the first time it reaches for one. `scripts/test/test-python.sh` and
`scripts/test/test-global.sh` build the two stages they read if they are
missing, so this step is about having the whole thing, including the Viewer
client the wheel carries.

For CAD Viewer development:

```bash
npm ci
npm run build:packages
```

When running a tool manually, use an interpreter that can import cadgen (the
repo `.venv`, or a skill-specific one) and invoke the `cadgen` front door:

```bash
./.venv/bin/python -m cadgen.cli step inspect --help
./.venv/bin/python -m cadgen.cli urdf validate --help
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

`test.yml` selects work from the dependency graph. Each job installs only its
root npm workspaces; Python and the two Playwright browser installations are
requested separately. A manual dispatch runs every job.

| Check | Runs for | Coverage |
| --- | --- | --- |
| Version Check | every change | canonical version, derived metadata, skill pins |
| cadgen (Linux/Windows) | cadgen, core, infrastructure | Python engine, daemon, CLI and viewer backend |
| cadgen-js | core, infrastructure | `@hardcore/core` and benchmark helper units |
| viewer | web, UI, core, cadgen, infrastructure | affected UI/web units, bundled launch, format/picking/kinematics/camera browser checks |
| skills | skills or runtime/host contracts | repo policy; skill CLI suites only for skills, cadgen, core or infrastructure |
| docs | docs, skills, cadgen, core, infrastructure | static asset contract, lint, Next build, icon verification |
| packaging | cadgen, core, UI, web, infrastructure | clean bundle, wheel contents, installed CLI behavior |
| Desktop (macOS) | desktop, UI, core, cadgen, infrastructure | native dependencies, typecheck, lint, unit tests, build, Electron tests |

Here `cadgen`, `core` and `UI` mean their package directories and tests;
`web`, `docs` and `desktop` mean their app directories. Infrastructure includes
`scripts/`, `.github/`, the root lockfile/manifests and version/plugin metadata.
Root prose, manual model changes and `LICENSE` run only Version Check. Skill
and package Markdown is test input and follows its owning component.

The eight existing required check names remain unchanged; `cadgen-js` is the
legacy GitHub check name for `@hardcore/core`, not a package to install. Desktop
has its own conditional check. A skipped job satisfies its required check;
renaming required checks needs a matching branch-protection update. Do not
change repository settings as a side effect of a code refactor.

A web-only edit does not run desktop or the Python engine. A UI edit exercises
both hosts, while a desktop-only edit runs desktop and policy. Core changes
reach every consumer. Policy checks for a host edit do not also run every skill
CLI suite. Windows runs the Python package suite because paths, locks,
subprocesses, file URLs and daemon behavior are platform-sensitive; Electron's
native integration is covered separately on macOS.

Viewer browser failures upload bounded renderer-state JSON for three days.
CI sets `VIEWER_TEST_DIAGNOSTICS_DIR` for this evidence; it does not enable the
optional review screenshots produced by `--out`. Capture timing stays in the
job log, so a stalled screenshot still leaves useful state diagnostics.

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
- `apps/web/` for the CAD Viewer's React client. Its backend is
  `cadgen.viewer` (in `packages/cadgen`), and its built `dist/` ships inside the
  cadgen wheel as `cadgen/_runtime/viewer` — built at release time, never
  committed.
- `apps/desktop/` for Electron workflows and native services; `apps/docs/` for the site.
- `packages/cadgen/` for the Python distribution and bundled runtime assets.
- `packages/core/` for non-React CAD/client code.
- `packages/ui/` for FileViewer, renderers, controls and shared styles.

One source tree ships whole and must work in isolation outside this repo — the
ships-alone law, enforced by the markdown-isolation check in
`tests/python/global/test_package_boundaries.py`: `packages/cadgen` builds into
the PyPI wheel with @hardcore/core and the viewer client bundled in at build time; its
README is the PyPI long description. Markdown under it must be true and
actionable with this repo gone: name the bundled thing ("the @hardcore/core runtime
bundled at build time"), never the repo path to its source, and keep commands
relative to the package itself. Repo-development guidance belongs here, not in
the package. `apps/web` is a client package with a boundary of its own
(`apps/web/scripts/selfContained.test.mjs`): it imports @hardcore/core and @hardcore/ui by their public exports; relative
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

The apps are `docs`, `web` and `desktop`. Framework-independent CAD code lives
in `@hardcore/core`; `@hardcore/ui` owns the complete FileViewer and injectable
renderers. Apps consume compiled public exports. Apps never import another app,
and packages never import apps. `npm run check:boundaries` checks the graph,
including aliases, re-exports and dynamic imports.

Package movement is a pure refactor: preserve UI, UX, file actions, defaults and
persistence. Incorporate explicitly requested upstream features in the shared
components so web and desktop receive the same behavior. Package/app READMEs
state the ownership rules.

Install from the repository root, selecting only the workflow being exercised:

```bash
# Python engine/runtime or shared core work:
npm ci --workspace @hardcore/core
npm run build --workspace @hardcore/core
# Viewer and shared UI work:
npm ci --workspace @hardcore/core --workspace @hardcore/ui --workspace @hardcore/web
npm run build:packages
# Docs work:
npm ci --workspace @hardcore/core --workspace cad-skills-docs
npm run build:docs
# Desktop work:
npm ci --workspace @hardcore/core --workspace @hardcore/ui --workspace hardcore
npm run native:rebuild --workspace hardcore
npm run build:desktop
```

There is one root lockfile. Do not create nested lockfiles or symlink dependency
trees from another checkout. Rebuild shared packages after editing them;
Vite, Next and Electron consume their `dist` exports. `npm ci` without a
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
changes. The web app owns URL/history and browser preferences; desktop owns
IPC, projects and native processes. FileViewer state is scoped by root, file
and renderer; each CAD render session owns its cache provider and worker lease.

The standalone launcher is `cadgen viewer`. A source checkout can serve the
local web build; `CADGEN_VIEWER_DIST`, `CADGEN_NODE_BUILDERS_DIR` and
`CADGEN_BROWSER_RUNTIME_DIR` are explicit asset overrides. A wheel resolves its
own bundled assets without the repository. Run `scripts/bundle/bundle.sh` after
editing build inputs to refresh all packaged outputs.

The self-contained browser suite creates tiny inputs and owns its project,
viewer and cache. It never reads the sample-model corpus. Install the npm
Playwright Chromium for UI/web tests and Python Playwright Chromium for
snapshot tests; their revisions can differ:

```bash
npx --no-install playwright install chromium
.venv/bin/python -m playwright install chromium
scripts/bundle/bundle.sh
scripts/test/test-viewer-browser.sh --ci
scripts/test/test-viewer-browser.sh --only kinematics
scripts/test/test-viewer-browser.sh
```

Use `--with-deps` when installing browsers on Linux. The CI subset covers
formats, picking, kinematics and camera behavior; the full browser gate adds
placement, appearance and quality transitions. Backend tests live in
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
`_runtime/browser`, and the CAD Viewer client under `_runtime/viewer` — is
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
- **Desktop** embeds that same wheel in a private Python runtime for each
  platform. Installers, blockmaps and `latest*.yml` update feeds are workflow
  artifacts until the tag job attaches them alongside the wheel and sdist on
  the same GitHub Release. These generated assets are never committed.
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
   `scripts/test/test-installed.sh --wheel <built-wheel>`; the distribution is uploaded as a workflow
   artifact (`cadgen-<version>`).
4. The desktop matrix downloads that exact wheel, freezes its dependency
   closure, builds private Python runtimes and packages macOS, Windows and
   Linux installers. Each completed platform uploads its installers, blockmaps
   and update feeds as workflow artifacts. See `apps/desktop/README.md` for
   signing, packaging and local qualification.
5. **On `main` only:** PyPI upload (`skip-existing`, so a rerun is a no-op),
   `Deploy Docs`, then the `v<VERSION>` tag and GitHub Release. The tag job
   attaches the wheel, sdist and all completed desktop artifacts through one
   create/resume path; it does not rebuild them. A failed desktop platform does
   not leave an already published Python release untagged, but failures to
   download existing artifacts fail the job. Nothing is committed or pushed
   to `main` after the release PR merge: the tag points at the source commit.

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

`main` requires a PR with eight stable status checks — `Version
Check`, `cadgen (Linux)`, `cadgen (Windows)`, `cadgen-js`, `viewer`, `skills`,
`docs`, `packaging` — strict (up to date with `main`), squash merges only, a
linear history, no force pushes and no deletions. A job skipped by its path
condition satisfies its check, so a prose pull request merges on Version Check
alone. The additional conditional `Desktop (macOS)` check exercises the app;
changing required check names also requires updating GitHub branch protection.
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

CAD exchange files, generated render/topology assets, and `assets/**` may be
LFS-tracked. Never disable LFS filters for `git add`, commits, or other
object-writing operations.

`assets/**` holds heavyweight demo GIFs and is excluded from default LFS pulls,
so lightweight clones do not fetch it. Hydrate it only when you need the demo
assets locally:

```bash
git lfs pull --include="assets/**"
```
