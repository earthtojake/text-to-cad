# Benchmarks

Manual commands that measure the viewer's pictures against OCCT's and the manufacturing
checks. None of them runs in CI:
what they write goes under an ignored `tmp/` folder, never into the tree
(`AGENTS.md`), and only their pure helpers are tested
(`tests/python/global/test_bench_helpers.py`). Performance numbers come from one
batch, run once every change it measures is in the branch, on a quiet machine:
numbers taken under other work's load, or by agents benching beside each other,
do not compare.

## Viewer against OCCT, mode by mode

```sh
PYTHONPATH=packages/cad/src .venv/bin/python scripts/bench/occt_parity.py \
  --doc motorbike=models/motorbike/XBF/motorbike.xbf --out tmp/bench/occt-parity/now
```

`occt_parity.py` measures how alike the viewer and OCCT draw an `.xbf`'s regular
display modes. Each `--doc NAME=PATH` (an `.xbf`, built first) is drawn in Solid,
Shaded, Parts, X-ray, Hidden line and Wireframe at iso and front (`--modes`,
`--cameras`, `--size`) twice, both from the engine daemon's meshes
(`CAD_ENGINE_DIR` picks the daemon): by OCCT, whose look is the reference
(`cad/engine/render/look.py`) and which `cad <type> snapshot` draws with; and by the
viewer's own scene code, `@cad/core`'s headless renderer, which the bench
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
under 1. The bench's `--preview` adds its internal OCCT photographic rig at each camera
and the viewer's with its job's `"preview": true`; its studio is
no flat backdrop, so its colour difference is measured where OCCT's picture leaves
its own studio drawn without the model, and its IoU is n/a. `--only chromium` keeps
the OCCT pictures already there while the viewer's side is tuned (`--only occt`, the
viewer's). OCCT's offscreen drawing is proven on macOS; on Linux it needs an X
server (Xvfb on a machine with no screen).

## Manufacturing checks on real parts

```sh
.venv/bin/python scripts/bench/dfm_bench.py --root models --limit 40                      # every process
.venv/bin/python scripts/bench/dfm_bench.py --root "$KICAD_3DMODELS" --limit 60 --process printing
.venv/bin/python scripts/bench/dfm_bench.py --dry-run --root models                           # the files, smallest first
```

`dfm_bench.py` runs `cad.step.dfm` for each process (`cnc`, `sheet`, `molding`, `printing`, or the
`--process` given) on every STEP file under each `--root`, smallest first, `--limit` of them, in this
process (the checkout's environment holds both integrations). A worktree holds no built model, so point
`--root` at a checkout whose models are built, or at any folder of STEP files (KiCad's 3D models). It
writes `tmp/bench/dfm-<time>/rows.jsonl` (each check's wall time, `ok`, findings by severity, failing rule
ids, families not measured, faces and parts; a check that raised records its error) and `table.md`, per
process: parts, median, p95 and max seconds, what raised or could not measure, and the most frequent
failing rules. Its table and file order are the pure helpers the global suite tests.

## The skills, A/B

`skill_ab.py` lays out an A/B test of the skills: the same tasks done once with the skills of a Git
ref and once with the working tree's, each by a fresh agent that reads only its own copy.

```sh
.venv/bin/python scripts/bench/skill_ab.py --base main                    # every task
.venv/bin/python scripts/bench/skill_ab.py --base main --task cad-part    # one; repeat --task for more
```

It writes one folder per task and skill set under `tmp/skill-ab` (`--out` names another): a copy of
the skills, the task's fixtures, an `env.sh` for a server of the run's own, and a `BRIEF.md` to hand
an agent. It runs no agent and grades nothing. `runs.tsv` says which folder had which skills and what
each task expects; keep it from the agents. The tasks are `skill_ab/tasks/*.md` (a request and its
objective answer) and their fixtures `skill_ab/fixtures/`; a STEP a task needs is built from its
model when the runs are laid out, never committed. How to run and grade one is
[Writing a skill](../../docs/contributing/writing-a-skill.md#test-a-large-change-ab).
