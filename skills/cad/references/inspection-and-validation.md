# Inspecting and checking saved CAD in Python

Use small Python scripts against the saved STEP/STP. `cadgen step inspect`
and `cadgen.step.inspect` have been removed. Choose the relevant entities,
measurements and acceptance criteria in the script; there is no replacement
inspection command or universal validation report.

Put exploratory scripts in the CAD project's ignored `tmp/`, for example
`tmp/check_clearance.py`; system `/tmp/` is also fine for disposable work.
Keep reusable design checks in `checks/` (for example `checks/clearance.py`),
or use the project's existing test location. Commit those checks so they can
be rerun after a model changes. Create the directory only when needed.
Keep checks outside `src/` model directories and raw format folders such as
`STEP/`. Examples below use paths relative to the CAD project root; run from
there, or anchor input paths explicitly when a script must run elsewhere.

Report what was measured, the units, the threshold and the selected geometry.
A failed computation is not a passing check, and an untested relationship has
no verdict. Run the model first when you want to check newly authored geometry.

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

`read_step` keeps its existing name. `read_scene` replaces the old
`load_step_scene` helper. Both record their document as a build input inside a
model. Paths expand `~` and resolve relative to the working directory.

- `scene.roots` and `occurrence.children` are tuples. `scene.leaves()` yields
  geometry occurrences, including repeated copies. A leaf can hold multiple
  solids; the reader does not infer manufactured parts.
- `scene.resolve(ref)` returns a selection with `ref`, `kind`,
  `occurrence_ref`, `shape()` and `entities(kind)`. Kinds for enumeration are
  `"shape"`, `"face"`, `"edge"`, `"vertex"`. Shape entities (`sN`) are solids,
  or shells when no solids exist, or the leaf geometry itself.
- Every `shape()` is caller-owned exact build123d geometry in the document's
  world coordinates, including ancestor placements. A group produces an
  unfused compound. Modifying the result cannot change the scene or another
  selection. Keep the returned shape when making several queries about it.
- `prototype_id` identifies shared geometry within this scene, allowing a
  script to avoid repeating a suitable body-local check. It is not a part
  number or an identity across revisions. Numeric self-intersection tests can
  behave differently at different placements; state which placements ran.
- A scene is bound to one document hash. Replacing the file does not change an
  already opened scene. Reopen it to inspect the new revision. Selector IDs
  are revision-scoped, not persistent feature names.
- Opening reuses the canonical BREP cache, decoding prototypes on demand.
  No display surfaces, tessellation, source discovery or source execution are
  needed. Cached inventory and occurrence lookup defer the build123d import
  until native geometry is requested. Keep the scene open: repeated reads
  still hash the document bytes, and fresh Python processes pay import costs.
- The scene describes the saved placement. It does not evaluate sidecar
  kinematics or animation poses.

### Reference syntax

```text
#o1.2          occurrence or subassembly
#o1.2.f7       canonical face 7 on that leaf occurrence
#housing.e3   canonical edge 3 on the occurrence labelled housing
#f7           face 7, only when the scene has exactly one leaf
part.step#o1  a file-prefixed ref matching the opened STEP
```

Pass one reference per `resolve()` call. To enumerate a subassembly's faces,
use `scene.resolve("#group").entities("face")`; a group has no independent
face ordinals. Enumeration preserves canonical occurrence IDs and never
merges coincident instances. Face and edge IDs agree with the viewer; vertex
IDs enumerate native STEP vertices (the viewer currently exposes no vertex
table).

Labels use letters, digits, `_` and `:`, and cannot start with a digit or
collide with numeric reference syntax. Other labels remain accessible through
numeric IDs. Duplicate labels receive numbered aliases in occurrence order;
resolving the ambiguous bare label raises and lists candidates. No fuzzy
matching or choosing the first match.

A copied reference's file prefix is a segment-aligned suffix of its path.
`read_scene` rejects a prefix naming a different document. If a copied prefix
names a model script (a bare stem), identify its saved STEP output first and
pass the `#...` portion to that scene. Do not guess between ambiguous files.

## Measurements

Most measurements already have native build123d interfaces:

```python
# p, q: chosen points; u, v, direction, normal: explicit vectors
length = (q - p).length
signed_offset = (q - p).dot(direction.normalized())
angle_degrees = u.get_angle(v)
signed_angle_degrees = u.get_signed_angle(v, normal)

# Select the actual geometric feature that defines the dimension.
center = circular_edge.arc_center
radius = circular_edge.radius
diameter = 2 * radius
length = edge.length
area = face.area
volume = solid.volume
size = shape.bounding_box().size
```

