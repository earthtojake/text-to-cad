# Materials

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

Materials are build123d's native `bd_materials.FinishedMaterial` objects. Import the
catalogue and finishes from `bd_materials`; the library defines no material class and does not
replace `Shape.material`. For what that catalogue lacks it ships named looks,
`cad.build123d.materials` (`build123d/materials.py`): boards and their parts (`soldermask`, `fr4`,
`silkscreen`, `bare_copper`, `enig`, `hasl`, `solder`, `mold_compound`, `ceramic`, `led_lens`,
`connector_housing`) and process finishes (`anodized`, `powder_coat`, `bead_blasted`, `brushed`,
`zinc_plated`, `black_oxide`), with presets (`soldermask_green`, `soldermask_matte_black`,
`anodized_black`, `powder_coat_black`). Each factory returns a fresh `FinishedMaterial` built from
bd_materials' own classes, never a subclass, so a release that knows none of these reads them
(`material_from_json`'s closed set): the physics bd_materials' table renamed for the look (its FR-4,
copper, 6061-T6, 304 stainless, mild steel, or the `substrate=` metal a finish is on) or a
`custom_metal`, `custom_plastic` or `SolidMaterial` of its own (SAC305, moulding compound, alumina,
clear epoxy, PBT-GF30), and a scalar `PbrProperties` look, no texture map. bd_materials' own textured
finishes (`bead_blast`, `brushed`, `zinc_plate`, `tin_plate`) draw untextured as a flat roughness 1.

A GLB names each material by its look (`pbr.name`: `frame_black`, `anodized_black`), not by the physical
material the look is of: two looks of one aluminium are two materials of two names, and what reads the file
(Blender, `cad.blender`) finds a look by the name the model gave it. The physical material's name rides
beside it, `extras.cad.material` (`Alu_G7075_T6`), which Blender reads as the material's custom property
(`export/glb.py`'s `_material`).

```python
from bd_materials import metals
from cad.build123d import paint

housing.material = metals.aluminum(metals.Alu.G6061_T6)
housing.material.pbr = housing.material.pbr.override(
    roughness=0.35, anisotropy=0.3, clearcoat=0.2, clearcoat_roughness=0.1)
housing.color = "#606b78"  # assign after material: build123d's setter sets colour
paint(housing, housing.faces().sort_by(bd.Axis.Z)[-1], metals.copper())
```

**What a model declares for a robot description.** Beside its material, a part may say what a robot
description needs that geometry does not decide, each a fact of the machine (`cad.build123d`'s `body`, `frame`,
`free`, `limits`, `link`, `mass`, `point_mass`): `frame(part, "tool", bd.Pos(160, 0, 25))` (in the part's own frame,
before its placement); `body(part, name=None)`, a body of its own fixed to the link it would merge into;
`limits(assembly, "elbow", effort=27, velocity=6.28)` (N*m or N, rad/s or m/s), kept on the part that holds each
revolute or linear joint of that label; `mass(shape, grams)`, what a part or an assembly weighs in all, its solids
keeping their densities' ratios (one density where none has one) and scaled alike to make it up, an inner
declaration fixing its own subtree and an outer one scaling only the solids no inner one holds (`describe.py`'s
**Mass**, which refuses a total its point masses and inner masses reach, or one its solids have no volume to
carry); `point_mass(part, grams, at, name=, inertia=)`, a lump at a point in the part's own frame that every `mass`
above it counts; `free(shape)`, a base not bolted to the world (each link hung from the world that holds a part at
or below it floats); and `link(shape, name)`, the name of the link its parts make. ISO 10303-105 bounds no drive and
has no ground that floats, so `limits` and `free` are facts of the machine that are not kinematics, kept here and
not in the mechanism (law 12). How a simulator collides a part, which pairs never collide, contact friction and a
joint's dynamics are a simulation's choices, made in a MuJoCo function (`cad.mujoco`), never declared on the
model. All travel with the prototype, in the structure (`frames`, and `body`, `drives`, `mass` -- each declaration
at or above the part, as levels above it and grams --, `pointMasses`, `free` -- the levels above the part declared
free -- and `link` -- each name at or above the part, as levels above it and the name -- where declared) and the xbf
(a JSON string under `DECLARATIONS_GUID` on the part's label, written only where a part declares something), and
two parts that differ only in them are two prototypes. The robot description reads them (`describe.py`: a body a
link on a fixed joint, a drive a joint's `effort` and `velocity`, the masses and point masses each link's inertial,
a free node a `floating` joint from the ground, a link name the link's), and gives each part its own mesh as its
collision. An MJCF export writes a collision geom of each part's mesh (MuJoCo collides it as its convex hull),
sites, child bodies, `<contact><exclude>` for every pair that touches at rest across a moving joint
(`export/contact.py`), `actuatorfrcrange`, and a free base's `<freejoint>` (its seven values in every key); a URDF a
fixed joint and a link, `<limit>`'s effort and velocity, a `<collision>` of each part's mesh, its root the free
base, and an empty `base_link` before a root that has a mass (KDL takes no inertia on the root) or whose frame is
not the world's (its first part's own frame, turned or moved), at the root's placement, so every link stands where
the MJCF stands it. Each writer keeps links and joints in a namespace each, as MJCF and URDF do, and says a rename
in its kind (`export.note`, the export's log).

**The zero, the scene and what an export says** (`describe.py`'s **The zero**, `export/mjcf.py`'s **The
scene**, `Description.summary`). An export to an MJCF or a URDF may name a mechanism state (`--zero`,
`zero=`; `export.zero_of` refuses one for any other kind, the daemon forwards it, a worker's row says it,
and the client refuses a server that wrote without it): the description is taken there, each joint's
origin moved by its value at the state, its limits, as-built value and coupling offset with it, and the
poses around it. A name no state has is refused, the states named. An MJCF export writes Menagerie's
`scene.xml` beside the robot where none is (an `include` of it, a `statistic`, a floor at or below its
lowest point, a light, a skybox, MuJoCo's built-in textures alone) and never writes over one, saying
which in the export's log. Each robot writer says what its file holds (`export.described`): `translate`
hands the description's summary, with the notes the file was written with, to the worker, whose row
carries it as `robot`; `said.robot` puts it in a line or two on stderr after the file's line, and
`--json` gives the row's `robot`. The description's warnings are notes of the file, so they are the
export's log lines.

**Couplings and loops in a robot description** (`describe.py`, `description.py`'s **Loops**). A
coupling's joints follow its first-named one; a virtual pinion is no link or joint, so its racks
follow the first of them by the ratio of their ratios: MJCF writes the follower's `<equality><joint
polycoef="0 r 0 0 0">`, URDF its `<mimic multiplier="r">`, and the file has the one control the
hardware has. A mechanism whose pairs close a loop is described as a tree and its closures: the
pairs followed from the ground breadth first in the mechanism's pair order, and each pair that
reaches a link the tree holds already a `Closure` (its frame on each of its two links, the two
checked to coincide as built within the tolerance the harvest reads every pair to, else refused by
name). A closure that would be a slide is traded for its loop's revolute or ball pair nearest it, as
MuJoCo has no slide equality. The MJCF writes each closure as a site on each body
(`<name>/1`, `<name>/2`) and `connect` equalities of them: one for a ball, two for a hinge (the
second pair of sites `export.mjcf.AXIS_SPAN` along the axis), so the point and the axis's direction
are held and the turn is free; its range is not enforced, and said; `contact` excludes its two
bodies where they touch at rest. The URDF leaves a closure out and says so; the viewer's
`<tcad:four_bar>` is never generated. A mechanism state that moves a joint of a loop is left out of
the description's poses, and `ranges` sweeps no joint of a loop.

`FinishedMaterial.material` is the native physical dataclass; `.pbr` is a native
`threejs_materials.PbrProperties`. Catalogue factories return fresh finished materials.
For a project's own material, use a native factory such as `metals.custom_metal`, or
`FinishedMaterial(RangeMaterial(name="Coating", density=None), pbr=PbrProperties.create(
"Coating", color="#202830", roughness=0.7))`. Unknown density remains unknown in
inspection. Assign materials and paints after geometric operations. Native material
assignment infers a preview alpha for transmission (`transmission=1` gives `0.3`), even
when its PBR `opacity=1`. A transmissive look (`transmission` above zero) is one fade, never two, and
the same part looks the same whichever file of it is opened. What draws transmission draws the part at
alpha 1 with it, so a path tracer refracts the part and does not also fade it: a GLB writes the look
`OPAQUE` at alpha 1, and the viewer's Render and its shaded modes (which keep a material's finish) draw an
xbf's part, and a GLB's, so. The one exception is a PBR `opacity` below 1, an author's fade, drawn at that
alpha everywhere (a GLB writes it `BLEND`). A translucent shape colour on a transmissive look is not one:
the document holds only the colour's value, and an inferred preview cannot be told from it (the same value
by hand, or a preview left from the transmission before a later `pbr.override`). What draws no
transmission draws the preview instead, once: the same inference, `max(0.15, 1 - 0.7 * transmission)`, or
the author's fade (`formats/gltf.py`'s `preview_alpha`, the viewer's `previewOpacity.js`), in the viewer's
Flat, X-ray and Parts, an OCCT still of an xbf or a GLB (`render/finish.py`), and the colour of a 3MF,
written from an xbf or converted from a GLB (`export/threemf.py`; both through `formats/gltf.py`'s
`drawn_alpha`, so the two give the same bytes). Native assignments,
inheritance and copying follow build123d; a child whose inherited value has already been
read can retain that cached value, so assign assembly materials before reading children.

**Physics and units.** Density is a single value in kg/m³. Mechanical properties use native
`Range` values with bounds, rather than the library choosing a single typical number: modulus of elasticity is GPa, tensile and yield
strengths are MPa. `bd_materials.core.PROPERTY_UNITS` defines the other units. A native
physical material's `mass(volume_mm3)` and build123d's default `shape.mass()` return grams;
`cad <type> inspect` continues to report kilograms. `None` is unknown; the native
`NOT_SUITABLE` range is distinct and survives XBF serialization.

**Appearance.** Use `material.pbr.override(...)` to return an edited native look, then
assign it to `material.pbr`. The existing controls use their native PBR names:
`metalness`, `roughness`, `ior`, `anisotropy`, `anisotropy_rotation` (radians),
`transmission`, `attenuation_color`, `attenuation_distance` (metres), `clearcoat`,
`clearcoat_roughness`, `emissive`, `emissive_intensity`, and `opacity`. Base `color` floats
are sRGB ratios; emission and attenuation floats are linear RGB. Hex strings are converted
by the upstream library. Shape colours keep build123d's sRGB inputs (a hex string, a name, a
`Color`, 0–1 floats: its setter refuses 0–255 integers), and plain face paints take sRGB hex, 0–255
integers and a build123d `Color`; documents and glTF base factors use linear RGB.

XBF stores the native physical dataclass, the complete resolved PBR data, including
embedded textures and texture transforms, and the part's declared manufacturing process
(`process=machined()`, `fdm(layer_height_mm=0.2)`: `bd_materials.processes.AppliedProcess`)
on the XCAF material label. Native texture maps
are not drawn yet (a part's mesh has no UVs): the viewer's scene, OCCT snapshots and GLB and 3MF
exports draw the part in its material's scalar look, every map and texture transform left out
(`document.scalar_pbr`), and the document keeps them whole, so drawing them later changes no
format. What is left out is named once, from the materials: the structure's prototype lists it
under `untextured` (map names by material name, only where there are any), a still's report
and a snapshot's `warning:` line, an export's line to its log, `cad <type> inspect`'s `textures`
list and the scene's `untextured` say it from there. Reading returns
native `FinishedMaterial` objects with that resolved look and an equal `process`; it does not
recreate a finish's recipe (`finish`, `color`, `thickness_mm`, `opacity`, `roughness`, `scale` and
`rotation` live on in the look alone, read back as their defaults). A material with no process, a
document written before processes were kept, and every STEP read `process` as `None`. XCAF's standard attributes also carry the name, density and core PBR factors for
other readers. STEP carries name, density and colour. The structure serves native physics
under `material` and `PbrProperties.to_dict()` under `pbr`, with the native physical type
named by `type`, and the process, where there is one, under `process`: the `Process` enum's value
and the dataclass's fields (`{"process": "fdm", "scale": [1, 1], "rotation": 0, "pitch_mm": 0.2,
"skin": false, "mm_per_uv": 1}`); no flattened material fields of the library's own remain. Only
those known dataclasses are rebuilt from it, never a type the data names.

A material's content key covers its process, so a part given one writes other document bytes
than the same part without. The closure's key does not cover the material (`FORMAT` did not move
when processes joined the document): a document built before then is taken as current, and reads
`process` `None`, until its model builds again.

A material edit changes document content without changing geometry keys. Warm document
patches and cold builds write identical bytes. GLB and the viewer retain clearcoat,
anisotropy, transmission, attenuation and emission. OCCT stills use the documented
approximations in **The look**. A part's chip card and `cad <type> inspect` weigh it from its
volume and native density, summed over an assembly.
