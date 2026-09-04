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

Mesh exports (`@stl`/`@3mf`/`@glb`) and DXF previews run the checkout's live
`packages/cadgen-js/bin` builders in Node, which import `three` and friends
from `packages/cadgen-js/node_modules`. A fresh worktree has none, and cadgen
refuses with an error naming this paragraph rather than letting the child die
with `ERR_MODULE_NOT_FOUND`. Symlink both `node_modules` directories from the
primary checkout (they are gitignored) or `npm install` in each package:

```bash
ln -s <main>/packages/cadgen-js/node_modules <worktree>/packages/cadgen-js/node_modules
ln -s <main>/apps/viewer/node_modules <worktree>/apps/viewer/node_modules
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

The `Test` workflow runs on pushes to `main` and PRs against it: it checks
generated outputs against their sources with `scripts/bundle/bundle.sh --check`,
runs `scripts/bundle/bundle.sh --clean`, checks the layout without rebuilding
it, runs documentation checks, and runs the code tests against that generated
output. The freshness check covers the generated outputs `main` commits as real
files — cadgen's Node builders and snapshot runtime built from
`packages/cadgen-js` — and version metadata derived from `VERSION`. The viewer
client (`_runtime/viewer`) is gitignored and built only for the wheel.

## Releases

Normal development PRs should not bump `VERSION`; release versions are reserved
for release PRs so the canonical repo version, the skill pins, the Git tag, the
PyPI wheel and the GitHub Release all describe one commit. PRs that do touch
release state must keep `VERSION`, the derived metadata and the pins valid; the
`Test` workflow checks all three in a separate job so code tests still run when
they are wrong.

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
2. `bundle.sh --clean` (cadgen's committed runtime reproduced byte for byte
   plus the gitignored viewer client), `check-builds.sh`, the docs and code
   tests, the wheel-contents check, `python -m build`.
3. Install test: the built wheel into a fresh venv — `cadgen --help`, `cadgen
   viewer --help`, `cadgen doctor skills/cad-viewer` — then
   `scripts/test/test-installed.sh`; the distribution is uploaded as a workflow
   artifact (`cadgen-<version>`).
4. **On `main` only:** PyPI upload (`skip-existing`, so a rerun is a no-op),
   `Deploy Docs`, then the `v<VERSION>` tag and the GitHub Release. Nothing is
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

For local release preparation, use the same scripts the workflow calls:

```bash
git fetch --tags origin
scripts/release/bump-version.sh patch --no-commit
node scripts/release/sync-version.mjs
scripts/release/pin-cadgen-requirements.sh
scripts/release/check-version.sh --incremented-from "refs/tags/$(source scripts/release/release-tags.sh && latest_release_tag)"
node scripts/release/sync-version.mjs --check
```

`scripts/release/publish-github-release.sh` is the manual fallback for the tag
and GitHub Release step. Unlike `Publish Release`, the script creates a
draft release unless `--publish` is passed.

### Repository settings

`main` requires a PR with the `Version Check`, `Test (Linux)` and `Test
(Windows)` status checks (strict: up to date with `main`), no force pushes and
no deletions — the rules `develop` carried before the cutover. `Prepare
Release`'s PR merges through the same gate via the API (no "allow auto-merge"
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
to main`; its merge base with the source history is `cce04de6` (the 0.4.28
release merge on `develop`). A normal merge of the source branch into it
conflicts on every path the publish transformation touched (the deleted
symlinks, `models/`, the pins), so the first landing replaces `main`'s history
rather than merging into it. Two options:

- **A (recommended): fast-forward `main` to the source head.** Land this work
  on the source branch first (merge `claude/cadgen-viewer` into
  `release/0.5.0`, finish 0.5.0 there), then point `main` at that head. The
  publish commits stay reachable from the release tags (`0.4.28^1` is the old
  main tip), so nothing is lost, and `main`'s history becomes the source
  history with no synthetic commits in it.
- **B: force-push the branch directly.** Same result, skipping the intermediate
  merge; only if 0.5.0 is not going to be finished on `release/0.5.0` first.

Steps, in order (none of these are run by the workflow):

1. Confirm the default branch and record the current rules (read-only):
   ```bash
   gh repo view --json defaultBranchRef --jq .defaultBranchRef.name     # main
   gh api repos/earthtojake/text-to-cad/branches/develop/protection
   gh api repos/earthtojake/text-to-cad/rulesets                          # "main publish only", id 17058028
   ```
2. Retire the `main publish only` ruleset (it blocks updates, deletions,
   non-fast-forward pushes and requires linear history — which would refuse
   both the cutover push and every future PR merge):
   ```bash
   gh api --method DELETE repos/earthtojake/text-to-cad/rulesets/17058028
   ```
3. Land the history. Option A:
   ```bash
   git fetch origin
   git push origin release/0.5.0:main --force-with-lease=main:0e94cd1d
   ```
   Option B: `git push origin claude/cadgen-viewer:main --force-with-lease=main:0e94cd1d`.
   `--force-with-lease` pins the expected old tip so a concurrent publish
   cannot be overwritten unseen.
4. Protect `main` the way `develop` was protected (the classic branch-protection
   API, mirroring what step 1 recorded):
   ```bash
   gh api --method PUT repos/earthtojake/text-to-cad/branches/main/protection \
     --input - <<'JSON'
   {"required_status_checks":{"strict":true,"contexts":["Version Check","Test (Linux)","Test (Windows)"]},
    "enforce_admins":false,"required_pull_request_reviews":null,"restrictions":null,
    "allow_force_pushes":false,"allow_deletions":false,"required_linear_history":false}
   JSON
   ```
   The `Test` workflow must have run once on `main` for the contexts to exist;
   push a no-op PR if GitHub rejects unknown contexts.
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
