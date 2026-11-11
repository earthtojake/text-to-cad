# Testing

How this repository tests itself: the rules, what runs where, how to add a test or a CI job, and what
to do when a run is red. Read it before adding or changing a test, a runner under `scripts/test/` or
`.github/workflows/test.yml`. The commands for each kind of change are AGENTS.md's **Checks**; the
runners' options are [`scripts/README.md`](../../scripts/README.md).

## The rules

Each is held by a test where one can hold it.

1. **Every test runs in CI.** A test file is reached by a runner under `scripts/test/`, a runner by a
   `test.yml` job, and a collector that finds nothing fails. A test no job runs is dead: wire it in or
   delete it. There is no manual-only gate. (`tests/python/global/test_ci_workspace_selection.py`)
2. **Tests are self-contained.** No test reads, builds or imports the sample corpus under `models/`; a
   test makes its own small fixture, on an engine daemon of its own.
   (`tests/python/global/test_tests_are_self_contained.py`)
3. **The cheapest level that exercises the real path.** A unit or jsdom test first; the CAD kernel, a
   daemon or a real browser only where the subject is geometry, a process or WebGL.
4. **A test earns its place once.** It protects a contract, a user flow or a fixed bug that no other
   test does.
5. **No flakes.** A flaky test is fixed by mechanism or deleted, never retried, skipped or tuned.
6. **CI time is a budget.** A change that lengthens a job says what it costs and why in its pull
   request; each `js-ui` job stays within 7 minutes.
7. **A test file has a time budget.** 120 seconds on Linux CI, 240 on Windows (where the same files
   take about twice as long). One that outgrows it is split: a shard cannot finish sooner than its
   slowest file. The runner names a file over its budget and never fails for it.
8. **One required check.** `main` requires `CI`, which fails when any job did: no job can fail without
   stopping a merge.

## What runs where

| Tier | Jobs | Runs | What it is for |
| --- | --- | --- | --- |
| static | `static` | every change, nothing installed but Python and Node | The version and tree checks, the policy tests that read only the repository's text, the API's tests: under a minute |
| unit | `packages (Linux)`, `js-core`, `js-ui`, `js-web`, `js-mcp`, `docs`, `skills` | when its component changes | Behaviour of one package or app |
| platform | `packages (Windows)`, `routing (macOS)` | with every change to the packages | What differs by operating system: paths, locks, subprocesses, line endings, the C library |
| integration | `fea`, `kicad`, `blender`, `packaging`, `viewer-e2e` | with every change to the packages; the last two with the UI and the apps too | A third-party tool installed as a person has it; the wheels as they ship; the bundled viewer through the real backend |
| release | `packages (Python 3.13 floor)`, `install (Linux)`, `install (Windows)` | a full run: a `VERSION` change, nightly, a dispatch | Rare breaks that must not reach a release, at a cost not worth paying on every push |
| gate | `CI` | always | The one required check |

**The release tier's criterion.** A job runs on a full run only, not on every push, when both hold:
it rarely catches what a per-push job does not, and catching it before a release ships is soon
enough. Every other job runs on the changes that reach it. The two there now:

