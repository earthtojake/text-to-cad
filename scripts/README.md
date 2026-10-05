# Scripts

Durable repo commands, one folder per concern. Every file here is called by a
GitHub Actions workflow, the pre-commit hook, a test, or a documented developer
step; nothing else belongs here (one-off helpers go in `tmp/`).

| Task | Command |
| ---- | ------- |
| Build the packaged runtime | `scripts/bundle/bundle.sh --clean` |
| Build it and assert it is complete | `scripts/bundle/bundle.sh --check` |
| Run code tests | `scripts/test/test.sh` |
| Run docs checks | `scripts/test/test-docs.sh` |
| Check the release version and skill pins | `scripts/release/check-version.sh` |
| Check the shipping contract | `scripts/github-workflows/check-builds.sh` |
| Install this checkout into an agent app to test it | `scripts/install/dev_install.py <host>` |

## Index

`bundle/` — cadgen's packaged runtime (`packages/cadgen/src/cadgen/_runtime`).
None of it is committed: the directory is gitignored end to end and the wheel is
where those files ship, so these scripts are what produces them.

- `bundle.sh` — the one entry point: stamps derived version metadata
  (`release/sync-version.mjs`), then runs `cadgen-runtime.sh`. `--check` builds
  the runtime and asserts every required output exists, and checks the derived
  metadata (which IS committed) rather than writing it. `--clean` removes the
  `_runtime` tree first. Called by `test.yml`, `release-publish.yml`,
  `check-builds.sh`, the pre-commit hook.
