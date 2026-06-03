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
python3.11 -m venv .venv
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
.venv/skills/cad/bin/python skills/cad/scripts/step --help
.venv/skills/urdf/bin/python skills/urdf/scripts/urdf --help
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
project, create it under this checkout, for example:

```bash
mkdir -p models/experiments/my-test
```

Then start your agent with `/path/to/text-to-cad` as the working directory and
ask it to write files under that scratch path. This keeps skill scripts,
fixtures, generated sidecars, and Viewer links using the same repo-relative
paths that CI and local checks expect.

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
`skills/*/scripts/packages/*`, `viewer/packages/*`, and `plugins/cad/skills/*`
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

Normal development PRs should not bump `plugins/cad/VERSION`. Release versions
are reserved for release PRs so the canonical repo version, Git tag, and GitHub
Release describe the same production commit. To prepare a release, run the
`Prepare Release` GitHub Actions workflow with `base_branch=develop`; it updates
`plugins/cad/VERSION` plus derived package/plugin metadata on a
`release/<version>` branch and opens a release PR.

For local release preparation, use the same script that the workflow calls:

```bash
git fetch origin develop
git fetch --tags origin
scripts/release/bump-version.sh patch --no-commit
node scripts/release/sync-version.mjs
scripts/release/check-version.sh --incremented-from origin/main
node scripts/release/sync-version.mjs --check
```

The `main` production branch must be installable from a plain checkout, so it
contains generated production outputs instead of symlinks. `main` is
publish-only: do not open PRs to `main` or push it directly. The `Test`
workflow runs a production bundle job on `develop` and PRs to `develop`: it starts from
the symlink layout, runs `scripts/bundle/bundle.sh --clean`, checks the
production layout without rebuilding it, runs documentation checks, and runs the
code tests against that generated output.

To ship a release, merge the release PR to `develop`, then manually dispatch the
`Publish` workflow from the `develop` workflow ref with `source_ref=develop` and
`target_branch=main`:

```bash
gh workflow run publish.yml --ref develop \
  -f source_ref=develop \
  -f target_branch=main \
  -f dry_run=false \
  -f publish=false \
  -f create_release=true
```

`Publish` only ships to `main` when the source version is newer than `main` and
the latest semver tag. It repeats the production bundle checks, refuses sources
that do not contain the previous publish source commit, writes a generated
production merge commit on top of the previous publish target with the release
source as the second parent, creates the semver tag from `plugins/cad/VERSION`,
and opens a draft GitHub Release with generated notes. This keeps the target
branch fast-forwardable while preserving source commits for release notes and
contributor attribution. If a run moves `main` but fails before tag creation,
rerunning Publish can resume while `main` already has the release version, as
long as the semver tag is still missing. Leave `publish=false` unless the
release should be published immediately rather than reviewed as a draft. Use
`target_branch=build-test` to rehearse the full publish flow without touching
`main` or creating a tag/release. Pushing `develop` runs tests but does not
publish `main`. During bundling, Publish rechecks duplicate package/plugin
metadata from `plugins/cad/VERSION`. Treat generated outputs as CI products, not
edit targets.

PRs opened against `develop` must keep `plugins/cad/VERSION` and derived version
metadata valid when they touch release state. The `Test` workflow checks release
version metadata in a separate job so code tests still run when that metadata is
wrong. It also verifies the symlink layout for `develop` and runs a temporary
production bundle check for `develop`. Configure GitHub branch settings/rulesets
so `main` rejects PRs and direct pushes, leaving the `Publish` workflow as the
only writer.
Enable repository tag rulesets for
`[0-9]*.[0-9]*.[0-9]*` before publishing from `main`, and enable immutable
releases once the production flow is trusted.

Production users should continue cloning `main`; developers should treat
`develop` plus the `Publish` workflow as the only route to `main`.

## Iteration Loop

1. Edit the relevant skill under `skills/<skill-name>/`.
2. Keep skill instructions narrow and executable: say when the skill applies,
   what inputs it expects, what it produces, and how to validate the work.
3. Prefer small files in `references/` and reusable scripts in `scripts/` over
   long inline instructions.
4. Add or update focused fixtures, tests, or benchmark cases when skill behavior
   changes so regressions are measurable.
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
working in a particular package, skill, plugin, docs site, or production-output
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

Use the printed URL with an absolute `?dir=/path/to/root` and any absolute
`?file=/path/to/model.step`. Do not assume a fixed dev port unless you pass
Vite's standard `--port` flag. Packaged Viewer runtime checks are
production-output checks; use `scripts/README.md` when you specifically need
that path.

## Git Hygiene

Do not commit local environments, dependency folders, caches, or temp files such
as `.venv/`, `node_modules/`, `.vite/`, `dist/`, `tmp/`, or local credentials.
Generated runtime changes should come from the production-output workflow, not
manual edits inside generated runtime folders.

CAD exchange files, generated render/topology assets, `assets/**`, and
`benchmarks/**` may be LFS-tracked. Never disable LFS filters for `git add`,
commits, or other object-writing operations.
