# Curved seams and smooth motion relief

A plane is one segmentation tool, not the default shape of a finished joint.
Treat **part ownership**, **motion clearance**, and **edge finishing** separately.
A smooth cutter does not choose a good visible seam or guarantee thick lips.

## Start from the required motion

Record a path or an allowed joint domain. A single animation path does not
cover a freely movable ball joint; use the full intended combinations of its
axes. Include the actual stem, hood and attachment geometry, not just the ball.

For moving solid B and rigid poses T(q), its forward occupied volume is the
union of T(q)B over the declared domain. Its outer boundary is a motion envelope.
Subtract an expanded local portion of that volume from the fixed part. To cut
the moving part, sweep the fixed obstacle using inverse poses instead. A
clearance offset, geometric approximation and between-pose allowance have
different meanings; record them separately.

`clearance_envelope` currently constructs conservative convex or partitioned
covers for fixed-pivot rotation domains, not arbitrary kinematics or an exact
analytical sweep. Translation or coupled motions require a compatible envelope
implementation; the rotation helper's padding is not their error bound.
Its facets/partition joins can leave angular cuts. Smoothing this cover cannot recover material it already
unnecessarily includes. To reduce that overcut, improve obstacle localization,
partitioning or the sweep approximation first and revalidate coverage.

## Design a curved parting boundary

Use sculpt creases, an overlapping hood, a spherical patch or an authored
spline/implicit surface where it suits the anatomy and assembly. Convert a
cutting surface into a closed regional volume before mesh booleans. Split the
stock into complementary ownership regions, introduce the seam gap, then add
motion relief. Keep unrelated appendages out of the region.

The motion envelope constrains this boundary; it does not determine a unique
parting surface. A region clipped with a hard plane remains a hard boundary
even when the enclosed cutter is smooth. Blending with a protective region or
original exterior needs its own transition design and attachment/thickness
check. Do not label a smooth cavity as a fully smooth exterior seam.

## Smooth a cutter explicitly

The optional `cadgen[organic,organic-smooth]` API provides
`smooth_clearance_envelope(envelope, pitch_mm=..., sigma_mm=..., outset_mm=...)`.
The extra declares VTK; no whole-model remesh is implicit in mesh/CAD integration.

It samples signed distance to the existing cutter, applies a Gaussian filter,
and extracts an offset isosurface. `pitch_mm` is the grid spacing;
`sigma_mm` controls filtering scale; `outset_mm` is the field threshold, **not**
a guaranteed maximum surface displacement. These are explicit design and
approximation choices, not printer-calibrated fit values.

A smoothed solid can shrink. The helper rejects a result if Boolean subtraction
finds missing input-cutter volume above `volume_tolerance_mm3`, or its component
count changes. This checks the discretized input mesh up to a volume tolerance,
not a continuous-motion or Hausdorff bound. Do not casually raise the tolerance
to make it pass. If it fails, revise the smoothing/offset/resolution within the
allowed material budget and document the new choice.

Only remesh the cutter. Preserve the organic exterior and exact joint surfaces
through restricted booleans. Use `carve_clearance` with an allowed region and
protected mechanical stock, then quantify additional removed material relative
to the unsmoothed result. Thin sheets or coincident contact surfaces exposed by
STL rounding are failures: change the source boundary/protection explicitly,
not a silent repair or a larger pass tolerance.

## Acceptance evidence

- Inspect the curved cutter, its intersection with the part, and the neutral
  before/after parts at the same scale, pose, camera and material.
- Report smoothing parameters, grid budget, added cutter volume, extra removed
  part volume, protected-feature loss and changes outside the allowed region.
- Validate STL round-trip topology, components, walls and attachments, then
  repeat the complete assembled motion check on the resulting geometry.
- Inspect the visible rim separately. A smoother void can remove more material
  and make an edge thinner. Design its radius/overlap/minimum thickness rather
  than smoothing the whole sculpt to hide it.
- A passing motion cut does not establish assembly insertion, elasticity or
  printability. Preserve those unresolved outcomes in the handoff.

References: [VTK signed distance](https://vtk.org/doc/nightly/html/classvtkImplicitPolyDataDistance.html),
[implicit-field sampling](https://vtk.org/doc/nightly/html/classvtkSampleFunction.html),
and [Manifold geometry operations](https://manifoldcad.org/docs/html/classmanifold_1_1_manifold.html).
