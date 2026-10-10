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
  `shape()` and `entities(kind)`, for kinds `"shape"`, `"face"`, `"edge"` and
  `"vertex"`. Shape entities (`sN`) are solids, or shells when there are none.
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
#o1.2          occurrence or subassembly
#o1.2.f7       canonical face 7 on that leaf occurrence
#housing.e3   canonical edge 3 on the occurrence labelled housing
#f7           face 7, only when the scene has exactly one leaf
part.step#o1  a file-prefixed ref matching the opened STEP
```

One reference per `resolve()` call. A group has no face ordinals of its own:
`scene.resolve("#group").entities("face")` enumerates its leaves' faces. Face and
edge ids agree with the viewer; vertex ids enumerate native STEP vertices.

Labels use letters, digits, `_` and `:`, and cannot start with a digit or look
like numeric ref syntax; other names stay reachable by numeric id. Duplicate
labels get numbered aliases in occurrence order (`#wheel_1`, `#wheel_2`), and the
bare duplicate label raises, listing them.

A copied reference's file prefix is the file's absolute path (quoted when it holds
a space or `#`) and must name the opened document; a relative prefix may match
the end of the document's path.

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
`[s for e in scene.resolve("#group").entities("shape") for s in e.shape().solids()]`.
Kernel failures raise.

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
