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
development. Skill-specific environments may install generated, skill-local
package copies so they match production, but on `develop` you should still edit the
source package under `packages/*`.

For CAD Viewer development:

```bash
npm --prefix viewer install
```

When running a tool manually, use that skill's interpreter:

```bash
.venv/skills/cad/bin/python skills/cad/scripts/gen --help
python3 skills/urdf/scripts/validate --help  # stdlib-only validator, no venv needed
```

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
iterating: `models/` contains fixtures and generated CAD artifacts, `viewer/`
contains the editable CAD Viewer source, and repo-relative validation commands
live under `scripts/`.

Write test, sample, and durable CAD/robot-description artifacts under `models/`;
do not create ad hoc artifact directories elsewhere. When you need a scratch
project, create it under the fixture bucket it belongs in (for example
`models/step/parts/my-test` for a standalone part), for example:

```bash
mkdir -p models/step/parts/my-test
```

Then start your agent with `/path/to/text-to-cad` as the working directory and
ask it to write files under that scratch path. This keeps skill scripts,
fixtures, generated sidecars, and Viewer links using the same repo-relative
paths that CI and local checks expect.

Review media such as snapshot PNGs and orbit GIFs are not model artifacts:
render them under `/tmp` and attach them to the pull request instead. `.gitignore`
keeps them out of `models/`.

## Source Boundaries

Each skill must be self-contained and independent when it is installed from a
production branch: it must not import or depend on code from another skill or
from repository-root modules at runtime.

The `develop` branch uses symlinks as a checkout layout convenience. Those symlinks
point generated-output paths back to the canonical sources so contributors can
edit one copy of shared code. They do not relax the runtime self-containment
rule: production branches must be able to replace the symlinks with real copies
that still run without `skills/`, the repository root, or sibling skill
directories on `sys.path`, `PYTHONPATH`, `NODE_PATH`, or similar lookup paths.

Canonical source directories are:

- `skills/*` for skill instructions, references, and skill-owned scripts.
- `viewer/` for CAD Viewer app and server source.
- `packages/*` for shared runtime helpers that are copied into consuming skills
  for production.

On `develop`, paths such as `skills/cad-viewer/scripts/viewer`,
`skills/*/scripts/packages/*`, and `viewer/packages/*`
should be symlinks when they mirror root sources. Treat those paths as
generated-output aliases, not separate source roots. Edit the canonical source
path instead.

Production-output checks are intentionally centralized. Normal development
should stay in the symlinked `develop` layout. When you specifically need to inspect
production outputs locally, use a temporary checkout or rerun
`scripts/dev/setup-symlinks.sh` afterward, then run:

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

Because the repository root is the plugin package, every source-only path on
`main` is copied into every install. The publish job therefore trims the tree
before committing it, after the bundle and all checks have run against the
untrimmed tree. `models/`, `viewer/`, `tests/`, `docs/`, `packages/`, and
`requirements-dev.txt` are removed, leaving `main` as close to just the plugin
package as it can be.

Nothing is lost, because each of those has a consumer that reads **source**
rather than the published tree:

- `viewer/` — what installs and runs is the dereferenced runtime under
  `skills/cad-viewer/scripts/viewer`, and the standalone cad-viewer mirror syncs
  from the release source commit.
- `docs/` and `packages/` — `Deploy Docs` builds and deploys from the release
  source commit. `packages/` has no other published consumer: every skill
  vendors the runtimes it needs, and the trim step fails the publish if a skill
  is found reaching into repo-root `packages/`.
- `models/`, `tests/`, `requirements-dev.txt` — source-only, with no consumer
  outside a source checkout.

`main` is publish-only: do not open PRs to `main` or push it directly. The `Test`
workflow runs on `develop` and PRs to `develop`: it starts from the symlink
layout, verifies that layout, checks generated outputs against their sources
with `scripts/bundle/bundle.sh --check`, runs `scripts/bundle/bundle.sh
--clean`, checks the production layout without rebuilding it, runs
documentation checks, and runs the code tests against that generated output.

