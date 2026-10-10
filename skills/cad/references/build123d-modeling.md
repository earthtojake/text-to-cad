# build123d modeling patterns

Read this file when constructing or repairing native CAD geometry. Model scripts
return build123d shapes; decorators declare the output files. See the
[model contract](step-generation.md) for execution and composition.

## Selection and topology

An **occurrence** is a placed assembly node. Its geometry contains bodies,
faces, edges and vertices. For inspection, keep the canonical `ref` and
`occurrence_ref`; see [inspection](inspection-and-validation.md) for enumeration.
Numeric selectors belong to one saved revision.

For construction, select by the feature's geometry or datum where practical:
normal, axis, plane, position or curve type. Re-evaluate selections after an
operation that changes the relevant topology. Select a fillet's or chamfer's
edges from the solid it rounds, after that solid's last operation: an
operation returns new native topology wherever it changed the solid, so an
edge held from before it may not be the solid's own. A fillet silently skips
such an edge, and fails when none is left; a chamfer fails on it. Shape
equality is build123d's own and compares native handles, so
`edge in solid.edges()` is true only for the solid's own edge.

## Labels and assemblies

Native labels name exported parts and assembly occurrences, including repeated
placements such as `m3_screw:front_left`:

```python
# Inside an assembly model, after constructing and placing its parts:
base.label = "base"
lid.label = "lid"
assembly = bd.Compound(children=[base, lid], label="electronics_enclosure")
```

A feature fused into or cut from a body does not retain a separate occurrence
label, and face/edge names do not persist through STEP export.

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

- **Rotation frame:** Euler-angle spelling does not reveal a local rotation axis;
  the transformed basis of a non-global `Plane` does, and explicit direction
  vectors or an axis-angle construction make the intended frame clear. A valid
  loft can still join incorrectly oriented sections.
- **Primitive alignment:** `align=None` preserves the primitive's raw datum;
  it does not mean centered. For example, a cylinder is based at Z=0 while a
  box starts at a corner.
- **Absolute versus relative placement:** `.located(loc)` replaces location;
  `.moved(loc)` and `Location * shape` compose it, so `.located()` after a
  rotation can discard the orientation. A child model placed with `.moved()` or
  multiplication stays linked; `.located()` also loses the link.

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
copies of their placed geometry. An unexpectedly constant interference result
across poses is the symptom.

## Loft and sampled-profile pitfalls

Sampled sections need consistent feature order, edge correspondence and
orientation across stations. Twisting or rippling can be present in valid
geometry.

- Corresponding feature rails or consistent samples per band can prevent a
  feature from drifting between sections. Equal sample counts alone do not
  guarantee a correct loft.
- Independently easing every interval to zero slope can introduce unintended
  flat spots. Smooth measured noise only within the task's geometric tolerance.
- A disconnected or self-crossing section can produce misleading downstream
  loft failures; face validity alone does not show it. Increasing prefixes or
  adjacent section pairs can localize a failing region.
- A ruled loft can help diagnose a smooth-loft failure, but changes the surface:
  its faceting and continuity differ.
- For fields built by blending sampled component profiles, a component ending
  inside its neighbor may leave a steep wall; the blend function and continuity
  are the place to look before increasing sample density.

## Boolean and finishing pitfalls

Kernel behavior depends on topology, tolerances and the installed build123d/OCP
version.

- **Many tools:** batch independent cuts when that avoids repeatedly rebuilding
  the same intersection network. Overlapping tools may need staged operations;
  sequential cuts are legitimate when later features depend on earlier ones.
  Excessive tool extents create unnecessary intersections.
- **Large spline surfaces:** even batched cuts can be expensive. `--profile`
  or a stack sample localizes the expensive operation; simpler surfaces, smaller
  tool regions or a different construction of the same feature can follow.
- **Near tangency or coincident boundaries:** a successful return does not show
  the removed/added region or solid count. A direct profile construction may avoid
  an unstable Boolean intersection, when it describes the same shape.
- **Fillets and chamfers:** edge selection and local space decide them. Smaller
  radii, different feature ordering, grouped selections or a profile bevel are
  possible remedies, subject to the required dimensions.
- **Tangent chains or complex outlines:** some kernel versions fail or crash
  during finishing operations. A profile bevel or separately constructed
  transition is a workaround, not a ban on 3D fillets.
- **2D algebra:** a `ShapeList` participates in Python list operations, which may
  concatenate instead of fusing geometry. Mirroring sampled points can flip wire
  winding and face normals before an extrusion, and an empty intersection used as
  a cut removes nothing.
- **Dense periodic splines:** build123d 0.10/OCP 7.9 have shown failures in taper,
  inward offset and coincident-face fusion for some densely sampled profiles.
  Simplifying the representation, or constructing the offset/transition
  explicitly, works around them. Numerical offsets are an option, not a universal
  replacement for kernel offsets.

A feature that cannot be built as specified is a design decision for the user,
not a silent approximation.

## Validity and visual artifacts

Topology validity does not prove positive orientation, the requested shape, or
suitability for a later Boolean; see
[inspection](inspection-and-validation.md#geometry-diagnostics). A validity gate
inside a model body — a retry ladder that accepts a fillet only when the result
is sound, a stage check on a casting — uses build123d's `shape.is_valid` and
`cadgen.geometry.is_sound` (the `BRepAlgoAPI_Check` verdict, which also
identifies Boolean-suitability issues such as tiny edges). Each check costs
kernel time on every build.

A periodic cylinder or revolved face has a seam edge that appears in CAD
linework; it is not a crack.
