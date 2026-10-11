# Lighten it (`topology`, lite)

It answers "where can I take material out", "what shape should this bracket be" and "make it
lighter but keep it stiff". It starts from the part as a block of material (the design space),
holds it and loads it as a static study does, and works out which material carries the load and
which can go. The plain word is Lighten it.

**It is a lite solver. Its limits are written into every result** (`analysis.limits`, the
verdict's "Lite · " and its Details): linear elastic and one material, a fixed design mesh of
linear tetrahedra (members thinner than about three elements cannot form, and the surface is a
smoothed staircase), a verification solve on the kept design elements whose stress is a guide, and
loads that stay where they are (no self-weight). The answer is a concept shape to rebuild in CAD,
not a finished part: say so whenever you quote it.

## When to use it

- A bracket, arm, mount or plate that should be lighter: the user knows where it is held and
  loaded, and has a block or plate it must fit in.
- "The stiffest part from 30 % of the material" (`objective: "stiffest"`, the default).
- "The least material that still holds" (`objective: "lightest"`, with a stress check, or a
  displacement check for "must not move more than 0.2 mm").
- Not for: a part already shaped as it must be (run `static`), a part whose weight is most of its
  load, an assembly (lighten one part at a time with `--occurrence`), or a question about buckling,
  vibration or fatigue of the new shape (rebuild it, then run those).

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys), and static's
`fixtures` and `loads` (forces and pressures on faces; no `gravity` or `acceleration`):

