# Benchmarks

Manual commands that measure cadgen and the CAD Viewer. None of them runs in
CI, and what they write goes under an ignored `tmp/` directory, never into the
tree (`AGENTS.md`). The three folders each have their own README:
[`cadgen-performance/`](cadgen-performance/README.md) (the edits an agent
makes, end to end; warm model execution), [`mesh-scoreboard/`](mesh-scoreboard/README.md)
(every solid of a STEP corpus scored on what a display mesh must have) and
[`viewer-memory/`](viewer-memory/) (viewer loading and lifecycle; its helper
units run in `scripts/test/test-js.sh`). The two scripts at this level are the
0.8.0 migration's measurements, below.

## The 0.8.0 migration measurements

The migration (identity by construction, files as exports, serial children)
is measured at every stage by the same three numbers, each one command: the
cold builds and the moonwatch edit loop compared between `main` and the
branch, interleaved; the cold moonwatch build; and the sample corpus built
and every exported STEP verified. Every number is wall-clock, so run one
command at a time on an otherwise idle machine, and compare runs made on the
same machine only.

### Setup, on a fresh Mac

```sh
git clone https://github.com/earthtojake/text-to-cad.git
cd text-to-cad
git checkout <branch>            # the migration branch; main stays local, for --base
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
scripts/bundle/bundle.sh --check  # the packaged runtime: the file tracer every build loads
source .venv/bin/activate         # or run each command below with .venv/bin/python
```

The venv's Python must be 3.11 or later, and Node 22 with npm on `PATH`:
`bundle.sh` builds the browser bundle with it, and `main`'s cadgen (0.7.21)
still exports meshes through it. `npm ci` is not needed; nothing here reads
the apps' `node_modules`. The two scripts find the venv themselves (the
activated one, else `.venv/`) and refuse to run without the built runtime.

### Compare main against the branch

```sh
scripts/bench/compare_commits.py --base main --head <branch> --rounds 2 \
  --models aft,nozzles,dial --edits --out final
```

About an hour on a four-core machine: the cold builds take a few minutes,
the edit loop about 25 minutes per side. The harness gives each commit a
detached worktree under the output directory with this checkout's built
runtime copied in, builds each model from that worktree's own sources and
models with the venv's Python, `PYTHONPATH` on the worktree's
`packages/cadgen/src`, a fresh store and no daemon, alternating base and head
with the order flipped each round, then runs the moonwatch edit loop
(`cadgen-performance/agent_edits.py`, on a disposable copy of each side's
`models/moonwatch`) for both sides, and removes the worktrees. It writes
`tmp/bench/final/`:

- `runs.jsonl`, one line per cold build, and `<side>-<model>-<round>.log`,
  that build's `--verbose` output;
- `edits-<side>.json`, `.out` and `edits-<side>-logs/`, the edit loop's
  report, output and per-run logs;
- `table.md`, the comparison, also printed: paste it into the stage's pull
  request comment.

What the numbers in `table.md` mean, all medians over the rounds:

- `wall`: the `python <model>.py --verbose` command, start to exit.
- `built`: cadgen's own total for the root model, from its `built ... in`
  line, else from the `generated <script> completed in` line (`main`'s cadgen
  0.7 prints only that one).
- `model code`: the seconds inside the model's own Python.
- `cadgen`: the rest of `built`: kernel, store, export. Both come from the
  `built ... in` line alone, so a side that prints none shows `—` there and a
  footnote under the table names what it did not report; a dash is no failure.
- `load`: the one-minute load average when the runs started; a side whose
  load is higher ran on a busier machine.
- `failures`: runs that exited non-zero or printed neither line; read their
  logs.
- `preview`, `done` and `saved`, per edit scenario: seconds into the root
  model's own run at which its source was ready (its preview is published
  then), at which it was done (`current` when nothing built) and at which its
  STEP was saved. Only the root's own events count; its children report too.
  `main` prints the STEP saved event before the root's done, the branch a
  `STEP saved <file> completed in` line after it. `—` where no run of the
  scenario has the mark (a run that writes no file saves none).
- The edit loop's own table: the median wall per scenario, `noop` (nothing
  changed), `comment` (a comment in a leaf source), `leaf` (a dimension in a
  leaf part, so the leaf and its parents rebuild), `parent` (a placement
  literal in the parent alone), `label` (a label alone) and each `revert-*`
  (back to sources the store has built). The branch restores those, outcome
  `current` with nothing built and the STEP files written back to the
  baseline's bytes, where `main` rebuilds them; the loop reports a revert on
  the branch that builds or leaves a file unlike the baseline's as a problem
  and leaves it out of the medians.

`--models` takes the names `aft`, `nozzles`, `dial` and `moonwatch`, or a model
script's path relative to the checkout; `--max-load L` makes the edit loop
wait for the load average to fall below `L` before each run; `--out` is a name
under `tmp/bench/` or a path. `scripts/bench/compare_commits.py --help` has
the rest.

### The cold moonwatch build

```sh
scripts/bench/compare_commits.py --base main --head <branch> --rounds 1 \
  --models moonwatch --out moonwatch
```

One cold build of the whole watch per side, each about ten minutes on a
four-core machine, into `tmp/bench/moonwatch/`: the `moonwatch` row's `wall`
and `built` are the number. What runs, per side, is `python moonwatch.py
--verbose` from that side's `models/moonwatch/src` with `CADGEN_CACHE_DIR` on a
fresh directory, `CADGEN_DAEMON=0` and `PYTHONPATH` on its
`packages/cadgen/src`. Without a daemon, `main` still builds the children
through a four-slot pool; a cadgen that builds its children serially inside
the parent's body reports the serial number the migration's brief asks for.
`--rounds 2` doubles the time and gives medians.

### The corpus verify

```sh
scripts/bench/corpus_verify.py
PROJECTS=radial,hypercar scripts/bench/corpus_verify.py   # a subset
```

Hours for the whole corpus (`tendon_hand` alone has over a hundred models,
`radial` an hour of builds); `PROJECTS` (or `--projects`) picks projects. The
script copies each project's tracked files under the run directory, so
nothing built earlier and no committed output is read and the builds' outputs
land in the copy; runs every model script under `models/<project>/src` (at
most two levels down, nothing under `lib/`, no `__init__.py` or
`conftest.py`) one at a time with this checkout's cadgen, `CADGEN_DAEMON=0`,
into one fresh store; then verifies every STEP the builds' records name
against the tree it was written from (`cadgen.store.exports.verify_document`,
the verify a build's own pool job runs), `--jobs` files at a time. It writes
`tmp/bench/corpus/<UTC timestamp>/` (`--out` or `CORPUS_OUT` names it):
`models/` (the copies and their outputs), `store/`, `logs/<project>/<script>.log`,
`build.jsonl` (status and seconds per script), `verify.jsonl` (result per
file) and `summary.md`, the summary it prints:

- `models ... built`: scripts run, and how many exited zero; a build that
  failed or ran past `--timeout` is listed with its log.
- `STEP files`: the STEP outputs the builds' records name.
- `verified`: files that hold the tree they were written from.
- `failed`: each file that does not, with why: `differs` and what differs,
  `file changed` (its bytes are no longer the record's), or the error.
- `written plain`: files written without names, verified by their
  occurrences alone.
- `seconds`: building, verifying, and both; then each model's own seconds.

The exit status is non-zero when any build or verify failed, so the command
is the gate.
