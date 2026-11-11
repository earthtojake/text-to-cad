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

A face or edge a person picked is named by a ref: `cad <type> inspect` says what it is
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
A transmissive part is one fade, never two, in every file of it: what draws transmission
(the viewer's Render and Solid, a GLB's path tracer) draws it opaque with its transmission,
and what draws none (Flat, X-ray, Parts, a snapshot, a 3MF) at that preview. The colour's
alpha does not fade it further; to fade it everywhere, give the look a PBR `opacity` below 1.

- **Leave air between glass and what lies behind it.** A see-through part lying on another (a
  window on its liner, two surfaces from one loft) draws mottled: each part is meshed on its own,
  to about a thousandth of its size, so their triangles cross. A gap wider than both meshes'
  error cures it: half a millimetre on an 80 mm part, a millimetre or two on a 400 mm one.
- **Smoked glass is a clear look with a tint, not a dark one that lets some light through.** A
  near-black colour with `transmission=0.35` draws as smoked glass in a snapshot, which fades it,
  and as a black surface where light is traced through it (the GLB in Blender): the colour
  tints what passes, and a third of nothing passes. Give it
  `transmission=1` and the tint as its colour (a mid grey).

```python
from bd_materials import metals
from cad.build123d import paint

body.material = metals.aluminum()
body.material.pbr = body.material.pbr.override(roughness=0.35, anisotropy=0.3)
body.color = "#2E3742"
insert.material = metals.brass()
polished = metals.aluminum()
polished.pbr = polished.pbr.override(roughness=0.15)
paint(body, body.faces().filter_by(bd.Axis.Z)[-1:], polished)
```

Each family is a module of `bd_materials` and each material a function of it (bd_materials 0.2):

- `metals`: `aluminum`, `stainless`, `mild_steel`, `alloy_steel`, `spring_steel`, `tool_steel`,
  `titanium`, `brass`, `copper`, `bronze`, `magnesium`, `gold`, `silver`
- `plastics`: `pla`, `petg`, `abs_`, `asa`, `nylon`, `pc`, `pp`, `pe`, `pom`, `ptfe`, `pmma`,
  `peek`, `pps`, `tpu`, `rubber`, `phenolic`, `fr4`, `cfrp`
- `resins`: `standard`, `tough`, `high_temp`, `flexible`, `transparent`, `castable`, `ceramic`, `esd`
- `wood`: `hardwood`, `softwood`, `oak`, `maple`, `walnut`, `birch`, `beech`, `ash`,
  `american_cherry`, `spruce`, `pine`, `engineered_wood`, `mdf`, `osb`
- `glass`: `soda_lime`, `borosilicate`; `paper`: `paper`, `cardboard`, `foamboard`;
  `textile`: `woven`, `felt`, `leather`

There is no `metals.steel()`: plain steel is `mild_steel()`. A grade is a name, as
`bd_materials.material_names()` lists them: `part.material = "alu_g6061_t6"`.

A part read from a STEP or an xbf keeps the file's colours until it is given a material, which
replaces its colour like any other part's, in the viewer and every export alike. To keep the
file's colour, set it again after the material: `color = part.color; part.material = plastics.pe();
part.color = color`. Faces the file paints (a cable's red and black wires) keep their colours
either way: the viewer draws them, and the GLB, the MJCF and the URDF all carry them.

A project's material is a native `FinishedMaterial`, with physics in `.material` and
appearance in `.pbr`. For custom physics, use the native `custom_metal` and other family
factories. Density is a single value in kg/m³; mechanical properties are native ranges,
with modulus in GPa and strength in MPa. `shape.mass()` defaults to grams; `cad <type> inspect` reports kilograms.
There is no text-to-cad material class or adapter. A measured weight is declared beside the
material, `mass(part, grams)` from `cad.build123d` ([kinematics](kinematics.md#declaring-for-a-simulator));
a simulator's contact friction is a choice made for the simulation, not declared on the model.

For boards, electronic parts and process finishes, which `bd_materials` lacks or draws poorly
untextured, `cad.build123d.materials` has named looks. Each returns a fresh native
`FinishedMaterial` (physics from `bd_materials`, a scalar look every renderer draws). A `color`
is a preset, a hex, a CSS name or an sRGB `(r, g, b)` of 0–1 floats; one colour is one material
whatever its spelling (`"grey"`, `"gray"` and `"RAL7016"` are `powder_coat_RAL7016_satin`), so
it is one BOM row. `zinc_plated` takes its passivation, not a colour. `substrate=` is the
`bd_materials` metal a finish is on: its physics are kept, its look replaced (`bead_blasted` on
an anodized part is bare aluminium).

```python
from cad.build123d import materials, paint

