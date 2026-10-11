# build123d modeling patterns

Read this file when constructing or repairing native CAD geometry. Model scripts
return build123d shapes; see the [model contract](step-generation.md) for
execution and composition.

## Selecting edges and faces

Select by the feature's geometry or datum (normal, axis, plane, position, curve
type), and re-select after an operation that changes the topology. Select a
fillet's or chamfer's edges from the solid it rounds, after that solid's last
operation: an operation returns new native topology wherever it changed the
solid, so an edge held from before may not be the solid's own. A fillet silently
skips such an edge (and fails when none is left); a chamfer fails on it. Shape
equality compares native handles, so `edge in solid.edges()` is true only for the
solid's own edge.

## Labels and assemblies

Native labels name exported parts and assembly occurrences, including repeated
placements such as `m3_screw:front_left`:

```python
# Inside an assembly model, after constructing and placing its parts:
base.label = "base"
lid.label = "lid"
assembly = bd.Compound(children=[base, lid], label="electronics_enclosure")
```

A feature fused into or cut from a body keeps no label of its own, and face and
edge names do not persist through STEP export. See [positioning](positioning.md)
for datums and joints, and [kinematics](kinematics.md) for motion.

## Colour and finish

Native `Color` channels are linear RGB; `cadgen.srgb` converts a display hex
value:

```python
from cadgen import srgb

body.color = srgb("#2E3742")
glass.color = srgb("#38414D", 0.42)
```

A group's colour colours the parts beneath it that have none of their own. Named
materials can also target a group and expand to its leaves:

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

Material keys are optional `name`, `baseColor` (`#RRGGBB`), `roughness`,
`metalness`, `clearcoat`, `clearcoatRoughness` and `opacity` (finite, 0..1).
Materials live in the sidecar and never change STEP colours or bytes; they
inherit through child composition and show in Render and GLB export, while the
normal CAD view keeps colour and opacity only.

## Placement and frame pitfalls

- **Rotation frame:** Euler-angle spelling does not reveal a local rotation axis;
  explicit direction vectors or an axis-angle construction make the frame clear.
  A valid loft can still join incorrectly oriented sections.
- **Primitive alignment:** `align=None` keeps the primitive's raw datum, not its
  centre: a cylinder is based at Z=0, a box starts at a corner.
- **Absolute versus relative placement:** `.located(loc)` replaces location;
  `.moved(loc)` and `Location * shape` compose it, so `.located()` after a
  rotation can discard the orientation.

```python
# A local box, rotated before placement:
box = bd.Solid.make_box(1, 1, 1)
rotated = box.rotate(bd.Axis.Z, 90)
placed = bd.Location((5, 0, 0)) * rotated  # retains the rotation
```

In build123d 0.11.1, a moved assembly compound's `intersect()` can traverse
unmoved `.children` although `.wrapped` carries the placement: extract the placed
`.solids()` first. `cadgen.geometry.overlap_volume` takes individual solids and
handles placement itself.

## Kernel pitfalls

- **Lofts:** sampled sections need consistent feature order, edge correspondence
  and orientation; equal sample counts alone do not guarantee it. A disconnected
  or self-crossing section produces misleading downstream loft failures, so check
  section wires as well as face validity. A ruled loft can localize a smooth-loft
  failure.
- **Many tools:** batching independent cuts avoids rebuilding the same
  intersection network; overlapping tools may need staged cuts, and oversized
  tool extents create needless intersections. On large spline surfaces even a
  batched cut can dominate a build; `--profile` finds it.
- **Near tangency or coincident boundaries:** a Boolean can return successfully
  with the wrong region or solid count; a direct profile construction of the same
  shape can avoid the intersection.
- **Tangent chains and complex outlines:** OCCT's 3D fillets can fail or crash
  there; a profile bevel or a separately constructed transition is a workaround.
- **2D algebra:** a `ShapeList` takes part in Python list operations, which may
  concatenate instead of fusing. Mirroring sampled points can flip wire winding
  and face normals, and an empty intersection used as a cut removes nothing.
- **Dense periodic splines:** OCP 7.9 has failed taper, inward offset and
  coincident-face fusion on some densely sampled profiles; a simpler
  representation or an explicitly constructed offset works around it.

## Validity and visual artifacts

Topology validity does not prove positive orientation, the requested shape, or
suitability for a later Boolean ([inspection](inspection-and-validation.md#geometry-diagnostics)).
A validity gate inside a model body (a retry ladder that keeps a fillet only when
the result is sound) uses `shape.is_valid` and `cadgen.geometry.is_sound`; each
check costs kernel time on every build. A periodic cylinder or revolved face has
a seam edge that appears in CAD linework; it is not a crack.
