# Assembly positioning and mating

Read this file when placing assembly parts, defining mating datums or checking
alignment.

## Transforms and local frames

```python
# Inside an assembly model's body:
post = spacer().shape                            # a child model's shape
left = bd.Pos(-pitch / 2, 0, height) * post      # a placement of it
right = bd.Pos(pitch / 2, 0, height) * post      # the same geometry, placed again
left.label, right.label = "spacer_left", "spacer_right"
pair = bd.Compound(children=[left, right], label="spacer_pair")
```

A placement shares its shape: `Pos(...) * part`, `.moved()` and `.located()` place
the same geometry again, so a part placed many times is one part in the document and in
every file. A placement that needs a B-rep of its own copies it with
`BRepBuilderAPI_Copy`. A functional group is a nested labelled `Compound`.
[Placement pitfalls](build123d-modeling.md#placement-and-frame-pitfalls) has the traps of
`.located()`, rotation frames and primitive alignment.

Mirroring makes new geometry, not a placement: `bd.mirror(left, about=bd.Plane.YZ)` is
a part of its own. Mirror inline, or make the mirrored part a model of its own where it
needs its own files.

A part read from a file ([inputs](model-contract.md#inputs)) keeps its vendor's origin
and orientation: find its mounting features with a snapshot or `cad <type> inspect`, and
write the measured offsets or joint frames in the source.

## Native joints

Joints express a relationship between datums without hand-solving the placement,
and the server keeps them as the assembly's mechanism. `src/enclosure.py` seats a lid
on a base with a gasket gap:

```python
import build123d as bd
from cad import model

BASE_HEIGHT = 30.0
LID_THICKNESS = 3.0
GASKET_GAP = 0.5


@model
def enclosure():
    base = bd.Box(80, 50, BASE_HEIGHT)
    lid = bd.Box(80, 50, LID_THICKNESS)
    base.label, lid.label = "base", "lid"
    bd.RigidJoint("lid_seat", base, bd.Location((0, 0, BASE_HEIGHT / 2 + GASKET_GAP)))
    bd.RigidJoint("lid_seat", lid, bd.Location((0, 0, -LID_THICKNESS / 2)))
    base.joints["lid_seat"].connect_to(lid.joints["lid_seat"])   # on the joint that stays; the lid moves
    return bd.Compound(children=[base, lid], label="enclosure")  # connected before the compound is made


if __name__ == "__main__":
    enclosure()
```

Two parts whose rigid joints are connected move as one. A moving joint (`RevoluteJoint`,
`LinearJoint`, `CylindricalJoint`, `BallJoint`) makes a pair that a pose and the model's
motions drive: its frames, the rules of `connect_to` and joints in a nested assembly are
in [kinematics](kinematics.md#joints-place-parts-and-make-the-mechanism).

## Alignment and measurement checks

No alignment mode guesses which points or axes the design means: a check names the
mating features and states the relationship in Python
([measurements](inspection-and-validation.md#measurements)). For the enclosure's two
mating faces, with `find_part` copied from
[Opening geometry](inspection-and-validation.md#opening-geometry):

```python
import build123d as bd

from enclosure import enclosure

doc = enclosure().shape
fixed = find_part(doc, "base").faces().sort_by(bd.Axis.Z)[-1]   # the base's world-Z top
moving = find_part(doc, "lid").faces().sort_by(bd.Axis.Z)[0]    # the lid's world-Z underside
n = fixed.normal_at().normalized()
m = moving.normal_at().normalized()
signed_gap_mm = (moving.center() - fixed.center()).dot(n)
parallel_error_deg = min(n.get_angle(m), n.get_angle(-m))
print(signed_gap_mm, parallel_error_deg)
assert abs(signed_gap_mm - 0.5) < 0.01
assert parallel_error_deg < 0.1
```

A plane gap and parallelism test does not establish lateral alignment or
overlapping face footprints, and accepting either parallel direction misses a
flipped part.