board.material = materials.soldermask("green")              # finish="matte" for a flat mask
paint(board, pads, materials.enig())
bracket.material = materials.powder_coat("RAL7016", finish="satin")
```

| Use for | Call |
| --- | --- |
| A board's body; its edge or a slot | `soldermask(color, finish="glossy"\|"matte")`, `soldermask_green()`, `soldermask_matte_black()`; `fr4()` |
| Markings, pads, joints | `silkscreen(color)`, `bare_copper(oxidized=False)`, `enig()`, `hasl(lead_free=True)`, `solder()` |
| IC packages, chip parts, LEDs | `mold_compound()`, `ceramic("white"\|"tan")`, `led_lens(color, diffused=False)` |
| Connector and switch bodies | `connector_housing(color)` (PBT-GF30) |
| Aluminium | `anodized(color)`, `anodized_black()`, `bead_blasted()` |
| Steel and stainless | `powder_coat(color, finish="matte"\|"satin"\|"gloss")`, `powder_coat_black()`, `brushed()`, `zinc_plated(passivation="clear"\|"blue"\|"yellow"\|"black")`, `black_oxide(oiled=True)` |

Prefer these to `bd_materials`' textured finishes (`bead_blast`, `brushed`, `zinc_plate`,
`tin_plate`), which draw flat at roughness 1 until textures are drawn.

`PbrProperties.override` returns an edited look. Its controls include `metalness`,
`roughness`, `ior`, `anisotropy`, `anisotropy_rotation`, `transmission`,
`attenuation_color`, `attenuation_distance`, `clearcoat`, `clearcoat_roughness`,
`emissive`, `emissive_intensity`, and `opacity`. Base colour floats are sRGB ratios;
emission and attenuation floats are linear. Hex strings avoid that ambiguity.
A shape's colour (`shape.color = ...`, build123d's own setter) takes a hex string (`"#f2f0ea96"`
with alpha), a colour name, a build123d `Color` or 0–1 sRGB floats `(0.95, 0.94, 0.92, 0.59)`; it
refuses 0–255 integers with OCCT's `Color out`. A paint (`paint(shape, faces, ...)`) takes those and
0–255 integers, `(242, 240, 234)` or four with alpha.

XBF keeps native physics and the resolved PBR data; GLB and the viewer retain the
appearance. STEP keeps name, density and colour. Native texture maps (every wood, cardboard
and CFRP in the catalogue, a finish such as `processes.mjf()`) are kept in XBF but not drawn
yet: the viewer, snapshots and GLB/3MF export draw the part in its material's scalar look (the
colour build123d's setter infers, metalness, roughness, transmission, ...) and name what they left out — a snapshot or
export warns `PART: Hardwood_ASH's color, normal and roughness maps not drawn: ...`, and `cad xbf
inspect` lists the parts under `textures`. Set the scalar values with `pbr.override(...)` when
the look matters. OCCT snapshots keep their documented appearance approximations.

## Placement and frame pitfalls

- **Rotation frame:** Euler-angle spelling does not reveal a local rotation axis;
  explicit direction vectors or an axis-angle construction make the frame clear.
  A valid loft can still join incorrectly oriented sections.
- **Primitive alignment:** `align=None` keeps the primitive's raw datum, not its
  centre: a cylinder is based at Z=0, a box starts at a corner.
- **Absolute versus relative placement:** `.located(loc)` replaces location;
  `.moved(loc)` and `Location * shape` compose it, so `.located()` after a
  rotation can discard the orientation.
- **A face's winding sets its extrusion:** `bd.extrude(face, h)` runs along the face's
  normal, so a `Polygon` whose points run clockwise (seen from +Z) faces -Z and extrudes
  down. Give the direction (`dir=(0, 0, 1)`) or list the points anticlockwise.

```python
# A local box, rotated before placement:
box = bd.Solid.make_box(1, 1, 1)
rotated = box.rotate(bd.Axis.Z, 90)
placed = bd.Location((5, 0, 0)) * rotated  # retains the rotation
```

In build123d 0.11.1, a moved assembly compound's `intersect()` can traverse
unmoved `.children` although `.wrapped` carries the placement: extract the placed
`.solids()` first. `cad.build123d.overlap_volume` takes individual solids and
handles placement itself.

## Kernel pitfalls

- **Build with build123d's constructions** (`bd.Cylinder`, not OCCT's
  `BRepPrimAPI_MakeCylinder`). The server keys and names build123d's operations, and
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
- **A smooth loft is one spline through all its sections,** so it goes where no section
  says: two sections added near the top of a 400 mm form moved its surface 77 mm near the
  bottom, and the result was still valid. Space sections evenly and carry a change in their
  values, not in more of them, or use `ruled=True`, which goes only where the sections say.
  A clearance is measured from the solid, never worked out from the sections.
- **A loft that ends in a `Vertex` ends in a cone point,** not a rounded cap, and on a blunt
  end it can stand millimetres past the point; rows added near the point to round it move
  the rest of the form. A shaded snapshot hides both and a render shows them.
- **A revolved polyline is one conical face a segment,** and a shaded picture draws a band
  for each. A profile that will be seen is arcs or a spline: one face. `EllipticalCenterArc`
  and `CenterArc` take `start_angle` and `arc_size`, not a start and an end angle.
- **Many tools:** batching independent cuts avoids rebuilding the same
  intersection network; overlapping tools may need staged cuts, and oversized
  tool extents create needless intersections. On large spline surfaces even a
  batched cut can dominate a run; split the body into `@memo` stages and the progress
  bar names the stage the time goes to.
- **Near tangency or coincident boundaries:** a Boolean can return successfully
  with the wrong region or solid count; a direct profile construction of the same
  shape can avoid the intersection. `is_valid` does not catch it, and `&`, `-` and `+`
  make no promise of their own: where a result on a lofted or spline solid matters, hold it
  to what it must be (its `bounding_box()` inside both operands', its volume near the one
  expected) before building on it.
- **Tangent chains and complex outlines:** OCCT's 3D fillets can fail or crash
  there; a profile bevel or a separately constructed transition is a workaround.
- **2D algebra:** a `ShapeList` takes part in Python list operations, which may
  concatenate instead of fusing. Mirroring sampled points can flip wire winding
  and face normals, and an empty intersection used as a cut removes nothing.
- **A Boolean that removes everything** returns an empty `Compound` (`&` of two `Solid`s
  returns None), and placing that (`bd.Pos(...) * empty`) returns a plain empty `list`, so the
  next line fails with `'list' object has no attribute 'label'`: the cut before it consumed
  the part. An empty one among an assembly's children (`Compound(children=[...])`) fails with a
  bare `AssertionError` from the tree. Test `result.solids()` before labelling or placing a
  Boolean's result.
- **Dense periodic splines:** OCP 7.9 has failed taper, inward offset and
  coincident-face fusion on some densely sampled profiles; a simpler
  representation or an explicitly constructed offset works around it.
- **Meshes are not B-rep:** a triangulated face (`import_stl`, `Mesher`) cannot go
  in a document. Read a scan with `stl.read` and build B-rep from its numbers.

## Validity and visual artifacts

Topology validity does not prove positive orientation, the requested shape, or
suitability for a later Boolean ([inspection](inspection-and-validation.md#geometry-diagnostics)).
A validity gate inside a model body (a retry ladder that keeps a fillet only when
the result is sound) uses `shape.is_valid` and `cad.build123d.is_sound`; each
check costs kernel time when its body runs. A periodic cylinder or revolved face has
a seam edge that appears in CAD linework; it is not a crack.
