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
- Loads are static and do not follow the deformation. No inertia, no
  fatigue, no thermal strain, no preload.
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
- Weight of a held object: mass in kg times 9.81 gives newtons. Gravity on
  the part itself is not modelled.
- A moment: two equal and opposite forces on two faces a known distance
  apart.

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
  degrees of freedom the solve is slow and the run says so; above 1.5
  million it refuses.

## Judging the answer

Before trusting a run, estimate the answer by hand and compare:

- A cantilever of length L with a tip load F: tip deflection F L³ / (3 E I),
  root bending stress F L (h/2) / I, with I = b h³ / 12 for a rectangle.
- A plate with a hole in tension: about three times the nominal stress at the
  hole's edge.
- A thin ring or cylinder under pressure p: hoop stress p r / t.

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
6. What the model assumes, in one or two sentences, and what would change
   the answer most (a softer fixture, a fillet at the peak, a different
   material).

Open the result GLB in the Viewer, and say that the deformation shown is
exaggerated by the scale in the sidecar.
