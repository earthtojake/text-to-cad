# Positioning logic, joints, and mating

Read this file when geometry has mating interfaces, repeated features, assembly children, axes, datums, motion, or user-specified alignment. This is the authoritative reference for assembly positioning, part-local origins, build123d joints, explicit `Location` transforms, CLI `inspect align`, and positioning report content.

## Core rule

Positioning is authored in source and validated after generation. Do not position parts by visually dragging or by editing exported STEP geometry. Use build123d parameters, local coordinate systems, `Location` transforms, `Plane`/`Axis` datums, `cadgen.assembly.AssemblyHelper` relationships, source-level `Joint` objects when useful, and labeled assembly children.

## Terminology

Use these terms carefully:

- **AssemblyHelper** is the preferred generated-script wrapper from `cadgen.assembly`. It records semantic relationships such as `face_to_face`, `coaxial`, `revolute`, and `linear`, then realizes them with native build123d joints.
- **build123d joints** are source-level objects such as `RigidJoint`, `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, and `BallJoint`. They are attached to `Solid` or `Compound` objects and can reposition parts with `connect_to()`.
- **CLI `inspect align`** is a selector-pair validation tool. It computes a read-only translation delta between selected local refs in a STEP/CAD entry. It does not edit source code, patch exported STEP files, or represent an authored mate feature. This is the one place that distinction is defined; the rest of the skill assumes it.
- **Mating intent** is the design relationship: flush, centered, coaxial, offset, hinge-like, slider-like, or otherwise datum-driven.

Use `AssemblyHelper` and build123d joints to express and compute source assembly placement where appropriate, then use CLI inspection to validate the generated STEP.

## Preferred assembly structure

For assemblies, prefer a mate/joint-driven structure over arbitrary transforms:

```text
root component
→ part-local coordinate systems
→ named datums / joint locations
→ AssemblyHelper semantic relationships backed by native build123d joints
→ labeled Compound assembly with verbose native labels
→ refs/measure/frame/align validation
```

A numeric `Location(...)` should usually correspond to a stated datum, offset, clearance, screw axis, face contact, or joint relationship.

Place a shape with `Pos(...) * shape`, `Rot(...) * shape`, `Location(...) * shape`, or `shape.moved(loc)` — these move the shape and keep its geometry shared. Avoid `shape.located(loc)`: it deep-copies the geometry, which is slower and, for a child model placed in an assembly, breaks the cache's ability to reference the child instead of copying it.

Group a functional unit — a bearing, a gearbox stage, a fastener set — into a sub-assembly node with `asm.add_module(name, children)` when it is placed, reasoned about, or repeated as a unit; nested occurrence refs such as `#o1.12.1` then stay meaningful.

## Part-local positioning

For each part, define a local coordinate convention before modeling:

```text
- Origin: center, base datum, mounting interface, or functional axis.
- XY plane: main sketch/base plane unless another datum is dominant.
- +Z: extrusion/up direction.
- Named dimensions: offsets, hole spacing, boss spacing, clearances.
- Datum features: mating faces, screw axes, centerlines, locating tabs, rails.
```

Good defaults:

- Symmetric standalone parts: origin at body center.
- Plates: origin at footprint center; thickness along Z.
- Enclosures: origin at footprint center; base/lid mating surfaces controlled by Z parameters.
- Shaft/knob/axisymmetric parts: origin on rotational axis.
- Mating adapter plates: origin on the primary mounting datum or center of the bolt pattern.

## Feature placement inside a part

Use named parameters and local coordinates:

```python
hole_offset_x = 30
hole_offset_y = 17.5
hole_positions = [
    (-hole_offset_x, -hole_offset_y),
    ( hole_offset_x, -hole_offset_y),
    (-hole_offset_x,  hole_offset_y),
    ( hole_offset_x,  hole_offset_y),
]

with Locations(*hole_positions):
    Hole(radius=hole_diameter / 2)
```

Avoid untraceable placement constants inside geometry calls. Put all meaningful offsets into parameters.

## AssemblyHelper pattern

Use `AssemblyHelper` for generated assembly scripts. It keeps the LLM-facing code intent-focused while still using native build123d labels, `Joint` objects, and `Compound` assemblies.