Most generated paths cannot drift on `develop` because they are symlinks to
their canonical sources, and the freshness check skips those. It covers the
generated outputs that `develop` does commit as real files, such as the CAD
snapshot runtime built from `packages/cadjs` and `packages/implicitjs`, and
version metadata derived from `VERSION`.

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

It cannot deploy `main`. The docs app builds against repo-root `packages/`
(`docs/tsconfig.json` maps `cadjs/*` to `../packages/cadjs/src/*`), and the
publish tree drops both `docs/` and `packages/`. The workflow checks for them up
front and fails with that explanation rather than an opaque module-resolution
error inside `next build`.

To redeploy the site as it stood at a past release, use that release's source
commit. Every publish commit records it as its second parent:

```bash
gh workflow run deploy-docs.yml -f ref="$(git rev-parse 0.4.6^2)"
```

The CAD Viewer is a local-filesystem app and has no hosted deployment.

### Mirroring the CAD Viewer repo

`viewer/` is published as its own standalone repo,
[`earthtojake/cad-viewer`](https://github.com/earthtojake/cad-viewer). The
`Release` workflow calls `Sync CAD Viewer Repo` after publishing to `main`, so
the mirror tracks releases rather than in-flight `develop` work. It mirrors from
the release **source** commit, not from `main`, which carries no `viewer/`.
Dispatch it on its own for an out-of-band sync, or with `dry_run` to build and
verify the mirror without pushing:

```bash
gh workflow run sync-cad-viewer.yml -f ref=develop
gh workflow run sync-cad-viewer.yml -f ref=develop -f dry_run=true
```

Use a past release's source commit — `git rev-parse <tag>^2` — to re-sync the
mirror as it stood at that release.

The workflow needs a `CAD_VIEWER_SYNC_TOKEN` secret with `contents:write` on the
mirror repo. Before pushing, it runs `npm ci`, `npm run test`, `npm run build`,
`pip install -r requirements.txt`, and the `server_py` tests inside the mirror,
so a mirror that cannot stand on its own fails the release instead of shipping.

The sync is a **straight copy** — nothing rewrites paths, commands, or prose on
the way out, and it does not run or depend on `bundle.sh`. The only structural
change is dereferencing `viewer/packages/*` into real directories; the script
refuses to publish a tree that still contains a symlink. What lands in the
mirror's `packages/` is whatever `viewer/packages/` holds, so syncing from a
published `main` mirrors the committed bundle output that `bundle.sh --check`
already validated. A sync from `develop` dereferences the symlinks to the live
package sources instead — a development snapshot, not what a release publishes,
and the script says so when it sees that layout. That works only because
`viewer/` stays self-contained, which `viewer/scripts/selfContained.test.mjs`
enforces on every test run: no import, markdown link, or `package.json` script
under `viewer/` may reach above it. Repo-level tooling belongs in `scripts/`,
not under `viewer/`.

To sync into a local clone, or to check an existing one for drift:

```bash
scripts/viewer/sync-cad-viewer-repo.sh ../cad-viewer
scripts/viewer/sync-cad-viewer-repo.sh --check ../cad-viewer
```

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
npm --prefix viewer run test
npm --prefix docs run check
```

Use `AGENTS.md` or `scripts/README.md` for path-specific validation when you are
working in a particular package, skill, docs site, or production-output
path.

For targeted Python skill-script tests, run the relevant unittest files with the
repo-local Python runtime, for example:

```bash
./.venv/bin/python -m unittest tests/python/skills/urdf/test_cli.py
```

Python tests live under `tests/python/`, grouped by tested surface:
`skills/<skill>`, `packages/<package>`, `viewer/<service>`, and `global`.

For fast CAD Viewer source iteration, run the root viewer app in dev mode. Do
not run the generated viewer from the cad-viewer skill while modifying Viewer
behavior:

```bash
npm --prefix viewer run dev -- --host 127.0.0.1
```

Put the absolute workspace directory in the URL path and the artifact in
`?file=<path relative to it>` — pick the project's model root, not the file's own
folder, so the file browser lists the whole project:
`http://127.0.0.1:<port>/abs/project/models?file=mechanisms/lift_table.step.py`.
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
