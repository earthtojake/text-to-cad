# Implicit fields

Read this file when the person wants organic or blended forms, smooth unions and fillet-like
blends, hollow shells that follow blends, radial or linear patterns of features, or implicit /
signed-distance modeling; for prismatic parts with exact faces, threads or chamfers, build123d is
the kernel ([build123d](build123d-modeling.md)).

## Contents

- [A field, not a boundary](#a-field-not-a-boundary)
- [A model from a field](#a-model-from-a-field)
- [A field in a B-rep assembly, or a STEP](#a-field-in-a-b-rep-assembly-or-a-step)
- [What comes back](#what-comes-back)
- [Choosing the cell](#choosing-the-cell)
- [What is refused and what to do](#what-is-refused-and-what-to-do)
- [Look inside the field](#look-inside-the-field)
- [Check each change](#check-each-change)
- [Authoring reference](#authoring-reference)
- [Rules](#rules)
- [Beyond geometry](#beyond-geometry)

## A field, not a boundary

[cadjoint](https://github.com/andrinr/cadjoint) is a CAD kernel of signed-distance fields, on JAX.
A cadjoint solid is a function that gives, at every point, the distance to its surface, negative
inside. A boolean is a pointwise min or max, or a smooth blend of the two; a shell, an offset and a
pattern are operations on the distances. No face or edge exists until the field is meshed.

So a blend at six junctions, a constant wall that follows those blends, and a ring of features are
each one operation that cannot fail, where filleting intersecting cylinders and then shelling the
result is where OCCT most often refuses. What a field lacks is exact faces: no analytic cylinder,
no edge to pick, no thread or chamfer. Choose a field for the first kind of part and build123d for
the second. One assembly can hold both, the field placed in it as a solid
([below](#a-field-in-a-b-rep-assembly-or-a-step)).

## A model from a field

A model of a field is a function declared `@implicit` that returns `field(scene, cell=...)` from
`cad.cadjoint`: the scene built with cadjoint's API, and the cell it is sampled at, in millimetres,
as the field is. For example, `src/node.py`, a hollow space-frame node: six 20 mm tubes leave a hub
at different angles, every junction blended, the whole node hollowed to a 4 mm wall that follows the
blends, every tube open at its end for a strut to slide in:

```python
import math

from cadjoint.construction import Solid
from cadjoint.sdf import Rotate, Shell
from cadjoint.sdf.boolean import Intersection, Union

from cad import implicit
from cad.cadjoint import field

# Tube directions as (tilt from +Z, turn about Z), in degrees: one straight up,
# three splayed downward like a tripod, two raking sideways.
DIRECTIONS = [(0, 0), (115, 0), (115, 120), (115, 240), (70, 60), (70, 300)]


def node_field(tube_radius=10.0, reach=44.0, wall=4.0, blend=4.0):
    """The node's field: `reach` from the hub's centre to a tube's end, `blend` the smoothness k."""
    hub = Solid.sphere(radius=15.0, name="hub")
    tubes = []
    for i, (tilt, turn) in enumerate(DIRECTIONS):
        tube = Solid.cylinder(
            radius=tube_radius, height=reach / 2, position=(0.0, 0.0, reach / 2), name=f"tube_{i}",
        )
        tubes.append(Rotate(Rotate(tube, "y", math.radians(tilt)), "z", math.radians(turn)))
    blended = Union(hub, *tubes, smoothness=blend)        # every junction at once, over about 4 * blend
    shell = Shell(blended, wall)                           # a wall `wall` thick, centred on the surface
    ends = Solid.sphere(radius=reach - 4.0, name="ends")   # a sharp cut: each tube end a clean ring
    return Intersection(shell, ends, smoothness=0.0)


@implicit
def node():
    return field(node_field(), cell=1.0)                   # the 4 mm wall spans four cells


if __name__ == "__main__":
    node()
```

```bash
cad run src/node.py
```

```text
built src/node.py::node cold in ...: bodies 1 run; 0 misses, 0 hits; body ..., sample ...
  triangles 70,628 · wall 4 cells (3.96 mm) · bounds 67.65 × 76.06 × 66.2 mm
  id: ...
  view: ...
```

The engine samples the field and holds the mesh as the model's document, addressed by its id; no
file is written, and a file is an export ([below](#what-comes-back)). Under the run line are the
sample's triangles, its thinnest wall ([the cell](#choosing-the-cell)) and its bounds, to compare
with the request; a rebuild that changed them says what they were, `(was 70,628)`. A rebuild whose
field is unchanged (an edit elsewhere in the script, a comment) samples nothing, in a fraction of a
second; a changed cell or parameter samples again. `@implicit(name="node_fine")` names the model, as
`@model(name=...)` does; stacking `@implicit` with `@model` or a file decorator is refused.

The script imports `cadjoint`, so `cad run` gives it the cadjoint integration (`cad[cadjoint]`) and
the build123d integration with it: no header, nothing to install. The library pins cadjoint (0.1.1);
its API is young, and the names below are that release's.

Three field operations make the node: `Union(..., smoothness=k)` blends every junction at once;
`Shell(blended, t)` makes a wall t thick centred on the surface, 4 mm through every blend; and
`Intersection` with a ball opens every tube at one distance from the centre, a slightly domed ring.
`Offset` grows or shrinks a field by a uniform distance (a tighter socket). Keep the field in a plain
function, as `node_field` is, so a check script can measure it ([below](#look-inside-the-field))
and an assembly can make a solid of it.

## A field in a B-rep assembly, or a STEP

An implicit model is a leaf, a mesh with no shape to place. Where the field must sit beside
build123d parts, be cut or joined with build123d, or go out as a STEP, a `@model` returns
`solid(scene, cell=...)` from `cad.cadjoint`, a build123d `Solid` of planar triangles, with `field`'s
`cell`, `bounds=` and refusals. `src/frame.py`, a strut in the node's upright socket:

```python
import build123d as bd
from cad import model
from cad.cadjoint import solid

from node import node_field


@model
def frame():
    node = solid(node_field(), cell=1.0)                   # B-rep: tens of seconds, every run
    node.label = "node"
    strut = bd.Pos(0, 0, 85) * bd.Cylinder(7.5, 120.0)     # z 25 to 145; the bore is 16 mm across
    strut.label = "strut"
    return bd.Compound(children=[node, strut], label="frame")


if __name__ == "__main__":
    frame()
```

`solid` samples the field as `@implicit` does, simplifies the mesh with cadjoint's error-bounded,
feature-preserving collapse (every changed triangle within cell / 20 of the field) and builds it face
by face, at two to six times a cold `@implicit` build, and again on every run of its body
([the cell](#choosing-the-cell)). That is ordinary B-rep, which every `cad model` command takes as
any part, but faceted:

- No face is a cylinder, and a flat side is many triangles: a pick or a ref names one triangle, and
  build123d's selectors find triangles, not features. A radius reads as its chords: measure a bore
  on the field ([below](#look-inside-the-field)).
- A STEP of it is faceted too, one planar face per triangle, larger than an STL of the same part.
  Hand it to a check that needs exact radii (a shop's quote, a CNC review) only saying so.
- An STL's or 3MF's `--tolerance` does not refine the triangles, which are its faces; a finer cell does.

## What comes back

An `@implicit` model's document is the sample: cadjoint's dual contouring (sharp edges and corners
kept), slivers welded, one closed body, nothing simplified, in the engine's memory and cache.

- **The viewer** shows it in the mesh view, smoothly shaded from the field's own normals, with no
  edges at all: no B-rep edge, and no fold guessed from the triangles, whose points settle either
  side of a crease from cell to cell. So Solid looks as Shaded, and a `hidden-line` snapshot shows
  of it only what a clip or the grid draws: judge its shape shaded. A pick names the mesh, never a
  face. Its Export menu offers STL, 3MF and GLB.
- **The commands** take its id: `cad implicit export`, `snapshot` (a mesh file's options: camera,
  display, grid, clip), `inspect` (triangles, bounds, volume, cell, wall; no ref: a mesh has no face
  to name) and `dfm`. `cad model snapshot|export|inspect` take it too, as Quick Edit's prompt does.
- **From Python**, on the handle a call returns: `implicit.export(node(), "STL/node.stl")`,
  `implicit.snapshot`, `implicit.inspect`, `implicit.dfm` (`from cad import implicit`). `cad.model`
  refuses the handle, naming `cad.implicit`, as `cad.implicit` refuses a model's.
- **Mesh files only**: STL, 3MF and GLB, with no `--tolerance`: the triangles are the sample's, so a
  finer cell makes finer files. A STEP is `solid()`'s.
- **No shape.** The handle has `.id` and `.url`; `.shape` is refused, naming `cad.cadjoint.solid`, as
  is a `@model` body that calls an implicit model.

## Choosing the cell

`cell` is the sampling cell's edge, in millimetres. The thinnest wall needs about four cells across:
`cell = wall / 4`. A wall or bridge thinner than about two cells falls apart; between two and four
it meshes closed, but its thickness is good only to about a cell. The smallest feature the mesh
resolves is about two cells. The sampling measures the thinnest wall on the field, a ray from each
vertex straight through the material to the face opposite (not the taper of a sharp edge), and the
line under the run says it in cells: `wall 4 cells (3.96 mm)`. Under two cells the build is refused,
naming the cell that gives it four.

- **Cost.** The field is compiled by JAX on its first evaluation, then sampled and meshed; `solid()`
  then simplifies the mesh and builds it face by face. Measured on CPU:

  | Build | `@implicit` | `solid()` in a `@model` |
  | --- | --- | --- |
  | A 120 mm clevis bracket at a 1 mm cell, cold | 13.6 s (7.6 s with JAX's compilation cache warm) | 32.6 s |
  | The same, an edit that leaves the field unchanged | 0.07 s | about 20 s |
  | The same, a changed cell or parameter | 9.4 s | about 20 s |
  | The node above at a 0.75 mm cell, cold | 8.2 s | 52.7 s |

  JAX's compilation cache is in the engine's cache folder, so later cold builds compile less. On
  the document, an STL export takes 0.1 to 0.4 s, `inspect` 0.2 s, a snapshot 1 to 4 s. The cost
  grows as the cell shrinks, roughly with the surface's area in cells: give a fine build the shell
  tool's longest timeout, or run it in the background.
- **At most 512 cells on an axis.** The cell is at least the part's longest extent / 512: 0.6 mm
  on a 300 mm part. A finer cell is refused, naming the coarsest cell that fits. When the four-cell
  rule cannot be met, say so and report the cell with the part. For a region of a large part,
  intersect the field with a box around it (`Intersection(field, Solid.box(...), smoothness=0.0)`)
  as its own model: the cap counts its cells alone.
- **`bounds=((x0, y0, z0), (x1, y1, z1))`** on `field` or `solid` replaces the automatic fit
  (cadjoint's `fit_bounds`, which scans at growing scales, so any size of part works) with a box of
  your own. The box must hold the whole part with room to spare: where the field is still inside on
  the box's faces, the mesh would be cut open there, and the build is refused.

## What is refused and what to do

A refusal writes nothing: the build fails, and its line names the fix: do it, rather than loosen the
request. `field` and `solid` refuse alike, but for the last two rows.

| Refused | Why | What to do |
| --- | --- | --- |
| Not a cadjoint field | `scene` is something else: a build123d shape, a list, `None` | Pass the field itself: a `Solid`, a `Union`, anything from `cadjoint.sdf` or `cadjoint.construction` |
| `cell` is not a positive number | zero, negative, not finite, not a number | A cell in millimetres, about the thinnest wall / 4 |
| More than 512 cells on an axis | the part is long for the cell | The coarsest cell the line names, or a region of the part as its own model ([above](#choosing-the-cell)) |
| No closed part found | the field is empty, or unbounded: a `Plane`, a missing `Intersection` | Bound it: intersect it with a solid around the part; `bounds=` only for a part that lies wholly inside the box |
| Part of the field lies on or beyond the bounds | `bounds=` cuts the part, so its mesh would be open | Widen `bounds=`, or drop it and let the fit find the part |
| The bounds hold no surface | the box lies wholly inside or wholly outside the part | Move or widen `bounds=`, or drop it |
| Not watertight | a concave corner sharper than the cell resolves | Round the corner (a blend, `RoundBox`, `rounded_rect`), or a finer cell |
| Several bodies | a wall or bridge thinner than about two cells, or pieces that do not touch | A finer cell; a thicker wall; or each piece its own model |
| `the thinnest wall is 1.6 cells (1.32 mm at a 0.825 mm cell) ...` | it meshes closed, but its thickness is the grid's | The cell the line names (the wall / 4), or a thicker wall |
| `an implicit document is made of cad.cadjoint.field(scene, cell=...), not ...` | an `@implicit` function returned something else: a bare scene, a `solid(...)`, a build123d shape | Return `field(scene, cell=...)` |
| `a model document is made of a build123d Shape ... (the cadjoint integration has no producer of model from Field)` | a `@model` returned `field(...)` | Declare it `@implicit`, or return `solid(scene, cell=...)` where a B-rep is needed |

## Look inside the field

A mesh shows where the surface is; a section shows how far every point is from it.
`section(scene, out, *, axis="z", at=0.0, step=None, pixels=900, bounds=None)` from `cad.cadjoint`
draws the plane `axis = at` into the PNG `out`: inside blue, outside orange, both darker with
distance, contours every `step` mm (a twentieth of the extent by default), the surface a black line.
It meshes nothing: confirm a wall or a blend's reach with it, and open the PNG, before building at a
fine cell. In a check script beside the model, `src/check_node.py`:

```python
import numpy as np

from cad.cadjoint import section
from node import node_field

field = node_field()
cut = section(field, "tmp/node-x0.png", axis="x", at=0.0, step=1.0)
print(cut.crosses_surface)                     # True: the plane cuts the part
print(cut.field_range)                         # (-2.0, ...): the thickest wall it cuts is 4 mm
print(field(np.array([[0.0, 10.0, 36.0], [0.0, 12.0, 36.0]])))   # [-2. 0.]: mid-wall; 2 mm out, the outside
```

```bash
cad run src/check_node.py
```

It returns a `Section`: `path`, `plane`, `across`, `up` (which world axes run across and up the
picture), `extent`, `pixel`, `contour_step`, `field_range` and `crosses_surface`. `field_range[0]`
is the deepest point inside, so twice it is the thickest wall the slice cuts; a thinner wall
elsewhere is read on the picture by its contours. A field is callable on an `(n, 3)` array of
points and answers their distances, which measures a wall, a bore or a blend's reach on the field
itself, without a mesh. `bounds=(u0, v0, u1, v1)` replaces the fit, in the slice's coordinates:
across and up are y and z for `axis="x"`, x and z for `"y"`, x and y for `"z"`.

## Check each change

After every run, read its line and the triangles and bounds under it, then check the change the way
it can be checked:

| The change | Check it with |
| --- | --- |
| An overall size, a volume | `cad implicit inspect "$ID"`: the mesh's bounds, volume, triangles, cell and thinnest wall |
| A dimension inside the part: a wall, a bore, a blend's reach | A check script that measures the field itself: `section` and the field at points ([above](#look-inside-the-field)) |
| A new feature, a blend, a pattern, the appearance | `cad implicit snapshot "$ID" tmp/review.png`, from the angle that shows the change |
| Whether it can be printed or molded | `cad implicit dfm "$ID" --process printing`: measured as a mesh, so a curved surface's draft and overhang are read from its triangles, at the cell's resolution |
| A file the person asked for | `cad implicit export "$ID" STL/node.stl`, then the file itself, checked again |

```bash
cad implicit inspect "$ID"
cad implicit snapshot "$ID" tmp/review.png --camera top
cad implicit dfm "$ID" --process printing
cad implicit export "$ID" STL/node.stl 3MF/node.3mf
```

A solid from `solid()` is a model's document, checked with `cad model` and the same operations.

- A blend moves the surface ([Rules](#rules)): check a dimension the person gave on the mesh or the
  field, never by restating the constant. A snapshot never shows a wall's thickness: section it.

## Authoring reference

A model file imports what it uses; nothing is injected.

### Conventions that differ from build123d

| Quantity | cadjoint |
| --- | --- |
| `Solid.box(size=...)` | **half**-extents: `size=(10, 5, 2)` is 20 x 10 x 4 |
| `Solid.cylinder(height=...)` | **half**-height, axis along local Z |
| `position=` | the centre, in world coordinates |
| `rotation=` on `Solid`, `Rotate(...)` | radians; `Solid` applies X, then Y, then Z |
| `extrude(draft=, twist=)`, `PolygonProfile.regular(start_angle=)` | degrees |
| `extrude(depth=)` | symmetric: spans plus and minus depth/2 about the sketch plane |
| boolean `smoothness` | `k` in millimetres, default 0.1 (pass 0 for sharp); acts within `4k` of a seam, shifts the surface by up to `k` |

### Primitives

```python
from cadjoint.construction import Solid
from cadjoint.sdf import Box, Capsule, Cylinder, RoundBox, Sphere, Torus

Solid.box(size=(hx, hy, hz), position=(x, y, z), rotation=(rx, ry, rz), name="plate")
Solid.sphere(radius=r, position=..., name="ball")
Solid.cylinder(radius=r, height=half_h, position=..., rotation=..., name="boss")
# raw primitives, centred at the origin and placed with Translate and Rotate:
RoundBox(size=(hx, hy, hz), radius=r)    # grows by r: outer half-extents are hx+r, hy+r, hz+r
Capsule(radius=r, height=half_len)       # Z axis; half-length of the straight part
Torus(major_radius, minor_radius)        # in the XY plane
```

`Solid` has only the first three. Faces: `box.face("+z")`, `cylinder.face("cap+")`.

### Booleans

```python
from cadjoint.sdf.boolean import Difference, Intersection, Union

Union(a, b, c, smoothness=0.0)
Difference(base, tool_1, tool_2, smoothness=0.0)   # the first argument is the base
Intersection(a, b, smoothness=1.0)
```

The operators `a | b`, `a - b` and `a & b` exist but always blend by 0.1: prefer the explicit
forms. The blend is Quilez's polynomial smooth minimum. It acts wherever two operands' distances
differ by less than `4k`, moves the surface by up to `k` there and by exactly `k` along faces that
coincide, and a chained `Union(a, b, c, ...)` applies it once per operand, so the shifts add up. Its
profile is a parabola, not a constant-radius fillet. To fillet several features onto one body,
join the features sharp and blend that group with the body once:
`Union(plate, Union(*lugs, *ribs, smoothness=0.0), smoothness=0.6)` rounds every root of every lug
and rib against the plate, with no edge to pick and none that can fail to round.

### Transforms and field operations

```python
from cadjoint.sdf import LinearPattern, Mirror, Offset, PolarPattern, Rotate, Scale, Shell, Translate, Twist

Translate(sdf, (dx, dy, dz))
Rotate(sdf, "x", angle_radians)      # axis "x", "y", "z" or a 3-vector
Scale(sdf, factor)                   # a float or a per-axis triple
Mirror(sdf, "x")                     # about the plane x = 0
Shell(sdf, thickness)                # the total wall, centred on the surface
Offset(sdf, distance)                # positive grows the solid
LinearPattern(sdf, (1, 0, 0), count, spacing)
PolarPattern(sdf, count)             # about world Z through the origin
```

`Rotate` silently treats an unknown axis string as Z: write `"x"`, `"y"` or `"z"` exactly. `Shell`
of a closed solid is a closed double wall; open it with an `Intersection` or a `Difference`.
`PolarPattern` copies about the Z axis only: build the feature off-axis, pattern it, then rotate the
result.

`Offset` rounds corners exactly. A triangular cutout with 3 mm corner radii is its triangle shrunk
about its incentre until the inradius is 3 mm smaller, extruded, then offset outward by 3 mm: the
straight edges come back where they were and every corner is an exact 3 mm arc (each vertex moved
toward the incentre by the factor `1 - 3 / inradius`; subtract the offset prism sharp). Offsetting
the original triangle in and back out does not round it: on a distance field the two cancel.

### Sketches

```python
from cadjoint.construction import PolygonProfile, SketchPlane, extrude, loft, revolve

plane = SketchPlane(origin=(0, 0, 0), normal=(0, 0, 1))
profile = PolygonProfile([(x0, y0), (x1, y1), (x2, y2)], plane=plane, name="outline")
PolygonProfile.circle(radius, center=(0, 0), plane=plane, name="disc")
PolygonProfile.rounded_rect(width, height, radius, plane=plane, name="slot")  # full width and height
PolygonProfile.regular(sides, radius, start_angle=0.0, plane=plane, name="hex")

extrude(profile, depth, draft=0.0, twist=0.0)
revolve(profile)                    # about the plane's in-plane Y axis
loft(profile_a, profile_b, height)  # the same vertex count; a at -h/2, b at +h/2
```

A profile point `(x, y)` lands at `origin + x*u + y*v`. Without `x_axis`, `u` and `v` are +X and +Y
for a +Z normal, -X and +Z for +Y, and -Z and +Y for +X. So a profile on a `normal=(0, 1, 0)` plane revolves about world Z, with profile x as the radius; a
profile may close along the axis (x = 0). Polygons must be simple, with at least three vertices and
no zero-length edge. Curves are polylines: `circle` uses 32 segments by default; raise `segments=`
when a round edge must be smooth at the cell.

Work planes come from existing geometry: `SketchPlane.on(solid.cap("+"))`,
`SketchPlane.offset(plane, distance)`, `SketchPlane.midplane(face_a, face_b)`.
`face.hole(radius, depth, at=(u, v), through=1.0)` returns a cylinder to subtract from the solid the
face belongs to.

### Parameters and constraints

`Scalar(40.0, free=True, name="width")` and `Vector2([0.0, 0.0], free=True, name="a")`
(`cadjoint.geometry`) are parameters, fixed unless `free=True`; `DistanceConstraint(a, b, width)`
(`cadjoint.constraints`) acts only once `satisfy_constraints(scene, steps=8)` runs, after the scene
is built, editing it in place. Plain numbers, the arguments of a helper like `node_field`, are enough
for a part that is only made; use parameters for a named dimension or an optimization later.

### Not available

No fillet, chamfer, thread, text, cone primitive, gyroid or other TPMS lattice. Round with blends,
`RoundBox` or `rounded_rect`; for the rest, model the part in build123d.

## Rules

- **Blends are in millimetres and change the size.** Every boolean blends unless told not to
  (`smoothness=0.1` by default); pass `smoothness=0` for a sharp edge. Join parts sharp and blend
  once, since chained blends add up; keep any face whose position matters more than `4k` from a
  blended seam; never blend two coincident faces, which pushes the surface out by the full `k`.
- **Give every `Solid` a unique name.** Its parameters are named after it, and two solids of one
  name collide when parameters are extracted.
- **Holes and pockets are tools.** `face.hole(...)` and `face.pocket(...)` return a solid to
  subtract. Run a subtracted tool past the face it cuts (or use `through=`), never flush with it, and
  subtract it sharp so its edges and diameter hold.
- **Bounded, one body, walls of four cells.** A `Plane` or an unbounded intersection is bounded
  with an `Intersection`; pieces that do not touch are separate models; the thinnest wall spans four
  cells, or the hand-off says it does not ([the cell](#choosing-the-cell)).

## Beyond geometry

Parameters declared `free=True` stay differentiable through the field, the mesh and cadjoint's FEM
studies, so `jax.grad` of a mass, a compliance or a peak temperature with respect to a sketch vertex
is one call. That workflow and cadjoint's interactive editor are cadjoint's own, documented at
https://andrinr.github.io/cadjoint/, outside this skill: offer them when the person asks to optimize
a shape, not by default.
