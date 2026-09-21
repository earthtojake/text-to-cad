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
| Stamp every skill's `cadgen==` pin from `VERSION` | `scripts/release/pin-cadgen-requirements.sh` |
| Check the shipping contract | `scripts/github-workflows/check-builds.sh` |
| Install local skills into agents | `scripts/install/install-skills.sh --agent codex` |
| Uninstall local skill links | `scripts/install/uninstall-skills.sh --agent codex` |

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
- `cadgen-runtime.sh` — builds the three runtime stages: `--node` (esbuilt Node
  builders), `--browser` (snapshot browser bundle), `--viewer` (vite build of
  `apps/viewer`). `--print-outputs` lists the two directories a bundle always
  produces; `--check` skips the viewer stage, which needs the client's
  `node_modules` and which nothing in a checkout reads. Called by `bundle.sh`,
  `check-builds.sh`, `test/test-installed.sh`, and `test/common.sh` when a test
  runner finds the two stages it needs missing; pinned by
  `tests/python/global/test_node_builder_bundles.py` and
  `test_js_runtime_reproducibility.py`. Call it directly only to debug one stage.
- `lib/node_builders.sh`, `lib/snapshot_runtime.sh` — sourced by
  `cadgen-runtime.sh`; esbuild the Node builders and the browser bundle with
  `three`/`meshoptimizer` pinned from `packages/cadgen-js/package-lock.json`.

`test/` — test runners.

- `test.sh` — `test-js.sh`, then `test-python.sh`, then `test-global.sh`: the
  whole tree on one machine. Called by `release-publish.yml`; `test.yml` calls
  the focused runners per job instead.
- `test-js.sh` — `packages/cadgen-js` and `apps/viewer` client suites, then the
  `node --test` units under `bench/viewer-memory/` (the benchmark drivers are
  manual; their pure helpers are not).
- `test-python.sh [--keep-going] [--select GROUP] [--print-weights]`
  — the cadgen package suite, then every skill's suite. Each test FILE runs in
  its own interpreter against its own temporary store, `CADGEN_TEST_JOBS` at a
  time (default: the core count; CI sets 4). `--keep-going` runs all suites and
  reports every failure.
  - `--select` picks one group: `cadgen` (the package suite, CAD Viewer backend
    included), `viewer` (that backend alone, ~11 s), `skills` (every skill's
    suite), `all` (the default).
  - `--print-weights` prints one `WEIGHT<TAB>path<TAB>seconds` line per slow file
    on stdout (everything else a run says goes to stderr): the first thing to
    read when a run is slow.
- `unittest_files.py` — the runner underneath, invoked by `common.sh`. Loads each
  test file under its full dotted path so an import failure names the file, and
  runs the files `--jobs` at a time in their own interpreters.
- `time-python.sh [N]` — times every Python test module on its own and prints
  them sorted by wall clock (results under `tmp/timing/`); `time_module.py` is
  its helper. Manual only: the first step of a bloat check. `--print-weights` is
  the same measurement taken from a run that was happening anyway.
- `test-global.sh` — `tests/python/global`, the repo-wide policy suite. Like
  `test-python.sh`, it builds the `--node` and `--browser` runtime stages first
  when they are absent: the suites read them and a fresh clone has neither.
- `test-docs.sh` — `npm --prefix apps/docs run check`, pulling the hero assets
  first. Called by `test.yml` and `release-publish.yml`.
- `test-installed.sh` — builds the wheel, installs it into a scratch venv and
  exercises cadgen from outside the repo. Called by `test.yml` and
  `release-publish.yml`.
- `test-viewer-launch.sh` — launches `cadgen viewer` against the built client and
  verifies reuse, cold STEP import, display derivation and browser drawing using
  a tiny test-owned STEP. Called by `test.yml`.
- `test-viewer-browser.sh` — self-contained browser checks for supported formats,
  Inspect/Render placement and appearance, and face/edge picking through detail
  changes. Generates its inputs in a temporary project and owns its viewer and
  cache; `--out DIR` keeps the screenshots it grades. Needs a bundled Viewer
  (`bundle.sh`) and the Node Playwright's Chromium
  (`npx --prefix packages/cadgen-js playwright install chromium`; `test.yml`
  installs the Python one). Called by nobody: it is a manual gate, because one
  run is over six minutes — too slow for `test.yml`, which already covers launch
  and reuse with `test-viewer-launch.sh`.
- `common.sh`, `unittest_files.py` — shared runner pieces (interpreter
  resolution, fail-closed unittest loading, the per-file parallel run). Sourced
  by the runners.

`release/` — the version and the release identity.

- `check-version.sh [--incremented-from REF]` — `VERSION` is valid semver, every
  skill pins `cadgen==VERSION`, and (with the flag) `VERSION` is greater than the
  one at `REF`. Called by `test.yml`, `release-prepare.yml`, `release-publish.yml`,
  `publish-github-release.sh`.
- `bump-version.sh major|minor|patch | --set-version X.Y.Z [--dry-run]` — writes
  `VERSION`; `--check-incremented-from REF` compares against a ref. Called by
  `release-prepare.yml` and `check-version.sh`.
