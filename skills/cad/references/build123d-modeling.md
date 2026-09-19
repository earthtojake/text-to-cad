# build123d modeling patterns

Read this file when constructing or repairing native CAD geometry. Model scripts
return build123d shapes; decorators declare the output files. See the
[model contract](step-generation.md) for execution and composition.

## Construction choices

Choose a construction that expresses the controlling dimensions directly and
preserves the intended geometry. Builder contexts and algebraic modeling are
both valid; profile operations, solid features and surface construction suit
different shapes. The examples and remedies below are options, not a required
feature sequence.

Use meaningful parameters and functional datums. Keep separately manufactured
or moving parts identifiable in an assembly; fuse bodies where the design calls
for one continuous part. Prefer solids for physical parts, but do not close or
thicken surfaces when the user requested surface geometry.

Operation order depends on the design. Applying finishing features late often
makes selectors simpler; constructing them in a profile can be more robust for
some outlines. Through-cut tools should span the intended material; choose any
extra extent relative to the geometry and nearby features, not a fixed distance.

## Selection and topology

An **occurrence** is a placed assembly node. Its geometry contains bodies,
faces, edges and vertices. For inspection, keep the canonical `ref` and
`occurrence_ref`; see [inspection](inspection-and-validation.md) for enumeration.
Numeric selectors belong to one saved revision.

For construction, select by the feature's geometry or datum where practical:
normal, axis, plane, position or curve type. Re-evaluate selections after an
operation that changes the relevant topology.

During a cadgen build, geometric equality and hashing can recognize equivalent
reconstructed subshapes rather than requiring the same native handle. Coincident
identical shapes may compare equal; this is not persistent feature identity or
proof that a selected edge survived an operation unchanged. The installed
cadgen package's `MEMO.md` describes that behavior.

## Labels and assemblies

Use concise, meaningful native labels on exported parts and assembly occurrences,
including repeated placements such as `m3_screw:front_left`:

```python
# Inside an assembly model, after constructing and placing its parts:
base.label = "base"
lid.label = "lid"
assembly = bd.Compound(children=[base, lid], label="electronics_enclosure")
```

Labels describe role or placement; they need not repeat topology categories.
A feature fused into or cut from a body does not retain a separate occurrence
label. Keep its intent in parameters, construction datums and geometric checks.
Do not promise persistent face/edge names through STEP export.

See [positioning](positioning.md) for assembly datums, joints, explicit transforms
and checks of saved mating relationships. Source joints position geometry;
[kinematics](kinematics.md) separately declares motion for the viewer.

## Colour and finish

Native `Color` channels are linear RGB. Use `cadgen.srgb` for a colour specified
as a display hex value:

```python
from cadgen import srgb

body.color = srgb("#2E3742")
glass.color = srgb("#38414D", 0.42)
```

Set native colour on leaf occurrences: a colour on a group compound does not
propagate to its leaves in the render tree. Named material assignments can target
a group and expand to its leaves:

```python
@step(materials={
    "definitions": {
        "cast": {"name": "As-cast steel", "roughness": 0.85, "metalness": 0.2},
        "ground": {"name": "Ground steel", "roughness": 0.25, "metalness": 0.9},
    },
    "assignments": [
        {"targets": ["#housing"], "material": "cast"},
        {"targets": ["#journal"], "material": "ground"},
    ],
})
def gearbox():
    ...
```

Material keys are optional `name`, `baseColor`, `roughness`, `metalness`,
`clearcoat`, `clearcoatRoughness`, and `opacity`. Numeric channels are finite
0..1 values; `baseColor` is `#RRGGBB`. STEP's sidecar carries these finishes;
`baseColor` does not change STEP colours or geometry bytes. Finishes inherit
through cached child composition and are consumed by Render and GLB export.
Normal CAD display keeps colour/opacity with workbench shading. Dynamically
setting `cad_material` is unsupported.

## Placement and frame pitfalls

- **Rotation frame:** do not infer a local rotation axis from Euler-angle
  spelling. Check the transformed basis for a non-global `Plane`; explicit
  direction vectors or an axis-angle construction can make the intended frame
  clearer. A valid loft can still join incorrectly oriented sections.
- **Primitive alignment:** `align=None` preserves the primitive's raw datum;
  it does not mean centered. For example, a cylinder is based at Z=0 while a
  box starts at a corner. Set alignment deliberately when placement depends on it.
- **Absolute versus relative placement:** `.located(loc)` replaces location;
  `.moved(loc)` and `Location * shape` compose it. Applying `.located()` after
  a rotation can therefore discard the orientation. For placed child models,
  use `.moved()` or multiplication to preserve shared geometry; `.located()`
  copies it and loses the child link. Absolute placement remains a native API
  option when replacement and copying are actually intended.