```python
from cadgen import build123d as bd, step
from cadgen.assembly import AssemblyHelper

base_height = 30.0
lid_thickness = 3.0
gasket_gap = 0.5

asm = AssemblyHelper("enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

base_seat = asm.rigid_frame(
    base,
    "lid_seat",
    bd.Location((0, 0, base_height / 2)),
)
lid_underside = asm.rigid_frame(
    lid,
    "underside",
    bd.Location((0, 0, -lid_thickness / 2)),
)

asm.face_to_face(base_seat, lid_underside, offset=gasket_gap)


@step
def model():
    return asm.build()
```

The fixed target is listed first and the moving target second. In the example above, the base stays fixed and the lid moves. The helper is a positioning tool: it calls native build123d `connect_to()` under the hood and its whole output is the placed geometry — nothing about the relationship is recorded or exported. The STEP contains the resolved static placement and native assembly labels, not persistent constraints. Motion that should persist (joints the viewer animates, pose presets) is declared with `kinematics=` on the decorator (`references/kinematics.md`), not with the positioning helper.

Use helper labels intentionally:

```python
standoff = asm.feature(Cylinder(radius=3.0, height=12.0), "m3_standoff", "front_left")
hinge_axis = asm.rigid_frame(lid, "hinge_axis", Location((0, -25, 0)))
```

Assembly labels name the root occurrence. `asm.add()` labels child component occurrences and their exported shape context. For repeated hardware or library parts, use role/location labels such as `front_left` and `rear_right` so STEP topology and viewer selections remain traceable after export.

Feature labels survive best when the labeled geometry remains a child shape in a `Compound`. Labels on boolean-subtracted or fused feature history are not reliable STEP feature history.

Use the frame method that matches native build123d joint inputs: `rigid_frame()` and `ball_frame()` take a `Location`; `revolute_frame()`, `linear_frame()`, and `cylindrical_frame()` take an `Axis` plus optional native range/reference arguments.

## Child dependencies

A child part is wired in one of two modes — a **CHILD** (a model in this
project: import its function and call it; the default) or an **INPUT** (a
document read via `cadgen.read_step`: imported parts, or a generated part the
user explicitly asked to decouple). The modes, what a rebuild tracks, and the
code live in "Composing on other parts" in `step-generation.md`.
Positioning-wise the two are identical: a child is a shape; place it with the
same frames and mates as authored geometry.

**Place a child with `Pos/Rot/Location * child` or `child.moved(loc)` — never
`child.located(loc)`.** `located()` deep-copies the geometry, so the parent
owns a duplicate component instead of linking to the child's tree, and it
also discards any rotation the shape already carried (`build123d-modeling.md`).
`AssemblyHelper` and build123d joints place through `connect_to()` and keep
the link. A mirrored placement is not a placement at all — STEP cannot express
a reflection — so a right-hand part is its own model built from the shared
factory (`step-generation.md`, "Mirrored parts are their own models").

## Imported components

For purchased or downloaded parts (see `$step-parts`), read the STEP file
with `cadgen.read_step` (never `build123d.import_step` — the whys are in
"Composing on other parts" in `step-generation.md`) and add it like any
authored part.

```python
from cadgen import read_step

servo = asm.add(read_step("models/parts/sg90_servo.step"), "servo")
```

Imported geometry was not authored here, so do not assume its origin or orientation. Derive mating frames from inspected geometry: run `refs --facts --planes --positioning` and `measure` against the imported part, then define `asm.rigid_frame(...)` locations from the measured faces, axes, and bolt patterns. Validate the resulting mate exactly like an authored one.

## When to use build123d joints

Use `AssemblyHelper`/build123d joints when assembly intent is clearer as a relationship between part datums than as a raw transform:

- lid-to-base, cover-to-frame, bracket-to-rail, flange-to-pipe, pin-to-hole, shaft-to-bearing
- hinge, slider, screw-like, cylindrical, ball/gimbal, or other motion-positioned assemblies
- repeated or library components that already expose joints
- source assemblies where a change to one dimension should recompute part placement

