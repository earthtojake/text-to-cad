# Assembly positioning and mating

Read this file when placing assembly parts, defining mating datums or checking
alignment. Placements live in the model source; the saved geometry is what was
written. Explicit transforms and native build123d joints both work at any
assembly size.

## Transforms and local frames

```python
# Inside an assembly model:
left = bd.Pos(-pitch / 2, 0, height) * spacer()
left.label = "spacer_left"
right = bd.Pos(pitch / 2, 0, height) * spacer()
right.label = "spacer_right"
assembly = bd.Compound(children=[left, right], label="spacer_pair")
```

A placed child model stays linked to its tree; `.located()` replaces the
placement and loses the link. Labels identify roles and repeated occurrences,
such as `m3_screw:front_left`; a functional group can be a nested labeled
`Compound`.

Mirroring changes geometry, so an inline mirrored child belongs to the parent
rather than linking to the original child's tree. It remains cached with that
parent. A separate mirrored model is useful for independent outputs or reuse,
not a requirement; see [mirroring and caching](step-generation.md#mirrored-geometry-and-reusable-models).

## Native joints

Joints can express a relationship between reusable datums without hand-solving
its placement. They perform source-level placement; they are not persistent
STEP constraints or a replacement for the separate [kinematics](kinematics.md)
interface. Call `connect_to()` on the fixed joint with the moving joint as its
argument.

For example, `src/enclosure.py` places a lid above a base with a specified gap:

```python
from cadgen import build123d as bd, step

BASE_HEIGHT = 30.0
LID_THICKNESS = 3.0
GASKET_GAP = 0.5


@step(out="../STEP/enclosure.step")
def enclosure():
    base = bd.Box(80, 50, BASE_HEIGHT)
    lid = bd.Box(80, 50, LID_THICKNESS)
    base.label, lid.label = "base", "lid"
    bd.RigidJoint(
        "lid_target", to_part=base,
        joint_location=bd.Location((0, 0, BASE_HEIGHT / 2 + GASKET_GAP)),
    )
    bd.RigidJoint(
        "underside", to_part=lid,
        joint_location=bd.Location((0, 0, -LID_THICKNESS / 2)),
    )
    base.joints["lid_target"].connect_to(lid.joints["underside"])
    return bd.Compound(children=[base, lid], label="enclosure")


if __name__ == "__main__":
    enclosure()
```

Native joint options include `RigidJoint` for fixed placement, `RevoluteJoint`
for rotation, `LinearJoint` for translation, `CylindricalJoint` for combined
rotation/translation and `BallJoint` for spherical orientation. Use `Location`
for rigid/ball joint frames and `Axis` for revolute/linear/cylindrical joints.

Creating joints reads the child's placement and may materialize it earlier
than a deferred transform. Cached child models return geometry, labels,
appearance and placements, not Python joint objects, so the joints a parent
needs are defined in its source.

## Child models and imported components

A project model is composed by calling it; `cadgen.read_step` reads a vendor
document or an explicitly decoupled export, an input like every file a build
reads. See the [model contract](step-generation.md) for dependency tracking.

An imported part keeps its vendor's origin and orientation; `read_scene` shows
them and its functional features. Measured offsets or joint frames go in the
source.

## Alignment and measurement checks

There is no generic alignment mode that guesses which points or axes the design
means: a check names the mating features (from `read_scene`) and states the
relationship in Python. See `inspection-and-validation.md` for the reader and
native measurement interfaces.

For example, for two planar mating faces (with their refs already identified):

```python
from cadgen import read_scene

scene = read_scene("STEP/assembly.step")
moving = scene.resolve("#moving.f1").shape()
fixed = scene.resolve("#fixed.f2").shape()
n = fixed.normal_at().normalized()
m = moving.normal_at().normalized()
signed_gap_mm = (moving.center() - fixed.center()).dot(n)
parallel_error_deg = min(n.get_angle(m), n.get_angle(-m))
print(signed_gap_mm, parallel_error_deg)
assert abs(signed_gap_mm) < 0.01
assert parallel_error_deg < 0.1
```

A plane gap and parallelism test does not establish lateral alignment or
overlapping face footprints, and accepting either parallel direction misses a
flipped part. A screw pattern's spacing is between the analytic centers of its
circular edges, clear space between bodies is `closest_points`, and
`shape.bounding_box().size` is the world-aligned envelope.
