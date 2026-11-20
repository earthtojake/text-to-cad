# Scripts

Reusable contributor commands, one folder per concern. Keep asset authoring and
one-off investigations in ignored `tmp/`, even when they have their own tests or
documentation. Every file here is called by a
GitHub Actions workflow, the pre-commit hook, a test, or a documented developer
step; nothing else belongs here (one-off helpers go in `tmp/`).

| Task | Command |
| ---- | ------- |
| Build the packaged runtime | `scripts/bundle/bundle.sh --clean` |
| Build it and assert it is complete | `scripts/bundle/bundle.sh --check` |
| Run code tests | `scripts/test/test.sh` |
| Run docs checks | `scripts/test/test-docs.sh` |
| Check the release version and every stamp of it | `scripts/release/check-version.sh` |
| Check the shipping contract | `scripts/github-workflows/check-builds.sh` |
| Install this checkout into the agent apps to test it, and go back | `scripts/install/dev_install.py`, `scripts/install/dev_install.py --release` |

## Index

`bundle/` — the server's packaged runtime (`packages/cad/src/cad_server/_runtime`).
None of it is committed: the directory is gitignored end to end and the wheel is
where those files ship, so these scripts are what produces them.

- `bundle.sh` — the one entry point: stamps derived version metadata
  (`release/sync-version.mjs`), then runs `cadgen-runtime.sh`. `--check` builds
  the runtime and asserts every required output exists, and checks the derived
  metadata (which IS committed) rather than writing it. `--clean` removes the
  `_runtime` tree first. Called by `test.yml`, `release-publish.yml`,
  `check-builds.sh`, the pre-commit hook.
- `cadgen-runtime.sh` — builds the two runtime stages: `--viewer` (vite build of
  `apps/web`) and `--mcp` (vite build of `apps/mcp`: `shell.html`, the shell a host keeps, and `app.js`,
  the app it loads from the engine), first removing any entry under `_runtime` that no stage builds, and saying so.
  `--print-outputs` lists the directories a bundle always produces; `--check` builds them and asserts each stage's
  pages (the viewer's `index.html`, the CAD app's `shell.html` and `app.js`) and the
  `THIRD_PARTY_LICENSES.txt` its build writes
  (`@cad/core/third-party-licenses`).
  Called by `bundle.sh` and `check-builds.sh`; pinned by `test_js_runtime_reproducibility.py`.
  Call it directly only to debug one stage.
- `lib/snapshot_runtime.sh [OUT_DIR]` — the OCCT parity bench's snapshot page,
  never part of the wheel: esbuilds `@cad/core`'s headless render entry
  with `three`/`meshoptimizer` pinned from `package-lock.json` into the ignored
  `tmp/bench/snapshot-page` (or `OUT_DIR`). Run by `bench/occt_parity.py`.

`test/` — test runners.

- `test.sh` — `test-js.sh`, `test-api.sh`, `test-python.sh`, then `test-global.sh`, on one
  machine, for a local run. It is not CI's coverage: the fea, KiCad and Blender suites, the docs
  check, packaging, the browser suite and the release tier are jobs of `test.yml`, which calls the
  focused runners.
