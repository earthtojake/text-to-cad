# Testing

How to add or change a test, a runner under `scripts/test/` or a job in `.github/workflows/test.yml`,
and what to do when a run is red. The command for each kind of change is in
[AGENTS.md](../../AGENTS.md#checks); the runners' options are in
[`scripts/README.md`](../../scripts/README.md).

- [The rules](#the-rules)
- [Adding a test](#adding-a-test)
- [Adding a CI job](#adding-a-ci-job)
- [CI](#ci): [the jobs](#the-jobs), [a full run](#a-full-run), [the release tier](#the-release-tier),
  [shards](#shards), [a tree is tested once](#a-tree-is-tested-once), [the gate](#the-gate),
  [timeouts](#timeouts)
- [When a run is red](#when-a-run-is-red)
- [Other ways to test](#other-ways-to-test)
- [Performance changes](#performance-changes)

## The rules

AGENTS.md states the four that hold everywhere. Here is what each means, why, and what holds it, with
two it leaves out.

1. **Every test runs in CI.** A runner under `scripts/test/` collects each test file, a `test.yml` job
   calls each runner, and a collector that finds nothing fails: a test no job runs is dead.
   (`tests/python/global/test_ci_workspace_selection.py`)
2. **Tests are self-contained.** What `models/` builds is generated and absent in CI, so a test that
   reads it fails on a fresh clone or passes only on what a developer built earlier. Nor does a test
   build on your own server. (`tests/python/global/test_tests_are_self_contained.py`, and the runner:
   step 3 below)
3. **The cheapest level, once.** A unit or jsdom test first; the CAD kernel, a daemon or a real
   browser only where the subject is geometry, a process or WebGL. A test protects a contract, a user
   flow or a fixed bug that no other test does.
4. **No flakes.** A test that passes on a re-run is a defect: fix its mechanism or delete it, and
   never retry, skip or tune it ([how](#when-a-run-is-red)).
5. **CI time is a budget.** A change that lengthens a job says what it costs and why in its pull
   request. Each `js-ui` job stays within 7 minutes.
6. **A test file has a time budget**: 120 seconds on Linux CI, 240 on Windows, where the same files
   take about twice as long. One that outgrows it is split by subject, because the suites run in
   shards and a shard cannot finish sooner than its slowest file. The runner names a file over its
   budget (`CAD_TEST_FILE_BUDGET`) after the summary, `OVER BUDGET`, and as a warning on the run. It
   never fails for it: a wall-clock bound that failed a run would be a flake.

## Adding a test

1. **Check that nothing covers it.** Test observable behaviour, not a private helper, source spelling
   or UI copy. A shared validator's cases are tested once; its callers get a wiring check, not a copy
   of its matrix. Assertions about one result share its setup: do not build the same geometry again
   for unrelated metadata, or repeat an existing integration case.

2. **Pick the level, and with it the place.** The runner that collects the folder runs the new file;
   most tests need no change to CI.

   | The subject | Level | Where the file goes | Job |
   | --- | --- | --- | --- |
   | A rule about the repository's own text, layout or wiring | policy test, standard library alone | `tests/python/global/test_*.py` | `static` |
   | The library, the server or the transport | unit; the kernel where geometry is the subject | `tests/python/packages/cad`, `cad_server`, `cad_mcp` | `packages (Linux)`, `packages (Windows)` |
   | A skill's pages against the code they document | unit | `tests/python/skills/<skill>/` | `skills`, or `static` (step 6) |
   | A tool run as a person has it installed | integration | `tests/python/packages/fea`, `kicad`, `blender` | `fea`, `kicad`, `blender` |
   | Shared JS logic, a React component | Node test or Vitest | beside the source, `*.test.*` | `js-core`, `js-ui (units)`, `js-web`, `js-mcp` |
   | What only WebGL in a real browser shows | browser spec | `packages/ui/src/**/*.browser.test.mjs` | `js-ui (browser)` |
   | The bundled viewer through the real backend | end to end | `tests/browser/viewer-e2e.mjs`, the one file there | `viewer-e2e` |
   | The version feed, the telemetry receiver | Node test | `apps/api/src/*.test.mjs` | `static` |

   `test_ci_workspace_selection.py` lists the names and extensions each runner collects, and fails a
   test file that none does.

3. **Make it self-contained.** Build the smallest fixture in a fresh temporary folder
   (`temporary_directory` in `tests/python/support/tmp_root.py`, whose cleanup waits out Windows'
   sharing violations; the system's temporary folder is fine too), or commit a tiny one beside the
   tests: a CAD or mesh file only when no test can make it, and then listed in
   `tests/python/global/test_no_cad_assets_tracked.py`.

   The runner gives each test file engine, state, cache and `cad` command folders of its own, with a
   server it starts there and stops when the file ends. It fails the run, naming the test, when the
   run writes a document, engine or installation record in your own state folder, or your `cad`
   command. A test that needs a server to itself (a cold start, its workers) calls
   `engine_daemon.isolate(unittest.addModuleCleanup)` in `setUpModule`
   (`tests/python/support/engine_daemon.py`), or sets `CAD_ENGINE_DIR` with `CAD_STATE_DIR` and
   `CAD_CACHE_DIR` beside it, registers an installation there and starts the server (`register` and
   `start`, which `watched` also calls): no command starts one, and a client starts no engine where no
   installation is registered. A test that spawns a build sets `CAD_ENGINE_DIR` itself, so that the
   file run directly never builds on your own server. Stop what a test starts and remove what it
   writes.

   A test that runs `cad plugin install` (by either name) or the install script gives it a computer
   of its own: a temporary home and stand-in programs on PATH for the agent apps' CLIs, git, uv and
   `cad` (`tests/python/support/agent_apps.py`: `AgentApps`, and `PluginRuns` for the command). The
   runner's folders are not enough: the command works in the home folder, and in yours it installs
   the plugin into the real apps on your computer.

4. **Count its cost.** A worker's first build pays about 2.6 s importing the CAD kernel, and every
   subprocess an interpreter's start. Build a fixture the tests only read once for the class and copy
   it in; build in-process (`daemon=False`) where the subject is not the daemon; start a subprocess
   only where the subject is the process; pin a non-deterministic property directly and run the case
   once, since repeating it is not coverage. `scripts/test/test-python.sh --print-weights <paths>`
   prints what each slow file costs.

5. **Write it for every platform it runs on.** The packages' suites run on Windows too, and before a
   release on Python 3.11, the packages' floor, to whose grammar
   `tests/python/global/test_cadgen_python_floor_syntax.py` holds every test file. Most Windows
   failures are a pull request's own new test, not the code under test: build paths with `pathlib` or
   `os.path`, never a POSIX literal; compare text read from a file or a process with its line endings
   normalised; start a command through the interpreter or the resolved executable, never a bare name
   that is a `.cmd` shim on Windows; expect a platform's own wording in an error message. CI runs the
   package test files a change touches before the suite ([shards](#shards)), so such a break reports
   in a minute or two.

6. **Wire it only where the selector cannot see it.** The selector
   (`scripts/github-workflows/select_checks.py`) knows components, not tests: a new file in a suite's
   folder runs with that suite, whatever it imports. Edit it only for:

   - a test that reads another component's file (a fixture one language writes and another asserts is
     current; a skill's pages): a rule names that path and the test or suite, as `skills/fea` selects
     the fea skill's suite;
   - a policy test that needs the CAD kernel or the built runtime: list it in `HEAVY_POLICY`, and it
     runs in `skills`. Every other one runs in `static` with nothing installed, where it fails if it
     needs more, and never catches `ImportError` to skip: it would pass having tested nothing;
   - a skill's suite that needs nothing installed: list its folder in `LIGHT_SKILL_TESTS`, and it
     runs in `static`, not `skills`;
   - a file at a kind of path no rule names: every tracked path matches a rule
     (`test_ci_workspace_selection.py`).

## Adding a CI job

A test joins an existing job unless it cannot run there. A job of its own is for tests that need
what no other job has:

- another operating system (`packages (Windows)`, `routing (macOS)`);
- another toolchain or environment, installed as a person has it (`fea`, `kicad`, `blender`);
- another interpreter (`packages (Python 3.11 floor)`);
- the built artifact in place of the source (`packaging`, `viewer-e2e`, the installer rehearsals).

Splitting a job that has outgrown its time is the other reason: shards of one suite, not a new kind
of job. Wanting a name of its own in the checks list is not one.

A new job:

- has `needs: changes` and one `if:` on one selector flag, and no step that reads a flag, so it runs
  whole or is skipped. A new flag goes in the selector's `FLAGS`, in a rule, and in the `changes`
  job's `outputs`;
- calls every runner it adds (`scripts/test/test-*.sh`), which gets a selector rule and, in
  `test_ci_workspace_selection.py`, the pattern of the files it collects;
- installs only what its tests need, through `.github/actions/setup-deps`: npm workspaces by name,
  the development environment from `uv.lock`, the Playwright browsers on request, system packages by
  its `apt` input (no `apt-get` in the workflow). A job that reads the packaged runtime builds it
  itself, as `packaging` and `viewer-e2e` do: an artifact would put it behind a bundle job for longer
  than the bundle takes;
- has a timeout of about twice its slowest run ([timeouts](#timeouts)), and one on every setup step;
- asks for no permission that `Publish Release` does not grant its call of `test.yml`;
- is in `CI`'s `needs`;
- says in its pull request what it costs each run and which tier it belongs to
  ([the release tier](#the-release-tier)).

`test_ci_workspace_selection.py` holds the flag, the runner and its files, `apt-get`, the presence
of each timeout, the permissions and `needs`, by what must stay true and not by the workflow's
layout: a job is renamed, split or retimed without an edit there.

## CI

`test.yml` runs one job per concern, each whole on its one selector flag or skipped, so a green job
ran all of itself. Its first job, `Changed paths`, puts every path the change touches (added,
modified or deleted, against the target branch as it is now) through
`scripts/github-workflows/select_checks.py`, a short table of components: the directories whose
change a job or a suite has to see. A path selects the union of the rules it matches. Selection is by
path, never by what a file says: a comment in a module selects what the module's code would. Ask the
selector what a change runs:

```bash
python3 scripts/github-workflows/select_checks.py --paths packages/cad/src/cad/results.py
```

### The jobs

The tiers: `static` runs on every change, with nothing installed but Python and Node. A unit job
tests one package or app. A platform job tests what differs by operating system: paths, locks,
subprocesses, line endings, the C library. An integration job tests a third-party tool installed as
a person has it, the wheels as they ship, or the bundled viewer through the real backend. The release
tier runs on a full run. The gate is the one required check.

In the table, the packages are `packages/cad`, `packages/aliases` and `scripts/bundle`, and the UI is
`packages/ui`.

| Tier | Job | Runs on a change to | What it runs |
| --- | --- | --- | --- |
| static | `static` | anything | The version check (on a pull request, [what merging it releases](releases.md#shipping-a-release)), the tracked tree's rules, the light contracts (every policy test not in the selector's `HEAVY_POLICY`, and the `render` and `sendcutsend` skill suites) and the API's tests |
| unit | `packages (Linux I/2)` | the packages; a file under their suites | The library's, the server's (the engine's and the viewer backend's included) and the transport's suites under Xvfb, or the files of them the change selected |
| unit | `skills` | the packages; `skills/fea`; a heavy policy test or skill suite | The policy tests and skill suites that load the CAD kernel or the built runtime |
| unit | `js-core` | `packages/core`, which starts a full run; `apps/docs` (the dependency check walks it) | `@cad/core`'s units, the dependency and kit-boundary checks |
| unit | `js-ui (units)`, `js-ui (browser)` | the UI | The checks, the type check, the Node tests and Vitest; the browser specs, one at a time because each renders WebGL in software |
| unit | `js-web` | the UI; `apps/web` and what its Markdown links to | The viewer client's type check and units |
| unit | `js-mcp` | the UI; `apps/mcp` | The CAD app's type check, units and one-file build |
| unit | `docs` | `apps/docs`; `docs/install.md` and `docs/migrations`, which the site shows as they are; `scripts/brand`; the one-line installers, which the site serves | Lint, the Next build, which resolves every link of the documentation, icon verification |
| platform | `packages (Windows I/3)` | as `packages (Linux)` | The same suites on Windows |
| platform | `routing (macOS)` | the packages; the router's unit files | Those files on the third C library (the router's copper is held to one digest on all three) |
| integration | `fea` | the packages; its suite | `test-fea.sh`, with netgen and CalculiX installed (the lock's `fea` group) |
| integration | `fea (Windows smoke)` | as `fea`, on its flag | One solve of the fea suite through the command on Windows, with the cad-ccx wheel for that platform: about 2 minutes a run, most of it installing |
| integration | `kicad` | the packages; its suite | `test-kicad.sh`, in the environment of `cad[kicad]` |
| integration | `blender` | the packages; its suite | `test-blender.sh`, in the environment `cad run` makes for bpy; a test that skips there fails the run |
| integration | `packaging` | what ships in a wheel (the packages, the UI, `apps/web`, `apps/mcp`); the scripts that build and check it | The bundle from clean, its layout, the wheels' contents and the installed commands |
| integration | `viewer-e2e` | the packages; the UI; `apps/web`; `tests/browser` | The bundle's viewer through the real backend: the launch smoke test, then the format and camera gates in Chromium |
| release | `packages (Python 3.11 floor I/2)`, `install (Linux)`, `install (Windows)`, `real install`, `update rehearsal (<system> I/2)` | a full run; a change to the thing itself | [The release tier](#the-release-tier) |
| gate | `CI` | anything | [The one required check](#the-gate) |

What the table leaves out:

- A test file runs itself; anything else in a suite's folder (a helper, a fixture) runs the suite. A
  suite with a job of its own (`fea`, `kicad`, `blender`) is that job's alone.
- A runner under `scripts/test/` runs what it feeds.
- Prose and metadata run `static` alone: root prose, `docs/`, the plugin manifests and configs,
  `skills/` but for `skills/fea`, the release scripts and workflows, `apps/api`, `models/`, and
  Markdown under `packages/` and `apps/`. The exceptions are what ships in a wheel
  (`packages/cad/README.md`, its `LICENSE` and the aliases' READMEs: `packaging`) and `apps/web`'s
  Markdown, whose links its tests resolve (`js-web`).
- `scripts/test/test.sh` is not what CI runs. It chains `test-js.sh`, `test-api.sh`, `test-python.sh`
  and `test-global.sh` on one machine, and leaves out the suites with a job of their own, the docs
  checks, `packaging`, `viewer-e2e` and the release tier.

### A full run

A full run is every job on every suite. A manual dispatch, `Publish Release`'s call and the nightly
schedule start one. So does a change to `VERSION` (a release is tested whole), `package.json`,
`package-lock.json`, the root `pyproject.toml`, `uv.lock`, `packages/core`, `scripts/build`,
`tests/python/support`, `test.yml`, `.github/actions`, the selector, `tested_tree.py`, the gate,
`scripts/test/common.sh` or `scripts/test/unittest_files.py`. So does a path no rule names, and
`test_ci_workspace_selection.py` fails until one does.

### The release tier

It runs on a full run, so before a release ships (a pull request that changes `VERSION` runs every
job) and not on every push. The nightly run, on `main`, is the tier for whatever merged without a
release; it runs nothing when a run already tested `main`'s tree in full.

A job belongs there when both hold: it rarely catches what a per-push job does not, and catching it
before a release ships is soon enough. A job moves into the tier, or out of it, with that argument in
its pull request. The tier holds:

- **`packages (Python 3.11 floor)`** (`test-floor.sh`): a third run of the suites the packages jobs
  run on the Python the server's installations use. It guards one rare kind of break, a call the
  floor's standard library lacks, which parses there and fails only when it runs. Whole it took 11 to
  17 minutes, so it is always two shards. A change to `test-floor.sh` runs it too.
- **The installer rehearsals** (`install-linux.yml`, `install-windows.yml`): the one-line installers
  on a fresh machine, against this tree's wheel, whose `cad plugin install` they hand over to.
  Dispatched with `published` (`gh workflow run install-linux.yml -f published=true`), they run
  against the release people install today.
- **The real install** (`real-install.yml`, `scripts/test/real-install.py`): the install script, and
  through it this tree's `cad plugin install`, against the real `claude`, `codex` and `gemini` on
  Windows, macOS and Linux, each on a private computer, with cad from this tree's wheel and the plugin
  from this tree's `latest` copy: an install, the script again, and a migration from the state
  0.11.10's installer left. It is the one test of what cad does in agent apps on Windows, where the
  unit tests of its table of apps (`tests/python/packages/cad_server/plugin/`, stand-in programs) are
  skipped. It cannot test the desktop apps (they need a person) or GitHub's `latest`
  branch, which before a release is the last release's. About 10 minutes a system.
- **The update rehearsal** (`scripts/test/rehearse-update.py`): the one test of the move every
  computer makes, unattended or by the install command, on Linux, macOS and Windows. On private
  computers it installs the real releases 0.11.11, 0.11.0 and 0.10.4 from PyPI (and 0.10.0, on
  Windows) and brings each to this tree's build by the route it takes (where the new server runs the
  install command once, that command hands the apps to the cad it installed); then cad's own update
  through the store, automatic and typed, inside its major and across one only by `cad update --major`:
  the automatic one gets the release ready with nothing restarted, at once even while a page asks and a
  command runs every few seconds, then the server restarts on it at its next start, by the viewer's button
  or by a typed `cad update` (PyPI reachable or not), and never by itself at a tending, however long it has
  been ready, nor with automatic updates off or a feed that no longer names it; back by itself from a release whose server does not start, typed or at a start, and
  then held back; a ready release damaged before its restart built again; untouched by one that cannot be
  built or does not run, while `cad` is called every 50 ms and while its files are held open, after a
  person's own reinstall, after its worker was stopped midway, and from the shipped 0.11.17's update in
  place; and after an update, the new server's one `cad plugin install`, read from cad's record of it.
  One more route starts on the real 0.11.13 (`plugin-update`, on shard 1/2 of each system): its own
  `cad plugin update` runs this tree's install command, which finds no `cad plugin install` there and
  has the newest release's do the work (`uv tool run ... cad@latest plugin install`: this tree's), then
  turns the switch on by 0.11.13's own command. `--help` lists the routes.

The last three start on one selector flag, `installer`: a change under `scripts/install`, to the
three workflows, to the two scripts or `scripts/test/real_computer.py`, or to a server module the
update rehearsal runs, among them what the install command hands the apps to (`cli/plugin.py`,
`_internal/plugin_catch_up.py`, `plugin/`; the selector's rule lists them).

Both scripts run locally, with uv and the network: one route as
`scripts/test/rehearse-update.py store-only`, and `scripts/test/real-install.py --wheels <dir>`
against the programs on your PATH, never your own configuration of them. `<dir>` holds this tree's
wheels: `CAD_KEEP_WHEEL=1 CAD_WHEEL_OUT_DIR=<dir> scripts/release/check-wheel-contents.sh`, after
`scripts/bundle/bundle.sh`.

### Shards

Run whole, the packages' suites are split over two jobs on Linux and three on Windows (the selector's
`SHARDS`), each taking its share of every suite (`CAD_TEST_SHARD=I/N`, which any
`run_python_unittest` honours). A narrowed selection runs in one job.

Shard 1 of each platform also runs the type check (once a platform, because the checker reads the
`win32` branches on Windows alone) and, before the suite, the package test files the change itself
touches, so that a break in a pull request's own test reports in a minute or two. Up to six files:
more would be much of the suite run twice.

### A tree is tested once

Every run records the tree it tested as an artifact, `tested-<tree>-<scope>`, where `scope` is `full`
or a digest of the selection. A push to `main` whose tree a successful run of this repository (never
a fork's) already tested with the same selection, or in full, runs `static` and nothing else: `main`
merges only up-to-date branches, so that is every ordinary merge. `Publish Release` ships a release
commit without testing it again when a run tested its tree in full
(`scripts/github-workflows/tested_tree.py`).

### The gate

`main` requires one check, `CI` (`scripts/github-workflows/ci_gate.py`). It needs every other job
and runs whatever became of them. A job passes by succeeding or by being skipped for its flag. The
run fails when `Changed paths` did not succeed (every job it gates was then skipped having tested
nothing, which GitHub counts as passing), when a job failed, and when one was cancelled, which is
also what a job that ran out its timeout reports.

One cancelled run passes: a pull request's run that a newer push superseded. Its commit is no longer
the head, so its check gates nothing. That pass stays on the superseded commit: a branch force-pushed
back to exactly that commit shows it until the new run's `CI` reports, so wait for the new run there.
A merge that slipped through is still tested, by the push's run and by `Publish Release` before a
release ships.

Because nothing else is required, a job is added, renamed, split or sharded with no change to branch
protection, and no job can fail without stopping a merge. What that asks of a reviewer is in
[Repository settings](releases.md#repository-settings).

### Timeouts

Every job has a timeout of about twice its slowest observed run, and every setup step one of its
own, so a stalled mirror fails in minutes instead of running out its job. The blender and KiCad
suites fetch their environments as they run and the rehearsals are installs: their jobs' timeouts
bound those. `setup-deps` installs a system package only when the image lacks it; its apt gives up on
a connection that says nothing for 30 seconds and, where the runner cannot resolve Ubuntu's mirrors,
reads mirrors named elsewhere.

Within a Python suite, a test file still running after 10 minutes prints every thread's stack and
fails by name, the run starts no further file or suite (`--keep-going` included), and a line a minute
names the files still running. So a job that runs Python test files has a timeout of at least its
slowest run and 11 minutes: the guard fires before the job's timeout does.

## When a run is red

Read the failing job, not the run: `CI` names the jobs that failed, and each job ran only itself.

- **A test failed.** Most failures are defects in the change. Reproduce it with the runner the job
  ran (for a package test, `scripts/test/test-python.sh <the test file>`, under `xvfb-run -a` on a
  Linux machine with no display), fix the change, and never skip the test.
- **A file hung.** The log has `hung:` naming the file, with every thread's stack as it hung: the
  stack says where it waits. `RUN CUT SHORT` says how many files never started.
- **A job timed out with nothing said.** Its last `still running:` line names the files that were
  running.
- **An install step timed out.** A mirror stalled. That is the one failure a re-run answers.
- **`viewer-e2e` failed.** The run's artifact `viewer-browser-diagnostics`, kept three days, holds
  bounded renderer-state JSON for each gate; capture timing is in the job log. Review screenshots are
  `scripts/test/test-viewer-browser.sh --out <dir>`, on your machine.
- **It passes on a re-run.** A flake (rule 4). Classify it first: a real bug, a retired behaviour or a
  platform problem. Then fix the mechanism: wait on the event that says the thing happened, not on a
  clock; give the test a server and folders of its own; assert a condition, not an elapsed time. A
  negative assertion behind a sleep ("it did not exit") is worse than none, because a slow runner only
  ever makes it pass. Where a deterministic unit test already pins the property, delete the racy
  end-to-end copy.

## Other ways to test

**The type check.** Pyrefly's
[basic preset](https://pyrefly.org/en/docs/configuration/#preset-basic) over the package's own `src`
(`[tool.pyrefly]` in `packages/cad/pyproject.toml`; the version is pinned in the root
`pyproject.toml`'s `dev` group): a limited set of diagnostics, not a full type check. Tests, scripts
and skills are outside it. Shard 1 of the packages' jobs runs it on each platform.

```sh
uv run pyrefly check --config packages/cad/pyproject.toml
```

**In an agent app.** Claude Code, Codex and Cursor are tested by hand before a change to the plugin,
the skills, the server or the CAD app ships:
[Test In Agent Apps](../../CONTRIBUTING.md#test-in-agent-apps).

**Browser specs on your machine.** The UI's browser specs run `UI_BROWSER_TEST_CONCURRENCY` files at
a time: 4 by default, and 1 in CI, where Linux renders their WebGL in software and several at once
saturate the runner. `CAD_TEST_SWIFTSHADER=1` makes a macOS run use that same software renderer, to
reproduce a failure only CI shows.

**Manual models.** Reusable edge cases and debugging models are kept in `models/tests/`, each with
how to reproduce it ([its README](../../models/tests/README.md)); despite its name, no test reads
that folder. For manual skill prompts and model review, make a scratch model where
[models/README.md](../../models/README.md) puts a new one, and start your agent with the repository
as its working directory. Review media such as snapshot PNGs are not model files: render them under
`/tmp` and attach them to the pull request. `.gitignore` keeps them out of `models/`.

**The release pipeline** is rehearsed on `build-test`:
[Rehearsing on `build-test`](releases.md#rehearsing-on-build-test).

## Performance changes

A change to the engine's memo, body retention, build closure, meshing or serving opens its pull
request with a before/after timing table, `main` against the branch, on representative models,
covering at least a leaf edit, a parent-only edit, a revert and a no-op. The table names any slowdown
as a regression, and a regression merges only with the repository owner's explicit approval: a cost
is approved as a trade-off, not found later deep in a description. A change that removes a cache or a
performance mechanism first lists what it made faster.

The numbers come from one batch, measured once every change that moves them is in the branch: on one
machine with nothing else building, `main` and the branch side by side on the same models, each on a
server of its own (`CAD_ENGINE_DIR`), cold and warm. They are timed by hand: each build's own line
says its seconds, the bodies it ran and replayed and its memo's hits and misses. Nothing measured is
committed.

Two mechanisms ask for more:

- **The memo** ([Body retention](../../packages/cad/src/cad_server/engine/docs/body-retention.md)).
  A change to it runs its pressure tests first: `tests/python/packages/cad/engine/test_memo.py` and
  `test_bodies.py`.
- **Meshing** ([Mesh](../../packages/cad/src/cad_server/engine/docs/mesh.md): one tolerance, the
  mesher used as it is). A change to it opens its pull request with what it does to the faces left
  unmeshed and the triangle counts across the sample corpus, `main` against the branch.
  `tests/python/packages/cad/engine/test_mesh.py` asserts the contract on small fixtures.
