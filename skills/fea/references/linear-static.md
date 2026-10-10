# Linear static checklist

What the solver assumes, how to set a study up so the answer means something,
and how to tell a good answer from a bad one.

## What the model is

- Small displacements, small strains: results scale linearly with the load.
  A part that deflects by more than a few percent of its own size, buckles,
  or contacts something else is outside the model.
- Isotropic linear elastic material below yield. The safety factor tells you
  whether that assumption held; below 1 the real part yields and the stresses
  reported are not what it sees.
- Fixtures are perfectly rigid and perfectly bonded. A real bolt, weld or
  clamp is softer and spreads load; a fixed face is the stiffest possible
  support.
- Loads are static and do not follow the deformation. A `gravity` or
  `acceleration` load is a steady body load (the part's weight, or a constant
  g-load), not a moving one: no vibration, no impact, no fatigue, no thermal
  strain, no preload.
- An assembly's parts are bonded where they touch (within 0.1 mm): the glued
  faces carry load as if welded, with no slip, no clearance, no preload and no
  bolt stiffness. A bonded joint is stiffer than a real bolted one and
  exaggerates the stress at its edge. Bolts, pins and contact are not yet
  modelled, and a part resting on another without being bonded carries
  nothing.

## Choosing faces

1. Prefer references the user selected in the Viewer: they arrive as
   `part.step#o1.f17` and are exact.
2. Otherwise run `cadgen fea faces part.step` and match by the hint
   (`plane, normal -Z, largest`), the centre, and the area. "The base",
   "the mounting face" and "the bottom" usually mean the largest planar face
   with a downward normal; "the top of the upright" is a small planar face
   at the highest Z. A hole is a `cylinder`.
3. When two faces match a description equally, ask, quoting both selectors
   and where they are. Do not guess between a face and its mirror image.
4. Restate what you chose before solving: "fixing #o1.f17 (3943 mm², bottom),
   500 N in -Y on #o1.f22 (640 mm², top of the back plate)". A wrong face is
   cheaper to catch here than after a run.

## Setting the load

- A force is the total over its faces, spread uniformly. 500 N on a 640 mm²
  face is 0.78 MPa of traction. A force on a hole's cylindrical face
  approximates a pin or bolt load.
- A pressure is normal to the face and positive pushing in. Convert bar to
  MPa (1 bar = 0.1 MPa) and psi to MPa (1 psi = 0.006895 MPa) before writing
  it down.
- Weight of a held object: mass in kg times 9.81 gives newtons, as a `force`
  on the face it rests on. The part's own weight is a `gravity` load (below).
- A moment: two equal and opposite forces on two faces a known distance
  apart.

## Body loads: gravity and acceleration

Two loads act on the whole volume instead of on faces. Neither has `faces`;
each takes `vector_g`, in g (1 g = 9.81 m/s²).

```json
"loads": [
  {"faces": ["#o1.f2"], "type": "force", "vector_N": [0, 0, -200]},
  {"type": "gravity", "vector_g": [0, 0, -1]},
  {"type": "acceleration", "vector_g": [5, 0, 0]}
]
```

- `gravity`: the part's own weight, pulling along `vector_g`. `[0, 0, -1]` is
  Earth's gravity with +Z up. Add it when the weight matters against the other
  loads: a long arm, a heavy casting, a large plate held at one edge. For a
  small bracket carrying a large force it changes little; leave it out unless
  asked.
- `acceleration`: the part itself is accelerated by `vector_g` (a vehicle
  braking, a robot arm swinging, a part on a spinning arm at a known g). It
  feels an inertial load the opposite way: speeding up at 5 g in +X loads
  every bit of the part toward -X, like a passenger pressed back into a seat.
  This is a steady g-load, not a shake or an impact.
- Both need a density greater than zero. Every table material has one; a
  material object must give `density_t_per_mm3` (steel 7.85e-9, aluminium
  2.7e-9), or the study is refused with a sentence saying so.
- In an assembly they act on every part, each with its own density.
- The sidecar's `applied_force_N` includes them (mass times acceleration), so
  the reactions still balance it: a 2 kg part under `gravity` alone shows
  about 19.6 N applied and 19.6 N of reaction.
- A drop, as an estimate: hold the faces that hit the floor fixed and add an
  `acceleration` of G g pointing away from the floor (opposite those faces'
  outward normal), G = drop height / stopping distance. A 1 m drop that stops
  in 2 mm is 500 g. Report it as an estimate of an equivalent steady load,
  never as an impact simulation, and say the stopping distance you assumed.
- The `load_scale` control scales the body loads with the rest, because the
  answer is linear in every load.

## Mesh

- First run at the default size (a fortieth of the bounding diagonal).
  `mesh.size_mm` is the largest element; small features (thin walls, fillets,
  chamfers, small holes) make the mesher go finer there by itself, with
  elements under about their radius or thickness.
