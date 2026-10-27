# build123d modeling patterns

Read this file when constructing or repairing native CAD geometry. Models return
build123d shapes; see [models](model-contract.md) for how they run and compose.

## Contents

- [Selecting edges and faces](#selecting-edges-and-faces)
- [Labels and assemblies](#labels-and-assemblies)
- [Colour and materials](#colour-and-materials)
- [Placement and frame pitfalls](#placement-and-frame-pitfalls)
- [Kernel pitfalls](#kernel-pitfalls)
- [Validity and visual artifacts](#validity-and-visual-artifacts)

## Selecting edges and faces

Select by the feature's geometry or datum (normal, axis, plane, position, curve
type), and re-select after an operation that changes the topology. Select a
fillet's or chamfer's edges from the solid it rounds, after that solid's last
operation: an operation returns new native topology wherever it changed the
solid, so an edge held from before may not be the solid's own. A fillet silently
skips such an edge (and fails when none is left); a chamfer fails on it. Shape
equality compares native handles, so `edge in solid.edges()` is true only for the
solid's own edge.

A face or edge a person picked is named by a ref: `cadgen inspect` says what it is
and which code made it, and the body picks the same element with build123d's
selectors ([a picked element in a model's body](inspection-and-validation.md#a-picked-element-in-a-models-body)).

## Labels and assemblies

A label names a part, an assembly or a placement: in refs, the viewer's tree, the
STEP's instances and the GLB's nodes.

```python
# Inside an assembly model, after constructing and placing its parts:
base.label = "base"
lid.label = "lid"
screws = [bd.Pos(x, y, 30) * screw for x, y in HOLES]
for placed in screws:
    placed.label = "m3_screw"          # siblings sharing a label are m3_screw.1, m3_screw.2, ...
fasteners = bd.Compound(children=screws, label="fasteners")
assembly = bd.Compound(children=[base, lid, fasteners], label="electronics_enclosure")
```

A feature fused into or cut from a body keeps no label of its own; a label on a
shape names the elements later features make of it (`f:boss.3` in `plate + boss`).
Elements are named by the code that made them, and the names travel with the
document into its STEP ([element names](inspection-and-validation.md#element-names)).
See [positioning](positioning.md) for datums and joints, and
[kinematics](kinematics.md) for motion.

## Colour and materials

Use build123d's native `bd_materials` objects. Set materials after geometric operations,
then set any explicit colour: build123d's material setter also sets colour. A transmissive
material infers preview alpha (`transmission=1` gives `0.3`), even with PBR `opacity=1`.
For an opaque base colour with physical transmission, assign an opaque `body.color`
after its material.

```python
from bd_materials import metals
from cadgen import paint

body.material = metals.aluminum()
body.material.pbr = body.material.pbr.override(roughness=0.35, anisotropy=0.3)
body.color = "#2E3742"
insert.material = metals.brass()
polished = metals.aluminum()
polished.pbr = polished.pbr.override(roughness=0.15)
paint(body, body.faces().filter_by(bd.Axis.Z)[-1:], polished)
```

A project's material is a native `FinishedMaterial`, with physics in `.material` and
appearance in `.pbr`. For custom physics, use the native `custom_metal` and other family
factories. Density is a single value in kg/m³; mechanical properties are native ranges,
with modulus in GPa and strength in MPa. `shape.mass()` defaults to grams; `cadgen inspect` reports kilograms.
There is no cadgen material class, catalogue or adapter.

`PbrProperties.override` returns an edited look. Its controls include `metalness`,
`roughness`, `ior`, `anisotropy`, `anisotropy_rotation`, `transmission`,
`attenuation_color`, `attenuation_distance`, `clearcoat`, `clearcoat_roughness`,
`emissive`, `emissive_intensity`, and `opacity`. Base colour floats are sRGB ratios;
emission and attenuation floats are linear. Hex strings avoid that ambiguity.
Shape colours and plain paints also accept 0–255 integers and build123d `Color`.

XBF keeps native physics and the resolved PBR data; GLB and the viewer retain the
appearance. STEP keeps name, density and colour. Native texture maps are preserved in
XBF; the viewer, GLB export and snapshots refuse them until UV mapping is supported.
Use scalar PBR looks for those paths. OCCT snapshots keep their documented appearance approximations.

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

- **Build with build123d's constructions** (`bd.Cylinder`, not OCCT's
  `BRepPrimAPI_MakeCylinder`). The engine keys and names build123d's operations, and
  of the OCCT makers a model drives itself only the transforms, `BRepBuilderAPI_Copy`,
  `ShapeFix_Shape`, `ShapeUpgrade_UnifySameDomain` and `BRepFilletAPI_MakeFillet`; a
  body built with another cannot be replayed. Where build123d has no construction for
  it (a hand-built B-spline surface), make that shape in a `@memo` function of values
  that returns it as OCCT made it, with no build123d operation on it inside: the call
  keys it, and what the model makes of it replays.
- **Lofts:** sampled sections need consistent feature order, edge correspondence
  and orientation; equal sample counts alone do not guarantee it. A disconnected
  or self-crossing section produces misleading downstream loft failures, so check
  section wires as well as face validity. A ruled loft can localize a smooth-loft
  failure.
- **Many tools:** batching independent cuts avoids rebuilding the same
  intersection network; overlapping tools may need staged cuts, and oversized
  tool extents create needless intersections. On large spline surfaces even a
  batched cut can dominate a run; split the body into `@memo` stages and the progress
  bar names the stage the time goes to.
- **Near tangency or coincident boundaries:** a Boolean can return successfully
  with the wrong region or solid count; a direct profile construction of the same
  shape can avoid the intersection.
- **Tangent chains and complex outlines:** OCCT's 3D fillets can fail or crash
  there; a profile bevel or a separately constructed transition is a workaround.
- **2D algebra:** a `ShapeList` takes part in Python list operations, which may
  concatenate instead of fusing. Mirroring sampled points can flip wire winding
  and face normals, and an empty intersection used as a cut removes nothing.
- **A Boolean that removes everything** returns an empty `Compound` (`&` returns None),
  and placing that (`bd.Pos(...) * empty`) returns a plain empty `list`, so the next line
  fails with `'list' object has no attribute 'label'`: the cut before it consumed the part.
- **Dense periodic splines:** OCP 7.9 has failed taper, inward offset and
  coincident-face fusion on some densely sampled profiles; a simpler
  representation or an explicitly constructed offset works around it.
- **Meshes are not B-rep:** a triangulated face (`import_stl`, `Mesher`) cannot go
  in a document. Read a scan with `read_mesh` and build B-rep from its numbers.

## Validity and visual artifacts

Topology validity does not prove positive orientation, the requested shape, or
suitability for a later Boolean ([inspection](inspection-and-validation.md#geometry-diagnostics)).
A validity gate inside a model body (a retry ladder that keeps a fillet only when
the result is sound) uses `shape.is_valid` and `cadgen.geometry.is_sound`; each
check costs kernel time when its body runs. A periodic cylinder or revolved face has
a seam edge that appears in CAD linework; it is not a crack.
