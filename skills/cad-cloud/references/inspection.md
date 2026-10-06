# Measuring and checking a build

`cad_inspect(build, code)` runs `code` as a fresh `python` script in a copy of
the build's files. `build` is an id or a build link, and the build must have
finished. The working directory is the build root, so paths are the build's own
(`STEP/bracket.step`), but the root is not on `sys.path`: the build's own modules
import only through the `pythonpath` the build was made with. Read the saved
outputs with `read_step` and `read_scene`; calling a model function would
rebuild it, cold.

The call returns the last 60 lines of what the script prints, the last 30 lines
of its errors, its exit code, and up to 8 PNG, SVG or JPEG images (10 MB each)
saved under `tmp/` (create the folder first). The copy is discarded afterwards,
nothing carries between calls, there is no network, matplotlib draws headless,
and a call has a shorter time cap than a build (by default 3 minutes). The code
may be at most 256 KiB, and each user runs one snapshot or inspection at a time.
Put what a question needs into one script, and make it print; a call that
outlasts about 40 s returns a job id to poll with `cad_status`.

Report what was measured, the units, the threshold and the selected geometry. A
failed computation is not a passing check, and a relationship you did not test
has no verdict.

## Opening and selecting geometry

```python
# cad_inspect
from cadgen import read_scene, read_step

shape = read_step("STEP/bracket.step")     # native build123d geometry
scene = read_scene("STEP/assembly.step")   # hierarchy and exact selector refs

for occurrence in scene.leaves():
    print(occurrence.ref, occurrence.label)

selection = scene.resolve("#pin_left")
print(selection.ref, selection.kind)
for face in selection.entities("face"):
    print(face.ref, round(face.shape().area, 1), "mm^2")
```

- `scene.roots` and `occurrence.children` are tuples. `scene.leaves()` yields
  geometry occurrences, repeated copies included. A leaf can hold several
  solids; the reader does not infer manufactured parts.
- `scene.resolve(ref)` returns a selection with `ref`, `kind`, `occurrence_ref`,
  `shape()` and `entities(kind)`. Entity kinds are `"shape"`, `"face"`, `"edge"`
  and `"vertex"`.
- Every `shape()` is caller-owned build123d geometry in the document's world
  coordinates, ancestor placements included. Changing it changes nothing else.
  Keep the shape when you ask several questions about it.
- `prototype_id` identifies shared geometry within one scene, so a body-local
  check need not repeat for copies. It is not a part number or an identity
  across builds.
- The scene describes the saved placement. It does not evaluate kinematic poses.

### Reference syntax

```text
#o1.2          occurrence or subassembly
#o1.2.f7       canonical face 7 on that leaf occurrence
#housing.e3    canonical edge 3 on the occurrence labelled housing
#f7            face 7, only when the scene has exactly one leaf
```

In a link the file is the path and the selector is the fragment: pass the
fragment to `resolve()`, or the link's path and fragment together
(`STEP/bracket.step#o1.1.f2`), one reference per call. To enumerate a subassembly's
faces use `scene.resolve("#group").entities("face")`; a group has no face
ordinals of its own. Labels use letters, digits, `_` and `:`, and cannot start
with a digit. Duplicate labels get numbered aliases in occurrence order, and an
ambiguous bare label raises and lists candidates. There is no fuzzy matching.
Selector IDs are scoped to one build: resolve again after a rebuild.

## Measurements

Most measurements are native build123d:

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

A bounding box is an envelope, not a hole diameter or a wall thickness, and a
surface centroid is not necessarily a datum. Use analytic centers, axes and
selected points when those define the requested dimension. The default
`bounding_box()` searches for tight bounds and can be slow on curved geometry;
`bounding_box(optimal=False)` is a fast conservative envelope for filtering
candidate pairs, not a tight dimension.

```python
# cad_inspect
from cadgen import read_scene
from cadgen.geometry import closest_points

scene = read_scene("STEP/assembly.step")
result = closest_points(scene.resolve("#pin_left").shape(), scene.resolve("#plate").shape())
print(result.distance, result.point_a, result.point_b)
```

`closest_points` returns a nonnegative minimum distance and one witness pair in
the input frame. Overlap, contact and containment all give zero; it does not
measure penetration depth. Witnesses can be nonunique or inside a solid, so pass
selected faces when you ask about boundary separation. Minimum distance does not
replace center spacing, angles, radii, lengths, areas or volume.

## Overlap and clearance

`overlap_volume(Solid, Solid)` is the exact intersection volume of two finite,
positively oriented solids, in mm^3 for STEP lengths in mm. It is zero for mere
contact and applies no minimum, exclusion or hierarchy; kernel failures raise.
Tolerances are design decisions, separate from the kernel's precision. Checking
every body pair of an assembly:

```python
# cad_inspect
from itertools import combinations

from cadgen import read_scene
from cadgen.geometry import overlap_volume

scene = read_scene("STEP/assembly.step")
bodies = [
    (leaf.ref, solid)
    for leaf in scene.leaves()
    for solid in scene.resolve(leaf.ref).shape().solids()
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
print({"tested_pairs": tested, "limit_mm3": max_overlap_mm3, "overlaps_mm3": failures})
if failures:
    raise SystemExit(1)
```

A nonzero exit code comes back with the result, so a failed check cannot read as
a pass. Adapt the pairs to the question: for clearance around a moving carriage,
compare the carriage with the relevant fixed geometry. List intentional press
fits explicitly instead of inferring exclusions from assembly depth. For large
pair sets, compute a conservative bound once per body: disjoint bounds rule out
overlap and intersecting bounds only identify candidates for the exact query.
For a clearance requirement use `closest_points(a, b).distance` against the
specified minimum. A static check proves only that pose; a path needs sampling.

## Geometry diagnostics

```python
from cadgen.geometry import boundary_edges, is_sound, self_intersections, topology_errors

ok = shape.is_valid                     # bool: BRepCheck passes (build123d)
clean = is_sound(shape)                 # bool: the boolean kernel's argument check; expensive
issues = topology_errors(shape)         # tuple of GeometryIssue
free = boundary_edges(shell)            # edges of an open shell
crossings = self_intersections(shape)   # tuple of GeometryIssue; expensive
```

A `GeometryIssue` has `code` and `entities`, the offending build123d geometry. A
failed or inconclusive check raises `GeometryError` and never returns an empty
success. None of these repairs geometry. `is_sound` is false for a null or empty
shape. It costs kernel time, so use it where a failure is plausible.

For an intended closed solid, check topology, free shell edges and each solid's
signed volume: a reversed solid passes topology validation with a negative
volume, and aggregate volumes can cancel. No free edges establishes closure, not
full manifold validity. Open shells are valid when surfaces were requested.

## Mass properties

```python
# cad_inspect
from cadgen import read_scene
from cadgen.geometry import mass_properties

scene = read_scene("STEP/assembly.step")
bodies = [scene.resolve(leaf.ref).shape().solids()[0] for leaf in scene.leaves()]
properties = mass_properties([(body, 2.70e-6) for body in bodies])  # aluminum, kg/mm^3
print(properties.volume, properties.mass, properties.center_of_mass)
print(properties.inertia)
```

`mass_properties` integrates a uniform density per solid and sums the bodies
supplied, overlaps included. It infers no materials and fuses nothing. With mm
and kg/mm^3 the results are mm^3, kg and mm; the 3x3 inertia is in kg*mm^2,
about the combined center of mass, in the input axes.

## Pictures

An image saved under `tmp/` comes back with the result, for a plot of measured
values. For pictures of the model itself use `cad_snapshot`, and turn a visual
concern into a measurement before calling it resolved.
