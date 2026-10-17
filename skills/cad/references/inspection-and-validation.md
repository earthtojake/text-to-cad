# Inspecting and checking saved CAD in Python

Checks are small Python scripts against the saved STEP/STP; there is no
inspection command. A check reads the last saved document, so it sees a source
edit only after the model runs. Paths resolve from the working directory and
expand `~`.

## Opening and selecting geometry

```python
from cadgen import read_step, read_scene

shape = read_step("STEP/bracket.step")  # native build123d geometry
scene = read_scene("STEP/assembly.step")  # hierarchy and exact selector refs

print(scene.document_hash)
for occurrence in scene.leaves():
    print(occurrence.ref, occurrence.label, occurrence.prototype_id)

housing = scene.resolve("#housing")
print(housing.ref, housing.kind)
solid_or_compound = housing.shape()
for face in housing.entities("face"):
    print(face.ref, face.shape().area)
```

- `scene.roots` and `occurrence.children` are tuples; `scene.leaves()` yields the
  geometry occurrences, repeated copies included. A leaf can hold several solids.
- `scene.resolve(ref)` returns a selection with `ref`, `kind`, `occurrence_ref`,
  `shape()` and `entities(kind)`, for kinds `"face"`, `"edge"` and `"vertex"`;
  each entity carries its own ref, the occurrence's token and the element's name.
- `shape()` is caller-owned exact geometry in document world coordinates; a group
  gives an unfused compound. Keep it when making several queries.
- `prototype_id` names geometry shared within this scene, so a body-local check
  can run once per prototype. It is not an identity across revisions.
- A scene is bound to one document hash: reopen it after the file changes, and
  keep it open rather than reopening (each open re-hashes the document). It shows
  the saved placement, not sidecar poses or animation.
- Inside a model, the document either function reads is a build input.

### Reference syntax

```text
#o:4b1f9e2a7c03                        an occurrence or subassembly, by its token
#o:4b1f9e2a7c03/f:bracket.make_box1.6  a face of that leaf occurrence, by its name
#housing/e:bore.cut1.2                 an edge of the occurrence labelled housing
#f:bracket.make_box1.6                 a face, only when the scene has exactly one leaf
#o:4b1f9e2a7c03/f:9d2e8c1b5a70         a face named by its geometry (an imported file's)
part.step#o:4b1f9e2a7c03               a file-prefixed ref matching the opened STEP
```