- `packages (Python 3.13 floor)` is a third run of suites the packages jobs already run on the Python
  the server's installations use. It guards one kind of break, a call the floor's standard library
  lacks, of which the repository has had one (argparse's `suggest_on_error`), at 11 minutes a run.
- The installer rehearsals install this tree's wheel on a fresh machine. What they exercise changes in
  few pull requests, and before this layout they ran only after a merge (in November 2026 the Linux
  one had passed 7 runs of 7, the Windows one 23 pushes of 25); a release pull request runs every job,
  so no release ships unrehearsed. They also run on a change to the installers themselves.

A job moves into the tier, or out of it, with that argument in its pull request.

Ask the selector what a change runs:

```bash
python3 scripts/github-workflows/select_checks.py --paths packages/cad/src/cad/results.py
```

## Adding a test

1. **Check that nothing covers it.** Keep regression tests focused on observable behavior. Reuse setup within a test
   when several assertions concern the same result; do not repeatedly build the
   same geometry to test unrelated metadata or duplicate an existing integration
   case. Each new test should protect a distinct contract or credible failure not
   already covered. Test a shared validator's cases once; callers need wiring
   checks, not copies of its full matrix. Avoid pinning private helpers, source
   spelling or UI copy when observable behavior already covers the requirement.
   Real kernel and browser tests remain necessary for geometry fidelity,
   cache reuse, rendering, and process-lifecycle behavior.

2. **Pick the level, and with it the place.** The runner that already collects the folder runs the
   new file; most tests need no change to CI.

   | The subject | Level | Where the file goes | Job |
   | --- | --- | --- | --- |
   | A rule about the repository's own text, layout or wiring | policy test, standard library alone | `tests/python/global/` | `static` |
   | The library, the server or the shim | unit, the kernel where geometry is the subject | `tests/python/packages/cad`, `cad_server`, `cad_mcp` | `packages (Linux)`, `packages (Windows)` |
   | A skill's own script | unit | `tests/python/skills/<skill>/` | `static` or `skills` |
   | A tool run as a person has it installed | integration | `tests/python/packages/fea`, `kicad`, `blender` | `fea`, `kicad`, `blender` |
   | Shared JS logic, a React component | Node test or Vitest | beside the source, `*.test.*` | `js-core`, `js-ui (units)`, `js-web`, `js-mcp` |
   | What only WebGL in a real browser shows | browser spec | `packages/ui/**/*.browser.test.mjs` | `js-ui (browser)` |
   | The bundled viewer through the real backend | end to end | `tests/browser/` | `viewer-e2e` |

3. **Make it self-contained.** A test must not read, enumerate, build or
   import sample models from this repository's `models/` directory. Generate the
   smallest fixture needed in a fresh temporary directory, or use a tiny fixture
   committed with the tests (a CAD or mesh one only when no test can make it, and then
   listed in `tests/python/global/test_no_cad_assets_tracked.py`); do not rely on existing outputs.
   Repo `tmp/` and system temporary directories are both fine. Give builds an
   engine daemon of their own (`CAD_ENGINE_DIR`) and clean up their processes and
   files. The runner gives every test file its own state, cache and `cad` command
   folders, its state folder registering the file's interpreter as its current installation
   (`tests/python/support/engine_daemon.py`'s `register`, as `isolate` and `watched` do for the folders a
   test makes: a client with no installation starts no engine), and fails the run, naming the test,
   when the run's server writes a
   document, engine or installation record in your own state folder, or your `cad`
   command. The shared
   temporary-directory helper retains the Windows cleanup retries used by the suite.

4. **Count its cost.** A test's cost is part of its design. Model runs go through the engine's daemon,
   as every build does: the runner gives each test file an engine directory of its
   own (`CAD_ENGINE_DIR`), so a build the file asks for runs on a daemon of that
   file's alone, and stops the daemon the file left there when it ends; a test that
   needs a daemon to itself -- a cold start, its workers -- names a directory of its
   own (the run's files share one bytecode folder, so the kernel's libraries compile once a run).
   A worker's first build pays ~2.6 s importing the CAD kernel, and every
   subprocess a test starts pays an interpreter's start: build a fixture the tests
   only READ once for the class and copy it in, build in-process (`daemon=False`)
   where the subject is not the daemon, and add a subprocess only where the subject
   IS the process. Repeating a non-deterministic case N times is not coverage — if
   the underlying property can be pinned directly, pin it and run the case once.

   `scripts/test/test-python.sh --print-weights` prints what the slow files cost,
   the first thing to read when a run is slow.

   A test file has a budget: 120 seconds on Linux CI, 240 on Windows. Add to a file near it and
   the file is split, by subject, into files that run beside each other: the suites are split over
   shards, and a shard cannot finish sooner than its slowest file. The package jobs set
   `CAD_TEST_FILE_BUDGET=<seconds>`; the runner then names each file over it on a line `OVER BUDGET`
   after the summary, and as a warning on the run. It never fails a run for it: a wall-clock bound
   that failed one would be a flake.

5. **Write it for every platform it runs on.** The packages' suites run on Windows too, and most
   Windows failures are a pull request's own new test, not the code under test. Build paths with
   `pathlib` or `os.path`, never a POSIX literal; compare text read from a file or a process with its
   line endings normalised; start a command through the interpreter or the resolved executable, never a
   bare name that is a `.cmd` shim on Windows; expect a platform's own wording in an error message. CI
   runs the test files a change touches before the suite, on each platform, so such a break reports in
   a minute or two.

6. **Wire it only where the table cannot see it.** The selector knows components, not tests: a new
   test file in a suite's folder runs with that suite, whatever it imports. A rule in
   `scripts/github-workflows/select_checks.py` is needed only when a test reads a file of another
   component (a fixture one language writes and another asserts is current), and names that path and
   the one test. A policy test that needs the CAD kernel or the built runtime is listed in the
   selector's `HEAVY_POLICY`; every other policy test runs in `static` with nothing installed, and one
   that needs more fails there.

## Adding a CI job

A test joins an existing job unless it cannot run there. A job of its own is for tests that need what
no other job has:

- another operating system (`packages (Windows)`, `routing (macOS)`);
- another toolchain or environment, installed as a person has it (`fea`, `kicad`, `blender`);
- another interpreter (`packages (Python 3.13 floor)`);
- the built artifact in place of the source (`packaging`, `viewer-e2e`, the installer rehearsals).

Splitting a job that has outgrown its time is the other reason: shards of one suite, not a new kind of
job. Wanting a name of its own in the checks list is not a reason.

A new job:

- runs whole on one selector flag, or is skipped; no step inside it reads another flag;
- has a timeout of about twice its slowest run (with Python test files, at least its slowest run and
  11 minutes), and a timeout on every install step;
- is in `CI`'s `needs` (`test_ci_workspace_selection.py` fails one that is not);
- says in its pull request what it costs each run, and which tier it belongs to
  ([the release tier's criterion](#what-runs-where)).

## CI

`test.yml` runs one job per concern, each on one flag: a job runs whole on its
flag or is skipped, and no step inside it reads another, so a green job ran all
of itself. Its first job, `Changed paths`, puts every path the change touches —
added, modified or deleted, against the target branch as it is now — through
`scripts/github-workflows/select_checks.py`: a short table of components, the
directories whose change a job or a suite has to see. A path selects the union of
every rule it matches. Selection is by path, never by what a file says: a comment
in a module selects what the module's code would, and no rule reads a file to
decide which tests reach it. The components:

- **The packages** (`packages/cad`, `packages/cad-server`, `packages/cad-mcp`,
  `packages/aliases`, `scripts/bundle`): their suites whole on Linux and Windows,
  `skills`, `packaging`, `viewer-e2e`, and the jobs that run them with a tool
  installed or on the third C library (`fea`, `kicad`, `blender`,
  `routing (macOS)`: minutes together, never the longest job).
- **The UI** (`packages/ui`): `js-ui`, `js-web`, `js-mcp`, `packaging`, `viewer-e2e`.
  **An app**: its own job, and for `apps/web` and `apps/mcp` the wheel that ships it.
- **A test file** runs itself; anything else in a suite's folder, the suite. A suite
  with a job of its own (`fea`, `kicad`, `blender`) is that job's alone.
- **A runner** under `scripts/test/` runs what it feeds.
- **Prose and metadata** run `static` and nothing else.

| Job | Runs on | What it runs |
| --- | --- | --- |
| `static` | every change | With Python and Node alone: the version check (canonical version, derived metadata, the release's pins; on a pull request, what merging it releases, see [Shipping a release](../../CONTRIBUTING.md#shipping-a-release)), the shipping contract's tree rules, the light contracts (every policy test that reads only the repository's text, and the print3d, render and sendcutsend suites) and the API's tests |
| `packages (Linux I/2)` | the packages, a package test | The library's, the server's (the engine's and the CAD Viewer backend's included) and the shim's suites under Xvfb, or the files of them the change selected; the type check |
| `packages (Windows I/3)` | the same | The same suites and the type check on Windows: paths, locks, subprocesses, file URLs and the daemon are platform-sensitive |
| `routing (macOS)` | the packages, the router's unit files | The router's unit files on the third C library (its copper is held to a digest on all three) |
| `skills` | the packages, `scripts/bundle`, the fea skill | The policy tests and skill suites that load the CAD kernel or the built runtime |
| `js-core` | `packages/core`, the dependency checks, `apps/docs` (the dependency check walks it) | `@cad/core`'s units, the dependency and kit-boundary checks |
| `js-ui (units)`, `js-ui (browser)` | `packages/ui` | The UI's type check and units; its browser specs |
| `js-web` | `packages/ui`, `apps/web` and what its Markdown links to | The CAD Viewer client's type check and units |
| `js-mcp` | `packages/ui`, `apps/mcp` | The CAD app's type check, units and one-file build |
| `docs` | `apps/docs`, `scripts/brand`, the one-line installers | Lint, the Next build, icon verification, the brand marks |
| `fea` | the packages, its suite | `test-fea.sh`, with netgen and CalculiX installed |
| `kicad` | the packages, its suite | `test-kicad.sh`, in the environment of `cad[kicad]` |
| `blender` | the packages, its suite | `test-blender.sh`, in the environment `cad run` makes for bpy; a test that skips there fails the run |
| `packaging` | the packages, the UI, `apps/web`, `apps/mcp`: whatever ships in a wheel | Clean bundle, layout, the wheels' contents, the installed commands |
| `viewer-e2e` | the packages, the UI, `apps/web`, `tests/browser` | The bundle's viewer through the real backend: the launch smoke test and the format and camera gates in Chromium |
| `packages (Python 3.13 floor)` | a full run | The three suites on the packages' oldest Python (`test-floor.sh`) |
| `install (Linux)`, `install (Windows)` | a full run; `scripts/install`, the two workflows | `install-linux.yml` and `install-windows.yml`: the one-line installers on a fresh machine, against this tree's wheel |
| `CI` | always | The one required check: every job that ran passed (`scripts/github-workflows/ci_gate.py`) |

**A full run** is every job on every suite. `VERSION` (a release is tested
whole), `package.json`, `package-lock.json`, `requirements-dev.txt`,
`packages/core`, `scripts/build`, `tests/python/support`, the workflow,
`setup-deps`, the selector, the gate, the runners' shared parts and any path the
table does not name start one; so do a manual dispatch, `Publish Release`'s call
and the nightly schedule. Prose inside a code tree (`packages/**/*.md`,
`apps/**/*.md`) is read by the light contracts alone — except the packages'
READMEs, the wheels' descriptions, and `apps/web`'s Markdown, whose links its
tests resolve. Root prose, the plugin manifests and configs, the release scripts,
`apps/api` and `models/` run `static` and nothing else.

**The release tier** runs on a full run only, so before a release ships and not
on every push ([its criterion](#what-runs-where)): the packages' suites on Python
3.13, and the installer rehearsals, which also run on a change to the installers
themselves (`scripts/install`, the two workflows). The nightly run, on `main`, is
that tier for whatever merged without a release; it runs nothing when a run
already tested `main`'s tree in full.

**Shards.** Run whole, the packages' suites are split over two jobs on Linux and
three on Windows, each taking its share of every suite (`CAD_TEST_SHARD=I/N`,
which any `run_python_unittest` honours); a narrowed selection runs in one. The
first shard also runs the type check, once a platform because the checker reads
the `win32` branches on Windows alone, and the package test files the change
itself touches before the suite, so a break in a pull request's own test (most
Windows failures are one: a POSIX path, a line ending) reports in a minute or
two (up to six files: more would be much of the suite run twice). The UI's tests are two jobs: `js-ui (units)` runs the checks, the type check,
the Node tests and Vitest (`test-js.sh --select ui-units`), and `js-ui (browser)`
the browser specs, one at a time because each renders WebGL in software
(`--select ui-browser`).

`tests/python/global/test_ci_workspace_selection.py` holds the table and the
workflow to the tree by what must stay true, not by how the workflow is laid out:
every test file is collected by a runner and every runner called by a job, every
rule matches a tracked file and names tests that exist, every job runs on one flag
and no step on any, a full run runs everything, and `CI` needs every job. A job
is added, renamed, split or retimed without an edit there; a new job goes in
`CI`'s `needs` (the same test fails one that is not there). Each job installs only
what its tests need: npm workspaces by job, Python and the two Playwright browsers
on request, system packages through `setup-deps`'s `apt` input, and nothing beyond
Python and Node for `static`.

Every run records the tree it tested as an artifact, `tested-<tree>-<scope>`
(`scope` is `full` or a digest of the selection). A push to `main` whose tree
its pull request's run already tested with the same selection runs nothing
again — `main` merges only up-to-date branches, so that is every ordinary merge
— and `Publish Release` ships a release commit without re-testing it when a run
here tested its tree in full (`scripts/github-workflows/tested_tree.py`: a
successful run of this repository, never a fork's).

**`CI` is the one required check.** It needs every other job and runs whatever
became of them. A job passes by succeeding or by being skipped for its flag; the
run fails when the selection itself did not run (every job it gates was then
skipped having tested nothing), when a job failed, and when one was cancelled or
ran out its timeout. A pull request's run that a newer push superseded is the one
cancelled run that passes: its commit is no longer the head, so its check gates
nothing, and failing it would report a failure for every push made while a run
was in flight. That pass stays on the superseded commit: a branch force-pushed
back to exactly that commit shows it until the new run's `CI` reports, so wait
for the new run there (a merge that slipped through is still tested by the push
run, and by `Publish Release` before a release ships). Because nothing else is required, adding, renaming, splitting or
sharding a job needs no branch-protection change, and no job can fail without
stopping the merge.

**Nothing waits long.** Every job has a timeout of about twice its slowest
observed run (a job that runs Python test files, at least its slowest run and
11 minutes, so the hang guard below fires before it), and every install step has
one of its own (`setup-deps` as a whole, the pip and uv installs): a stalled
mirror fails in minutes rather than running out its job. The blender and KiCad
suites fetch their environments as they run and the rehearsals are installs;
their jobs' timeouts bound those. `setup-deps` installs system packages only when the image
lacks one, and apt gives up on a connection that says nothing for 30 seconds. Where a runner
cannot resolve Ubuntu's mirrors, it points that job's apt at mirrors named elsewhere.
Within a Python suite, a test file still running after 10 minutes prints every
thread's stack and fails by name, the run starts no further file or suite
(`--keep-going` included), and a line a minute says which files are running.

Viewer browser failures upload bounded renderer-state JSON for three days.
CI sets `VIEWER_TEST_DIAGNOSTICS_DIR` for this evidence; it does not enable the
optional review screenshots produced by `--out`. Capture timing stays in the
job log, so a stalled screenshot still leaves useful state diagnostics.

**The packaged runtime is built per job** that reads it (`packaging`,
`viewer-e2e`), not built once and passed between them: an artifact would
serialise every test job behind a bundle job for longer than the bundle takes.

## When a run is red

Read the failing job, not the run: `CI` names the jobs that failed, and each job ran only itself.

- **A test failed.** Most failures are real: of 52 failed jobs read in one review (November 2026), 47 were defects in
  the change, and 27 were on Windows. Reproduce it with the same runner
  (`scripts/test/test-python.sh <the test file>`), fix the change, and never skip the test.
- **A file hung.** The log has `hung:` naming the file and every thread's stack as it hung, and ends
  `RUN CUT SHORT`; the files after it did not run. The stack says where it waits.
- **A job timed out with nothing said.** Its last `still running:` line names the files that were
  running.
- **An install step timed out.** A mirror stalled; that is the one failure a re-run is the answer to.
- **It passes on a re-run.** That is a flake, and a flake is a defect:

  **Flakes are fixed by mechanism or deleted — never skipped, retried, or tuned.**
  Classify first: a real bug, a retired behaviour, or a platform problem. Then fix
  the mechanism — wait on the event that says the thing happened, not on a clock;
  give a test its own engine daemon and folder; assert a condition rather than an
  elapsed time. A negative assertion behind a sleep ("it did not exit") is worse
  than useless, because a slow runner only ever makes it pass. If a deterministic
  unit test already pins the property, delete the racy end-to-end copy instead of
  stabilising it.

## Other ways to test

**The type check.** With the development environment active, check the three distributions' Python sources with:

```sh
for project in cad cad-server cad-mcp; do
  python -m pyrefly check --config "packages/$project/pyproject.toml"
done
```

Pyrefly is pinned in `requirements-dev.txt`. Each package's `[tool.pyrefly]`
configuration uses the [basic preset](https://pyrefly.org/en/docs/configuration/#preset-basic)
over its own `src`. It checks a limited set of diagnostics, including
undefined names in annotations, and skips unannotated function bodies and broader
argument and assignment checks. Tests, scripts and skill helpers are outside this
check's scope. The first shard of the packages' suites runs it on each platform, before the suite.

**In an agent app.** Claude Code, Codex and Cursor are tested by hand before a change to the plugin,
the skills, CAD's server or the CAD app ships:
[Test In Agent Apps](../../CONTRIBUTING.md#test-in-agent-apps).

**Browser specs on your machine.** The UI's browser specs (`packages/ui/**/*.browser.test.mjs`) run as their own
pass, `UI_BROWSER_TEST_CONCURRENCY` files at a time (4 by default; the CI
`js-ui` jobs set 1, because Linux renders their WebGL in software and several
at once saturate the runner; they are a job of their own). `CAD_TEST_SWIFTSHADER=1` makes a macOS run use that same
software renderer, to reproduce a CI-only browser failure locally.

**Manual models.** Keep reusable manual edge-case and debugging models in `models/tests/`, with
reproduction instructions. Despite its name, that folder is never CI input;
see [its manual-validation policy](../../models/tests/README.md).

For manual skill prompts and model review, work inside this repository and keep
samples and CAD/robot-description artifacts under `models/`
([its README](../../models/README.md) maps the corpus and says where a new model goes). Create a scratch
project in the fixture bucket it belongs in: a standalone part
goes in the `models/examples/` cad-project, an assembly gets its own group in
`models/assemblies/` (`src/<assembly>/`), a drawing goes in `models/drawings/` —
each a `@model` script in `src/`; a run writes nothing, and files are exported on
request into the project's gitignored `STEP/`, `STL/`, `GLB/`, `3MF/` or `DXF/`.
For example:

```bash
$EDITOR models/examples/src/my_test.py     # @model def my_test(): ...
python models/examples/src/my_test.py      # prints its id: and view:
```

Then start your agent with `/path/to/text-to-cad` as the working directory and
ask it to write files under that scratch path. This keeps manual model sources,
generated artifacts, and Viewer links together, independently of the automated
test suite.

Review media such as snapshot PNGs are not model artifacts:
render them under `/tmp` and attach them to the pull request instead. `.gitignore`
keeps them out of `models/`.

**Rehearsals.** The release pipeline is rehearsed on `build-test`
([Rehearsing on `build-test`](../../CONTRIBUTING.md#rehearsing-on-build-test)), and the installers on
a fresh machine by `install-linux.yml` and `install-windows.yml`, which `test.yml` calls in the release
tier and which a dispatch with `published` runs against the release people install today.

### Performance changes

A change to the engine's memo, body retention, build closure, meshing or serving
opens its PR description with a before/after timing table for `main` and the
branch, on representative models, covering at least a leaf edit, a parent-only
edit, a revert and a no-op. The table names any slowdown as a regression, and a
regression merges only with the repository owner's explicit approval. A change
that removes a cache or a performance mechanism first lists what it made faster.
#478 removed a kernel-op memo for correctness and slowed re-runs (f1's
`power_unit` forced rebuild went from 24 s to 102 s); that cost sat deep in a long
PR body instead of being approved as a trade-off. The engine's memo
(`packages/cad-server/src/cad_server/engine/README.md`, **Body retention**) is keyed by
each operation's parameters and the keys of the shapes it was given, and answers
a hit with the live object the first run made; its pressure tests are
`tests/python/packages/cad/engine/test_memo.py` and `test_bodies.py`, and a
change to it runs them first.

Those numbers come from one batch, measured once every change that moves them is
in the branch: on one machine with nothing else building, `main` and the branch side
by side on the same models, each on a daemon of its own (`CAD_ENGINE_DIR`), cold
and warm. The benchmarks are manual and write under `tmp/` (`scripts/bench/`); their
output is never committed.

A part is meshed at one tolerance, 0.25 % of its size and 28.5 degrees, by
`BRepMesh_IncrementalMesh` as it is (`engine/mesh.py`): no check before it, no
second pass, no repair. A change
to that opens its PR with what it does to the faces left unmeshed and the triangle
counts across the sample corpus, `main` against the branch; the engine's mesh tests
(`tests/python/packages/cad/engine/test_mesh.py`) assert the contract on small
fixtures.
