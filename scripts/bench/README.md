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
.venv/bin/python scripts/bench/corpus_bench.py --model tom       # one; repeat --model for more
```

A model in `corpus.json` is its project folder (`root`, from the repository), the
folder its builds run from (`cwd`), the folders put on `PYTHONPATH` beside
cadgen's (`pythonpath`), its `targets` (`script.py`, as `python script.py` builds
it, or `script.py::model`), its document (`xbf`: where the batch saves the model its stem names), one `edit` (`{file, from, to}`,
`from` found exactly once in `file`), the inputs a build reads that are never
committed (`needs`: tom's vendor STEP) and a `note`. The models, smallest first:
`l_bracket`, `planetary_gear`, `qdd`, `motorbike`, `case`, `juno`, `movement`,
`tom`, `hypercar` and `f1`, all from `models/`. `--dry-run` checks every key,
that each file is there and each edit's `from` occurs once, and that the
interpreter imports this checkout's cadgen (`--cadgen-src`; not the venv's
editable install), and runs nothing.

Each model is copied into the batch's folder without its `XBF/` (an APFS clone on
macOS), so the checkout is never written. In the copy, the model its `xbf` stem names
declares that document (`@xbf(out=...)` above its `@model`), so each build saves it and
a restart takes it, as the old engine reloaded its store after a restart: the restart
row compares like with like. It is built on an engine daemon of its own
(`CADGEN_ENGINE_DIR`: a folder per model under `--engine-dir`, emptied first;
telemetry off), step by step:

- `cold`: a fresh daemon, no xbf to take;
- `noop`: the same build, warm;
- `edit`: the configured edit, built;
- `revert`: the file's original bytes, built;
- `restart`: the daemon stopped and the unchanged model built again, its xbf taken;
- `restart-cold`: the daemon stopped and the xbf deleted, the model built again: a
  restart with nothing to take;
- `serve`, `mesh-cold`, `mesh-warm`, `structure`: the document served (`cadgen
  serve`), every part meshed on the server's pool (`POST /api/doc/<id>/mesh`), again
  with its meshes dropped, and the structure a page reads first (`export`, the
  document saved by `cadgen export <id>`, only when a build left none);
- `snapshot-first`, `snapshot`: `cadgen snapshot --json` of the document, twice.

A build runs as `python script.py` asks for it (`cadgen.engine.api.build_script`)
in a process of its own, so its wall is what an agent waits for, interpreter start
to exit. Its row adds the engine's report, summed over the models it built: the
timings, memo hits and misses, bodies run, replayed and loaded, whether it took its
xbf whole (and if not, why), the files written and kept with their bytes, the
worker's memory after it (`cadgen status --json`) and the load average before it.

The batch writes `tmp/bench/corpus-<time>/` (`--out` for another): `rows.jsonl`, a
row per step appended as the step ends (the first says what ran: the commit, the
cadgen, the interpreter, the machine); `table.md`, a line per model, rewritten after
each; and the snapshots. A failed step is a row too, with its error, and ends its
model. `--keep` keeps the work copies.

## Main against this branch

`compare.py` sets a batch beside the old engine's numbers, model by model:

```sh
.venv/bin/python scripts/bench/compare.py tmp/bench/corpus-<time>/rows.jsonl [more rows.jsonl ...] \
  --out tmp/bench/compare.md
```

The new side is the median of each model's `cold`, `noop` and `edit` walls over
the batches given, and its xbf's size and write time. The old side is
`old-engine-numbers.json`, kept by hand: what #568's store engine measured before the
xbf engine (2026-10-19, at 830f3ae86, a 0.8.0 branch with main through 0.7.24 merged, not
a main release; on the maintainer's machine, at load 7–10), each a range of
seconds or the STEP's size, with the note it was recorded in and the words that say
it. Nothing here runs the old engine. tom, hypercar and juno have numbers; every
other model, and every measure missing, says "no old number; rebuild on main to
fill", and filling one is a build of that model on `main`, recorded in the file
with its source. The table has a row per model and measure, old beside new, and the
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
viewer's own scene code, `@text-to-cad/core`'s headless renderer, which
`scripts/bundle/bundle.sh` builds into cadgen's `_runtime/browser`
(`CADGEN_BROWSER_RUNTIME_DIR` names another): the bench loads it in a headless
Chromium and drives it itself. Per picture pair it prints the silhouettes' IoU, the
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
