# Flow and bending (`fsi`, lite)

It answers "the flow pushes the part and the part bends: how far, how hard, and does the bend
change the flow": steady two-way fluid-structure interaction, solved in-house (no outside
software). The flow is `cfd`'s (laminar) or `cfd_turbulent`'s, the part's bending is the linear
elastic solve of `static`, and the two are iterated until they agree. The plain word is Flow and
bending.

**Limits, written into every result: "Steady flow two-way coupled to a linear elastic part: no
flutter, vortex shedding or other unsteady motion; small-to-moderate deflection, the flow mesh
following the part (ALE mesh motion)."** Quote them whenever you quote its numbers. The flow's own
limits ([cfd.md](cfd.md), [cfd-turbulent.md](cfd-turbulent.md)) hold too.

## When to use it, and when one-way is enough

- "How far does this flap, reed, fin or valve leaf bend in the flow, and how hard is it stressed?"
  when it bends enough to change the flow around it.
- "Does this soft tube or hose swell under its own flow, and how much does that lower the pressure
  drop?"
- One-way is enough when the part barely moves: a stiff manifold, a metal pipe, a bracket in a
  breeze. Use `cfd` with `map_to_structure` ([cfd.md](cfd.md#the-study)) there: one flow solve,
  the wall pressure onto the part once. A rule of thumb: if the largest displacement is under about
  1 % of the gap or the opening the flow passes through, the two-way answer will not differ from
  the one-way one by more than a few percent. Every `fsi` result reports the one-way answer beside
  its own, so one run tells you whether it mattered.
- Not for anything that moves in time: flutter, galloping, vortex-induced vibration, a valve that
  slams. Not for large deflection (a flap whose tip moves more than about a tenth of its length),
  contact (a reed closing on its seat) or a part that yields.

## The study

On top of the common keys in [study-file.md](study-file.md#common-keys):

```json
{"analysis": "fsi", "material": {"name": "silicone", "E_MPa": 5, "nu": 0.3, "yield_MPa": 3},
 "mesh": {"size_mm": 0.8},
 "fixtures": [{"faces": ["#o1.f9"]}],
 "flow": {"kind": "internal", "fluid": "water", "regime": "auto",
          "inlets": [{"opening": "x_min", "velocity_m_s": 0.5}],
          "outlets": [{"opening": "x_max", "pressure_Pa": 0}]},
 "coupling": {"method": "aitken", "tolerance": 0.001, "max_iterations": 25},
 "view": {"checks": [{"kind": "stress"},
                     {"kind": "displacement", "limit_mm": 0.5},
                     {"kind": "pressure_drop", "limit_Pa": 2000}]}}
```

- `flow`: everything a [`cfd`](cfd.md#the-study) study's `flow` takes (`kind`, `fluid`, `inlets`
  with `opening`, `velocity_m_s` and `profile`, `outlets`, an external `velocity_m_s`), plus
  `regime`: `"auto"` (default: laminar below Re 2000 inside the part, Re 1000 around it, turbulent
  above), `"laminar"` or `"turbulent"`. A turbulent flow takes `turbulence_intensity` as
  [cfd-turbulent.md](cfd-turbulent.md#the-study) says; a laminar one refuses it.
- `material` (required: the part's) and `fixtures` (required, as in a static study: `fixed` or
  `roller` faces). There are no `loads`: the flow is the load.
- `coupling` (optional):
  - `method`: `"aitken"` (default: the relaxation is Aitken's dynamic factor, which settles most
    couplings in 3-8 iterations) or `"fixed_point"` (the same share of each new displacement every
    time).
  - `relaxation`: the first share taken (Aitken) or every share (fixed point), default 1.
  - `tolerance`: the run has settled when the displacement and the load each changed by less than
    this share of themselves in the last iteration; default 0.001.
  - `max_iterations`: default 25.
- `mesh.size_mm` is the element size of both the part and the flow's walls and openings.
- One part, as a flow study (name it with `--occurrence` in an assembly). Every face the fluid
  wets moves with the part; the fluid's own openings stay put.
- Checks: `stress` (default), `displacement` (`limit_mm`, optional `faces`) and `pressure_drop`
  (`limit_Pa`).

## What comes out

- Fields on the part: `von_mises` (MPa, the colour it opens on), `pressure` (the wall pressure, Pa,
  signed), `wall_shear` (Pa) and `displacement` (the deformed shape, drawn exaggerated by the
  deformation control). All at the settled state.
- Summary: the flow's numbers as `cfd` gives them (`reynolds`, `flow_regime`, `pressure_drop_Pa`,
  `flow_rate_L_min`, `max_velocity_m_s`, the wall pressure and shear ranges, `force_N`); the part's
  (`max_von_mises_MPa`, `max_displacement_mm` and where, `safety_factor`); `coupling` (`method`,
  `iterations`, `converged`, `residual`, `load_change`, `tolerance`, each iteration's `history` and
  `relaxation`, `ramped`, `flow_solves`); `one_way` (the deflection, stress, pressure drop and force
  of the flow at rest pushing the part once) and `two_way_vs_one_way` (`displacement_change_pct`,
  `pressure_drop_change_pct`, `pressure_drop_change_Pa`).
- CLI: "internal laminar flow of syrup: Re 0.25, coupled two ways with the part's bending",
  "coupling: 4 iterations (aitken), converged to 2.2e-05", "largest displacement 0.5284 mm
  (one-way 0.568 mm, -6.96%)", "pressure drop 1414 Pa (one-way 1413 Pa, +0.0856%) ...".
- The viewer: Study says "Water at 0.5 m/s bends the flap", the flow in and out, where it is held
  and what it is made of; Details give "Coupling: settled in 4 iterations"; the takeaway leads with
  "Laminar · " or "Turbulent · ".

## How it is solved

A partitioned, strongly coupled iteration on two meshes, the part's and the fluid's:

1. The flow is solved around the part as it stands (Taylor-Hood Navier-Stokes, or RANS k-omega SST).
2. Its traction on each wetted wall triangle (the pressure along the wall's normal, and the viscous
   shear from the velocity gradient in the element the triangle closes; turbulent: the wall
   function's shear) is carried to the part's nearest surface triangle on the same face, and
   applied as a surface load (no corner, a third of the area at each mid-edge node).
3. The part's linear elastic bending is solved (its stiffness factored once).
4. The part's displacement is evaluated where each of the fluid's wall nodes sits (the quadratic
   field on the part's surface triangles), and carried into the fluid by a harmonic mesh-motion
   solve, each element's stiffness the inverse of its volume, so the small elements next to the part
   move almost rigidly (ALE). Openings stay put; a node on an opening's rim keeps to its plane.
5. The displacement is relaxed (Aitken, or a fixed share) and the loop repeats until the
   displacement and the load settle. The first pass is the one-way answer, kept for the summary.

A relaxed step that would fold the moved flow mesh over is halved, up to four times. A coupling
that grows for three iterations running is restarted once with the inflow ramped up in steps (25 %,
50 %, 100 %) and a first relaxation of at most 0.5, each stage starting from the one before.

## Judging the answer (hand checks)

- A soft tube swelling under its own flow, away from its ends: the bore grows by the thin-wall
  formula δ = p R_m² (1 − ν²) / (E t) with the flow's local wall pressure p (both ends held; a free
  end drops the (1 − ν²)). In the test, a 2 mm bore with a 0.2 mm wall at E 1 MPa agrees within 5 %
  along its length.
- Its pressure drop: Poiseuille's law where the radius follows the pressure, dp/dx = −8 μ Q / (π a⁴)
  with a = R + c p, c = R_m² (1 − ν²) / (E t), integrates to a_in⁵ = R⁵ + 5 c (8 μ Q / π) L. The
  test's tube agrees within 1 % (3027 Pa against 3010 Pa; rigid, 3200 Pa).
- A flap in a stream: two-way it leans less than one-way (leaning, it blocks less of the flow and is
  pushed less). The test's soft flap leans 7 % less (0.528 mm against 0.568 mm); a fixed-relaxation
  iteration to ten times tighter tolerance lands on the same deflection within 0.2 %.
- A published benchmark: Turek and Hron's FSI1 (a flag behind a cylinder in a 2D channel, Re 20)
  is not reproduced here: it is two-dimensional, and a quasi-2D slab in this solver has no-slip walls
  on its faces, so its answer would not be FSI1's.

## When it does not settle

The run never refuses: it reports its last state, says "the flow and the bending did not settle in
N coupling iterations ... this is the last state, not a converged answer" (warnings, a
`coupling_not_converged` finding, the CLI's "NOT converged", the verdict's "not converged"), with
the change it still made. Say so first when you report. Then offer, in order:

- raise `coupling.max_iterations` (a residual that is still falling only needs more);
- lower `coupling.relaxation` (0.5, 0.3), or use `"fixed_point"` with a small one, for a coupling that
  overshoots back and forth;
- solve a slower flow first, to see whether the deflection is still small-to-moderate;
- a part that bends so far the flow mesh folds ("the moved flow mesh folded over") is past this
  solver's range: stiffen it in the model, or report the one-way answer as an upper bound.

A turbulent flow settles less tightly than a laminar one (the RANS march settles to its own
tolerance), so a very soft part in a turbulent flow may stop short of the default tolerance.

## Limits

- Steady only: the answer is the balance the flow and the part settle to, if they settle. Nothing
  about flutter or vibration in the flow.
- Linear elastic part, small-to-moderate deflection: the load is the deformed flow's, applied to
  the part's shape at rest.
- The fluid mesh is moved, never rebuilt: deflections past a fraction of the gap next to the part
  fold it.
- The flow's own limits: one part; openings on sides of the bounding box.

## When the model is big

It runs at any size. The ladder may take, in order: `continuation` (above Re 100: the inflow ramped
up in steps, each flow solve reaching its Reynolds number by continuation), `iterative` solvers for
the flow and the bending, `fluid_coarsen` (the flow's core coarsened away from its walls, which keep
their size), and `local_refine` (the part fine only near its peak stress, coarse elsewhere, with how
far the peak moved between the passes; taken only when the part's solve is most of the cost, as two
passes repeat the whole coupling). Each step is an `adapted:` line with its accuracy note; report
every one.