- `test-js.sh [--select core|ui|ui-units|ui-browser|web|mcp|all]` — builds the required shared exports,
  checks dependency boundaries, type-checks each selected workspace (`npm run
  typecheck`: `tsc`, which neither Vite's builds nor the Node test runners do) and
  runs its suite. `mcp` runs the CAD app's tests and builds it, since its one-file
  build is half its contract. `ui-units` and `ui-browser` are the two halves of `ui`
  (everything but the browser specs; the browser specs alone): CI's two `js-ui`
  jobs run one each.
- `test-python.sh [--keep-going] [--select GROUP] [--print-weights] [PATH...]`
  — the package suites (the library's, the server's and the shim's), then every skill's suite. Each test FILE runs in
  its own interpreter with an engine daemon of its own, `CAD_TEST_JOBS` at a
  time (default: the core count; CI sets 4). `--keep-going` runs all suites and
  reports every failure. PATHs (repo-relative files or directories) narrow the
  run to the test files at or under them — CI passes what the change selected
  — and a PATH that holds no test fails the run. `CAD_TEST_SHARD=I/N` runs one
  shard of each suite's files: CI splits a whole run over two jobs on Linux and
  three on Windows.
  - `--select` picks one group: `cadgen` (the package suites, viewer backend
    included; CI's `packages` jobs), `viewer` (that backend alone, ~11 s), `skills` (every skill's
    suite), `all` (the default).
  - `--print-weights` prints one `WEIGHT<TAB>path<TAB>seconds` line per slow file
    on stdout (everything else a run says goes to stderr): the first thing to
    read when a run is slow.
- `unittest_files.py` — the runner underneath, invoked by `common.sh`. Loads each
  test file under its full dotted path so an import failure names the file, and
  runs the files `--jobs` at a time, each in its own interpreter with an engine
  directory of its own (`CAD_ENGINE_DIR`), and stops the daemon a file left
  there after it; run one test file through it too, rather than
  `python -m unittest`, which would build on your own daemon.
  Each file's state, cache and `cad` command folders are its own too
  (`CAD_STATE_DIR`, `CAD_CACHE_DIR`, `CAD_LAUNCHER_DIR`), and a document,
  engine or installation record the run's server writes in your own state folder,
  or your `cad` command written, fails the run, naming the test that was running
  (what another installation of yours writes there meanwhile is listed, and fails nothing).
  A file still running after 10 minutes is hung: it prints every thread's stack
  and fails, and the run starts no further file. A line a minute names the files
  still running.
- `test-global.sh [PATH...]` — `tests/python/global`, the repo-wide policy
  suite, narrowed to PATHs as `test-python.sh` is.
- `test-docs.sh` — `npm --prefix apps/docs run check`. Called by `test.yml`.
- `test-kicad.sh` — native board DRC, every export, a STEP/mesh round trip and the board's and
  schematic's edits (`kicad_pcb.edit`, `kicad_sch.edit`), through kicode's `kicad-cli` and KiPy in the environment of `cad[kicad]`, which it makes once
  as the server does (in `tmp/kicad-suite`, naming its Python to the tests, `CAD_TEST_KICODE_PYTHON`):
  `tests/python/packages/kicad`, each file with private engine, state and cache folders. Called by
  `test.yml`'s `kicad` job; no KiCad install, footprint library or browser is needed.
- `test-blender.sh` — `cad.blender.load` in the environment `cad run` makes for a script that imports
  bpy (cad's blender integration: bpy 5.2.3 on Python 3.13, from PyPI the first time): one script that
  imports cad, build123d and bpy builds a part, loads the GLBs the checkout's `cad` exported and ones
  made by hand, plays the clips in both orders, and renders a Cycles and an EEVEE still. On CI a test
  that skips fails the run (`PYTHON_TEST_NO_SKIPS`). `tests/python/packages/blender`, each file with private
  engine, state and cache folders. Called by `test.yml`'s `blender` job; on Linux it needs X11's
  client libraries and OpenGL from the system.
- `test-floor.sh` — the library's, the server's and the shim's suites on the oldest Python the packages declare
  (`requires-python`: 3.11, so pip, pipx or a plain `uv tool install` can put cad on an older system
  Python). Its Python is the development environment made on that line (`uv sync --python 3.11`, then
  `uv run scripts/test/test-floor.sh`), or a `PYTHON_BIN` of that line; another is refused in one line. A call that Python's standard library lacks parses there
  and fails only when it runs, so only running the suites holds the floor. Called by `test.yml`'s
  `packages (Python 3.11 floor)` job, under Xvfb, on a full run: before a release ships, and nightly.
- `test-api.sh` — `npm --prefix apps/api test`: the version feed's and the
  telemetry receiver's tests, which need no install. Called by `test.yml` (`static`, on every
  change) and `deploy-api.yml`.
- `test-installed.sh` — builds the `cad` wheel and its aliases' (or accepts
  `--wheels DIR` to test the exact artifacts already built), installs them together into a
  scratch venv and exercises them from outside the repo, including `cad mcp` serving the
  packaged CAD app over stdio and a manufacturing check of a built part for each process
  (the checks' measuring modules, loaded from the wheel); installs the same wheels as the uv tool
  the install command makes (`uv tool install cad`, offered them above PyPI's newest), where
  `cad update auto` and `cad plugin update auto` answer, and as an updater of 0.10.0 to 0.11.11
  brings a release. Called by `test.yml` and `release-publish.yml`.
- `rehearse-update.py [ROUTE ...] [--old RELEASE]` — rehearses cad's updates on private computers (each its
  own home, state, engine, cache and `cad` command folders), with real uv and real servers. `self`: cad, a uv
  tool, updating itself (idle, typed with `cad update` with and without a server running, at a server's
  start, switched off, past a release
  whose server cannot start, back from one uv cannot install, inside its major with a higher major out and
  across it only by `cad update --major`, by pipx), and the new cad's server running `cad plugin
  install` once, as its own run under a deadline, where `cad plugin update auto` is on and cad got newer, by
  itself or by a typed `cad update`, never after a failed update; that run installs the plugin with cad's own
  code, so it is read from cad's record of it, and the install command's count stays 0.
  `bridge`: a computer on a shipped release (0.11.11, or `--old`'s) arriving at this build by its updater,
  its automatic update, its typed `cad update`, the install command and the uv line, this build's server
  running the install command once where the computer had it (counted: the command hands the apps to the cad
  it installed, this build's), installing cad with uv itself where the
  computer had only a store's copy or the install command failed, and handing over to the uv tool's server;
  this build's servers there tend themselves every two seconds (`CAD_ENGINE_TEND_SECONDS`).
  `plugin-update`, of neither group: the real 0.11.13 from PyPI, a uv tool, whose own `cad plugin update`,
  typed, runs this tree's install command; that cad, left as it is, has no `cad plugin install` (exit status
  2), so the newest release's runs instead (`uv tool run ... cad@latest plugin install`: this tree's); then
  the install command turns the switch on by 0.11.13's own `cad plugin update auto on`, and 0.11.13 keeps
  itself as the release the plugin is up to date for. Nothing it runs comes back to the install command. It
  installs the real releases from PyPI and publishes this tree as later releases. Needs uv and the network. Called by
  `test.yml`'s `update-rehearsal` job on Linux, macOS and Windows.
- `real-install.py --wheels DIR [--require claude,codex,gemini] [--keep] [--work DIR]` — the install script
  run for real against the real `claude`, `codex` and `gemini` found on PATH, on a private computer
  (`real_computer.py`: its own home and folders, each program told its configuration folder there, the
  machine's own home compared before and after and never changed). The script runs as a person runs it
  (piped to `sh`; on Windows handed to `Invoke-Expression` by Windows PowerShell 5.1), cad from this tree's
  wheels in `DIR`, the plugin from this tree's `latest` copy (`plugin_branch.py`) in a local repository the
  computer's git reads for every address of ours on GitHub (Gemini CLI still asks GitHub's API for a release
  first, and finds none). It checks each program's own list (ours, once, this run's copy), `cad` (a uv tool
  at this run's release, `cad update auto` on, `cad plugin update auto` turned on by the script's last step,
  by the cad it hands the apps to, no server started), a model built and its page; then the script again (cad installed already,
  nothing newer for its `cad update` to bring, each copy updated); then each program moved from the state
  0.11.10's installer left. The commands it keeps off the computer's PATH are those of cad's table of apps
  (`cad_server/plugin`). It cannot test the desktop
  apps, or GitHub's `latest` branch before a release. A program missing is skipped and said, unless
  `--require` names it. Called by `real-install.yml`, which `test.yml`'s `real-install` job calls, on
  Windows, macOS and Linux, with each program pinned there. The few files of the machine's own apps and cad
  are watched before and after (`real_computer.Sentinels`): by their times, and Claude Desktop's config by
  its `mcpServers` section alone, which the running app does not rewrite. `real_computer.py` is the computer
  alone, for another test to run real programs on; `real_computer.py stamp` prints the release every
  rehearsal writes this tree's wheels again as (this tree's major and minor, a patch of 9000 or more, so uv,
  offered them beside PyPI, installs them), and `real_computer.py publish` writes them.
- `test-viewer-launch.sh` — launches `cad viewer` against the built client and
  verifies reuse, the engine serving a tiny test-owned STEP and the bundled client
  drawing it. Called by `test.yml`'s `viewer-e2e` job.
- `test-viewer-browser.sh` — creates tiny inputs and owns its temporary project,
  engine daemon and viewer. Requires a bundled viewer and npm Playwright Chromium
  (`npx --no-install playwright install chromium`). Runs the format and camera
  gates, exactly what `test.yml` runs.
  `--only NAME` selects a gate; `--out DIR` retains screenshots.
- `check-dependencies.mjs`, `check-kit-boundaries.mjs`, `check-ui-strings.mjs` (each with its
  `.test.mjs`) — the JS workspaces' import graph, the renderer kit's format-blindness (and that
  every renderer draws its chrome through the one frame, `kit/shell/ViewFrame.jsx`), and every
  string the viewer and the CAD app show read through the locale files. Run by `test-js.sh`
  (the first two also as `npm run check:boundaries`).
- `common.sh`, `unittest_files.py` — shared runner pieces (interpreter
  resolution, path narrowing, fail-closed unittest loading, the per-file
  parallel run). Sourced by the runners.

`release/` — the version and the release identity.

- `bump-version.sh major|minor|patch|X.Y.Z [--base REF] [--dry-run]` — makes a
  branch a release: sets `VERSION` past the one on `REF` (default `origin/main`,
  fetched first; it must already be merged into the branch) and stamps the
  derived metadata and every mention of the release's own (`sync-version.mjs`). Relative to `REF`,
  so a second run changes nothing. `--check-incremented-from REF` compares
  `VERSION` against a ref, for `check-version.sh`. Run by hand and by
  `release-prepare.yml`; see `docs/contributing/releases.md`, "Shipping a release".
- `check-pr-version.sh HEAD_REPO` — on a pull request's merge commit, says what
  merging it releases: nothing when `VERSION` is unchanged against the target
  branch; otherwise the bump must come from a branch of this repository (never a
  fork) and pass both the target's version and the latest tag, and a patch, which
  breaks nothing, may not add a migration guide, though it may correct one already
  there (a minor may carry one: it installs itself on every computer of its major,
  `release-tags.sh`'s `version_installs_itself`). Called by `test.yml` (`static`); see `docs/contributing/releases.md`,
  "Which number a release bumps".
- `pypi_release.py --project NAME --version X.Y.Z --built DIR --upload DIR --released DIR`
  (or `--wait`) — what a release uploads to PyPI of one of its four projects
  (`PROJECTS`: `cad`, `cad-server`, `cad-mcp`, `cadgen`, in the order they go up) and what its GitHub Release attaches: of
  the run's files, that project's at the version; one PyPI does not hold goes to
  `--upload`; one PyPI already holds (a resumed release) is not uploaded again, and
  PyPI's own bytes, checked against the sha256 PyPI lists, go to `--released`; a
  file PyPI holds that the run did not build fails it. `--wait` asks PyPI's simple
  index until it lists the version (ten minutes at most). Called by
  `release-publish.yml`'s `pypi` job, project by project.
- `check-version.sh [--incremented-from REF]` — `VERSION` is valid semver, the four
  `pyproject.toml`s, the plugin manifests, Codex's server line and the release the skills name are
  `VERSION`, no skill command names a version, and (with the flag)
  `VERSION` is greater than the one at `REF`. Called by `test.yml` (`static`), `release-publish.yml`,
  `publish-github-release.sh`.
- `newest_cad.py` — whether PyPI's newest cad has `cad plugin install`, which the install command hands
  the agent apps to: uv is asked for `cad@latest plugin install --help`, as the install command's fallback
  resolves it, in a home folder of its own, so nothing of an install runs and nothing of this machine is
  read. Exit 0 where it has the command; 1, with one line saying why and what to do, where it has none
  (ship the release that carries it first) or could not be asked (no uv, PyPI not reached, a cad that does
  not start). Needs uv and the network. Called by `deploy-docs.yml` before a production deploy; held by
  `tests/python/global/test_newest_cad.py`, with a stand-in uv.
- `sync-version.mjs [--check]` — stamps the derived versions (package, plugin,
  lockfile and `pyproject.toml` metadata, the aliases' `cad==` pins, Codex's server line
  `cad@<VERSION>`, and the release each skill's Setup block names) from
  `VERSION`. Called by `bump-version.sh`, `bundle.sh`, `test.yml` (`static`), `release-publish.yml`.
- `check-wheel-contents.sh` — builds the four wheels and asserts the aliases carry no package of
  their own and only `cad` at the release as their requirement; that the `cad` wheel carries the
  modules of `cad`, `cad_server` and `cad_mcp`, the engine's page and environment image,
  the engine's README and its pages and `_runtime/{viewer,mcp}` with each page's third-party notice, and
  nothing else at the top of `_runtime`, and the runtime with bytes identical to the bundled
  source; and that no engine test golden ships. The only gate on package data, which fails
  quietly. `CAD_KEEP_WHEEL=1` keeps the wheels in `CAD_WHEEL_OUT_DIR`. Called by `test.yml`
  and `release-publish.yml`.
- `plugin_zip.py --out PATH | --check` — builds the plugin ZIP OpenAI's plugin
  submission portal takes (the archive's root holding `.codex-plugin/`, `skills/`,
  `LICENSE` and every file the manifest names, with the MCP config as the root
  `.mcp.json`) and checks it against the portal's documented package rules. Its skills are the
  repository's as they are: each Setup block installs cad by uv's one line, `uv tool install cad`, the
  same in every copy, and a file that names our install script fails the build (`text_errors`). The same
  build is the `codex` copy `plugin_branch.py` commits.
  Called by `release-publish.yml`; tested by
  `tests/python/global/test_plugin_zip.py`.
- `plugin_branch.py --check | --commit --copy latest|directory|codex [--parent REF]` —
  builds the plugin alone, as the branches installers follow take it (the
  manifests and icon, the MCP configs they name, `skills/`, `LICENSE`, and the
  README with outside links pinned to the release commit), checks it against
  claude.ai's file rules, and with `--commit` commits it on `REF` and prints the
  commit. The `latest` copy holds every app's manifest and config and the
  marketplace catalogs; the `directory` copy is Claude's manifest and the skills alone, no MCP
  server and no hooks, every file one of the types claude.ai's directory accepts from an
  unverified organization (any other fails `--check`). Every copy carries main's skills byte
  for byte, so the same Setup block, which installs cad by uv's line; no copy names our
  install script or holds a download piped to a shell
  (`plugin_zip.text_errors`, `PIPE_TO_SHELL`). Its README, like `latest`'s, installs cad by
  uv's line rather than the install script, and it leaves out the manifest's four listing
  links; each substitution fails `--check` when what it replaces is not there exactly once
  (`docs/contributing/releases.md`, "The install branches"). The `codex` copy is the files of
  `plugin_zip.py`'s ZIP, from the same build. Called by
  `release-publish.yml`, whose `tag-release` job first pushes the `latest` copy to `latest`, the
  `directory` copy to `claude-plugin` and the `codex` copy to `codex-plugin`, together;
  tested by `tests/python/global/test_plugin_branch.py`.
- `publish-github-release.sh [--target REF] [--dry-run] [--publish]` — creates and
  pushes the `v<VERSION>` tag and the GitHub Release (a draft unless
  `--publish`). Called by `release-publish.yml`; a local run on the merged release
  commit is the manual fallback.
- `release-tags.sh` — sourced helpers for tag spelling (`v0.5.0`, and the bare
  `0.4.x` releases before 0.5.0) and for comparing versions, Semantic Versioning's
  among them: the part a release bumps, the breaking part, and whether a computer on an earlier
  release installs it by itself (`version_installs_itself`: a later release of the same major, which
  a test holds to that rule). Sourced by
  `bump-version.sh`, `check-pr-version.sh`, `publish-github-release.sh`,
  `release-publish.yml`.
- `unavailable-versions.txt` — the versions no release can take (the PyPI project `cad`'s
  earlier owner published them); `check-version.sh` and `bump-version.sh` refuse a `VERSION` on
  it, and `docs/contributing/releases.md` lists the same ("Versions a release cannot take").
- `sourcemaps.py collect --out DIR [--zip FILE]` — gathers the pages' source maps, each chunk
  with its map under its debug id, for the PostHog upload and the GitHub Release. Called by
  `release-publish.yml`.
- `wheel_contents.py` — `check-wheel-contents.sh`'s Python half: the server wheel's runtime
  against the bundled source.

`github-workflows/` — scripts a workflow runs whole.

- `select_checks.py [--paths PATH... | --light policy|skills]` — what a change can break: maps every
  changed path through a short table of components (`RULES`: the packages, the UI, an app, a
  suite, a test file itself) to the
  `test.yml` jobs that run (one flag a job), the test files the narrowed jobs take and the
  shards the packages' suites are split over, and names
  the run's record, `tested-<tree>-<scope>`. A path no rule names runs
  everything. `--paths` prints the selection for a list of paths; `--light` prints the
  light contracts `static` runs on every change.
  Called by `test.yml`'s first job and its `static` job; held to the tree by
  `tests/python/global/test_ci_workspace_selection.py`. See `docs/contributing/testing.md`.
- `ci_gate.py` — the one required check, `CI`: given every `test.yml` job's result
  (`NEEDS`, the workflow's `toJSON(needs)`), fails when the selection did not run, a job
  failed, or one was cancelled or timed out, unless a newer push superseded the pull
  request's run. Called by `test.yml`'s last job; tested by
  `tests/python/global/test_ci_workspace_selection.py`.
- `tested_tree.py NAME...` — finds the successful `test.yml` run of this
  repository (never a fork's) that recorded one of the NAMEs: the run that
  already tested a tree. Called by `select_checks.py` on a push and on the nightly run, and by
  `release-publish.yml`'s gate, which tests the release commit itself when it
  finds none; tested by `tests/python/global/test_release_gate.py`.

- `check-builds.sh [--skip-bundle-check | --tree-only]` — the shipping contract: no tracked
  symlink anywhere, no `.gitattributes` rule that rewrites files at checkout or
  changes the archive (so no LFS), every tracked file under 5 MiB, no skill
  reaching into a repo root; then `bundle.sh --check` unless the workflow
  already bundled; then every path `cadgen-runtime.sh --print-outputs` names
  exists and holds no symlink. `--tree-only` stops after the tree rules, which
  need no runtime, so `static` runs them for every change.
  Called by `test.yml`, `release-publish.yml`, the pre-commit hook path. The
  no-symlink rule is load-bearing: Codex `plugin add` drops symlinks silently.
- `deploy-vercel-app.sh` — deploys one Vercel project to production and verifies
  its public URLs; with `--preview`, deploys the checkout as a Vercel preview instead
  and leaves production alone. Called by `deploy-docs.yml` and `deploy-api.yml`.

`install/` — the one-line installer, and local testing.

- `install.sh`, `install.ps1` — the one-line installer texttocad.dev serves (`curl -fsSL
  https://texttocad.dev/install.sh | sh`; `irm https://www.texttocad.dev/install.ps1 | iex`), thin and with no
  options (given one, they say so and change nothing): they find uv or install it with uv's own installer,
  download `install.py` from beside themselves on the site, and run it with uv's Python 3.14. Where one fails
  before `install.py` runs, it sends one anonymous report of where (`uv`, `fetch`, `python`), under
  `install.py`'s rules, on a person's run alone: on a run cad started they say and send nothing, so those
  three stages go unreported there.
- `install.py` — the installer itself, the standard library alone, carrying no version and taking no
  options, and knowing no agent app: it gets the computer a cad that works and is current, then hands over to
  it. It installs cad as a uv tool, PyPI's newest, only where no cad is installed (one that does not start is
  installed again; a cad installed with pipx is a global cad too, installed again with pipx where it does not
  start), and puts cad's folder on the PATH with uv's own `uv tool update-shell` (unless `UV_NO_MODIFY_PATH`
  is set). Where a person ran it and cad was here already, that cad's own `cad update` brings it up to date,
  inside its major, never failing the run, its output captured and said in one line (two on a pipe); where
  cad ran it (0.11.12 and 0.11.13 do, and the bridge from earlier releases), cad is left as it is. Then `<cad> plugin install` puts the plugin into each agent app
  (cad's table of apps, `cad_server/plugin`, with the terminal's logo and live line); a cad with no such
  command, or none at all, gets the newest release's by `uv tool run cad@latest plugin install`. Last, that
  cad's own `cad plugin update auto on` turns the switch on (`CAD_INSTALL_FAILED=1` where the plugin's step
  ended non-zero or named an app as failed). It never runs `cad plugin update` alone or `cad setup`, and passes no cad server's name for
  its run (`CAD_INSTALL_ATTEMPT`, `CAD_PLUGIN_SERVER_RUN`) to anything it starts. It exits 0 only where the run ended well, and writes the report 0.11.12 and
  0.11.13 read (`CAD_INSTALL_REPORT`) last: `apps` as `cad plugin install` said them, and, since those releases
  read the report and never the exit status, with `"plugin": "failed"` added wherever the plugin's step ended
  non-zero and named no app as failed (cad itself installed), so they run the command again later. It reads
  no version feed. A run that fails where no working cad can
  count it sends one anonymous report of where (`cad`, `plugin`, or `script` for a crash, to
  `api.texttocad.dev/v1/install`), said in one line first on a person's run; none where `DO_NOT_TRACK` is on or
  `CAD_TELEMETRY` off, in CI, where cad's kept settings say no, or from a checkout. A run cad started says no
  line, and sends its report only where cad's kept settings show the person was told what cad sends, or said
  yes. The docs site copies the three into its
  `public/` as it builds (`apps/docs/scripts/install-scripts.mjs`). Tested by
  `tests/python/global/test_install_script.py` (a temporary home, a stand-in uv, cad, pipx and curl on PATH,
  a stand-in receiver on loopback); `.github/workflows/install-windows.yml` and
  `install-linux.yml` rehearse the scripts on fresh runners, against this tree's wheel or, dispatched
  with `published`, what people install today.

