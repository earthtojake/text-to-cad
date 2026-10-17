# The mesh scoreboard

How well cadgen meshes, measured: every solid of a STEP corpus, scored on the
properties a display mesh must have (`packages/cadgen/README.md`, law 1) and on
cost. A pull request that changes how a part is meshed -- the mesher and its
checks and repairs (`cadgen/_internal/tessellate.py`, `cadgen/_internal/face_fallback.py`),
or `cadgen/tessellation_policy.py` -- opens
with this table for `main` and the branch (`CONTRIBUTING.md`, "Performance
changes"). It is a manual benchmark: its output goes under `tmp/` and is never
committed, and it does not run in CI. The CI contract test
(`tests/python/packages/cadgen/test_mesh_contract.py`) asserts the same
properties on small fixtures it builds itself; this scoreboard says how well
they hold on real models.

## Scoring

`score.py` meshes each solid once and writes one JSON row per solid. The cadgen
it scores is the one `PYTHONPATH` names, so two checkouts are scored by one
script:

```sh
export PYTHONPATH="$PWD/packages/cadgen/src"
./.venv/bin/python scripts/bench/mesh-scoreboard/score.py --mesher cadgen \
  --out tmp/mesh-scoreboard/branch.jsonl models/examples/STEP/*.step models/moonwatch/STEP/*.step
PYTHONPATH=/path/to/main-worktree/packages/cadgen/src \
./.venv/bin/python scripts/bench/mesh-scoreboard/score.py --mesher cadgen \
  --out tmp/mesh-scoreboard/main.jsonl models/examples/STEP/*.step models/moonwatch/STEP/*.step
./.venv/bin/python scripts/bench/mesh-scoreboard/score.py --mesher occt \
  --out tmp/mesh-scoreboard/occt.jsonl models/examples/STEP/*.step models/moonwatch/STEP/*.step
```

`--mesher occt` scores OCCT's `BRepMesh` alone at the same tolerances: the
baseline, and the triangle and time budget a verified mesh is compared with.
The corpus is whatever STEP files are passed; the sample projects under
`models/` (built first, with their own `python <model>.py`) are the one used for
the table in a pull request, named in it. Score one mesher at a time on an
otherwise idle machine; the `seconds` column is wall time on one core.

Each row carries: the file, the solid's index, its face count, the BREP's own
open edges (`free`: an open boundary every mesher shares, so a solid with any is
not scored on volume), the absolute deflection `d`, and the mesher's
`seconds`, `triangles`, `open` (odd edges of the welded mesh: cracks, holes,
T-junctions), `widest` (the widest crack between two faces, in `d`), `named`
(faces the body names as unmeshed), `empty` (faces at least `d²` in area left
silently empty), `area_off` (faces whose area is off the exact by over 1%),
`volume_error`, `dev_off` and `dev_worst` (faces whose sampled triangles sit
more than `2 d` off their exact surface, and the worst distance in `d`),
`folded` (sampled triangles whose facet points against the surface) and
`needles` (triangles with an angle under half a degree). A mesher that raises on
a solid gets an `error` row.

## The table

```sh
./.venv/bin/python scripts/bench/mesh-scoreboard/summarize.py \
  main=tmp/mesh-scoreboard/main.jsonl branch=tmp/mesh-scoreboard/branch.jsonl \
  occt=tmp/mesh-scoreboard/occt.jsonl
```

One column per JSONL, totals by default (`--by file` for a row per corpus
file). Every cell is `open-edge solids / cracks over 1 d / silent empty faces /
faces off area / faces off surface / folded / needles / errors`, then triangles
and seconds. The first seven are correctness and every one of them should be
zero; the table names any that grew as a regression, and a regression merges
only with the repository owner's explicit approval. Triangles and seconds are
cost: a verified mesh is expected within 1.3× of OCCT's time on the same corpus.
