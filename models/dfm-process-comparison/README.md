# One mounting tray, four manufacturing processes

Controlled design exercise using the existing `dfam-check` skill and the new
the `dfm` skill's sheet-metal, CNC and injection-molding guided reviews. These are authored redesigns,
not outputs from an automatic optimization solver.

Every variant retains an 80 × 60 × 25 mm envelope and four holes that are Ø4.5 mm at the underside datum
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

- Reimported all five STEP exports: each is valid, one solid, correct envelope.
- Intersected exported solids with probes to measure floor/wall thickness.
- Confirmed four hole centers and diameters from actual circular STEP edges.
- Confirmed sheet bend radii and CNC root radius from exported edges.
- Ran the **existing** `skills/dfam-check/scripts/dfam_tool.py measure` on baseline
  and FDM STL with a 45° threshold. Both are watertight, one body. Sampled minimum
  wall thickness rose from **0.8 to 2.4 mm**, clearing the skill's generic FDM
  supported/unsupported wall defaults (1.2/1.6 mm). Sampling is not exhaustive.
- Both baseline and FDM have zero flagged overhang area upright; this redesign
  improves wall thickness, not the already-clear upright overhang result.
- Tested six axis-aligned FDM orientations. Upright: zero flagged area; upside
  down: 4,294.88 mm². This is a geometric heuristic, not slicer verification or
  proof of a globally optimal orientation.
- Ran the new `skills/dfm/scripts/mold_tool.py measure --pull z`
  on the injection and baseline STL, and `pulls` on the injection STL
  Injection: no
  zero-draft wall area, mean wall draft 1.005° over 6,590 mm² of wall, no
  straight-pull undercut candidates for Z; an X pull would trap 7,499 mm² and a
  Y pull 1,729 mm². Cone-sampled thickness: median 2.4 mm, p05 1.7 mm on the
  ribs, minimum 0.97 mm at rib edges where the cone reads under the true wall.
  Baseline: 6,233 mm² of zero-draft wall, median 3.0 mm, p05 0.8 mm. Per-facet
  reading; the pooled faces list merges parallel walls that share a normal.
  The injection STL is not watertight as exported, so its volume is unreported.
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
```

CAD exports and scratch images are regenerable and ignored. The share image is
`tmp/manufacturing-comparison.png`. Nothing from a run is committed: rerun the
commands above to reproduce the numbers this README quotes.


## Injection-molding fourth process

Concept assumes an untextured, unfilled thermoplastic (resin grade unspecified),
Z pull and parting near the bottom perimeter. These are design assumptions, not
supplier-approved limits. The floor is 2.4 mm; the two inner and two outer tall
wall surfaces have 1° draft verified from STEP surface normals. Opposing draft
makes walls taper (about 2.36 mm above the floor to 1.57 mm at the rim), so this
is not a uniform-wall claim. Four triangular ribs have nominal 1.2 mm feet and
1° tapered side faces. The holes open upward with 1° draft: Ø4.5 at Z=0, about
Ø4.584 at the floor top. Mounting centers and the underside datum are preserved.

Geometry assertions check wall draft, sampled rib widths, floor thickness,
envelope and datum hole diameters. The STEP validator checks solid validity.
The thin ribs illustrate reducing bulk at junctions compared with the FDM
gussets; no sink or strength performance was simulated. Rib/root fillets are
not modeled yet and need review alongside stress and local wall transitions.
Toolmaker review is still required for resin, texture, shrinkage, parting and
shutoffs, gate/vent locations, cooling, ejection and the complete withdrawal
path. No undercut-free verdict or mold-flow result is claimed.
