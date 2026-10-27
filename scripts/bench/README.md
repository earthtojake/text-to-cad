# Benchmarks

Manual commands that measure cadgen and the CAD Viewer. None of them runs in CI:
what they write goes under an ignored `tmp/` folder, never into the tree
(`AGENTS.md`), and only their pure helpers are tested
(`tests/python/global/test_bench_helpers.py`). Performance numbers come from one
batch, run once every change it measures is in the branch, on a quiet machine:
numbers taken under other work's load, or by agents benching beside each other,
do not compare.

## The corpus batch

`corpus_bench.py` builds each model in `corpus.json` with the xbf engine, cold to
warm, and times every step:

```sh
.venv/bin/python scripts/bench/corpus_bench.py --dry-run         # the config and the interpreter, checked
.venv/bin/python scripts/bench/corpus_bench.py --max-load 16     # every model; each step waits for load <= 16 and no other busy cadgen build
.venv/bin/python scripts/bench/corpus_bench.py --model l_bracket # one; repeat --model for more
```

A model in `corpus.json` names its project folder (`root`, relative to this repository),
working folder (`cwd`, within that project), import folders (`pythonpath`, within the
project), and `targets`: Python scripts relative to `cwd`. Each script runs with its
own `__main__` control flow in a separate client process. `document` selects a model
that those calls actually built, as `script.py::function` relative to `cwd`. It does
not execute that function. The selected report supplies the document's actual id;
missing, failed or ambiguous selections fail the step. `xbf` names a separate export
destination, independent of the selected function's name. `edit` is `{file, from, to}`,
with `from` occurring exactly once; `needs` lists required inputs. `note` describes the
case. `comparison_note` records a workload difference that prevents a build speedup
comparison with the recorded baseline.

The models, smallest first, are `l_bracket`, `planetary_gear`, `qdd`, `motorbike`,
`case`, `juno`, `movement`, `tom`, `hypercar` and `f1`. Tom stays in its own repository:
its default root is `../tom-cad`. A worktree or isolated clone may have no such sibling;
give `--config` a copy of `corpus.json` with the relative path to the external checkout
or copied checkout. `--dry-run` checks configuration, files, edits and the selected
interpreter's cadgen import (`--cadgen-src`), without building anything. It does not
infer calls from source or promise that a script calls the selected model.

Each project is copied into a fresh output folder. Source stays unchanged except for
the configured edit and its revert. Local Git metadata, virtual environments,
`node_modules`, scratch directories and XBF/DXF outputs are excluded at every level;
pinned inputs such as `STEP/imported` are retained. A symlink is refused, so a copied
edit or output cannot write through it into the original checkout. Files use APFS
clones where available. An existing output folder is refused.

Every model gets private engine, state, cache and launcher directories. The door is
under a fresh batch folder in `--engine-dir`; the other three directories are under
`<out>/runtime/<model>`. The engine uses a free port, no standby worker, telemetry off,
and a browser stub that records any attempted launch in `<out>/browser-requests.log`.
The batch never stops another batch's engine or clears its cache. Steps are:

- `cold`: a fresh daemon and empty private document cache;
- `noop`: the unchanged script, on the same daemon;
- `edit`, `revert`: the configured edit, then the file's original bytes;
- `restart`: stop successfully, then run with the private document cache retained;
- `restart-cold`: stop successfully, remove only that private cache's `documents/`,
  then run again. Bytecode stays warm; declared or exported files are never cache inputs;
- `export`: explicitly export the selected document id to `xbf`, recording bytes and
  translation time separately from build walls;
- `serve`, `mesh-cold`, `mesh-warm`, `structure`: serve that model id, mesh every part
  (`POST /api/doc/<id>/mesh`), mesh again after dropping those meshes on the now-warm
  pool, then read the page's structure. No file is substituted for the model document;
- `snapshot-first`, `snapshot`: draw that document id twice with `cadgen snapshot --json`.

The small measurement driver runs the target with Python's `runpy` and records reports
returned by `api.build_script` when the script's explicit model calls reach it. It
introduces no model call, decorator or export. A build wall covers interpreter startup,
the whole script and report capture; `wall_api` sums its calls' engine round trips.
Rows include timings, memo counts, bodies run/replayed/loaded, cache source/reason,
declared files and worker memory. HTTP and command result shapes are checked; a failed
step records its error and ends that model. Failure to stop preserves its working files.

