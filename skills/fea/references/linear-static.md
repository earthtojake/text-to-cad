# Linear static checklist

Read this for a drop or a braking load as a steady g-load, how the mesh is sized and refined, by
the run and by hand, and how to tell a good answer from a bad one. The study's keys are in
[study-file.md](study-file.md).

## Choosing faces

A face and its mirror image match a description equally: ask rather than guess between them.

## Body loads: gravity and acceleration

`gravity` and `acceleration` are steady loads on the whole volume
([`loads`](study-file.md#loads)), not a shake or an impact. A part that brakes, swings or spins at
a known g is an `acceleration` of that vector, with its mounting faces held. A drop is estimated
the same way: hold the faces that hit the floor `fixed` and add an `acceleration` of G g pointing
away from the floor, with G = drop height / stopping distance (a 1 m drop that stops in 2 mm is
500 g). Report it as an estimate of an equivalent steady load, never as an impact simulation, and
say the stopping distance you assumed.

## Mesh

- Elements are quadratic (10-node) tetrahedra, CalculiX's C3D10. `mesh.size_mm` is the largest
  element: thin walls, fillets, chamfers and small holes make the mesher go finer there by itself,
  with elements under about their radius or thickness, so small features, not only the size, can
  set the element count.
- `mesh.straightened` counts the elements made straight because the mesher's curving turned them
  inside out, where an element is thin across a fillet, a hole or a thin wall; the surface there
  is solved a little less curved. Many mean the elements are larger than the wall is thick, and a
  smaller `mesh.size_mm` keeps them curved.
- The nodal peak (usually the higher of the two, as SKILL.md's Findings say) is averaged over the
  elements at a node, in an assembly over each part's own, so stress steps across a joint between
  two materials as it does in the parts.
- When the safety factor is under 3 the run solves again by itself at half the element size (half
  at fillets and holes too), within a budget: under 150 000 degrees of freedom where that still
  leaves a finer mesh, and never past 250 000. So a big part gets less than half, or no finer
  solve and a `solver_note` saying its convergence is unchecked. The finer result is the one
  written, `refined` records both sizes and peaks, and `mesh_not_converged` is listed when the
  peak moved more than 10 %.
- To check convergence yourself, solve twice and compare the peaks. Away from small features,
  halve `mesh.size_mm`. At a fillet, hole or chamfer the elements are already sized by the feature
  (the slow-solve warning says when small features set the mesh), so halving it changes little:
  set `mesh.size_mm` to about a third of the feature's radius, then halve that, watching the
  degrees of freedom since this refines the whole part, or refine the one spot with a
  `mesh.refine` ball ([`mesh`](study-file.md#mesh)).
- Above 150 000 degrees of freedom the solve is slow and the run says so: CalculiX's direct solver
  took about 10 s and 1.8 GB at 140 000, and 74 s and 4.3 GB at 207 000. A first solve is never
  refused for its size, and the model is never simplified to fit: a larger `mesh.size_mm` is the
  fix, unless the warning says small features set the mesh.

## The solver

Every study is solved by the CalculiX cad installs, or by the one `CAD_CCX` names where that is set;
a `ccx` on PATH is never run. `--deck` keeps the input of the solve written, which any CalculiX of
your own solves too. A mesh or a solve that runs past an hour is stopped and says so.

## Judging the answer

Estimate the answer by hand before trusting a run: beam bending for a cantilever, about three
times the nominal stress at a hole in tension, p r / t for a thin ring under pressure. For a body
load the reaction is mass times acceleration: density (t/mm³) times volume (mm³) times 9806.65
times `vector_g`, in N. Within roughly 20 % of the estimate, the model is doing what you asked. Off
by a factor, the load, the fixture or the units are wrong: check the fixture reactions first (they
equal minus the applied force, body loads included), then the face choice, then the material.
