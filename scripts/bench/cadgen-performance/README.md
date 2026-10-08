# Performance benchmarks

Manual commands for four distinct measurements: the edits an agent makes,
end to end; warm model execution in one interpreter; adaptive viewer loading;
and viewer lifecycle costs.

Run from the repository root after installing the development dependencies in
`CONTRIBUTING.md`. Use a disposable model copy and a dedicated store. Run only
one timed workload at a time; record the checkout, inputs, cache state, hardware,
and quality settings when comparing results.

Reports, logs, profiles and screenshots belong in ignored `tmp/` directories.
CAD inputs and generated geometry for these manual benchmarks belong under
`models/tmp/` or a scratch folder outside the checkout. These commands are not
automated tests and do not run in CI.
Automated tests generate their own fixtures independently of `models/`.

## Agent edits, end to end

`agent_edits.py` times what an agent waits for after each kind of edit: one
`python <model>.py --json --verbose` client per run, against a private warm
daemon and a dedicated store. An unmeasured forced rebuild of the top model
starts the daemon. Then, from a current baseline, each iteration runs `noop`;
`comment` (a comment appended to the leaf source); `leaf` (a dimension edit in
a leaf part, so the leaf and its parents rebuild) and `revert-leaf`; `parent`
(a parent-only edit, such as a placement literal) and `revert-parent`; and
`label` (a label-only edit) and `revert-label`. Each `--*-to` value is used by
one iteration, so every edit is new to the store and every revert returns to
sources it has built. Point it at a disposable copy of a project: it edits the
sources and restores them in `finally`.

```sh
./.venv/bin/python scripts/bench/cadgen-performance/agent_edits.py \
  --configuration main --model /tmp/bench/moonwatch/src/moonwatch.py \
  --store /tmp/bench/store --daemon-socket /tmp/bench.sock \
  --cadgen-src packages/cadgen/src --node-bin ~/.nvm/versions/node/v22.22.0/bin \
  --leaf-model /tmp/bench/moonwatch/src/lib/dial.py \
  --leaf-from 'INDEX_RAISE = 0.18' --leaf-to 'INDEX_RAISE = 0.19' --leaf-to 'INDEX_RAISE = 0.2' \
  --parent-from 'MOVT_Z_OFFSET), (1' --parent-to 'MOVT_Z_OFFSET + 0.01), (1' \
  --parent-to 'MOVT_Z_OFFSET + 0.02), (1' \
  --label-from 'label="moonwatch")' --label-to 'label="watch")' --label-to 'label="moonwatch_2")' \
  --report tmp/cadgen-performance/moonwatch-main.json --iterations 2
```

`--parent-*` and `--label-*` are optional (a single part has no parent).
Each run records its wall time; which models built, with each model's seconds
between its build-tree phases; the root's `--verbose` stages; the one-minute
load average around it; and the sha256 of every STEP under the project, so a
configuration that skips work can be checked for identical bytes. On a shared
machine, `--max-load 8` waits for other work to settle before each run.
`--compare A.json B.json` prints the medians of several reports side by side.
Compare checkouts with a store, socket and project copy each; `--cadgen-src`
selects the cadgen that runs.

## Warm model execution

`warm_build.py` times unchanged calls and geometry/placement edits in one Python
interpreter. Pass exact source substitutions for your disposable model; each
original string must occur once. For example, given `WIDTH = 20.0` and
`OFFSET_X = 0.0` in `models/tmp/performance/model.py`:

```sh
export PYTHONPATH="$PWD/packages/cadgen/src"
./.venv/bin/python scripts/bench/cadgen-performance/warm_build.py \
  --model models/tmp/performance/model.py \
  --store models/tmp/performance/store \
  --geometry-from 'WIDTH = 20.0' --geometry-to 'WIDTH = 21.0' \
  --placement-from 'OFFSET_X = 0.0' --placement-to 'OFFSET_X = 1.0' \
  --report tmp/cadgen-performance/warm.json --iterations 3
```

The command primes each edit before measuring it. Repeated
`--novel-geometry-to` and `--novel-placement-to` values measure distinct new
edits separately; use a fresh store to exclude previous runs. `--geometry-model`
and `--placement-model` select child sources when edits live outside the root.
`--child-daemon-socket` selects a dedicated caller-owned daemon; the default
uses transient child workers. See `--help` for child-pin checks and import timing.

The report records individual samples, output identities, stage events and
source fingerprints. The timing excludes root Python/kernel startup and browser
drawing. Preview publication is not first visible geometry. Source bytes and
timestamps are restored in `finally`; interruption or a failed build can leave
CAD output from the last edit, so rebuild before using that output.

## Viewer loading and lifecycle

Use an existing viewer serving disposable models, built from this checkout.
Follow `CONTRIBUTING.md` to build and start it. The commands open their own
Chromium instance and leave the server running. They currently target macOS
with Metal; process-memory probes use `ps`. Install Playwright in the viewer's
development dependencies, or point `PLAYWRIGHT_FROM` at its installed package.

`adaptive.mjs` measures default LOD loading, completed component publication,
orbit cadence and memory bounds. Supply the expected component and occurrence
counts; record whether the caller-owned display cache is cold or warm.

```sh
node scripts/bench/viewer-memory/adaptive.mjs \
  --url http://127.0.0.1:3245 --file assembly.step \
  --components 9 --occurrences 9 --cache-state 'warm display cache' \
  --out tmp/cadgen-performance/adaptive.json
```

The default limit is 180 seconds and 2 GiB of renderer memory. `--resize-to
1600x900` also checks viewport-driven reevaluation. Screenshots and failure
reports are written beside the report after grading.

`lifecycle.mjs` measures repeated same-tab switching, topology demand, selection,
orbiting, and buffer/worker release. Both files must be in the viewer catalog;
`--first-part` names a part in the first model.

```sh
node scripts/bench/viewer-memory/lifecycle.mjs \
  --url http://127.0.0.1:3245 --file repeated.step --other assembly.step \
  --first-part box_1 --out tmp/cadgen-performance/lifecycle.json
```

Optional `--animation-ms 5000` exercises a model with an animation sidecar.
`--edit-target`, `--edit-variant`, and `--edit-cycles 6` alternate two disposable
geometry-only STEP files under `models/` and restore the target afterward.
Browser frame intervals measure presentation cadence, not GPU completion.
Lifecycle readings include settling and explicit garbage collection; they do
not prove the absence of every long-session leak.

Run the viewer benchmark helpers' focused tests with:

```sh
node --test scripts/bench/viewer-memory/*.test.mjs
```
