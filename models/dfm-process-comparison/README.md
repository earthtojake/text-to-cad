# One mounting tray, three manufacturing processes

Controlled design exercise using the existing `dfam-check` skill and the new
`sheet-metal-dfm` and `cnc-dfm` guided reviews. These are authored redesigns,
not outputs from an automatic optimization solver. Injection molding is not
part of this three-process experiment.

Every variant retains an 80 × 60 × 25 mm envelope and four Ø4.5 mm floor holes
at (±25, ±18) mm, with the underside at Z=0. Interior space changes; equal load
capacity is not established. Materials are illustrative process assumptions,
not measured material assignments: PLA, 5052-H32 sheet, and 6061-T6 billet.

| Variant | Measured geometry | Process rationale | Still unverified |
| --- | --- | --- | --- |
| Baseline | 0.8 mm walls, 3 mm floor | Common starting point | Load capacity |
| FDM | 2.4 mm walls/floor, four 8 mm triangular gussets | Addresses thin walls; upright build | Slicer, loads, layer adhesion |
| Sheet metal | 1.5 mm stock, R2 inside/R3.5 outside bends | Uniform section, two bends | Flat pattern, bend allowance, tooling, springback |
| CNC | 3 mm walls/floor, R3 roots | Less fragile walls; open-ended channel | Workholding, CAM, cutter reach, feeds, loads |

The CNC root fillets are optional transitions, not a mandatory cure for an
unmachinable corner. A flat end mill can produce a sharp floor-to-wall junction;
R3 roots may require corner-radius/ball tooling and extra finishing. Do not
confuse these roots with in-plane pocket corners. This comparison does not
claim cost or cycle-time optimization.

## Checks performed

- Reimported all four STEP exports: each is valid, one solid, correct envelope.
- Intersected exported solids with probes to measure floor/wall thickness.
- Confirmed four hole centers and diameters from actual circular STEP edges.
- Confirmed sheet bend radii and CNC root radius from exported edges.
- Ran `cadgen step inspect validate` on each export; reports are alongside the
  numerical checks in `reports/`.
- Ran the **existing** `skills/dfam-check/scripts/dfam_tool.py measure` on baseline
  and FDM STL with a 45° threshold. Both are watertight, one body. Sampled minimum
  wall thickness rose from **0.8 to 2.4 mm**, clearing the skill's generic FDM
  supported/unsupported wall defaults (1.2/1.6 mm). Sampling is not exhaustive.
- Both baseline and FDM have zero flagged overhang area upright; this redesign
  improves wall thickness, not the already-clear upright overhang result.
- Tested six axis-aligned FDM orientations. Upright: zero flagged area; upside
  down: 4,294.88 mm². This is a geometric heuristic, not slicer verification or
  proof of a globally optimal orientation.
- Visually reviewed CAD snapshots and the comparison figure. The figure uses
  real STL triangles with a depth buffer; colors only distinguish variants.

## Reproduce

Use the repository's cadgen/build123d environment, plus trimesh, numpy, rtree,
networkx, lxml and matplotlib for analysis/figure generation. From this folder:

```sh
for model in src/*.py; do python "$model"; done
python scripts/verify.py
python scripts/figure.py
```

From the repository root, run these for `baseline` and `fdm`:

```sh
python skills/dfam-check/scripts/dfam_tool.py measure models/dfm-process-comparison/STL/fdm.stl --angle-limit 45
python skills/dfam-check/scripts/dfam_tool.py orientations models/dfm-process-comparison/STL/fdm.stl --angle-limit 45
python -m cadgen.cli step inspect validate models/dfm-process-comparison/STEP/fdm.step
```

CAD exports and scratch images are regenerable and ignored. The share image is
`tmp/manufacturing-comparison.png`. Recorded JSON reports capture this run.

## Caption for Jake

Same mounting interface, three manufacturing approaches: FDM gets thicker walls
and gussets; sheet metal becomes uniform stock with two bends; CNC gets thicker
walls and optional rounded roots. The existing DfAM checker measured the print
version's minimum wall thickness increasing from 0.8 to 2.4 mm. Geometry checked;
strength, tooling, and production performance still need validation.