```python
# A local box, rotated before placement:
box = bd.Solid.make_box(1, 1, 1)
rotated = box.rotate(bd.Axis.Z, 90)
placed = bd.Location((5, 0, 0)) * rotated  # retains the rotation
```

In build123d 0.11.1, a moved assembly compound's `intersect()` can traverse
unmoved `.children` despite `.wrapped` carrying the correct placement. Extract
placed `.solids()` or operate on the placed OCCT shapes when affected.
`cadgen.geometry.overlap_volume` takes individual solids and queries private
copies of their placed geometry. Check the actual pose when diagnosing an
unexpectedly constant interference result.

## Loft and sampled-profile pitfalls

For sampled sections, keep feature order, edge correspondence and orientation
consistent across stations. Twisting or rippling can be present in valid
geometry, so check the intended sections and review the surface.

- Corresponding feature rails or consistent samples per band can prevent a
  feature from drifting between sections. Equal sample counts alone do not
  guarantee a correct loft.
- Independently easing every interval to zero slope can introduce unintended
  flat spots. Choose interpolation for the desired continuity. Smooth measured
  noise only within the task's geometric tolerance.
- A disconnected or self-crossing section can produce misleading downstream
  loft failures. Inspect section wires as well as face validity. Increasing
  prefixes or adjacent section pairs can localize a failing region.
- A ruled loft can help diagnose a smooth-loft failure, but changes the surface;
  use it as a replacement only if its faceting and continuity meet the design.
- For fields built by blending sampled component profiles, a component ending
  inside its neighbor may leave a steep wall. Inspect the blend function and
  continuity before increasing sample density. Adjust component overlap or the
  blend only if it preserves the required boundary.

## Boolean and finishing pitfalls

Kernel behavior depends on topology, tolerances and the installed build123d/OCP
version. Diagnose the failing operation before changing the construction.

- **Many tools:** batch independent cuts when that avoids repeatedly rebuilding
  the same intersection network. Overlapping tools may need staged operations;
  sequential cuts are legitimate when later features depend on earlier ones.
  Restrict excessive tool extents when they create unnecessary intersections.
- **Large spline surfaces:** even batched cuts can be expensive. Localize the
  expensive operation with timing or a stack sample, then consider simpler
  surfaces, smaller tool regions or a different construction of the same feature.
  A groove's screen size is not a reason to remove it from the CAD model.
- **Near tangency or coincident boundaries:** inspect the removed/added region
  and solid count, not only a successful return. A direct profile construction
  may avoid an unstable Boolean intersection, when it describes the same shape.
- **Fillets and chamfers:** check selected edges and available local space.
  Smaller radii, different feature ordering, grouped selections or a profile
  bevel are possible remedies, subject to the required dimensions. Do not
  silently reduce or omit a specified feature through a retry ladder.
- **Tangent chains or complex outlines:** some kernel versions fail or crash
  during finishing operations. Isolate a reproducible case; a profile bevel or
  separately constructed transition is a workaround, not a ban on 3D fillets.
- **2D algebra:** inspect intermediate types. A `ShapeList` participates in
  Python list operations, which may concatenate instead of fusing geometry.
  Check wire winding/face normals before extrusion, especially after mirroring
  sampled points. Confirm an intersection is nonempty before using it as a cut.
- **Dense periodic splines:** build123d 0.10/OCP 7.9 have shown failures in taper,
  inward offset and coincident-face fusion for some densely sampled profiles.
  If reproduced, simplify the representation or construct the offset/transition
  explicitly and verify its distance, continuity and topology. Numerical offsets
  are an option, not a universal replacement for kernel offsets.

Preserve the requested geometry while repairing it. If an exact feature cannot
be built, report the limitation or seek a design decision rather than quietly
substituting an approximation.

## Validity and visual artifacts

Topology validity does not prove positive orientation, the requested shape, or
suitability for a later Boolean. Check signed volume per intended solid;
aggregate volumes can hide inverted members. Open shells are legitimate when
surfaces were requested.

Use `cadgen.geometry.topology_errors`, `boundary_edges` and, when relevant,
`self_intersections` on saved geometry. During a failing construction, check
intermediates around the suspect operation. `BRepAlgoAPI_Check` can additionally
identify Boolean-suitability issues such as tiny edges; there is no need to run
an expensive diagnostic after every simple operation. Any repair must preserve
the dimensions being checked. See [inspection](inspection-and-validation.md).

A periodic cylinder or revolved face has a seam edge that may appear in CAD
linework. Use shaded display or another camera to distinguish a display seam
from a crack. Do not rotate a finished, datum-constrained part solely to hide
its seam.

For further failure diagnosis and before/after checks, see [repair loop](repair-loop.md).