A bounding box dimension is an envelope, not a hole diameter or wall
thickness. A surface centroid is not necessarily a datum. Use analytic
centers, axes and selected points when those define the requested dimension.
The default `bounding_box()` searches for tight bounds and can be expensive
on curved geometry. Use `bounding_box(optimal=False)` for a fast conservative
envelope when filtering candidate collision pairs, not for a tight dimension.

```python
from cadgen.geometry import closest_points

result = closest_points(a, b)
print(result.distance, result.point_a, result.point_b)
```

`closest_points(Shape, Shape) -> ClosestPoints` returns a nonnegative minimum
set distance and one witness pair in the input frame. Solid overlap, contact
and containment have distance zero; it does not measure penetration depth.
Witnesses may be nonunique or internal to a solid. Pass selected faces/shells
when asking about boundary separation. Minimum distance does not replace
center spacing, angles, radii, lengths, areas or volume measurements.

## Overlap and clearance checks

`overlap_volume(Solid, Solid) -> float` measures the exact intersection volume
of two finite, positively oriented solids. It returns zero for mere contact.
It applies no minimum volume, exclusions, part hierarchy or pass/fail policy.
Kernel failures raise; inputs remain unchanged. Length units from STEP are mm,
so overlap volume is mm³. Tolerances in these scripts are design decisions,
separate from the kernel's numerical precision.

For example, checking every body pair inside a chosen subassembly:

```python
from itertools import combinations
from cadgen import read_scene
from cadgen.geometry import overlap_volume

scene = read_scene("STEP/assembly.step")
selection = scene.resolve("#housing_assembly")
bodies = [
    (entity.ref, solid)
    for entity in selection.entities("shape")
    for solid in entity.shape().solids()
]
if len(bodies) < 2:
    raise ValueError("This interference check needs at least two bodies")

max_overlap_mm3 = 0.01  # chosen for this design
failures = []
tested = 0
for (ref_a, a), (ref_b, b) in combinations(bodies, 2):
    volume = overlap_volume(a, b)
    tested += 1
    if volume > max_overlap_mm3:
        failures.append((ref_a, ref_b, volume))
print({"tested_pairs": tested, "limit_mm3": max_overlap_mm3,
       "overlaps_mm3": failures})
if failures:
    raise SystemExit(1)
```

Adapt pair selection to the question: for clearance around a moving carriage,
compare that carriage against relevant fixed geometry. List intentional
press fits/excluded pairs explicitly. Do not infer exclusions from assembly
depth. For large pair sets, retain the shapes and compute conservative bounds
once per body. Disjoint bounds rule out overlap; intersecting bounds only
identify candidates for the exact query. For a clearance requirement use
`closest_points(a, b).distance` and
compare against the specified minimum. A static check proves only that pose;
path or motion checks need an explicit sampling or swept-volume strategy.

## Geometry diagnostics

```python
from cadgen.geometry import topology_errors, boundary_edges, self_intersections

issues = topology_errors(shape)            # tuple[GeometryIssue, ...]
free = boundary_edges(shell)              # tuple[Edge, ...]
crossings = self_intersections(shape)     # tuple[GeometryIssue, ...], expensive
```

`GeometryIssue` has `code` and `entities`, containing owned build123d geometry.
Topology codes are OCCT `BRepCheck_*` statuses; self-intersection codes are
`BOPAlgo_SelfIntersect`. Failed/inconclusive checks raise `GeometryError`,
never an empty success result. None of these functions repairs geometry.

Choose checks appropriate to the artifact. For an intended closed solid,
check topology, free shell edges and each solid's signed volume. A reversed
solid can pass topology validation but have negative volume; check individual
solids because aggregate volumes can cancel. Open shells can be valid when
surfaces are intended. No free edges establishes closure, not full manifold
validity. Run self-intersection checks explicitly when required and report
any checks you did not complete.

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

`mass_properties(Iterable[tuple[Solid, float]]) -> MassProperties` integrates
uniform density per solid and sums the supplied bodies, including overlaps.
Densities must be finite and positive. It does not infer materials or fuse
bodies. The 3×3 inertia tuple is about the combined center of mass in the input
coordinate axes. With mm and kg/mm³, outputs are mm³, kg, mm and kg·mm².

Use snapshots for visual review per `snapshot-review.md`. Turn visual concerns
into explicit geometric checks before claiming they have been resolved.