- The run reports both the nodal and the Gauss-point von Mises peak. When the
  Gauss-point value is more than 50 % above the nodal one, the peak is not
  resolved; when that matters the run lists a `peak_concentration` finding.
  When the safety factor is under 3 the run solves again by itself on a finer
  mesh, finer at fillets and holes by the same ratio, and lists
  `mesh_not_converged` when the peak moved more than 10 %.
- To check convergence yourself, solve twice and compare the peaks; how
  depends on where the peak is. Away from small features, halve
  `mesh.size_mm` (`--mesh-size` on the command line). At a fillet, hole or
  chamfer, halving it changes little: the elements there are already sized
  by the feature, not by `mesh.size_mm` (the run's slow-solve warning says
  so when small features set the mesh). Set `mesh.size_mm` to about a third
  of that feature's radius instead, then halve that; this refines the whole
  part, so watch the degrees of freedom.
- A peak that moves less than about 10 % between the two runs is converged
  enough for a first answer. A peak that keeps growing sits on a singularity:
  a clamped edge, a sharp inside corner, a point load. Report the value a
  short distance away from it, say why, and suggest a fillet or a softer
  fixture if the location is real.
- Element count grows as the cube of the refinement. Above about 400 000
  degrees of freedom the solve is slow and the run says so. A model too big
  for the machine is not refused: the run adapts it to fit (below).

## When the model is big: the static ladder

Never ask the user to shrink, simplify or defeature a model first. Run it as
it is. Before meshing, the run estimates the memory and time the solve needs,
and while that misses the target (half the machine's memory and 600 seconds,
unless the study's `fit` says otherwise) it takes the next step that applies,
in this order:

1. `iterative`: an iterative solver, or one that never stores the whole
   matrix. No accuracy cost.
2. `local_refine`: a coarse first pass everywhere, then a second mesh kept at
   the requested size only around the first pass's peak and on loaded, fixed
   and checked faces, coarse elsewhere. Its note gives how far the peak moved
   between the passes ("the peak is still meshed at 0.8 mm; peak stress moved
   2.1 % between passes").
3. `defeature`: small fillets, chamfers and holes far from every named face
   and from the peak are left out of the mesh. A named face is never removed.
   Its words name what was left out ("Left out 6 small fillets far from the
   load to mesh it").
4. `linear_elements`: simpler elements. Bending stress reads about 10 to 30 %
   low with them; the note says how much, measured where it could be.
   `idealise` (a thin-walled part as a shell, a slender part as a beam) sits
   at this step too, where this cadgen has those models.
5. `symmetry`: when the part and every load, fixture and check is symmetric
   about a plane, it solves half (or a quarter) and mirrors the result. Exact.

A step that does not apply is skipped. When every step is taken and the
estimate still misses, the run goes ahead anyway and says how long and how
much memory to expect.

Each step taken is one `adapted:` line in the CLI output, one entry of the
sidecar's `fit`, and an `info` finding `fit_<step>`. Report every one, with
its accuracy note, in plain words: "To fit this machine, it meshed coarsely
away from the hole; the peak there is still meshed finely, and it moved 2 %
between the coarse and fine passes." Never report an adapted result as if no
step was taken.

The study's `fit` key ([study-file.md](study-file.md#fit)) changes the
targets or forbids steps. Use it only when the user rules a simplification
out ("keep every fillet": leave `defeature` out of `fit.allow`) or names a
budget.

## Judging the answer

Before trusting a run, estimate the answer by hand and compare:

- A cantilever of length L with a tip load F: tip deflection F L³ / (3 E I),
  root bending stress F L (h/2) / I, with I = b h³ / 12 for a rectangle.
- A plate with a hole in tension: about three times the nominal stress at the
  hole's edge.
- A thin ring or cylinder under pressure p: hoop stress p r / t.
- A body load: the reaction equals mass times acceleration, density times
  volume times 9806.65 (g in mm/s²) times `vector_g`, in N when density is in
  t/mm³ and volume in mm³. A cantilever of length L under its own
  weight w per unit length: tip deflection w L⁴ / (8 E I), root bending
  stress w L² (h/2) / (2 I).

If the model is within roughly 20 % of the estimate, it is doing what you
asked. If it is off by a factor, the load, the fixture or the units are
wrong; check the reactions in the sidecar first (they must equal minus the
applied force), then the face choice, then the material.

## Reporting

In this order, with units:

1. Max von Mises stress (MPa), and where (from `max_von_mises_at_mm` in the
   sidecar; say which feature it is near).
2. Safety factor against yield, and the yield used.
3. Max displacement (mm) and where.
4. Applied load and reaction.
5. Mesh: element size, count, and whether a refinement was run.
6. Every adapted step, with its accuracy note, when the run took any.
7. What the model assumes, in one or two sentences, and what would change
   the answer most (a softer fixture, a fillet at the peak, a different
   material).

Open the result GLB in the Viewer, and say that the deformation shown is
exaggerated by the scale in the sidecar.
