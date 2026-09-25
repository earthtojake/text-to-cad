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
- One part. An assembly is solved one occurrence at a time; every face in a
  study must be on the same occurrence.

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
- The run reports both the nodal and the Gauss-point von Mises peak. When the
  Gauss-point value is more than 50 % above the nodal one, the peak is not
  resolved; the run warns. Halve `mesh.size_mm` once (`--mesh-size` on the
  command line) and compare the peaks.
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
