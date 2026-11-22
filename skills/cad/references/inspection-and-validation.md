# Inspecting and checking models

Read this file when resolving a reference, measuring a model, checking clearances or
contact, or diagnosing geometry. Which check a change calls for is
[Check each change](../SKILL.md#check-each-change); this file is what the checks are made of.

## Contents

- [Opening geometry](#opening-geometry)
- [References](#references)
- [Which code made it](#which-code-made-it)
- [Measurements](#measurements)
- [Geometry diagnostics](#geometry-diagnostics)
- [Interference](#interference)
- [Mass properties](#mass-properties)

A check script calls the model and measures what it returns, so it measures the model as its code
is now. Keep it in the project's ignored `tmp/`, or in a `checks/` folder when it is worth keeping.
An assert on a dimension goes inside the body, on the shape about to be returned, where the
geometry already is:

```python
@model
def bracket():
    body = bracket_body(80, 6, 8)
    assert abs(body.bounding_box().size.X - 80) < 1e-6, body.bounding_box().size
    return body
```

Never read `.shape` in the model's own script after its call: that brings the shape into the
script's process and loads the kernel there, two to three seconds on every run. A check script
pays that once.

## Opening geometry

A model's `.shape`, `step.read(path)` and `xbf.read(path)` are build123d trees. Each node's
`location` is relative to its parent, and `.children`, `.descendants` and `.leaves` give nodes
without their ancestors' placements. `leaves(tree)` (`cad.build123d`) gives every leaf placed where
it stands in the tree's frame: a new shape with the leaf's label, colour and material, no parent,
on the same B-rep. `leaves(tree, paths=True)` gives `(path, leaf)` pairs, `path` the labels from the
root. Never call `located` or `moved` on a node of the tree: build123d copies the node with its
parents, the whole assembly on every call (seconds and hundreds of megabytes on a large one).

```python
from cad.build123d import leaves


def find_part(tree, label):
    matches = [part for part in leaves(tree) if part.label == label]
    if len(matches) != 1:
        raise ValueError(f"Expected one part labelled {label!r}, found {len(matches)}")
    return matches[0]
```

`find_part` is a project helper to copy into a check, not the library's. It refuses a missing or a
repeated label: take repeated parts by their path, which they share, and tell them apart by where
they stand.

```python
doc = kit().shape                                # or step.read("kit.step"), xbf.read("kit.xbf")
palm = find_part(doc, "palm")
top = palm.faces().sort_by(bd.Axis.Z)[-1]        # the world-Z top: a leaf is placed
fingers = [part for path, part in leaves(doc, paths=True) if path[-2:] == ("hand", "finger")]
```

- A leaf is a copy, not the tree's node: a material or a declaration set on one is the leaf's own,
  so a model that changes a read tree's parts returns those leaves, not the tree.
- `bounding_box()` is the tight axis-aligned box in the shape's frame, at tens of milliseconds a
  part. `bounding_box(optimal=False)` is fast and loose on curved geometry, several times too wide
  on a piece cut from a lofted face (a 13 mm strip read 39 to 72 mm): rule pairs out with it, and
  never say where a part is by it.

## References

A ref names a part, an assembly or one element of a document by the server's own
names, resolved in the document as the latest run left it:

```text
REF      = [FILE "#"] SELECTOR ("," SELECTOR)*
SELECTOR = OWNER | [OWNER "/"] ELEMENT          no OWNER: the document's root
OWNER    = SEGMENT ("/" SEGMENT)*               an occurrence's path, or its last segments
SEGMENT  = LABEL | LABEL "." N | "QUOTED" ["." N]
ELEMENT  = NAME | face N | edge N | vertex N    NAME: f:..., e:..., v:...
```

```text
kit/hand/finger.2                       the second component labelled finger in hand
finger.2/face 3                         face 3 of it: the path may start at any level that names one occurrence
palm/f:kit.body.6;M:kit.relief          a face of palm by its name
7a9724e8-f676-5676-acaa-160d7c6cc5fa#palm,finger.1   two selectors, with the model's id first
/work/STEP/kit.step#palm                a file's document, by its absolute path
"m3/screw"/f:kit.screw.1                a label holding '/', ',' or a quote is JSON-quoted
plate/face 3                            in a document of one part, its elements by the document's name
```

- **An occurrence is named by the labels on the way to it.** Siblings sharing a label are numbered
  among them, in component order, so a repeated part is reached by its path, never by a number
  across the document. A label naming several occurrences is refused with their paths (`finger
  names 3 occurrences in kit: kit/hand/finger.1, kit/hand/finger.2, kit/hand/finger.3`), except one
  an assembly shares with a part inside it: `stem` is the assembly, and the part is `stem/stem`.
- **An element is named by its name or its number**, the part's own face, edge and vertex numbers
  that the viewer and `inspect` show. A name survives edits that a number does not. A bare element
  after an owner belongs to that owner (`palm,f:kit.body.1`).
- **`FILE` must be the document resolved in**: the model's id, or the file's path or its last
  segments. The viewer copies a ref with it first.
- **A ref resolves now, never as it was.** An element a later run moved or resized resolves where
  it is; one it deleted fails, naming it; one whose making changed fails too, saying what it is
  named now (`plate.body.6 is now f:plate.body.6;M:plate.relief`).
- **The canonical ref**, the `ref` that `inspect` answers, spells an element by its name under its
  part's label, or under the occurrence's path from the root where that label names several.

### References into other files

A reference into a file that is not a document names what the viewer picked in it, in that file's
own terms. None is a ref `cad <type> inspect` resolves:

| File | Reference | Means |
| --- | --- | --- |
| URDF, SRDF | `/work/arm/arm.urdf#upper_arm` | the link `upper_arm` |
| GLB | `/work/out/model.glb#n12` | the glTF node `nodes[12]` (0-based, the file's own index) |
| 3MF | `/work/out/plate.3mf#o2.1` | the 2nd `<build><item>`'s 1st `<component>` (1-based); `#o3` is the 3rd build item |
| STL | the file alone, on `File:` | one mesh: nothing in it is picked |
| DXF | `/work/DXF/panel.dxf#h2F` | the modelspace entity whose handle is `2F`; what a block reference draws is named by its INSERT |

### Element names

Every face, edge and vertex of a part is named by the feature history that made it, so it keeps its
name until that history changes. A name is its kind, the element it starts from, and a step for
each feature that made it out of another: `f:plate.body.6;M:plate.relief` is face 6 of `plate`'s
`body`, modified by `relief`.

- **A feature is the author's name for its result**: `relief = body - hole` in the function `plate`
  is `plate.relief`. A reassignment (`body = body - hole`) carries a tag spelled from its statement
  with the numbers masked (`bracket_body.body_dedanl`); a call the same statement made on the way
  is `<function>.<target>_<operation><n>` (`standoff.post_make_cylinder1`); a result assigned
  nowhere (a model's `return a + b`) is `<function>.<operation><n>` (`plate.fuse1`).
- **So a dimension edit keeps every name**, renaming a variable renames that feature's elements and
  nothing else, and moving code or inserting a statement of another shape renames nothing.
- **A label** on a shape handed to a later operation names, in what that operation makes, the
  feature that first made the shape (`f:fork.1;M:pair.twin` in the mirror of a part labelled
  `fork`). A placed part keeps its prototype's names: its label names the occurrence.
- **An element read from a file** keeps the name the file gives it (a STEP or an `.xbf` text-to-cad
  wrote names every one), else it is named by the read and its number within its part:
  `motor = step.read(...)` in `rig` names face 12 of a foreign STEP `f:rig.motor.12`.
- A long name folds to its last feature and a digest (`f:plate.relief~5d1e0c2f9a3b`): copy names
  whole.

### A picked element in a model's body

A ref resolves in the server (`cad <type> inspect`, the viewer), never in a model: a body selects
from the live shape it is building with build123d, by what the element is. To change what a person
picked, read the ref's answer and either edit the code its `made_by` names or pick the same element
in the body:

```bash
cad model inspect "$ID" "plate/f:plate.body.6;M:plate.relief"   # centroid (0, 0, 2), a plane: the top
```

```python
import build123d as bd
from cad import model

from plate import plate


@model
def bracket():
    base = plate().shape
    top = base.faces().sort_by(bd.Axis.Z)[-1]                 # the face the person picked
    return base + bd.Pos(top.center(bd.CenterOf.MASS)) * bd.Cylinder(4, 10)
```

## Which code made it

`cad model inspect "$ID" REF` answers what a ref names, placed where its occurrence stands
(`cad xbf inspect FILE REF` or `cad step inspect FILE REF` for a file):

- an element: its kind, number, name and canonical ref; the kernel's facts (a face's area,
  centroid, surface type, exact box and radius; an edge's length, curve type, class and endpoints;
  a vertex's position); and `made_by`: the feature that made it, its operation, and the function,
  file and line of the call;
- a part or an assembly: its volume, its world bounds, and its mass at each part's material
  density, the parts that have no material under `unweighed`; one part, its material, density and
  placement too.

```text
$ cad model inspect "$ID" "bracket/face 7"
{
  "ref": "bracket/f:bracket_body.hole.1;M:bracket_body.body_dedanl",
  "path": "bracket/bracket",
  "kind": "face",
  "ordinal": 7,
  "surface": "cylinder",
  "radius": 4.0,
  "made_by": {"feature": "bracket_body.body_dedanl", "operation": "cut", "function": "bracket_body",
              "file": "/work/src/bracket.py", "line": 8},
  ...
}
```

The bore's wall is face 1 of the cylinder `hole`, modified by the cut whose result `body` took.
`made_by` comes from the worker that built the document: it is `null` once that worker has retired
(the summary's `state` reads `held`, not `live`), and running the script again brings it back. A
file's element has none: a file names no model. A ref of several selectors answers a list; one that
names nothing is refused (exit 2) with the nearest names.

Without a ref, `cad model inspect "$ID"` prints what the document holds, then the closure it was
built from (its script, modules and input files, each by digest). Read it for the names a ref, a
pose or a snapshot takes, rather than guessing them:

```text
$ cad model inspect "$ID"
hinge  09ffb984-e388-502a-96e4-a5f9feb2f88c
state       live, not cached, built 4s ago
parts       2 in hinge
bounds      193.9 x 60 x 88.66 mm, from (-50, -30, 0)
volume      144,000 mm^3
materials   0.324 kg in all
  Alu_G6061_T6: 0.324 kg, hinge/base
  no material: hinge/arm
joints
  elbow  revolute  -10 to 120 deg, as built 30
couplings   none
states
  closed  elbow 0
  open  elbow 90
sequences
  cycle  5 s
...
```

`--json` prints it as `{"summary", "closure"}`, and `--query structure` prints the lists without
the bounds, volume and masses, measuring nothing. Two lines appear only where they apply:

- `declared`, where the model declares what a part or an assembly weighs (`mass`, `point_mass`):
  the masses are then the robot description's (the declared total, its solids scaled to it), and
  the line says how much is declared and how much computed at the materials' densities, with each
  declared mass under it (`--json`: `declared`). A mass the description cannot carry reads
  `declared    refused:` with the reason.
- `inside out`, naming each part with a solid whose faces point inward (`--json`: `inverted`): a
  negative volume a Boolean can leave, which a run and a snapshot do not show. Build that part
  another way (a revolved profile in place of stacked Booleans) before trusting its volume or a fit.

## Measurements

```python
angle = u.get_signed_angle(v, normal)      # degrees from vector u to v about normal; u.get_angle(v) unsigned
center, radius = circular_edge.arc_center, circular_edge.radius
axis = cylindrical_face.axis_of_rotation   # Axis (a point on it, its direction); None for a plane
bore = cylindrical_face.radius
```

A cylindrical face's `center()` is a point on its wall, not on its axis.

```python
from cad.build123d import closest_points, overlap_volume

result = closest_points(a, b)   # .distance, .point_a, .point_b
volume = overlap_volume(solid_a, solid_b)
```

`closest_points` returns the minimum distance and one witness pair; overlap, contact and
containment all give 0, so it does not measure penetration. `overlap_volume` is the exact
intersection volume (mm³) of two finite, positively oriented solids, 0 for mere contact; a kernel
failure raises. `cad model interference` is that measure over every pair of a document
([interference](#interference)).

- A part meant to sit on, bolt to or bear against another measures `closest_points` distance 0
  against it; above 0 is a gap, and the part floats.
- A solid-to-solid `closest_points` on large parts (a vendor STEP's, thousands of faces each)
  takes seconds a pair: rule pairs out first by `bounding_box(optimal=False)` boxes that do not
  meet, and measure from a point (`bd.Vertex(*p)`) where a point answers the question.
- Both measure the parts as built: a part clear there can still pass through another in a pose
  ([reviewing motion](kinematics.md#reviewing-motion)).

## Geometry diagnostics

```python
from cad.build123d import is_sound, topology_errors, boundary_edges, self_intersections

ok = shape.is_valid                       # bool: BRepCheck passes (build123d)
clean = is_sound(shape)                   # bool: the boolean kernel's argument check passes, expensive
issues = topology_errors(shape)           # tuple[GeometryIssue, ...]
free = boundary_edges(shell)              # tuple[Edge, ...]
crossings = self_intersections(shape)     # tuple[GeometryIssue, ...], expensive
```

A `GeometryIssue` has `code` (an OCCT `BRepCheck_*` or `BOPAlgo_SelfIntersect` status) and
`entities`. An inconclusive check raises `GeometryError` rather than passing; none of these repair
geometry. `is_sound` is the gate a fuse or cut demands of an operand (`False` for a null or empty
shape). A reversed solid can pass topology checks with negative volume and aggregate volumes can
cancel, so check signed volume per solid; no free edges means closed, not manifold.

## Interference

`cad model interference "$ID"` (`cad xbf interference FILE`, `cad step interference FILE`) says which
parts of a document share volume. The verdict is the kernel's, exact, on the parts' own solids, so a
plate through a 2.6 mm skin is found and a part 0.3 mm from another is not; meshes only rule out
the pairs with air between them.

```bash
cad model interference "$ID"                                  # as built
cad model interference "$ID" --pose crouch --pose bow       # and at mechanism states
cad model interference "$ID" --pose walk@0 --pose walk@0.6 --pose '{"l_knee": 90}'   # a sequence at times of it, joint values
cad model interference "$ID" --fit 'bearing*' housing --fit pin base   # pairs meant to share volume
```

```text
$ cad model interference "$ID" --pose '{"elbow": -10}'
error: overlapping_parts at hinge/base: shares 176.3 mm^3 with hinge/arm ({"elbow":-10}) Hint: move or resize one of the two, or name the pair a fit if it is meant to share volume (--fit A B)
FAILED hinge: 1 pair of parts share volume (2 parts at 2 poses, the boxes of 2 pairs met: 1 kept, 1 measured, in 1.82 s)
```

- **The status is the verdict**: 0 clear, 1 a pair shares volume, 3 none found but a pair could not
  be measured, which is no pass. A pair is unmeasured (`reason`) when its Boolean ran past five
  minutes or the whole check past twenty (`over_time`), when its process was lost (`process_lost`)
  or when the kernel refused the two (`error`): run the check again, which goes on from what was
  measured, or measure that pair in a check of its own. `--json` is the result whole
  (`measurements.overlaps`, `.fits`, `.unmeasured`: each row `between` its two occurrence paths,
  with every pose it holds at).
- **The first check of an assembly is the slow one** (a 700-part humanoid: ten minutes on four
  cores, most of it eight pairs of large lofted surfaces in contact over their whole area). Each
  pair's answer is kept, so a later check measures only the pairs a changed part or a new pose
  moves. The summary counts the pairs `apart` by their meshes, `kept` and `measured`, and
  `measurements.slowest` names the pairs that took longest.
- **It checks the poses it is given, and chooses none.** `--pose` repeats and takes what a
  snapshot's does: a mechanism state's name, a configuration sequence at a time of it (`walk@0.6`),
  or `{joint or coupling: value}`. `cad model inspect "$ID"` lists the states, and the sequences
  with their durations.
- **A fit is named, never inferred.** `--fit A B` takes two refs or globs; the pair's overlap is
  listed as a fit and is no overlap to fix. A shared volume of 0.001 mm^3 or less is the rounding
  along a face where two parts touch, and none (`--min-volume`).
- **What it cannot see**: a pose it was not given (a time between two of a sequence), a part with
  no solid (left out, and counted), and joints that share a centre taken to the corners of their
  travel together, which is a `--pose` for each corner. Say so with the result.
- From a script, `cad.model.interference(robot(), poses=["crouch", "walk@0.6"], fits=[("pin", "base")])`
  returns the same result (`.ok`, `.findings`, `.measurements`).

## Mass properties

A part given a material ([materials](build123d-modeling.md#colour-and-materials)) is weighed by
`cad model inspect "$ID" OWNER`. A script that needs every part's density (a link's mass summed
from its parts) asks the server, which transfers no solid:

```python
from cad import model

materials = model.inspect(robot(), query="structure")["summary"]["materials"]
# [{"name": "Alu_G6061_T6", "density": 2700, "parts": ["robot/hip/bracket", ...]}, ...]
```

`model.inspect(handle, "hip/bracket")` answers one part or assembly as the command does. For
explicit densities, a centre of mass or inertia:

```python
from cad.build123d import mass_properties

properties = mass_properties([
    (aluminum_body.solid(), 2.70e-6),  # (Solid, kg/mm³)
    (steel_insert.solid(), 7.85e-6),
])
print(properties.volume, properties.mass, properties.center_of_mass)
print(properties.inertia)
```

`mass_properties` takes `Solid`s, integrates uniform density per solid and sums the bodies,
overlaps included. The 3×3 inertia is about the combined centre of mass in the input axes; with mm
and kg/mm³, outputs are mm³, kg, mm and kg·mm².

`.volume`, `mass_properties` and `overlap_volume` integrate at a fixed order, exact on planes,
cylinders and spheres and a little off on lofted and spline solids: 0.4 % high on one lofted solid,
so the three volumes of a correct cut (what was there, what is left, what was removed) need not add
up, and a hole can change a volume by more than its own. A check that guards a Boolean by volume
allows a per cent, or integrates adaptively (0.04 to 2.4 s a solid):

```python
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

props = GProp_GProps()
BRepGProp.VolumePropertiesGK_s(solid.wrapped, props, 1e-6, False, False, False, False, False)
volume = props.Mass()
```
