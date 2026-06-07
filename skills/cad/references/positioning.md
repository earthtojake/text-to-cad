# Positioning logic, joints, and mating

Read this file when geometry has mating interfaces, repeated features, assembly children, axes, datums, motion, or user-specified alignment. This is the authoritative reference for assembly positioning, build123d joints, explicit `Location` transforms, CLI `inspect align`, and positioning report content.

## Contents

- Core rule
- Terminology
- Preferred assembly structure
- Part-local positioning
- Feature placement inside a part
- AssemblyHelper pattern
- When to use build123d joints
- Joint type selection
- Assembly positioning workflow
- CLI alignment validation
- Frame validation
- Measurement validation
- Source-level positioning corrections
- Reporting positioning

## Core rule

Positioning is authored in source and validated after generation. Do not position parts by visually dragging or by editing exported STEP geometry. Use build123d parameters, local coordinate systems, `Location` transforms, `Plane`/`Axis` datums, `cadpy.assembly.AssemblyHelper` relationships, source-level `Joint` objects when useful, and labeled assembly children.

## Terminology

Use these terms carefully:

- **AssemblyHelper** is the preferred generated-script wrapper from `cadpy.assembly`. It records semantic relationships such as `face_to_face`, `coaxial`, `revolute`, and `linear`, then realizes them with native build123d joints.
- **build123d joints** are source-level objects such as `RigidJoint`, `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, and `BallJoint`. They are attached to `Solid` or `Compound` objects and can reposition parts with `connect_to()`.
- **CLI `inspect align`** is a selector-pair validation tool. It computes a read-only translation delta between selected local refs in a STEP/CAD entry. It does not edit source code, patch exported STEP files, or represent an authored mate feature.
- **Mating intent** is the design relationship: flush, centered, coaxial, offset, hinge-like, slider-like, or otherwise datum-driven.

There is no general instruction to ignore the CLI because build123d has joints. Use `AssemblyHelper` and build123d joints to express and compute source assembly placement where appropriate, then use CLI inspection to validate the generated STEP.

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
from build123d import *
from cadpy.assembly import AssemblyHelper

base_height = 30.0
lid_thickness = 3.0
gasket_gap = 0.5

asm = AssemblyHelper("enclosure")
base = asm.add(make_base(), "base")
lid = asm.add(make_lid(), "lid")

base_seat = asm.rigid_frame(
    base,
    "lid_seat",
    Location((0, 0, base_height / 2)),
)
lid_underside = asm.rigid_frame(
    lid,
    "underside",
    Location((0, 0, -lid_thickness / 2)),
)

asm.face_to_face(base_seat, lid_underside, offset=gasket_gap)

def gen_step():
    return asm.build()
```

The fixed target is listed first and the moving target second. In the example above, the base stays fixed and the lid moves. The helper records the relationship in source and calls native build123d `connect_to()` under the hood; exported STEP contains the resolved static placement and native assembly labels, not persistent external constraints.

Use helper labels intentionally:

```python
standoff = asm.feature(Cylinder(radius=3.0, height=12.0), "m3_standoff", "front_left")
hinge_axis = asm.rigid_frame(lid, "hinge_axis", Location((0, -25, 0)))
```

Assembly labels name the root occurrence. `asm.add()` labels child component occurrences and their exported shape context. For repeated hardware or library parts, use role/location labels such as `front_left` and `rear_right` so STEP topology and viewer selections remain traceable after export.

Feature labels survive best when the labeled geometry remains a child shape in a `Compound`. Labels on boolean-subtracted or fused feature history are not reliable STEP feature history.

Use the frame method that matches native build123d joint inputs: `rigid_frame()` and `ball_frame()` take a `Location`; `revolute_frame()`, `linear_frame()`, and `cylindrical_frame()` take an `Axis` plus optional native range/reference arguments.

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
7. Generate the assembly through the Python source, not by re-importing the generated STEP:

```bash
python scripts/step path/to/assembly.py
python scripts/inspect refs path/to/assembly.step --facts --planes --positioning
```

Passing a generated assembly STEP directly treats it as imported native STEP and does not preserve source-level composition semantics.

## CLI alignment validation

After generation, use CLI inspection to validate the STEP result:

```bash
python scripts/inspect refs path/to/assembly.step \
  --facts --planes --positioning
```

Then select moving and target refs from the returned local selector refs and compute read-only deltas:

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

Use `--mode flush` for coplanar face alignment. Use `--mode center` for centerline, plane-center, or symmetrical alignment where supported by the selected references. If the returned delta is outside tolerance, edit the build123d source placement, helper relationship, or joint location, regenerate, and rerun inspection.

## Frame validation

Use `frame` to inspect an occurrence or selector's world frame:

```bash
python scripts/inspect frame path/to/assembly.step '#selector'
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
python scripts/inspect measure path/to/assembly.step \
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