- `dev_install.py [APP...]` / `dev_install.py --release` — installs this checkout into the agent apps
  (every app found, or those named by the keys of cad's table of apps), and goes back to the published
  release. It installs the checkout as the `cad` uv tool, editable, with automatic updates off (the cad step is
  `install.py`'s), writes the plugin into
  `tmp/dev-plugin/text-to-cad` (its version `<VERSION>-dev.<time>`, Codex's CAD server `cad mcp`, the
  catalog `earthtojake-dev`) and hands that folder to cad's table (`cad_server/plugin`, loaded from the
  checkout's files) in place of GitHub, so
  each app's published copy of ours goes and the development copy comes in; `--release` uninstalls the
  editable tool and runs `install.py` as it is, which hands the apps to the published cad. Developer step in
  `CONTRIBUTING.md` ("Test In Agent Apps"); tested with
  `install.py` by `tests/python/global/test_install_script.py`.

`git-hooks/pre-commit` — the body `.githooks/pre-commit` runs: `bundle.sh --check`
when staged paths touch `packages`, `apps`, `skills` or `scripts/bundle`. It is
kept now that nothing is committed, because the question it asks is still worth
asking locally and costs seconds (the shared packages, then two vite builds): does
this edit still BUILD? It no longer has anything to say about the index.

`build/library.mjs` — the esbuild library build `packages/core` and
`packages/ui` share; each package's `scripts/build.mjs` calls it.

`brand/` — `export-logos.mjs` exports app and plugin icons from the committed SVGs.
Run by hand when the brand changes; ordinary builds use the committed files. See
[the brand recipe](brand/README.md).

`look/` — `bake-environment.mjs` bakes the engine's look's reflection environment
(`packages/cad/src/cad/engine/render/studio.hdr`, committed): core's neutral
studio scene ray-cast into a small equirectangular Radiance image, which the viewer
and the OCCT prototype both light an engine document's regular modes with. Run by
hand when the studio or the look changes.

`bench/` — manual measurements, never run in CI ([`bench/README.md`](bench/README.md)):
`occt_parity.py`, the viewer against OCCT, mode by mode; `dfm_bench.py`, the manufacturing checks
over a folder of STEP files; and `skill_ab.py`, which lays out an A/B test of the skills (a Git
ref's against the working tree's, one fresh agent a task) from the tasks in `bench/skill_ab/`. Their
reports are local output under `tmp/`, never committed here;
only their pure helpers are tested (`tests/python/global/test_bench_helpers.py`).

## CI

| Workflow | Branches/events | Purpose |
| -------- | --------------- | ------- |
| `test.yml` | pushes to and PRs against `main` and `build-test`; nightly on `main`; manual dispatch; called by `release-publish.yml` | One job per thing that has to work, each run whole on its one flag, only when the change selects it (`select_checks.py`; `docs/contributing/testing.md#ci` lists the jobs): `static` always (the version check, the tracked tree's rules, the light contracts, the API's tests; on a pull request, what merging it releases); the package suites on Linux and Windows, in shards (`packages (Linux I/2)`, `packages (Windows I/3)`); `routing (macOS)`; `skills`; `js-core`, `js-ui`, `js-web`, `js-mcp`, `docs`; `fea`, `kicad`, `blender`; `packaging` bundles from clean (nothing under `_runtime/` is committed, so this is where it comes from), checks the layout, inspects the wheels and runs the installed-mode tests; `viewer-e2e` serves that bundle's viewer through the backend to the launch smoke test and the browser gates. A full run (a `VERSION` change, the nightly, a dispatch, `Publish Release`'s call) adds the release tier: the package suites on Python 3.11, the installer rehearsals and the update rehearsal (`update-rehearsal`, on Linux, macOS and Windows). `CI`, the one required check, fails when any job did. Each run records the tree it tested; a push whose tree its pull request already tested runs nothing again. Superseded PR runs are cancelled. |
| `release-prepare.yml` (`Prepare Release`) | manual dispatch (`bump` or `set_version`; `target`, `dry_run`) | Opens a release pull request of what the target already has: `bump-version.sh` on `release/X.Y.Z`, pushed and opened with `PREPARE_RELEASE_TOKEN` so its checks run. It never merges: merging the pull request releases it. `target=build-test` rehearses. |
| `release-publish.yml` (`Publish Release`) | pushes to `main` and `build-test` that change `VERSION` (a release pull request's merge); manual dispatch (resume the commit that last moved `VERSION`) | Gate (`VERSION` past the latest tag); the record of a run that tested that tree in full, or else every `test.yml` job on it; the checked OpenAI plugin ZIP (built first, from the untouched release commit) and plugin trees; bundle, wheel build, an `unzip -l` assertion that the shipping wheel carries `_runtime`, install test, distribution artifact; then — on `main` only — PyPI upload (its own `pypi` job in the `release` environment, the only job that may mint a PyPI token; a file PyPI already holds is taken from PyPI, not uploaded again), a wait until PyPI's index lists the version, the plugin committed onto `latest`, `claude-plugin` and `codex-plugin`, and after them the docs deploy and the `v<VERSION>` tag and GitHub Release carrying the wheel, sdist and plugin ZIP. On `build-test` it prints what it would have uploaded, pushed and tagged, and stops. |
| `deploy-docs.yml` (`Deploy Docs`) | manual dispatch; called by `release-publish.yml` | Deploys the docs app to Vercel production from a ref (default `main`), or, dispatched with `preview`, that ref as a Vercel preview with production untouched: configures Vercel Authentication for preview deployments only, runs `vercel pull/build/deploy --prod`, and verifies the public production URLs. The site serves the install command, so a production deploy first asks PyPI's newest cad whether it has `cad plugin install` (`scripts/release/newest_cad.py`) and deploys nothing where it has not; a preview, and a ref from before that check, are not asked. |
| `deploy-api.yml` (`Deploy API`) | pushes to `main` that change `apps/api`; manual dispatch | Deploys `api.texttocad.dev` (`apps/api`) to Vercel production after its tests (`test-api.sh`). It follows no release. |
| `install-linux.yml` (`Linux installer rehearsal`) | called by `test.yml` (a full run; a change under `scripts/install` or to cad's `cad plugin install`); manual dispatch | Runs `install.sh`, piped, on `ubuntu-latest` and in `python:3.12-slim-bookworm`, against this tree's wheel or, dispatched with `published`, the site's `install.sh` and PyPI; checks `cad --version`, both switches on, a model and `cad doctor`. |
| `install-windows.yml` (`Windows installer rehearsal`) | called by `test.yml` (a full run; a change under `scripts/install` or to cad's `cad plugin install`); manual dispatch | Runs `install.ps1` on a fresh Windows runner against the wheel the tree builds, or, dispatched with `published`, the site's `install.ps1` and PyPI. |

`Prepare Release` opens a release pull request, or a pull request carries its own
bump (`release/bump-version.sh`); merging either starts `Publish Release` (PyPI,
then the install branches); `Deploy Docs` redeploys. `main` is the one branch you
develop on, and what releases tag; installers follow `latest`, written only by
`Publish Release`; `build-test` is the rehearsal. The viewer is a local-filesystem
app with no hosted deployment.
