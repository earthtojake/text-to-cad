# Assembly positioning and mating

Read this file when placing assembly parts, defining mating datums or checking
alignment. Author placements in the model source, then check the saved geometry.
Choose explicit transforms or native build123d joints according to which makes
the intended relationship easiest to express and maintain. Neither requires a
particular assembly size or complexity.

## Transforms and local frames

Use functional datums and explicit dimensions for placements. A part's origin
might be its mounting interface, symmetry center or rotational axis; use the
convention that fits the design. Record it when another part depends on it.

```python
# Inside an assembly model:
left = bd.Pos(-pitch / 2, 0, height) * spacer()
left.label = "spacer_left"
right = bd.Pos(pitch / 2, 0, height) * spacer()
right.label = "spacer_right"
assembly = bd.Compound(children=[left, right], label="spacer_pair")
```

Place child models with `.moved()` or `Pos/Rot/Location * child` to preserve
shared geometry. `.located()` replaces the existing placement and copies the
geometry; it loses the cached child link. Labels identify roles and repeated
occurrences, such as `m3_screw:front_left`. A functional group can be a nested
labeled `Compound` when the design benefits from that hierarchy.

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
appearance and placements; do not rely on Python joint objects surviving a
child's cache round trip. Define the joints needed by the parent in its source.

## Child models and imported components

Call a project model to compose it. Use `cadgen.read_step` for a vendor document
or an explicitly decoupled export; that records the file as a build input.
See the [model contract](step-generation.md) for dependency tracking.

For imported geometry, inspect its existing origin, orientation and functional
features with `read_scene` before choosing datums. Express measured offsets
or joint frames in the source, then validate the placed result. Anchor model
input paths on `__file__` when they must work from any working directory.

```bash
python path/to/assembly.py
python tmp/check_assembly.py
```

## Alignment and measurement checks

Select the actual mating features from `read_scene`, then express the intended
relationship in Python. There is no generic alignment mode that guesses which
points or axes the design means. See `inspection-and-validation.md` for the
reader and native measurement interfaces.

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

These thresholds are illustrative; use the task's tolerances. The plane gap
and parallelism test does not establish lateral alignment or overlapping face
footprints. Check those when required. For opposed normals, assert the signed
orientation explicitly instead of accepting either parallel direction.

For a screw-pattern dimension, compare the analytic centers of the selected
circular edges. For clear space between bodies use `closest_points`.
`shape.bounding_box().size` measures the world-aligned envelope. Use explicit
vectors and datums for orientation, signed offsets and center spacing.
Update source placements, regenerate, and rerun the relevant checks.

Correct failed positioning in the model source, then regenerate and rerun the
relevant checks. Report measured relationships and any intended alignment left
unchecked; no positioning report is needed when positioning is irrelevant.
