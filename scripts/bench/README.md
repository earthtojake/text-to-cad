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

## The PCB corpus and its tasks

How well an agent does PCB work, measured on real boards: `pcb_corpus.json` names the projects,
`pcb_fetch.py` fetches them, `pcb_tasks.json` names the tasks, and `pcb_bench.py` makes a run folder per
task and grades what an agent left in it. Nothing of it runs in CI or is committed: the corpus is
downloaded into the ignored `tmp/pcb-corpus/`, runs go under `tmp/pcb-bench/`.

```sh
.venv/bin/python scripts/bench/pcb_fetch.py --check          # the manifest, checked (no network)
.venv/bin/python scripts/bench/pcb_fetch.py                  # every project (--project NAME, --tier small)
.venv/bin/python scripts/bench/pcb_bench.py tasks            # the task file, checked against the manifest
.venv/bin/python scripts/bench/pcb_bench.py prepare --task ecc83-reconnect --runs 3
.venv/bin/python scripts/bench/pcb_bench.py check tmp/pcb-bench/runs/w1a2b3c4d5e   # one JSON verdict a folder
.venv/bin/python scripts/bench/pcb_bench.py selftest         # every task: fails seeded, passes its reference fix
```

**The corpus.** An `upstream` project is a KiCad project on GitHub, pinned to a full commit sha (a tag is
resolved to its commit, and `ref` keeps the tag's name): the files it needs to open (`.kicad_pro`, every
sheet, the board, the project's own library tables and libraries, its rules), each with its sha256 and
size, none over 10 MB; 3D models, gerbers and images are not fetched. A file is kept only when its bytes
hash to the manifest's, lands by rename, and is fetched once (a second run keeps it). Paths are relative
to the project's `root` in its repository; one with `..`, an absolute one, or one through a symlink is
refused. Beside each project the fetch writes `SOURCE.md` (repository, commit, folder, licence) and the
licence file itself. The manifest takes open licences only, by SPDX id: a non-commercial (NC),
no-derivatives (ND) or unlicensed design is refused. A `build` project is one of this repository's ECAD
samples: its tracked files are copied to `tmp/pcb-corpus/<name>/` and its build runs there, never in
`models/`, with an engine, state and cache of the corpus's own (`tmp/pcb-corpus/.runtime`), whose server
the fetch starts with the checkout's cad and stops once the builds are done; it is built again only when its
sources change. KiCad's stock libraries come from KiCad.app or the samples' variables, as their READMEs say.

| Project | Tier | Source | Licence | Format | Copper | Parts | Size |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ecc83` | small | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20241229 | 2 | 15 | 0.4 MB |
| `interf_u` | small | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20241229 | 2 | 25 | 1.3 MB |
| `easyduino_nano` | small | Hanqaqa/Easyduino | CERN-OHL-P-2.0 | 20260206 | 4 | 31 | 0.7 MB |
| `stackchan_pantilt` | small | stack-chan/stack-chan v2.0.1 | Apache-2.0 | 20221018 | 2 | 39 | 0.9 MB |
| `pic_programmer` | small | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20260206 | 2 | 63 | 1.1 MB |
| `complex_hierarchy` | small | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20260206 | 2 | 68 | 1.1 MB |
| `piantor_left` | medium | beekeeb/piantor | GPL-3.0-only | 20211014 | 2 | 36 | 2.1 MB |
| `multichannel` | medium | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20241229 | 2 | 114 | 2.6 MB |
| `bitaxe_ultra` | medium | skot/bitaxe | CERN-OHL-S-2.0 | 20221018 | 4 | 137 | 2.2 MB |
| `kit-dev-coldfire-xilinx_5213` | medium | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20260206 | 4 | 160 | 4.1 MB |
| `openair-max` | medium | KiCad/kicad-source-mirror 10.0.8 | CC-BY-SA-4.0 | 20241229 | 4 | 210 | 3.4 MB |
| `macropad` | medium | `models/electronics/macropad` (build) | MIT | 20261031 | 2 | 73 | built, ~30 s |
| `eurorack_lfo` | medium | `models/electronics/eurorack_lfo` (build) | MIT | 20261031 | 2 | 76 | built, ~30 s |
| `cm5_minima` | large | KiCad/kicad-source-mirror 10.0.8 | CERN-OHL-S-2.0 | 20250513 | 6 | 112 | 5.2 MB |
| `bms_c1` | large | libresolar/bms-c1 | CERN-OHL-W-2.0 | 20241229 | 4 | 210 | 3.7 MB |
| `tiny_tapeout` | large | KiCad/kicad-source-mirror 10.0.8 | Apache-2.0 | 20241229 | 4 | 309 | 6.7 MB |
| `hackrf_one` | large | greatscottgadgets/hackrf v2026.01.3 | CERN-OHL-P-2.0 | 20211014 | 4 | 437 | 6.3 MB |
| `orbit_clock` | large | `models/electronics/orbit_clock` (build) | MIT | 20261031 | 4 | 182 | built, ~40 s |
| `pinball` | large | `models/electronics/pinball` (build) | MIT | 20261031 | 4 | 250 | built, ~20 min |

**The tasks.** Each names its project, a `kind` (`fix_drc`, `fix_erc`, `renet`, `move_part`,
`route_net`, `review`, `build_edit`), the `prompt` a person would write (no word of a benchmark), the
faults seeded before the run (`mutations`: text edits of the fetched files: delete an item by its own
uuid, strip a net's tracks and vias, move a part, edit inside one item), the `checks`, a `reference` fix
and the `proof`. `pcb_tasks.json`'s `about` names every field; `pcb_bench.py tasks` lists them. A check
reads the run folder with the library (`cad.kicad_pcb.read`, `cad.kicad_sch.read`) and runs KiCad's DRC
and ERC on it and on the untouched corpus project, so "no worse" is measured kind by kind against the
original board: no error-severity DRC type and no unconnected count above the original's, no ERC error
or warning code above the original's (KiCad caps a type at 199 findings). Connections are compared pad
by pad (schematic: as sets of pins), with a rename where the task asks for one; parts are where they were
to 0.01 mm unless the task moves them. A review is graded by whether its file names each seeded fault
(any of a fault's patterns) and leaves the design files as prepared. A `build_edit` task is graded on its
sources built again in a scratch copy (every file of the run folder but what the corpus build wrote), so
a board edited by hand instead of its scripts does not pass. DRC, ERC and the rebuilds run in an
environment of the bench's own, `tmp/pcb-bench/.runtime` (the `cad[kicad]` environment made as
`scripts/test/test-kicad.sh` makes the suite's), never the person's engine or installation.

`prepare` copies the project into `<out>/<run>/`, applies the mutations and writes `PROMPT.md`; `<run>`
is a hash of the task and run id, so the path says nothing of the task. What the grader needs (task, run
id, corpus folder, every file's hash as prepared) is in `<out>/<run>.json`, beside the folder, never in
it. `check` prints one verdict a folder, `{"task", "run", "pass", "checks": [{"check", "pass", "detail"}],
"seconds"}`, and exits 1 when any fails. `selftest` proves the task file: each task prepared twice, the
seeded copy must fail and the copy given its reference fix must pass (a `refill` in a reference has KiCad
fill the pours again, through its IPC API: run it outside a sandbox that refuses sockets).

**A blind A/B.** Launching agents is the harness's, not this script's:

1. Fetch the corpus once, then `prepare` each task with the same run ids for both arms' pairs
   (`--run a1 --run b1 ...`): one folder an arm and a pair, identical but for the name.
2. Give each agent its run folder alone, as its working folder, at a neutral path: when the agent can see
   the folder's parent (the sidecar `.json` is there), copy the folder, keeping its name, into a fresh
   empty parent such as `/tmp/work/<random>/`, and copy the sidecar beside it only to grade it. Nothing in
   a path or a prompt names the arm, the task or the benchmark.
3. Give each run a private engine: its own `CAD_ENGINE_DIR`, `CAD_STATE_DIR`, `CAD_CACHE_DIR` and
   `CAD_LAUNCHER_DIR` outside the run folder, `CAD_UPDATE_CHECK=0`, the arm's own cad's server started
   there (`cad server start`, as `pcb_fetch.py` starts the checkout's), and telemetry off (`DO_NOT_TRACK=1`,
   `CAD_TELEMETRY=0`).
4. Launch the two runs of a pair together, on the same machine, with the same model, effort and limits;
   keep the arm-to-folder map in the harness's own file until every verdict is in.
5. `check` every folder (the grader sees only opaque names), then compare per task across pairs (a sign
   or McNemar test on the paired pass/fail), with the harness's wall time and tokens beside it.

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
