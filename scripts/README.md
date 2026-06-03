# Scripts

Use these durable entrypoints for normal work:

| Task | Command |
| ---- | ------- |
| Set up dev symlinks | `scripts/dev/setup-symlinks.sh` |
| Check dev symlinks | `scripts/dev/setup-symlinks.sh --check` |
| Bundle production outputs | `scripts/bundle/bundle.sh --clean` |
| Check production outputs are fresh | `scripts/bundle/bundle.sh --check` |
| Bundle one skill output | `scripts/bundle/bundle-skill.sh <skill-id>` |
| Run code tests | `scripts/test/test.sh` |
| Run docs checks | `scripts/test/test-docs.sh` |
| Check canonical release version | `scripts/release/check-version.sh` |
| Install local skills into agents | `scripts/install/install-skills.sh --agent codex` |
| Uninstall local skill links | `scripts/install/uninstall-skills.sh --agent codex` |

Lower-level scripts stay grouped by ownership:

- `bundle/`: production bundle wrapper, skill bundle router, skill runtime
  bundlers, and plugin package bundle/check scripts.
- `test/`: code test runner and targeted test subcommands.
- `github-workflows/`: release-layout and development-layout check entrypoints
  used by GitHub Actions.
- `dev/`: symlink layout setup and verification for development checkouts.
- `install/`: local skill install/uninstall scripts for agent skill folders.
- `utils/`: shared helper scripts used by durable repo commands.
- `release/`: version bumping, release commits, tags, and GitHub Releases.
- `viewer/`, `git-hooks/`: specialized repo tooling.

Root `tests/` contains repo-wide policy tests that are not owned by one package,
skill, or app runtime.

## Bundle

`scripts/bundle/bundle.sh` is the master production bundle script. It runs every
bundle-capable skill through the skill bundle router and then refreshes the plugin
package copy:

```text
scripts/bundle/bundle-skill.sh --all
scripts/bundle/bundle-plugin.sh
```

Use:

```bash
scripts/bundle/bundle.sh --clean
scripts/bundle/bundle.sh --check
scripts/bundle/bundle-skill.sh <skill-id> --check
```

`scripts/github-workflows/check-builds.sh` is the release-layout gate. It verifies
there are no symlinks under production runtime paths, then runs
`scripts/bundle/bundle.sh --check` by default. Use `--skip-bundle-check` only in
workflows that already ran `scripts/bundle/bundle.sh --clean` in the same
checkout. Plugin skill-copy
freshness and plugin metadata validation are part of
`scripts/bundle/bundle-plugin.sh --check`, which runs through the master bundle
check.

`skills/cad-viewer/scripts/viewer/dist/` is generated and ignored in source
layout, but the root `.gitignore` unignores that exact production-runtime path so
`Publish` can commit the bundled Viewer assets on `main`. On `develop`,
`scripts/dev/setup-symlinks.sh --check` requires `skills/cad-viewer/scripts/viewer`
to be the source symlink instead.

## Dev

`scripts/dev/setup-symlinks.sh` is the master development-layout script:

```bash
scripts/dev/setup-symlinks.sh
scripts/dev/setup-symlinks.sh --check
```

It links generated-copy targets back to their canonical source directories and
checks that those symlinks are present.

## Install

Use the install scripts for local agent links:

```bash
scripts/install/install-skills.sh --agent codex
scripts/install/uninstall-skills.sh --agent codex
```

They install or remove local development skill symlinks in agent-specific skill
directories.

## Test

`scripts/test/test.sh` is the broad code test runner for source/package tests.
Documentation checks are separate so CI can run them with production bundle
checks. Python tests live under `tests/python/`, grouped by tested surface, so
skill and package runtimes do not carry test-only modules. Production bundle
copy steps also exclude conventional test directories and `*.test.*` /
`*.spec.*` files as a safety net. Focused subcommands can be run directly for
smaller checks:

```bash
scripts/test/test-js.sh
scripts/test/test-docs.sh
scripts/test/test-python.sh
scripts/test/test-global.sh
```

## Version And Release

Use `scripts/release/check-version.sh` for CI/read-only checks:

```bash
scripts/release/check-version.sh
scripts/release/check-version.sh --incremented-from origin/main
```

Normal development branches should not bump `plugins/cad/VERSION`. Use the
`Prepare Release` GitHub Actions workflow to open a release PR from `develop`; use
`scripts/release/bump-version.sh` only as a local fallback for that release PR:

```bash
scripts/release/bump-version.sh patch --dry-run
scripts/release/bump-version.sh patch --no-commit
```

`plugins/cad/VERSION` is the only canonical release bump file. Duplicate
package, plugin, lockfile, and Python `pyproject.toml` versions are derived from
it; `Prepare Release` stamps them with `scripts/release/sync-version.mjs`, and
`scripts/bundle/bundle.sh` re-checks the same metadata before writing or
checking production outputs.

Use `scripts/release/publish-github-release.sh` only from the `Publish`
workflow after a main production bundle, or as a manual production-branch
fallback. It creates the semver git tag from `plugins/cad/VERSION` and creates a
draft GitHub Release with generated notes.
Use `scripts/release/check-publish-source.sh` to verify that a source ref
contains the previous release source before Publish writes a new generated
target commit.
`scripts/release/create-github-release.sh` remains as a manual all-in-one
fallback, but the workflow path is preferred.

## CI

| Workflow | Branches/events | Purpose |
| -------- | --------------- | ------- |
| `test.yml` | pushes to `develop`; PRs to `develop`; manual dispatch | Checks `plugins/cad/VERSION` and derived metadata as a separate job so test jobs still run if release metadata is wrong. The source test job checks the branch-specific layout and runs the broad code test wrapper. On `develop` and PRs to `develop`, a production-bundle job bundles temporary production outputs, checks that layout without rebuilding it, runs docs checks, and reruns code tests. |
| `prepare-release.yml` | manual dispatch | Bumps `plugins/cad/VERSION`, syncs derived version metadata on `release/<version>`, and opens a release PR back to `develop` by default. |
| `publish.yml` | manual dispatch | Uses `source_ref=develop` and `target_branch=build-test` by default for rehearsals; dispatch from `develop` and set `target_branch=main` only for a real release. Main publishes are allowed only when the source version is newer than `main` and the latest semver tag, and when the source contains the previous publish source commit. When publishing, it bundles, validates that layout without rebuilding it, runs docs/code tests, writes the production merge commit on top of the target branch with the source commit as a second parent for release-note attribution, deploys the docs and demo viewer Vercel projects only for non-dry-run `main` publishes, and creates the semver tag/GitHub Release only for `main`. Use `dry_run=true` to rehearse without writing or deploying. |

In short: `develop` is the editable symlink branch, `test.yml` performs temporary
production-output rehearsals, and `main` is the explicit publish-only production
branch for user clones and published releases.