An occurrence's token is `o:` and twelve lower-case hexadecimal characters,
minted from its place in the tree (its parent's token, its name, its placement).
An element's name is `f:`, `e:` or `v:`, the operation of the model's code that
made it, and its number among the elements of its kind that operation made:
`f:bracket.make_box1.6` is the sixth face of the first `make_box` the function
`bracket` called for that part. The operation is the function, then the build123d
operation and how many times that function had called it in making the part, or the label of a
shape the model labelled and made something else of (`f:boss.3`, in `plate + boss`;
a part placed as it is keeps its own names, its label naming the occurrence). An element
a later operation split adds its piece's number (`f:bracket.make_box1.6.2`); an
operation that only trims or moves it does not rename it. Lines are never in a
name, so moving code renames nothing, and the viewer, the build's warnings and
`resolve()` all name a face alike. An element no operation of the model's run
made -- every element of an imported STEP -- is named by its geometry: `f:`,
`e:` or `v:` and twelve hexadecimal characters, hashed from the element's shape
within its body (a face's surface class, tight box and normal; an edge's curve
class, end points and length; a vertex's point). `resolve()` also finds an
element by that geometric name in a document whose elements are named by
operations, measuring the body's geometry the first time it is asked. One
reference per `resolve()` call. A group has no faces of its own:
`scene.resolve("#group").entities("face")` enumerates its leaves' faces.

Labels use letters, digits, `_` and `:`, and cannot start with a digit; other
names stay reachable by occurrence token. Duplicate labels get numbered aliases
in occurrence order (`#wheel_1`, `#wheel_2`), and the bare duplicate label
raises, listing them.

A copied reference's file prefix is the file's absolute path (quoted when it holds
a space or `#`) and must name the opened document; a relative prefix may match
the end of the document's path.

### Which code made it

`cadgen store where <file.step> <ref>` answers, for a STEP a model of this
cadgen wrote, which operation at which line of the model's code made what the
ref names -- a part's body, a face, an edge or a vertex -- and, for an element,
which operation last modified it (a cut that trimmed a box's face, a fillet that
shortened an edge), each as `file:line in function (operation)` with the
operation's name. The ref is one the viewer copies or `resolve()` takes
(`#o:…`, `#o:…/f:…`, `#label/e:…`). It reads the build's own account of the
run, written with the model's record, so it speaks for the file's current bytes
only: after an edit, run the model, then ask. `--json` returns the answer as
data; the exit status is 0 when it knows and 1 when it does not (no build of
this cadgen, other bytes, a body read from a file or built outside build123d's
constructions), with the reason.

```text
$ cadgen store where STEP/bracket.step "#bracket/f:bore.make_cylinder1.1"
document  /work/STEP/bracket.step
ref       #o:624d1aa32b5a/f:bore.make_cylinder1.1
model     /work/src/bracket.py::bracket
face      made by bracket.py:6 in bore (Solid.make_cylinder)   bore.make_cylinder1
          last modified by bracket.py:6 in bore (cut)   bore.cut1
```

The bore wall is the cylinder's face, trimmed by the cut that bored it. A face's
name holds the operation that made it, so the same name answers across the
builds of a model that leave that operation alone, and a face of a placed child
model is answered from that child's own build.

## Measurements

```python
# p, q: points; u, v, direction, normal: vectors
length = (q - p).length
signed_offset = (q - p).dot(direction.normalized())
angle_degrees = u.get_angle(v)
signed_angle_degrees = u.get_signed_angle(v, normal)
center = circular_edge.arc_center
radius = circular_edge.radius
size = shape.bounding_box().size
```

The default `bounding_box()` searches for tight bounds and can be slow on curved
geometry; `bounding_box(optimal=False)` is a fast conservative envelope.

```python
from cadgen.geometry import closest_points, overlap_volume

result = closest_points(a, b)   # .distance, .point_a, .point_b
volume = overlap_volume(solid_a, solid_b)
```

`closest_points` returns the minimum distance and one witness pair; overlap,
contact and containment all give 0, so it does not measure penetration.
`overlap_volume` is the exact intersection volume (mm³) of two finite, positively
oriented solids, 0 for mere contact; pair bodies with
`scene.resolve("#group").shape().solids()`.
Kernel failures raise.

Two solids at `overlap_volume` 0 at most touch. A pair meant to overlap (a
press-fit pin, a bearing in its bore) is named as such, not inferred from where it
sits in the tree. A part meant to sit on, bolt to or bear against another measures
`closest_points` distance 0 against it; above 0 is a gap, and the part floats.
Over many parts, two `bounding_box(optimal=False)` envelopes that do not meet rule
a pair out, leaving the exact queries for the pairs that remain. Both queries
measure the saved placement: a part clear at rest can still pass through another
in a pose or a clip ([reviewing motion](kinematics.md#reviewing-motion)).

## Geometry diagnostics

```python
from cadgen.geometry import is_sound, topology_errors, boundary_edges, self_intersections

ok = shape.is_valid                       # bool: BRepCheck passes (build123d)
clean = is_sound(shape)                   # bool: the boolean kernel's argument check passes, expensive
issues = topology_errors(shape)            # tuple[GeometryIssue, ...]
free = boundary_edges(shell)              # tuple[Edge, ...]
crossings = self_intersections(shape)     # tuple[GeometryIssue, ...], expensive
```

A `GeometryIssue` has `code` (an OCCT `BRepCheck_*` or `BOPAlgo_SelfIntersect`
status) and `entities`. An inconclusive check raises `GeometryError` rather than
passing; none of these repair geometry. `is_sound` is `BRepAlgoAPI_Check`'s
verdict, the gate a fuse or cut demands of an operand (`False` for a null or
empty shape). A reversed solid can pass topology checks with negative volume and
aggregate volumes can cancel, so signed volume is checked per solid; no free
edges means closed, not manifold.

## Mass properties

```python
from cadgen.geometry import mass_properties

properties = mass_properties([
    (aluminum_body, 2.70e-6),  # kg/mm³; use the material density for the task
    (steel_insert, 7.85e-6),
])
print(properties.volume, properties.mass, properties.center_of_mass)
print(properties.inertia)
```

`mass_properties` integrates uniform density per solid and sums the bodies,
overlaps included. The 3×3 inertia is about the combined centre of mass in the
input axes; with mm and kg/mm³, outputs are mm³, kg, mm and kg·mm².
