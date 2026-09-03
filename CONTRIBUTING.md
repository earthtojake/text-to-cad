# Contributing

This repository is a local workbench for CAD-related agent skills. Treat
`skills/` as the product under test and `models/` as the shared
fixture/artifact area.

## Local Checkout

For development, branch from `develop` and open PRs back to `develop`:

```bash
git clone --branch develop https://github.com/earthtojake/text-to-cad.git
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
reported number drift further from the code than it has to. Skill-specific environments may install generated, skill-local
package copies so they match production, but on `develop` you should still edit the
source package under `packages/*`.

For CAD Viewer development:

```bash
npm --prefix apps/viewer install
```

When running a tool manually, use an interpreter that can import cadgen (the
repo `.venv`, or a skill-specific one) and invoke the `cadgen` front door:

```bash
./.venv/bin/python -m cadgen.cli step inspect --help
./.venv/bin/python -m cadgen.cli urdf validate --help
```

The skills ship no launcher scripts: every operational verb is a `cadgen`
subcommand (`cadgen <verb>`, or `python -m cadgen.cli <verb>` when the console
script is not on PATH), and a model script builds itself (`python <model>.py`).
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

Run development and test prompts from inside this repository instead of a
separate project checkout. The skills assume this workbench layout while you are
iterating: `models/` contains fixtures and generated CAD artifacts, `apps/viewer/`
contains the editable CAD Viewer source, and repo-relative validation commands
live under `scripts/`.

Write test, sample, and durable CAD/robot-description artifacts under `models/`;
do not create ad hoc artifact directories elsewhere. When you need a scratch
project, create it under the fixture bucket it belongs in (a demo part or
assembly belongs in the `models/examples/` cad-project — script in `src/`,
artifact declared into a format folder), for example:

```bash
$EDITOR models/examples/src/my_test.py     # @step(out="../STEP/my_test.step")
python models/examples/src/my_test.py
```

Then start your agent with `/path/to/text-to-cad` as the working directory and
ask it to write files under that scratch path. This keeps skill scripts,
fixtures, generated sidecars, and Viewer links using the same repo-relative
paths that CI and local checks expect.

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
  cadgen wheel as `cadgen/_runtime/viewer`.
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
- Editing anything the bundlers consume? `scripts/bundle/bundle.sh`, then commit
  the regenerated `_runtime/node` and `_runtime/browser` (`_runtime/viewer` is
  gitignored: the wheel build writes it, a checkout serves `apps/viewer/dist`).
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

Launcher reuse keys on realpath(root) × identity token (the cadgen version
salted with the newest mtime across `cadgen/viewer/*.py` and the default client
location), so another checkout's instance can never be handed back for a
worktree's root — and a resident instance running pre-pull or pre-rebuild code
fails the match and a fresh one starts.

Worktrees deliberately carry no `node_modules`; link them from the primary
checkout before building. cadgen-js needs all three of its runtime
dependencies linked — `three-mesh-bvh` included, which an earlier version of
this recipe omitted:

```bash
ln -s <main>/apps/viewer/node_modules apps/viewer/node_modules
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

Production-output checks are intentionally centralized:

```bash
scripts/bundle/bundle.sh --clean
scripts/bundle/bundle.sh --check
```

Do not run lower-level bundle scripts as part of routine iteration; use the
script-specific details in `scripts/README.md` only when you are debugging a
production-output check.

## Branch Layouts

Open development PRs against `develop`, not `main`. The `develop` branch keeps
generated copy targets as symlinks so the editable source remains under
`skills/`, `viewer/`, and `packages/`:

```bash
scripts/dev/setup-symlinks.sh
scripts/dev/setup-symlinks.sh --check
```

The `main` production branch must be installable from a plain checkout, so it
contains generated production outputs instead of symlinks. The repository root
is itself the agent plugin package — `.claude-plugin/` and `.codex-plugin/` hold
the manifests and the plugin's skills are `skills/` directly — so whatever is on
`main` is what agent installers copy.

Replacing symlinks with real copies on `main` is a correctness requirement, not
a convention. The installers disagree about symlinks and one loses data
silently: the Skills CLI dereferences them into real files, Claude Code
preserves them verbatim, and Codex `plugin add` drops them with no error at all,
publishing a skill whose files are simply missing at runtime.
`scripts/github-workflows/check-builds.sh` is the gate that enforces this.

`main` is `develop` with the skill bundles materialized, versions stamped, skill
requirements pinned to the release, and ONLY `models/` removed. The publish job
(`.github/workflows/release.yml`) produces it in this order, after the bundle and
every check have run against the untrimmed tree: `scripts/release/prepare-publish-tree.sh`
drops `models/`; `scripts/release/pin-cadgen-requirements.sh` rewrites every skill's
`cadgen` line to `cadgen==<VERSION>`; `scripts/github-workflows/check-publish-tree.sh`
asserts the result over exactly the paths `git add -A` will stage; then the
publish commit is written. Root `docs/` (the hand-migration guides) ships too,
because the cad skill's migration references link to it by hosted URL.

What that means for what you find on `main`:

- `apps/`, `packages/`, `tests/`, and `requirements-dev.txt` are present. They
  used to be trimmed; they no longer are, because the source behind a release
  should be discoverable on the default branch and together they are ~15 MB with
  no LFS objects. `models/` is the fixture corpus, the one root whose absence
  buys anything, and the only one removed.
- `apps/viewer/` (the CAD Viewer client's source) is there to read. The
  Viewer itself ships in the cadgen wheel (`cadgen viewer`), so no skill carries
  a runtime and nothing is bundled into the publish tree.
- `tests/` ships without its `models/` fixtures, so it is readable, not runnable,
  on `main`. Run the suites from a `develop` checkout.
- `packages/` being present is NOT permission for a skill to import from it. The
  ships-alone law stands: the Skills CLI installs `skills/<name>` alone, plugin
  installers copy the whole tree, and neither runs an editable install, so a
  skill that reached into `../../../packages/` would work on `main` and break
  on the first `npx skills add`. `check-publish-tree.sh` fails the publish on any
  such reference; `tests/python/global/test_skill_self_containment.py` and
  `test_package_boundaries.py` hold the same law on `develop`.
- No symlink, anywhere. The repository has no development symlinks left, and
  `check-publish-tree.sh` refuses any that appears.
- No LFS-tracked path except the README demo media under `assets/`. Installers
  clone without git-lfs and receive pointer files, so an LFS-tracked skill fixture
  or runtime asset would ship broken; `check-publish-tree.sh` fails on any LFS
  path outside `assets/`. The three gifs stay LFS-tracked because they are 17-26
  MB each and GitHub renders LFS media in the README regardless.

`main` is publish-only: do not open PRs to `main` or push it directly. The `Test`
workflow runs on `develop` and PRs to `develop`: it checks generated outputs
against their sources with `scripts/bundle/bundle.sh --check`, runs
`scripts/bundle/bundle.sh --clean`, checks the production layout without
rebuilding it, runs documentation checks, and runs the code tests against that
generated output.

The freshness check covers the generated outputs `develop` commits as real
files — cadgen's Node builders and snapshot runtime built from
`packages/cadgen-js` — and version metadata derived from `VERSION`. The viewer
client (`_runtime/viewer`) is gitignored and built only for the wheel.

## Releases

Normal development PRs should not bump `VERSION`; release versions
are reserved for release PRs so the canonical repo version, Git tag, and GitHub
Release describe the same production commit. PRs that do touch release state
must keep `VERSION` and derived version metadata valid; the `Test`
workflow checks that metadata in a separate job so code tests still run when it
is wrong.

### Shipping a release

Run the `Release` GitHub Actions workflow. Its defaults are the real-release
settings — build from `develop` (`base_branch=develop`), publish to `main`
(`target_branch=main`), and publish the GitHub Release (`publish=true`, not a
draft) — and the input descriptions in `.github/workflows/release.yml` are
authoritative. Choose the semver bump (`patch`, `minor`, or `major`) or an
exact `set_version` deliberately for every release; if a release request does
not specify one, confirm it rather than assuming. `bump=none` is not a release
setting — see "Publishing without a version bump" below:

```bash
gh workflow run release.yml --ref develop -f bump=patch
```

One run bumps `VERSION` plus derived metadata on a
`release/<version>` branch, opens a release PR, merges it into `develop`
immediately, and then runs the publish, docs deploy, and tag/GitHub Release
jobs in the same run. The release PR does not wait for its own CI checks; the
publish job repeats the full bundle and test validation against exactly what
ships. The publish job ships to `main` only when the
source version is newer than `main` and the latest semver tag, and refuses
sources that do not contain the previous publish source commit. It writes a
generated production merge commit on top of the previous publish target with
the release source as the second parent, which keeps `main` fast-forwardable
while preserving source commits for release notes and contributor attribution.
The GitHub Release is published immediately by default; set `publish=false` to
review it as a draft first. Treat generated outputs as CI products, not edit
targets.

The publish job also uploads `packages/cadgen` to
[PyPI](https://pypi.org/project/cadgen/). The upload runs after the production
bundle is validated but BEFORE `main` is pushed: the publish tree pins
`cadgen==<version>` from PyPI (`scripts/release/pin-cadgen-requirements.sh`
rewrites the editable requirement lines), so a failed PyPI upload must block the
release rather than ship a `main` whose skill installs cannot resolve. The PyPI version always
equals `VERSION`; `sync-version.mjs` stamps
`packages/cadgen/pyproject.toml` and the publish job refuses to upload on a
mismatch. Uploads use `skip-existing`, so a rerun after a post-upload failure
(for example a failed `main` push) is idempotent and resumes like any other
failed publish. Local development keeps the editable symlinked installs.

#### One-time PyPI setup

The PyPI upload authenticates with [trusted
publishing](https://docs.pypi.org/trusted-publishers/) (GitHub OIDC); no API
token secret is stored. Before the first release that publishes to PyPI, add a
trusted publisher for the `cadgen` project on PyPI (use "Add a pending
publisher" if the project does not exist yet): repository
`earthtojake/text-to-cad`, workflow `release.yml`, environment left blank.

### Publishing without a version bump

`bump=none` publishes `base_branch` exactly as it stands: no version change, no
release PR, straight to the publish jobs. Use it whenever the version is already
right or is beside the point — resuming a failed publish, and rehearsing the
pipeline against `build-test`. `set_version` is only for naming a specific *new*
version; it is not the way to say "leave the version alone".

`sync-version.mjs` still runs under `bump=none`, so a base branch whose derived
metadata has drifted from `VERSION` is caught and goes through a release PR
rather than publishing the drift.

### Testing CI/CD and build changes

Use `target_branch=build-test` only when explicitly testing changes to the
CI/CD pipeline or production build outputs; it is never part of a normal
release and should never be chosen by default. It rehearses the full publish
flow without touching `main`, deploying, creating a tag/release, uploading to
PyPI, or syncing the CAD Viewer mirror:

```bash
gh workflow run release.yml --ref <branch> \
  -f bump=none -f base_branch=<branch> -f target_branch=build-test
```

Pair it with `bump=none` so a rehearsal does not consume a version number or
move `VERSION` on the branch you are testing. Bump for real (`bump=patch`) only
when the change under test is the version machinery itself — `bump-version.sh`
or `sync-version.mjs` — since `bump=none` skips that stage. `dry_run=true`
previews the version changes only, and `auto_merge=false` stops after preparing
the release PR.

### Resuming a failed publish

If a run fails partway — including after `main` has moved but before the semver
tag exists — rerun `Release` with `bump=none`. The version already reached
`base_branch` on the first attempt, so there is nothing to bump; the workflow
skips the release PR and proceeds straight to the publish jobs, and the publish
gate handles both shapes (`main` not yet moved, and `main` moved with the tag
missing).

### Redeploying the docs site

The standalone `Deploy Docs` workflow redeploys the docs site to Vercel
production without running a release. It deploys a **source** ref and defaults
to `develop`:

```bash
gh workflow run deploy-docs.yml -f ref=develop
```

Deploy from a source ref, not `main`. The docs app lives at `apps/docs/` and
builds against repo-root `packages/` (`apps/docs/tsconfig.json` maps
`cadgen-js/*` to `../../packages/cadgen-js/src/*`). `main` carries both since
the publish trim stopped at `models/`, but the site is built from the commit the
release was cut from (the one `git rev-parse <tag>^2` recovers), and publish
commits from before that change have no `apps/` at all. The workflow checks for
`apps/docs` and `packages/cadgen-js/src` up front and fails with that
explanation rather than an opaque module-resolution error inside `next build`.

The deploy runs the Vercel CLI from the repo root and takes the project root
from the **Vercel project's Root Directory setting**, which lives in Vercel, not
in this repo; it must read `apps/docs` (see `apps/docs/README.md`). No docs
deploy has run since the site moved there, so the first post-move deploy is the
one that proves the setting.

To redeploy the site as it stood at a past release, use that release's source
commit. Every publish commit records it as its second parent:

```bash
gh workflow run deploy-docs.yml -f ref="$(git rev-parse 0.4.6^2)"
```

The CAD Viewer is a local-filesystem app and has no hosted deployment.

### Local and manual fallbacks

For local release preparation, use the same scripts the workflow calls:

```bash
git fetch origin develop
git fetch --tags origin
scripts/release/bump-version.sh patch --no-commit
node scripts/release/sync-version.mjs
scripts/release/check-version.sh --incremented-from origin/main
node scripts/release/sync-version.mjs --check
```

`scripts/release/publish-github-release.sh` is the manual fallback for the tag
and GitHub Release step. Unlike the `Release` workflow, the script creates a
draft release unless `--publish` is passed.

### Repository settings

Configure GitHub branch settings/rulesets so `main` rejects PRs and direct
pushes, leaving the `Release` workflow's publish job as the only writer. Enable
repository tag rulesets for `[0-9]*.[0-9]*.[0-9]*` before publishing from
`main`, and enable immutable releases once the production flow is trusted.

Production users should continue cloning `main`; developers should treat
`develop` plus the `Release` workflow as the only route to `main`.

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
scripts/dev/setup-symlinks.sh --check
scripts/release/check-version.sh
npm --prefix apps/viewer run test        # the Viewer's CLIENT half only
scripts/test/test-python.sh              # includes the Viewer's BACKEND suite
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
behavior:

```bash
npm --prefix apps/viewer run dev -- --host 127.0.0.1
```

The dev server serves ONE root, fixed at startup (the directory Vite runs
from); the page is the bare origin and `?file=` names the artifact relative to
that root:
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
