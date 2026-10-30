# Linear static checklist

What the solver assumes, how to set a study up so the answer means something, and how to tell a
good answer from a bad one. The keys are in [study-file.md](study-file.md).

## What the model is

- Small displacements, small strains: results scale linearly with the load. A part that deflects by
  more than a few percent of its own size, buckles, or contacts something else is outside the model.
- Linear elastic, isotropic material below yield. The safety factor tells you whether that assumption held; below 1 the real part
  yields and the stresses reported are not what it sees.
- Fixtures are perfectly rigid. A `fixed` face is held still and bonded: a real bolt, weld or clamp
  is softer and spreads load, so a fixed face is the stiffest possible support. A `roller` face
  slides freely in its own plane and is held only along its normal (on a curved face, its normal
  at each point): a frictionless support.

## Fixed or roller

- `fixed` where the part is bolted, welded or clamped. It also stops the face shrinking sideways as
  the part is squeezed (Poisson's effect), so the stress right at it reads high: read the peak a
  little away from it. Fixing a whole hole wall is stiffer than a real screw with a washer, so
  peaks at fixed holes read high.
- `roller` where the part rests on a smooth support it can slide on, and on a symmetry plane when
  you model half a part yourself (the cut face moves only in its plane). A block on rollers on
  three faces that meet at a corner, pulled on the opposite face, is in pure uniaxial stress:
  σ = F/A everywhere and it narrows by ν times its stretch, the textbook answer, which a fixed face
  would spoil at the clamp.
- Rollers alone must stop the part sliding and turning every way: three faces whose normals are
  not all in one plane do it; one flat face does not (the part could slide along it), and the run
  says the part is not held.
- Loads are static and do not follow the deformation. A `gravity` or `acceleration` load is a
  steady body load (the part's weight, or a constant g-load), not a moving one: no vibration, no
  impact, no fatigue, no thermal strain, no preload.
- Quadratic (10-node) tetrahedra, CalculiX's C3D10, solved by CalculiX's direct solver on one
  thread, so the same study gives the same numbers every run.
- An assembly's parts are bonded where they touch (within 0.1 mm): the glued faces carry load as
  if welded, with no slip, no clearance, no preload and no bolt stiffness. A bonded joint is
  stiffer than a real bolted one and exaggerates the stress at its edge. A part
  resting on another without being bonded carries nothing. Parts that press and slide, and bolts,
  are not in this version.

## Choosing faces

1. Prefer references the user selected in the Viewer: they arrive as `/work/bracket.step#bracket/face 17` and are
   exact.
2. Otherwise run `cadgen fea faces part.step` and match by the hint (`plane, normal -Z, largest`),
   the centre, and the area. "The base", "the mounting face" and "the bottom" usually mean the
   largest planar face with a downward normal; "the top of the upright" is a small planar face at
   the highest Z. A hole is a `cylinder`.
3. When two faces match a description equally, ask, quoting both refs and where they are. Do
   not guess between a face and its mirror image.
4. Restate what you chose before solving: "fixing bracket/face 17 (3943 mm², bottom), 500 N in -Y on
   bracket/face 22 (640 mm², top of the back plate)". A wrong face is cheaper to catch here than after a
   run.

## Setting the load

- A force is the total over its faces, spread uniformly. 500 N on a 640 mm² face is 0.78 MPa of
  traction. A force on a hole's cylindrical face approximates a pin or bolt load.
- A pressure is normal to the face and positive pushing in. Convert bar to MPa (1 bar = 0.1 MPa)
  and psi to MPa (1 psi = 0.006895 MPa) before writing it down.
- Weight of a held object: mass in kg times 9.81 gives newtons, as a `force` on the face it rests
  on. The part's own weight is a `gravity` load (below).
- A moment: two equal and opposite forces on two faces a known distance apart.

## Body loads: gravity and acceleration

Two loads act on the whole volume instead of on faces. Neither has `faces`; each takes `vector_g`,
in g (1 g = 9.81 m/s²).

```json
"loads": [
  {"faces": ["bracket/face 2"], "type": "force", "vector_N": [0, 0, -200]},
  {"type": "gravity", "vector_g": [0, 0, -1]},
  {"type": "acceleration", "vector_g": [5, 0, 0]}
]
```

- `gravity`: the part's own weight, pulling along `vector_g`. `[0, 0, -1]` is Earth's gravity with
  +Z up. Add it when the weight matters against the other loads: a long arm, a heavy casting, a
  large plate held at one edge. For a small bracket carrying a large force it changes little;
  leave it out unless asked.
- `acceleration`: the part itself is accelerated by `vector_g` (a vehicle braking, a robot arm
  swinging, a part on a spinning arm at a known g). It feels an inertial load the opposite way:
  speeding up at 5 g in +X loads every bit of the part toward -X, like a passenger pressed back
  into a seat. This is a steady g-load, not a shake or an impact.
- Both need a density greater than zero (steel 7.85e-9, aluminium 2.7e-9 t/mm³;
  [`loads`](study-file.md#loads)). In an assembly they act on every part, each with its own density.
- The summary's `applied_force_N` includes them (mass times acceleration), so the reactions still
  balance it: a 2 kg part under `gravity` alone shows about 19.6 N applied and 19.6 N of reaction.
- A drop, as an estimate: the faces that hit the floor fixed and an `acceleration` of G g pointing away from the floor, G = drop height / stopping distance (a
  1 m drop that stops in 2 mm is 500 g). Report it as an estimate of an equivalent steady load,
  never as an impact simulation, and say the stopping distance you assumed.
- The `load_scale` control scales the body loads with the rest, because the answer is linear in
  every load.

## Mesh

- First run at the default size (a fortieth of the bounding diagonal). `mesh.size_mm` is the
  largest element; small features (thin walls, fillets, chamfers, small holes) make the mesher go
  finer there by itself, with elements under about their radius or thickness, so they, not only
  the bounding box, can set the element count.
- netgen curves the elements on a curved face onto it. Where an element is thin across a fillet,
  a hole or a thin wall, that can turn it inside out: at one of CalculiX's integration points it
  refuses the mesh, at a node alone it would solve it folded. Each element is checked at both, and
  one inside out at either is made straight (the surface there is a little less curved). Many
  straightened elements mean the elements are larger than the wall is thick: a smaller
  `mesh.size_mm` keeps them curved. The result's
  `mesh.straightened` counts them, also in the GLB's study. An element whose corners enclose no
  volume cannot be straightened, and the run refuses the mesh.
- The run reports two von Mises peaks. The nodal one (the reported peak, which the safety factor
  uses) is each element's stress at its four integration points, extrapolated to its nodes and
  averaged over the elements at a node, per part in an assembly; it is usually the higher of the
  two. The integration-point one is the raw element value. When the integration-point peak stands
  more than 50 % above the nodal one, a concentration is not resolved; when that matters the run
  lists a `peak_concentration` finding.
- When the safety factor is under 3 the run solves again by itself at half the element size (and
  half the size at fillets and holes too), capped to keep the finer solve under 150 000 degrees of
  freedom where it can and never past 250 000 (so a big part may get less than half, or none, with
  a warning); the finer result is the one written and reported, the result's `refined` block
  records both sizes and peaks, and `mesh_not_converged` is listed when the peak moved more than
  10 %.
- To check convergence yourself, solve twice and compare the peaks; how depends on where the peak
  is. Away from small features, halve `mesh.size_mm`. At a
  fillet, hole or chamfer, halving it changes little: the elements there are already sized by the
  feature, not by `mesh.size_mm` (the run's slow-solve warning says so when small features set the
  mesh). Set `mesh.size_mm` to about a third of that feature's radius instead, then halve that;
  this refines the whole part, so watch the degrees of freedom.
- A peak that moves less than about 10 % between the two runs is converged enough for a first
  answer. A peak that keeps growing sits on a singularity: a clamped edge, a sharp inside corner, a
  point load. Report the value a short distance away from it, say why, and suggest a fillet or a
  softer fixture if the location is real.
- Element count grows as the cube of the refinement. Above 150 000 degrees of freedom the solve is
  slow and the run says so: CalculiX's direct solver took about 10 s and 1.8 GB at 140 000, and
  74 s and 4.3 GB at 207 000. A first solve is never refused for its size, and the model is never
  simplified to fit: when it is too slow, a larger `mesh.size_mm` is the fix (unless the warning says
  small features set the mesh, where a larger size helps little).

## The solver

- Every study is solved by CalculiX (`ccx`), 2.20 or newer, which the person installs: `conda
  install -c conda-forge calculix`, or the `calculix-ccx` package on Debian and Ubuntu. cadgen runs
  `CADGEN_CCX` when it is set, else `ccx` on PATH. cadgen meshes with netgen, writes CalculiX's
  input (each part its own element set and material, a roller on a sloped or curved face in its own
  frame), runs it, and reads the displacements, the reactions and the stress at each element's
  integration points back.
- A missing `ccx`, or one older than 2.20, stops the solve before meshing with an error naming how
  to install it. cadgen downloads nothing and has no fallback solver.
- The result names the version that ran: `mesh.solver` in the result (`calculix 2.23 (C3D10)`),
  also at the end of the first line the command prints. A solve that runs past an hour is stopped
  and says so.

## Judging the answer

Before trusting a run, estimate the answer by hand and compare:

- A cantilever of length L with a tip load F: tip deflection F L³ / (3 E I), root bending stress
  F L (h/2) / I, with I = b h³ / 12 for a rectangle.
- A plate with a hole in tension: about three times the nominal stress at the hole's edge.
- A thin ring or cylinder under pressure p: hoop stress p r / t.
- A body load: the reaction equals mass times acceleration, density times volume times 9806.65 (g
  in mm/s²) times `vector_g`, in N when density is in t/mm³ and volume in mm³. A cantilever of
  length L under its own weight w per unit length: tip deflection w L⁴ / (8 E I), root bending
  stress w L² (h/2) / (2 I).

If the model is within roughly 20 % of the estimate, it is doing what you asked. If it is off by a
factor, the load, the fixture or the units are wrong; check the result's fixture reactions first
(they must equal minus the applied force), then the face choice, then the material.