The batch writes `tmp/bench/corpus-<time>/` (`--out` selects another fresh folder):
`rows.jsonl`, appended after every step; `table.md`, updated after each model; snapshots;
and private runtime state. The first row records the commit, interpreter, platform and
configuration. `--keep` retains source copies with the edit reverted. The normal exit
stops each private daemon. These are manual measurements, not CI tests; the global
suite tests the pure configuration, copy, selection, aggregation and comparison helpers.

## Recorded store-engine baseline against this branch

`compare.py` sets a batch beside the old engine's numbers, model by model:

```sh
.venv/bin/python scripts/bench/compare.py tmp/bench/corpus-<time>/rows.jsonl [more rows.jsonl ...] \
  --out tmp/bench/compare.md
```

The new side is the median of each model's `cold`, `noop` and `edit` walls over
the batches given, and its explicitly exported xbf's size and write time. Current
build walls exclude the benchmark's export; the recorded store-engine walls include
their original work, so those boundaries must accompany any performance claim.
Juno's current script also calls its 28 link models, whereas its baseline built the
robot alone: its build speedup is withheld and the difference is printed. The old side is
`old-engine-numbers.json`, kept by hand: what #568's store engine measured before the
xbf engine (2026-10-19, at 830f3ae86, a 0.8.0 branch with main through 0.7.24 merged, not
a main release; on the maintainer's machine, at load 7–10), each a range of
seconds or the STEP's size, with the note it was recorded in and the words that say
it. Nothing here runs the old engine. tom, hypercar and juno have numbers; every
other model, and every missing measure, says "no recorded old number". The command
never runs old code to fill gaps. The table has a row per model and measure, old beside new, and the
speedup (old over new; for the file, how many times smaller the xbf is than the
STEP), then the sources.

## Viewer against OCCT, mode by mode

```sh
PYTHONPATH=packages/cadgen/src .venv/bin/python scripts/bench/occt_parity.py \
  --doc motorbike=models/motorbike/XBF/motorbike.xbf --out tmp/bench/occt-parity/now
```

`occt_parity.py` measures how alike the viewer and OCCT draw an `.xbf`'s regular
display modes. Each `--doc NAME=PATH` (an `.xbf`, built first) is drawn in Solid,
Shaded, Parts, X-ray, Hidden line and Wireframe at iso and front (`--modes`,
`--cameras`, `--size`) twice, both from the engine daemon's meshes
(`CADGEN_ENGINE_DIR` picks the daemon): by OCCT, whose look is the reference
(`cadgen/engine/render/look.py`) and which `cadgen snapshot` draws with; and by the
viewer's own scene code, `@text-to-cad/core`'s headless renderer, which the bench
builds at the start of each run (`scripts/bundle/lib/snapshot_runtime.sh`, into the
ignored `tmp/bench/snapshot-page`; the wheel does not carry it), then loads in a
headless Chromium and drives itself. Per picture pair it prints the silhouettes' IoU, the
median and 95th-percentile CIE76 colour difference over the pixels both give the
model, and, for the line modes, the share of inked pixels that differ visibly; and
it writes each picture, `metrics.json`, `table.json` and a contact sheet per
document (viewer, OCCT and the difference, 1800 px wide). Its hue check reads the
metal faces that face up (normal within 25 degrees of +Z, metallic 0.5 or more, the
authored colour's chroma 10 or more) in each Solid iso picture and prints, per
renderer, how far their CIELab hue turns from the authored colour's and the share of
its chroma they keep: a washed-out top face is a hue near 0 at a chroma ratio well
under 1. `--preview` adds Preview at each camera, OCCT's as `cadgen snapshot
--preview` draws it and the viewer's with its job's `"preview": true`; its studio is
no flat backdrop, so its colour difference is measured where OCCT's picture leaves
its own studio drawn without the model, and its IoU is n/a. `--only chromium` keeps
the OCCT pictures already there while the viewer's side is tuned (`--only occt`, the
viewer's). OCCT's offscreen drawing is proven on macOS; on Linux it needs an X
server (Xvfb on a machine with no screen).