- `pin-cadgen-requirements.sh [--check]` — stamps `cadgen==VERSION` into every
  skill's `requirements.txt`. Called by `release-prepare.yml`; tested by
  `tests/python/global/test_pin_cadgen_requirements.py`.
- `sync-version.mjs [--check]` — stamps the derived versions (package, plugin,
  lockfile and `pyproject.toml` metadata) from `VERSION`. Called by `bundle.sh`,
  `test.yml`, `release-prepare.yml`.
- `check-wheel-contents.sh` — builds the wheel and asserts the Python modules and
  `_runtime/{node,browser,viewer}` are inside it, with bytes identical to the
  bundled source. The only gate on package data, which fails quietly. Called by
  `test.yml` and `release-publish.yml`.
- `publish-github-release.sh [--target REF] [--dry-run] [--publish]` — creates and
  pushes the `v<VERSION>` tag and the GitHub Release (a draft unless
  `--publish`). Called by `release-publish.yml`; a local run on the merged release
  commit is the manual fallback.
- `release-tags.sh` — sourced helpers for tag spelling (`v0.5.0`, and the bare
  `0.4.x` releases before 0.5.0). Sourced by `bump-version.sh`,
  `publish-github-release.sh`, `release-prepare.yml`, `release-publish.yml`.

`github-workflows/` — scripts a workflow runs whole.

- `check-builds.sh [--skip-bundle-check]` — the shipping contract: no tracked
  symlink anywhere, no LFS path under `skills/`, no skill reaching into a repo
  root; then `bundle.sh --check` unless the workflow already bundled; then every
  path `cadgen-runtime.sh --print-outputs` names exists and holds no symlink.
  Called by `test.yml`, `release-publish.yml`, the pre-commit hook path. The
  no-symlink rule is load-bearing: Codex `plugin add` drops symlinks silently.
- `deploy-vercel-app.sh` — deploys one Vercel project to production and verifies
  its public URLs. Called by `deploy-docs.yml` only.

`install/` — local development links.

- `install-skills.sh`, `uninstall-skills.sh` — symlink `skills/*` into an agent's
  skill directory (`--agent codex|claude|...`, `--all`, `--dry-run`). Developer
  step in `CONTRIBUTING.md`.

`git-hooks/pre-commit` — the body `.githooks/pre-commit` runs: `bundle.sh --check`
when staged paths touch `packages`, `apps`, `skills` or `scripts/bundle`. It is
kept now that nothing is committed, because the question it asks is still worth
asking locally and is cheap once `tmp/`'s pinned esbuild toolchain exists: does
this edit still BUILD? It no longer has anything to say about the index.

`utils/list-skills.sh` — prints every `skills/*/SKILL.md` directory. Used by the
install scripts and `test-python.sh`.

`bench/` — manual warm-build and viewer performance commands. See
[benchmark usage](bench/cadgen-performance/README.md). Reports and profiler
captures are local output under `tmp/`, never committed here. The drivers are
manual; their `*.test.mjs` helper units run in `test-js.sh`.

## CI

| Workflow | Branches/events | Purpose |
| -------- | --------------- | ------- |
| `test.yml` | pushes to `main`; PRs to `main`; manual dispatch | One job per thing that has to work, each conditional on the paths that can break it (`AGENTS.md` has the table, `CONTRIBUTING.md` the reasoning): `Version Check` always; the cadgen package suite on Linux and Windows; cadgen-js, viewer, skills and docs jobs on Linux; `packaging` bundles from clean (nothing under `_runtime/` is committed, so this is where it comes from), checks the layout, inspects the wheel and runs the installed-mode tests. Superseded PR runs are cancelled. |
| `release-prepare.yml` (`Prepare Release`) | manual dispatch | The version bump as a PR: bumps `VERSION`, stamps metadata and skill pins, opens `release/X.Y.Z` against `target` (default `main`; `build-test` rehearses) and merges it. The merge is what runs `Publish Release`. |
| `release-publish.yml` (`Publish Release`) | pushes to `main` and `build-test`; manual dispatch (resume/republish the head) | Gate (VERSION past the latest tag, or untagged), bundle, tests, wheel build, an `unzip -l` assertion that the shipping wheel carries `_runtime`, install test, distribution artifact; then -- on `main` only -- PyPI upload, docs deploy, `v<VERSION>` tag and GitHub Release. On `build-test` it prints what it would have tagged and stops. |
| `deploy-docs.yml` (`Deploy Docs`) | manual dispatch; called by `release-publish.yml` | Deploys the docs app to Vercel production from a ref (default `main`): configures Vercel Authentication for preview deployments only, runs `vercel pull/build/deploy --prod`, and verifies the public production URLs. |

In short: `Prepare Release` bumps, `Publish Release` ships, `Deploy Docs`
redeploys. `main` is the one branch: the source, what installers clone, and what
releases tag; `build-test` is the rehearsal. The CAD Viewer is a local-filesystem
app with no hosted deployment.