| key | meaning | default |
| --- | --- | --- |
| `objective` | `"stiffest"`: the stiffest design from `volume_fraction` of the material; `"lightest"`: the least material whose design passes the study's stress check (and displacement checks, where it names them) | `"stiffest"` |
| `volume_fraction` | the share of the part's volume to keep, 0.01 to 1 (0.3 keeps 30 %); `lightest` starts its search there | 0.3 (`lightest`: 0.5) |
| `keep` | faces whose nearby material stays solid, beyond the ones that always do: the fixtures, the loaded faces and whole cylindrical holes (bolt holes) | none |
| `min_member_mm` | the thinnest bar or wall the design may make (the density filter's size); never under 2.5 design elements | 3 design elements |
| `penalty` | SIMP's exponent, reached by continuation from 1 | 3 |
| `symmetry` | planes the design must be symmetric about: `"x"` (through the part's middle) or `{"axis": "x", "at_mm": 20}` | none |
| `extrusion` | a direction the design must be prismatic along (cut from plate, extruded): `"z"` or `{"direction": [0, 0, 1]}` | none |
| `load_cases` | instead of `loads`: several load cases, `[{"name": "lift", "loads": [...]}, ...]`; the design is stiffest for their sum | one case |
| `iterations` | the most optimisation iterations, 10 to 2000 | 150 |

`mesh.size_mm` is the design element size, and `mesh.order` is 1 (linear tets; order 2 is
refused). A finer mesh makes thinner members and takes longer: about 1000 to 5000 elements is a
quick concept, 20 000 to 100 000 a detailed one.

Checks (`view.checks`): `mass_saved` (`min_percent`, the least share of the mass the design must
save, 25 by default; titles "Barely lighter", "Close", "Much lighter"), and `stress` and
`displacement` judged on the verified design. With none named: `mass_saved` and `stress`.

Draw direction (a moulded or cast part's pull direction) is not a constraint here: use
`extrusion` for plate-cut parts, and rebuild a moulded part with draft by hand.

### Example

```json
{
  "analysis": "topology",
  "material": "aluminum-6061-t6",
  "fixtures": [{"faces": ["#o1.f3", "#o1.f4"]}],
  "loads": [{"faces": ["#o1.f9"], "type": "force", "vector_N": [0, 0, -800]}],
  "volume_fraction": 0.3,
  "keep": ["#o1.f12"],
  "min_member_mm": 6,
  "symmetry": ["x"],
  "mesh": {"size_mm": 2},
  "view": {"checks": [{"kind": "mass_saved", "min_percent": 50}, {"kind": "stress"}]}
}
```

The lightest version of the same bracket that must not move more than 0.1 mm:

```json
{"analysis": "topology", "objective": "lightest", "material": "aluminum-6061-t6",
 "fixtures": [{"faces": ["#o1.f3", "#o1.f4"]}],
 "loads": [{"faces": ["#o1.f9"], "type": "force", "vector_N": [0, 0, -800]}],
 "view": {"checks": [{"kind": "displacement", "limit_mm": 0.1}, {"kind": "stress"}]}}
```

## What comes out

- The GLB coloured by **Material kept** (the density, 1 where the material stays, 0 where it
  goes), with one frame per stage of the run ("Iteration 12" ... "Final design", at most 24). The
  viewer opens on the final design with "Show above 0.5", so what goes is drawn grey; its routine
  "Watch it form" plays the design forming. Stress and Displacement are the verified design's.
- `<name>.fea.design.stl` beside the GLB (the sidecar's `files.design_stl`): the design's surface at
  density 0.5, closed by the part's own faces where it is solid, Taubin-smoothed so it keeps its
  volume. Open it in the CAD Viewer next to the original part.
- The summary: `mass_saved_percent`, `design_volume_fraction` (the thresholded design that is
  built), `volume_fraction` (the optimiser's, on target within about 1 %), `compliance_Nmm` and
  `solid_compliance_Nmm` (the whole part solid, the baseline), `compliance_ratio` (how many times as
  flexible as the solid part the verified design is: 1.3 to 2.5 is usual at 30 to 50 %),
  `max_von_mises_MPa`, `max_displacement_mm` and `safety_factor` of the verified design,
  `kept_solid` (each face kept and why: fixture, load, bolt hole, kept), `iterations`,
  `converged`, `grey_percent` (how much is still between solid and void; under 10 % is crisp) and
  `lightest_rounds` for a lightest study (each volume tried and whether it passed).
- Curves: compliance, volume and grey share against iteration.

## How to read it and rebuild it in CAD

1. Look at the final design and the STL: which load paths it keeps (bars from the load to the
   fixtures, a web, a rim round a hole).
2. Rebuild it as clean CAD in the original part's source, not by converting the STL: sketch the
   bars and webs on the design's outline, give them the thickness the STL shows (at least
   `min_member_mm`), fillet the joints, and keep every kept face as it was. For a plate part, one
   sketch of the outline extruded through is usually enough (`extrusion` makes that exact).
3. Run a `static` study on the rebuilt part with the same fixtures and loads. Its stress is the
   number to trust: the verification stress here is on a staircase of linear tets, which reads high
   at the staircase's corners and low in bending.

## Judging the answer (hand checks)

- The volume: `volume_fraction` within 1 % of the target; `mass_saved_percent` is 100 minus the
  kept share (a little more when loose pieces were left out: a warning says so).
- The stiffness: the design is more flexible than the solid part (`compliance_ratio` > 1) but much
  stiffer than the same mass spread evenly (for SIMP at penalty 3, a uniform 50 % part is 8× as
  flexible as solid; a good design at 50 % is 1.3 to 2×).
- The shape: a classic beam held at both ends and pushed in the middle (the MBB beam) gives an arch
  with diagonal struts; a cantilever gives a truss of two chords and diagonals. A symmetric problem
  gives a symmetric design (name `symmetry` to make it exact).
- Benchmarks this engine is tested on (thin 2 mm steel slabs, 2 mm and 1.5 mm design elements): the
  MBB beam at 50 % keeps 50.0 % and is 1.35× as flexible as the solid slab; the cantilever at 40 %
  is 2.1×. On a structured half-MBB mesh, halving the element size moves the optimum's compliance
  under 5 %.

## Limits

- One part, one isotropic or orthotropic material, linear elastic, small displacement.
- The design is the stiffest for the loads given, not checked for buckling, fatigue or vibration:
  run those on the rebuilt part.
- The design mesh is fixed linear tetrahedra: no local refinement; members thinner than about
  three elements cannot form. The surface is a smoothed staircase.
- The verification solve runs on the kept elements (linear tets): its stress is a guide.
- Loads stay where they are: no self-weight, no pressure that follows the new surface.
- No draw-direction (moulding) or overhang (printing) constraint; `extrusion` and `symmetry` only.

## When the model is big

The ladder never refuses a design space for its size. In order:

1. `iterative`: AMG-preconditioned CG, warm-started from the last iteration's displacement, the
   multigrid hierarchy reused while it still converges quickly.
2. `symmetry`: when the part, its fixtures, loads, kept faces and checks are symmetric, it solves the
   half (or quarter) with sliding supports on the cut and mirrors the design back.
3. `coarse_design`: a coarser design mesh, the coarsest that fits from the requested size. It says
   the member size that mesh can resolve ("Used a coarser design mesh (5.3 mm elements, from 2 mm)
   to fit: it resolves members down to about 16 mm"); report it, since thinner members cannot form.

`local_refine` does not apply: the design mesh is fixed for the whole run. For finer detail, run a
coarse study first, then a finer one on a smaller design space (cut the part down to the region
that matters), or give the run a larger `fit.seconds`.