- `cadgen-runtime.sh` — builds the five runtime stages: `--node` (esbuilt Node
  builders), `--browser` (snapshot browser bundle), `--viewer` (vite build of
  `apps/web`), `--mcp` (vite build of `apps/mcp`, one `index.html`), `--native`
  (the file tracer, zig-compiled for every platform; `--native-host` builds this
  machine's only). `--print-outputs` lists the three directories a bundle always
  produces; `--check` skips the viewer and MCP stages, which need the apps'
  `node_modules` and which nothing in a checkout reads. Called by `bundle.sh`,
  `check-builds.sh`, `test/test-installed.sh`, and `test/common.sh` when a test
  runner finds a stage it needs missing; pinned by
  `tests/python/global/test_node_builder_bundles.py` and
  `test_js_runtime_reproducibility.py`. Call it directly only to debug one stage.
- `lib/node_builders.sh`, `lib/snapshot_runtime.sh` — sourced by
  `cadgen-runtime.sh`; esbuild the Node builders and the browser bundle with
  `three`/`meshoptimizer` pinned from `package-lock.json`.

`test/` — test runners.

- `test.sh` — `test-js.sh`, then `test-python.sh`, then `test-global.sh`: the
  whole tree on one machine, for a local run; `test.yml` calls the focused
  runners per job instead.
- `test-js.sh [--select core|ui|web|mcp|all]` — builds the required shared exports,
  checks dependency boundaries and runs the selected shared JS/UI/web suites.
  Core includes the pure `bench/viewer-memory/` helper units; `mcp` runs the CAD
  app's tests and builds it, since its one-file build is half its contract.
- `test-python.sh [--keep-going] [--select GROUP] [--print-weights] [PATH...]`
  — the cadgen package suite, then every skill's suite. Each test FILE runs in
  its own interpreter against its own temporary store, `CADGEN_TEST_JOBS` at a
  time (default: the core count; CI sets 4). `--keep-going` runs all suites and
  reports every failure. PATHs (repo-relative files or directories) narrow the
  run to the test files at or under them — CI passes what the change selected
  — and a PATH that holds no test fails the run.
  - `--select` picks one group: `cadgen` (the package suite, CAD Viewer backend
    included), `viewer` (that backend alone, ~11 s), `skills` (every skill's
    suite), `all` (the default).
  - `--print-weights` prints one `WEIGHT<TAB>path<TAB>seconds` line per slow file
    on stdout (everything else a run says goes to stderr): the first thing to
    read when a run is slow.
- `unittest_files.py` — the runner underneath, invoked by `common.sh`. Loads each
  test file under its full dotted path so an import failure names the file, and
  runs the files `--jobs` at a time in their own interpreters. A file still
  running after 15 minutes is hung: it prints every thread's stack and fails.
- `test-global.sh [PATH...]` — `tests/python/global`, the repo-wide policy
  suite, narrowed to PATHs as `test-python.sh` is. Like `test-python.sh`, it
  builds the `--node` and `--browser` runtime stages and this machine's file
  tracer first when they are absent: the suites read them and a fresh clone has
  none. `PYTHON_TEST_RUNTIME=0` skips that build for a selection that reads none
  of it (the skills job's light phase); a test that does read it then fails on the
  missing file.
- `test-docs.sh` — `npm --prefix apps/docs run check`, then the animated brand
  marks' tests. Called by `test.yml`.
- `test-installed.sh` — builds the wheel (or accepts `--wheel PATH` to test
  the exact artifact already built), installs it into a scratch venv and
  exercises cadgen from outside the repo, including `cadgen mcp` serving the
  packaged CAD app over stdio. Called by `test.yml` and `release-publish.yml`.
- `test-viewer-launch.sh` — launches `cadgen viewer` against the built client and
  verifies reuse, cold STEP import, display derivation and browser drawing using
  a tiny test-owned STEP. Called by `test.yml`.
- `test-viewer-browser.sh` — creates tiny inputs and owns its temporary project,
  viewer and cache. Requires a bundled viewer and npm Playwright Chromium
  (`npx --no-install playwright install chromium`). Runs the format and camera
  gates, exactly what `test.yml` runs.
  `--only NAME` selects a gate; `--out DIR` retains screenshots.
- `common.sh`, `unittest_files.py` — shared runner pieces (interpreter
  resolution, path narrowing, fail-closed unittest loading, the per-file
  parallel run). Sourced by the runners.

`release/` — the version and the release identity.

- `bump-version.sh major|minor|patch|X.Y.Z [--base REF] [--dry-run]` — makes a
  branch a release: sets `VERSION` past the one on `REF` (default `origin/main`,
  fetched first; it must already be merged into the branch) and stamps the
  derived metadata and every cadgen pin (`sync-version.mjs`). Relative to `REF`,
  so a second run changes nothing. `--check-incremented-from REF` compares
  `VERSION` against a ref, for `check-version.sh`. Run by hand; see
  `CONTRIBUTING.md`, "Shipping a release".
- `check-pr-version.sh HEAD_REPO` — on a pull request's merge commit, says what
  merging it releases and the command that releases it: nothing when `VERSION`
  is unchanged against the target branch; otherwise the bump must come from a
  branch of this repository (never a fork) and pass both the target's version
  and the latest tag, and the version goes to `GITHUB_OUTPUT`. Called by
  `version.yml` (Version Check).
- `release_pr.py published VERSION | resolve --pr N --base BRANCH | land --pr N
  --sha HEAD [--version X] | settle VERSION` — releases a pull request with
  PyPI first and `main` after: whether PyPI serves a version (Version Check holds
  a release's merge on it), whether a pull request may be released, waiting for
  PyPI, re-running the held Version Check and merging, and waiting until the
  upload is older than PyPI's index cache (`max-age=600`) before anything
  announces it. Called by `release-publish.yml` and `version.yml`; tested by
  `tests/python/global/test_release_gate.py`.
- `check-version.sh [--incremented-from REF]` — `VERSION` is valid semver, every
  skill pins `cadgen==VERSION`, and (with the flag) `VERSION` is greater than the
  one at `REF`. Called by `version.yml`, `release-publish.yml`,
  `publish-github-release.sh`.
- `sync-version.mjs [--check]` — stamps the derived versions (package, plugin,
  lockfile and `pyproject.toml` metadata, the cadgen pins) from `VERSION`. Called
  by `bump-version.sh`, `bundle.sh`, `version.yml`, `release-publish.yml`.
- `check-wheel-contents.sh` — builds the wheel and asserts the Python modules and
  `_runtime/{node,browser,viewer}` are inside it, with bytes identical to the
  bundled source. The only gate on package data, which fails quietly. Called by
  `test.yml` and `release-publish.yml`.
- `plugin_zip.py --out PATH | --check` — builds the plugin ZIP OpenAI's plugin
  submission portal takes (`cad/` holding `.codex-plugin/`, `skills/`,
  `LICENSE` and every file the manifest names, with the MCP config as the root
  `.mcp.json`) and checks it against the portal's documented package rules.
  Called by `release-publish.yml`; tested by
  `tests/python/global/test_plugin_zip.py`.
- `plugin_branch.py --check | --commit [--parent REF]` — builds the plugin
  claude.ai's directory follows (`.claude-plugin/` manifest and icon, the Cursor
  and Gemini manifests, `claude.mcp.json`, `skills/`, `LICENSE`, and the README with outside
  links pinned to the release commit), checks it against claude.ai's file
  rules, and with `--commit` commits it on `REF` and prints the commit. Called
  by `release-publish.yml`, whose `plugin-branch` job pushes it to the `plugin`
  branch (and to `claude-plugin` until claude.ai's listing moves); tested by
  `tests/python/global/test_plugin_branch.py`.
- `publish-github-release.sh [--target REF] [--dry-run] [--publish]` — creates and
  pushes the `v<VERSION>` tag and the GitHub Release (a draft unless
  `--publish`). Called by `release-publish.yml`; a local run on the merged release
  commit is the manual fallback.
- `release-tags.sh` — sourced helpers for tag spelling (`v0.5.0`, and the bare
  `0.4.x` releases before 0.5.0) and for comparing versions. Sourced by
  `bump-version.sh`, `check-pr-version.sh`, `publish-github-release.sh`,
  `release-publish.yml`.

`github-workflows/` — scripts a workflow runs whole.

- `select_checks.py [--paths PATH...]` — what a change can break: maps every
  changed path through a table of the tests that read it (`RULES`) to the
  `test.yml` jobs that run and the test files the narrowed jobs take, and names
  the run's record, `tested-<tree>-<scope>`. A path no rule or `INERT` entry
  names runs everything. `--paths` prints the selection for a list of paths.
  Called by `test.yml`'s first job; held to the tree by
  `tests/python/global/test_ci_workspace_selection.py`. See `CONTRIBUTING.md#ci`.
- `tested_tree.py NAME...` — finds the successful `test.yml` run of this
  repository (never a fork's) that recorded one of the NAMEs: the run that
  already tested a tree. Called by `select_checks.py` on a push, and by
  `release-publish.yml`'s gate, which tests the release commit itself when it
  finds none; tested by `tests/python/global/test_release_gate.py`.

- `check-builds.sh [--skip-bundle-check | --tree-only]` — the shipping contract: no tracked
  symlink anywhere, no `.gitattributes` rule that rewrites files at checkout or
  changes the archive (so no LFS), every tracked file under 5 MiB, no skill
  reaching into a repo root; then `bundle.sh --check` unless the workflow
  already bundled; then every path `cadgen-runtime.sh --print-outputs` names
  exists and holds no symlink. `--tree-only` stops after the tree rules, which
  need no runtime, so Version Check (`version.yml`) runs them for every change.
  Called by `version.yml`, `test.yml`, `release-publish.yml`, the pre-commit hook path. The
  no-symlink rule is load-bearing: Codex `plugin add` drops symlinks silently.
- `deploy-vercel-app.sh` — deploys one Vercel project to production and verifies
  its public URLs. Called by `deploy-docs.yml` only.

`install/` — local testing.

- `dev_install.py <host> [--uninstall] [--no-build] [--restart] [--wheel]` — installs this
  checkout into an agent app: the development plugin `text-to-cad@earthtojake-dev`
  for `claude` (which Cursor and Grok Build load too), `codex`, `cursor`, `grok`
  and `gemini` (skills copied, server run by `.venv`, serving a copy of the page
  taken at install, assembled under `tmp/<host>-dev`), with the skills' launch
  command rewritten to that same runtime; `--wheel` builds the checkout's wheel and
  runs both through `uvx --from <wheel>`; the server alone for `claude-desktop`. Refuses a host where another copy of the plugin, or this
  repository's skills installed loose, would load. Developer step in
  `CONTRIBUTING.md` ("Test In Agent Apps"); its assembly and loose-skill check are
  tested by `tests/python/global/test_dev_install.py`.

`git-hooks/pre-commit` — the body `.githooks/pre-commit` runs: `bundle.sh --check`
when staged paths touch `packages`, `apps`, `skills` or `scripts/bundle`. It is
kept now that nothing is committed, because the question it asks is still worth
asking locally and is cheap once `tmp/`'s pinned esbuild toolchain exists: does
this edit still BUILD? It no longer has anything to say about the index.

`build/library.mjs` — the esbuild library build `packages/core` and
`packages/ui` share; each package's `scripts/build.mjs` calls it.

`brand/` — the logo generators: `generate-logos.mjs` draws the brand SVGs and the
models' profiles, `export-logos.mjs` exports every other logo file from them.
Run by hand when the brand changes; ordinary builds use the committed files. See
[the brand recipe](brand/README.md).

`bench/` — manual edit, warm-build and viewer performance commands. See
[benchmark usage](bench/cadgen-performance/README.md). Reports and profiler
captures are local output under `tmp/`, never committed here. The drivers are
manual; their `*.test.mjs` helper units run in `test-js.sh`.

## CI

| Workflow | Branches/events | Purpose |
| -------- | --------------- | ------- |
| `test.yml` | pushes to and PRs against `main` and `build-test`; manual dispatch; called by `release-publish.yml` | One job per thing that has to work, each run only when the change selects it (`select_checks.py`; `CONTRIBUTING.md#ci` documents the table): `Version Check` always; the cadgen package suite on Linux and Windows; `core-js` (`@text-to-cad/core`), `web` (shared UI and the web app), `mcp`, skills and docs on Linux; `packaging` bundles from clean (nothing under `_runtime/` is committed, so this is where it comes from), checks the layout, inspects the wheel and runs the installed-mode tests. Each run records the tree it tested; a push whose tree its pull request already tested runs nothing again. Superseded PR runs are cancelled. |
| `version.yml` (`Version`) | pushes to and PRs against `main` and `build-test`; manual dispatch | Version Check, a required check: canonical version, derived metadata, cadgen pins, the tracked tree's rules; on a pull request, what merging it releases — and for a release into `main`, red until PyPI serves the version, so nobody merges it before its wheel is out. |
| `release-publish.yml` (`Publish Release`) | manual dispatch with `pr` (release that pull request) or without (resume the commit that last moved `VERSION`); pushes to `main` and `build-test` that change `VERSION` (a bump that skipped the pull-request route) | Gate (the pull request open, this repository's, up to date and a real bump; VERSION past the latest tag); the record of a run that tested that tree in full, or else every `test.yml` job on it; the checked OpenAI plugin ZIP (built first, from the untouched release commit) and plugin tree; bundle, wheel build, an `unzip -l` assertion that the shipping wheel carries `_runtime`, install test, distribution artifact; then — on `main` only — PyPI upload, and only after it the merge of the pull request; ten minutes later, docs deploy, `v<VERSION>` tag and GitHub Release carrying the wheel, sdist and plugin ZIP, and the plugin committed onto the `plugin` branch (and `claude-plugin`, until claude.ai's listing moves). On `build-test` it merges, prints what it would have uploaded and tagged, and stops. |
| `deploy-docs.yml` (`Deploy Docs`) | manual dispatch; called by `release-publish.yml` | Deploys the docs app to Vercel production from a ref (default `main`): configures Vercel Authentication for preview deployments only, runs `vercel pull/build/deploy --prod`, and verifies the public production URLs. |

A pull request bumps (`release/bump-version.sh`), `Publish Release` ships it
(PyPI, then the merge), `Deploy Docs` redeploys. `main` is the one branch: the source, what installers clone, and what
releases tag; `build-test` is the rehearsal. The CAD Viewer is a local-filesystem
app with no hosted deployment.
