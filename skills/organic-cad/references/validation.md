# Clearance and validation

## Two distinct negative volumes

1. **Functional fit/assembly voids:** bearing bore or socket cavity, pin entry,
   guide channel, axial gaps and required flexure slots, as applicable to the
   selected mechanism. These are dimensioned CAD features.
2. **Motion clearance:** a local obstacle swept through the required relative
   poses, expanded by a clearance allowance and an approximation bound.

For a moving head and fixed body, cut the moving head with the fixed body's
local obstacle transformed by the **inverse** head poses. Cut the fixed body
with a moving-head obstacle transformed by the forward poses. A ball alone
does not cover its stem or the surrounding shoulder.

## Match checks to the selected mechanism

Use the mechanism's actual relative transforms and allowed coordinates. For a
hinge/swivel, activate only its rotation axis in the joint frame; the other two
intervals are `(0, 0)`. Check radial/axial fit, engagement, pin retention and stops
as applicable. A rotational sweep alone does not show that unintended sliding or
pull-out is restrained. For sliders, check the specified stroke, anti-rotation,
end retention and minimum guide engagement; for coupled mechanisms, sample the
coupling relation rather than an independent box of impossible poses.

The built-in motion helpers only cover fixed-pivot rotations. Sliding, helical,
offset-axis and general linkage motion need explicit transform generation plus
a compatible interference check and sweep/approximation bound. Independent samples
without such a bound are discrete evidence only. If that route is absent, report
unverified motion instead of claiming the angular helpers checked it.

Evaluate all relevant moving bodies, including an intermediate gimbal carrier or
separate pin. Use the clearance target appropriate to each function: intended
bearing/stop contact is different from the free gap around a cover. Locate intended
contact regions explicitly and verify unwanted interference elsewhere; do not
ignore a whole adjacent pair or cut away retention features to make a report pass.

## Built-in fixed-pivot rotation checks

`RotationGrid` uses `Rz @ Ry @ Rx` about a fixed world-space pivot. It covers
an Euler-angle box, not a spherical cone limit. A grid includes every Cartesian
combination of the three axes, interval endpoints and neutral angles when in
range. Checking each axis independently misses compound-rotation collisions.

For a tilted shoulder or other non-world-aligned joint, define a rigid
`world_from_joint` matrix explicitly. Transform the fixed and moving parts
with its inverse, then use a zero-pivot `RotationGrid` in that common local
frame. To display a pose, apply
`world_from_joint @ local_pose @ inverse(world_from_joint)` to the world mesh.
Record the frame matrix and label the angle domain as joint-local. Perform
STL round-trip validation in the **world** coordinate system used by the
printed files before transforming the checked geometry into the joint frame.

A moving arm must be checked against every relevant obstacle, including the
head, not only its adjacent torso. If the head is held neutral, state that;
separate one-joint sweeps do not cover coupled neck/shoulder poses. After
segmentation, require the intended component count on both sides: a forearm
sliver left with the torso is a segmentation defect, not permission to delete
it or report an assembly-ready part.

`clearance_envelope` uses convex sweep covers. With `cell_size_mm` it clips
an obstacle into spatial cells, builds a cover for each nonempty cell, and
unions those covers. This preserves concavities more closely than a single
whole-obstacle hull; it is still a conservative approximation, not a minimal
or exact swept volume. Smaller cells improve spatial fidelity at higher cost;
the runtime caps the bounding grid at 512 cells.

Between-sample padding uses `R * sum(delta_axis_radians**2 / 8)`, where each
delta is the largest angular cell width and R is that spatial cell's maximum
radius about the pivot. Linear interpolation of a rotation has operator-norm
error at most delta²/8. A telescoping product bounds the combined XYZ error by
the sum because rotations and their convex interpolants have norm at most one.
The interpolated vertex is a convex combination of sampled corner vertices,
so it is already inside the cover. Reversing order for inverse poses keeps the
same bound. The requested clearance, input geometry error and this bound are
added as a circumscribed padding cube. This covers the supplied obstacle and
domain, not obstacles omitted by the recipe.

Use a local obstacle; the hull of an entire model can erase the other part.
For a spherical joint, the invariant ball cavity and the swept stem have
separate roles. Check both; an excessively large torso hull can accidentally
hide a missing stem obstacle. Full final-geometry checks remain mandatory.
If simplifying a proxy, prove it contains the relevant geometry or include a
validated deviation allowance. `carve_clearance` intersects the envelope with
an allowed region and subtracts a protected region. It rejects changed
component counts, but does not measure minimum wall thickness. Validate the
remaining walls independently. Protection/clipping can defeat the original
clearance bound, so the final parts must undergo a fresh motion check.