Direct `Location(...)` transforms are acceptable for simple static layouts when they are parameterized and documented, such as a row of identical spacers or a visual exploded view.

Raw build123d joints are acceptable for advanced cases not covered by `AssemblyHelper`, but preserve the same fixed-first directionality: call `connect_to()` on the fixed/root joint and pass the moving part's joint as `other`. `connect_to()` is a source-generation operation. It repositions the moving part for the generated model; it is not a persistent external constraint in the exported STEP file.

## Joint type selection

Use the simplest joint that expresses the source-level relationship:

- `RigidJoint` / `asm.rigid_frame()`: fixed placement, face-to-face seating, mounting datums, imported components with known interfaces.
- `RevoluteJoint` / `asm.revolute_frame()`: hinge or rotational pose; define with an `Axis` and drive with an angle parameter for a static STEP pose.
- `LinearJoint` / `asm.linear_frame()`: slider, latch, telescoping component; define with an `Axis` and drive with a position parameter.
- `CylindricalJoint` / `asm.cylindrical_frame()`: combined axial translation and rotation, such as screw-like or pin-in-slot relationships.
- `BallJoint` / `asm.ball_frame()`: gimbal or spherical orientation relationship; define with a `Location` and angular ranges.

When only final static placement matters and no meaningful joint datum exists, use explicit `Location` transforms and validate them.

## Assembly positioning workflow

1. Choose the fixed/root component.
2. Define part-local frames and datums before modeling child placement.
3. Identify functional datums such as mating faces, screw axes, hinge axes, sliding axes, locating tabs, gasket offsets, or contact planes.
4. Name source-level joints or mating datums on each child with `asm.rigid_frame()`, `asm.revolute_frame()`, `asm.linear_frame()`, or another helper frame method.
5. Use `AssemblyHelper` relationship methods where they improve source clarity, otherwise use parameterized `Location` transforms.
6. Build a labeled `Compound` assembly with `asm.build()`.
7. Generate the assembly through the Python source, not by re-importing the generated STEP (see `step-generation.md`):

```bash
python path/to/assembly.py
cadgen step inspect refs path/to/assembly.step --facts --planes --positioning
```

## CLI alignment validation

After generation, select moving and target refs from the local selector refs returned by `refs --positioning` and compute deltas:

```bash
cadgen step inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

Use `--mode flush` for coplanar face alignment. Use `--mode center` for centerline, plane-center, or symmetrical alignment where supported by the selected references. If the returned delta is outside tolerance, apply a source-level correction (see below), regenerate, and rerun inspection.

## Frame validation

Use `frame` to inspect an occurrence or selector's world frame:

```bash
cadgen step inspect frame path/to/assembly.step '#selector'
```

Use this when:

- a child appears in the wrong orientation
- a mating face is offset in world coordinates
- an axis is expected to align with X/Y/Z
- repeated parts should share orientation
- a downstream task needs a stable coordinate frame

## Measurement validation

Use `measure` for scalar checks:

```bash
cadgen step inspect measure path/to/assembly.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis z
```

Examples:

- lid bottom face to base top face should be 0 mm for flush contact
- two screw axes should have matching X/Y positions
- bracket mounting face should sit a specified distance from a datum plane
- spacer height should equal requested offset

## Source-level positioning corrections

When a positioning check fails, fix one of these in source:

- child `Location` translation
- child `Location` rotation
- `AssemblyHelper` relationship fixed/moving order or offset
- build123d joint location or axis
- part-local origin convention
- feature offset parameter
- sketch plane
- workplane selection
- assembly hierarchy
- symmetric placement signs

Then regenerate. Do not patch the exported STEP directly.

## Reporting positioning

In the final response, report only checks that were run:

```text
Positioning/joints:
- source used RigidJoint lid_seat → underside
- base/lid Z mate flush, delta 0.00 mm
- screw boss axis alignment: checked in XY by measurement
- lid occurrence frame: +Z up, origin at assembly centerline
```

If no positioning-sensitive features exist, say:

```text
Positioning: not applicable beyond centered part-local origin.
```

If a mate or alignment was intended but not checked, say `not checked`; do not imply success.
