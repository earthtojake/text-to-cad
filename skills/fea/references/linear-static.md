# Linear static checklist

What the solver assumes, what the mesh and the solver do, and how to tell a good answer from a bad
one. The keys are in [study-file.md](study-file.md).

## What the model is

- Small displacements and strains, so results scale linearly with the load: a check's `ratio` of
  0.5 holds at twice the load. A part that deflects more than a few percent of its size, buckles,
  or touches something else is outside the model (`large_displacement` warns at 1 %).
- Linear elastic, isotropic material below yield. Below a safety factor of 1 the real part yields
  and the stresses reported are not what it sees.
- Fixtures are perfectly rigid. A `fixed` face is held still, which also stops it shrinking
  sideways as the part is squeezed (Poisson's effect), so the stress right at it reads high; a
  real bolt, weld or clamp is softer and spreads load, and fixing a whole hole wall is stiffer
  than a screw with a washer. A `roller` face is held along its normal alone: a frictionless
  support, or the cut face when you model half of a symmetric part
  ([`fixtures`](study-file.md#fixtures)).
- Loads are static and do not follow the deformation. `gravity` and `acceleration` are steady body
  loads, not a shake or an impact; there is no preload and no thermal strain.
- Quadratic (10-node) tetrahedra, CalculiX's C3D10, solved by CalculiX's direct solver on one
  thread, so the same study gives the same numbers every run.
- An assembly's parts are bonded where they touch (within `contact_tolerance_mm`, 0.1 by default):
  the glued faces carry load as if welded, with no slip, clearance, preload or bolt stiffness, so a
  bonded joint is stiffer than a real bolted one and exaggerates the stress at its edge. A part
  resting on another without being bonded carries nothing.

## Choosing faces

A face the user selected in the CAD Viewer arrives as `/work/bracket.step#bracket/face 17` and is
exact. Otherwise the setup (`cad step solve part.step`) lists each face with its area, centre,
surface type and a hint (`plane, normal -Z, largest`): "the base" or "the mounting face" is usually
the largest planar face with a downward normal, "the top of the upright" a small planar face at the
highest Z, a hole a `cylinder`. A face and its mirror image match a description equally; ask
rather than guess between them.

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

- `gravity`: the part's own weight, pulling along `vector_g` (`[0, 0, -1]` is Earth's gravity with
  +Z up). It matters for a long arm, a heavy casting or a large plate held at one edge; for a small
  bracket carrying a large force it changes little.
- `acceleration`: the part itself is accelerated by `vector_g` (a vehicle braking, a robot arm
  swinging, a part on a spinning arm at a known g), so it feels the inertial load the opposite
  way: speeding up at 5 g in +X loads every bit of the part toward -X.
- Both need a density greater than zero (steel 7.85e-9, aluminium 2.7e-9 t/mm³;
  [`loads`](study-file.md#loads)). In an assembly they act on every part, each with its own density.
- The summary's `applied_force_N` includes them (mass times acceleration), so the reactions still
  balance it: a 2 kg part under `gravity` alone shows about 19.6 N applied and 19.6 N of reaction.
- A drop, as an estimate: hold the faces that hit the floor `fixed` and add an `acceleration` of
  G g pointing away from the floor, G = drop height / stopping distance (a 1 m drop that stops in
  2 mm is 500 g). Report it as an estimate of an equivalent steady load, never as an impact
  simulation, and say the stopping distance you assumed.

## Mesh

- The default `mesh.size_mm` is a fortieth of the bounding diagonal. It is the largest element:
  small features (thin walls, fillets, chamfers, small holes) make the mesher go finer there by
  itself, with elements under about their radius or thickness, so they, not only the bounding box,
  can set the element count.
- netgen curves the elements on a curved face onto it. Where an element is thin across a fillet, a
  hole or a thin wall, that can turn it inside out: at one of CalculiX's integration points it
  refuses the mesh, at a node alone it would solve it folded. Each element is checked at both, and
  one inside out at either is made straight (the surface there is a little less curved). The
  result's `mesh.straightened` counts them; many mean the elements are larger than the wall is
  thick, and a smaller `mesh.size_mm` keeps them curved. An element whose corners enclose no
  volume cannot be straightened, and the run refuses the mesh.
- The run reports two von Mises peaks. The nodal one (the reported peak, which the safety factor
  uses) is each element's stress at its four integration points, extrapolated to its nodes and
  averaged over the elements at a node, per part in an assembly; it is usually the higher of the
  two. The integration-point one is the raw element value. When the integration-point peak stands
  more than 50 % above the nodal one, a concentration is not resolved; when that matters the run
  lists a `peak_concentration` finding.
- When the safety factor is under 3 the run solves again by itself at half the element size (and
  half at fillets and holes too), capped to keep the finer solve under 150 000 degrees of freedom
  where it can and never past 250 000, so a big part may get less than half, or none, with a
  warning. The finer result is the one written and reported, the result's `refined` records both
  sizes and peaks, and `mesh_not_converged` is listed when the peak moved more than 10 %.
- To check convergence yourself, solve twice and compare the peaks. Away from small features, halve
  `mesh.size_mm`. At a fillet, hole or chamfer halving it changes little, since the elements there
  are already sized by the feature (the slow-solve warning says so when small features set the
  mesh): set `mesh.size_mm` to about a third of the feature's radius instead, then halve that; this
  refines the whole part, so watch the degrees of freedom. A `mesh.refine` ball refines one spot
  alone ([`mesh`](study-file.md#mesh)).
- A peak that moves less than about 10 % between two runs is converged enough for a first answer.
  A peak that keeps growing sits on a singularity: a clamped edge, a sharp inside corner, a point
  load. Report the value a short distance away from it, say why, and suggest a fillet or a softer
  fixture if the location is real.
- Element count grows as the cube of the refinement. Above 150 000 degrees of freedom the solve is
  slow and the run says so: CalculiX's direct solver took about 10 s and 1.8 GB at 140 000, and
  74 s and 4.3 GB at 207 000. A first solve is never refused for its size, and the model is never
  simplified to fit: when it is too slow, a larger `mesh.size_mm` is the fix, unless the warning
  says small features set the mesh, where a larger size helps little.

## The solver

- Every study is solved by CalculiX (`ccx`), the one the `calculix` integration carries
  (`cad[calculix]`, the cad-ccx package: CalculiX 2.23), which the `cad` command installs on first
  need. text-to-cad runs `CAD_CCX` instead when it is set (2.20 or newer), never a `ccx` on PATH.
  It writes CalculiX's input (each part its own element set and material, a roller on a sloped or
  curved face in its own frame), runs it, and reads the displacements, the reactions and the stress
  at each element's integration points back. There is no fallback solver: a missing `ccx`, or one
  older than 2.20, stops the solve before meshing with an error naming how to install it.
- `--deck` keeps the input of the solve written as `ccx.inp` in the results folder, which
  `cad run ccx -i ccx` runs again. The result's `mesh.solver` names the version that ran
  (`calculix 2.23 (C3D10)`). A solve that runs past an hour is stopped and says so.

## Judging the answer

Estimate the answer by hand before trusting a run: beam bending for a cantilever, about three
times the nominal stress at a hole in tension, p r / t for a thin ring under pressure. For a body
load the reaction is mass times acceleration: density (t/mm³) times volume (mm³) times 9806.65
times `vector_g`, in N. Within roughly 20 % of the estimate, the model is doing what you asked. Off
by a factor, the load, the fixture or the units are wrong: check the fixture reactions first (they
equal minus the applied force, body loads included), then the face choice, then the material.
