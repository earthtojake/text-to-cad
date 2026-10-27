# Assembly positioning and mating

Read this file when placing assembly parts, defining mating datums or checking
alignment.

## Contents

- [Transforms and local frames](#transforms-and-local-frames)
- [Native joints](#native-joints)
- [Child models and imported components](#child-models-and-imported-components)
- [Alignment and measurement checks](#alignment-and-measurement-checks)

## Transforms and local frames

```python
# Inside an assembly model:
left = bd.Pos(-pitch / 2, 0, height) * spacer()
left.label = "spacer_left"
right = bd.Pos(pitch / 2, 0, height) * spacer()
right.label = "spacer_right"
assembly = bd.Compound(children=[left, right], label="spacer_pair")
```

A placement shares its shape: `Pos(...) * part`, `.moved()` and `.located()` place
the same geometry again, so a part placed many times is one part in the document.
`.located()` replaces the placement where `.moved()` composes it. Labels name roles
and repeated placements, and a functional group is a nested labelled `Compound`.

Mirroring makes new geometry, not a placement: `bd.mirror(left, about=bd.Plane.YZ)`
inline is a part of its own. A separate mirrored model suits a part that needs its
own files or reuse across assemblies; a shared factory in `lib/` serves both hands.

## Native joints

Joints express a relationship between datums without hand-solving the placement,
and the engine keeps them as the assembly's mechanism. Call `connect_to()` on the
joint that stays, with the moving part's joint as its argument.

For example, `src/enclosure.py` seats a lid on a base with a gasket gap:

```python
import build123d as bd
from cadgen import model

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
    base.joints["lid_seat"].connect_to(lid.joints["lid_seat"])
    return bd.Compound(children=[base, lid], label="enclosure")


if __name__ == "__main__":
    enclosure()
```

The joint kinds are `RigidJoint` for fixed placement, `RevoluteJoint` for rotation,
`LinearJoint` for translation, `CylindricalJoint` for both about one axis and
`BallJoint` for spherical orientation. Use a `Location` for rigid and ball joint
frames and an `Axis` for revolute, linear and cylindrical joints. Two parts whose
rigid joints are connected move as one; a moving joint makes a pair the viewer's
Position, a snapshot's `--pose` and the model's motions drive ([kinematics](kinematics.md)).

Connect parts before putting them in the compound that holds them. `connect_to`
cannot place a part inside a nested assembly: there, put each part where it stands
and give the two joints one label, and the engine pairs them by it. A child model's
joints stay in its own document, so the joints an assembly needs are authored in the
assembly's body, on the parts it places.

## Child models and imported components

A project model is composed by calling it; `read_xbf` reads a vendor part converted
once from its STEP (`cadgen export vendor.step vendor.xbf`), and `read_step` a STEP
as it is. Both are inputs, like every file a run reads
([inputs](model-contract.md#inputs)). An imported part keeps its vendor's origin and
orientation; a snapshot or `cadgen inspect` shows them and its functional features, and the
measured offsets or joint frames go in the source.

## Alignment and measurement checks

There is no generic alignment mode that guesses which points or axes the design
means: a check names the mating features and states the relationship in Python
([inspection](inspection-and-validation.md)).

For example, for the enclosure's two mating faces, using `find_part` and `world_parts`
copied from [Opening geometry](inspection-and-validation.md#opening-geometry):

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
flipped part. A screw pattern's spacing is between the analytic centers of its
circular edges, clear space between bodies is `closest_points`, and
`shape.bounding_box().size` is the world-aligned envelope once ancestor placements
have been applied.