## Reports and honest results

`check_motion` measures Boolean intersection volume in mm³ and surface gap in
mm for each sampled pose. A collision-volume tolerance is **not** a distance
tolerance. `min_gap` searches a bounded distance; a saturated result is marked
as a lower bound, not an exact global separation.

Before the final check, use `stl_roundtrip` on each printable part. This
serializes float32 STL and welds it as an importer would, requiring closed
positive-volume geometry and unchanged component counts. It returns that
geometry and a rounding audit. `write_mesh` also applies this gate; it never
repairs a failed export implicitly. Resolve local coincident sheets in source,
record the affected location and geometric change, and rerun the checks.

A result is `pass_sampled`, `fail` or `inconclusive`. Any kernel error prevents
a pass. An initially invalid solid aborts. Keep failing configuration coordinates
with units and the full sampled domain; show a failing/limiting pose and the
clearance cutter visually.

Suggested checks for an initial joint:

- Source and outputs: scale, closed surfaces, positive volume, component count.
- Joint: compare measured local installation space and derived parameters with
  actual integrated dimensions: ball/pin/shaft/guide size, fit gaps, engagement,
  retaining features, wall and attachment, as appropriate; validate authored STEP.
- Motion: neutral, extrema and intermediate configurations, combinations of
  independent freedoms or declared coupling, before/after overlaps and minimum
  separation. Record the coverage as discrete samples.
- Manufacturing: retained wall thickness, build orientation and coupon fit.
- Assembly: insertion path and required elastic deformation, separately from
  operational motion. Mark untested behavior; do not imply simulated assembly.

For more than one joint, define a kinematic tree and all relevant link pairs.
The two-body checker can evaluate specified relative poses but does not
 enumerate a multijoint configuration space or perform flexible-body FEA.

References: [Manifold solid operations](https://manifoldcad.org/docs/html/classmanifold_1_1_manifold.html)
and [Trimesh Boolean operations](https://trimesh.org/trimesh.boolean.html).

## Interactive Viewer handoff

When interactive review is requested, use a canonical URDF plus per-link mesh
assets and hand that file to CAD Viewer. Match the mechanism: one `revolute`
joint for a limited hinge/swivel, `continuous` only for actual unrestricted
rotation, `prismatic` for a guided translation, and `fixed` for a rigid connector.
A gimbal uses its real two axes and carrier. Do not turn every connector into
three virtual ball-joint axes. A screw/cam/linkage needs its actual coupling;
confirm viewer support before claiming independent sliders enforce that relation.

For a spherical joint using the local `Rz @ Ry @ Rx` domain, use a
Z-then-Y-then-X chain of revolute joints sharing the same pivot, with
geometry-free intermediate frames. Apply `world_from_joint` before the chain.
Either export the moving mesh in the final link frame, or document a fixed
`inverse(world_from_joint)` mounting frame for its original rest-frame mesh.
Convert angular limits to radians and prismatic travel to metres. Mechanical
stops/retention must exist in the geometry; URDF limits alone do not provide them.

Keep relative mesh assets inside the URDF folder for portable snapshot
resolution. Record mesh source paths, units and any frame transforms;
millimetre STL meshes use explicit `0.001` scale. Compare URDF FK to the mesh
recipe across the checked configurations. Sweep every slider through its limits
and inspect the actual geometry, not only changed controls or an XML validation pass.

The current Viewer exposes motion but does not run the mesh collision checker.
Continuous slider positions between checked samples remain unverified. Keep
head/other joints fixed if their coupled configurations were not checked, and
keep elastic insertion, holding torque and strength outside the preview claim.

## Preserving the sculpt

Compare original segmentation, joint stock addition, fit-cavity subtraction,
motion relief and any reinforcement as separate stages. Save positive and
negative differences and their volumes. Audit that changes outside the allowed
joint region stay within the explicit export error budget. Compare the same
neutral pose, camera and material: a posed arm or changed shading is not an
external-shape measurement.

A broad flat trim followed by a large collar can pass motion checks while
replacing the sculpt's intended shape. First revise local cutters and obstacle
coverage; add reinforcement only where an attachment/thickness measurement
requires it. Preserve the original exterior where possible. If the requested
travel requires a visible silhouette change, quantify and show it rather than
silently calling all removed material necessary clearance. Keep failed trials
out of the current deliverable and rerun thickness/attachment checks after the
final shape changes.
