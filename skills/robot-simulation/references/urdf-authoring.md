# URDF Authoring Contract

Use this reference when writing or editing URDF XML directly. The `.urdf` file is the source of truth: it must carry its own documentation, and its structure must be predictable enough that any later agent or engineer can audit it without external context.

## Edit Loop

1. Locate the target `.urdf`. It is the source of truth; edit it directly.
2. Identify target consumers and strictness requirements: visualization, TF tree, simulation, planning, or real robot integration.
3. Read the design-ledger comment block at the top of the file; create it if missing (see [urdf-ledger.md](urdf-ledger.md)). Update the ledger in the same edit that changes modeled facts.
4. If links reference meshes, prepare or verify the per-link assets first (see [meshes.md](meshes.md)).
5. Apply URDF frame semantics exactly: joint origin in parent frame, child link frame at joint frame, joint axis in joint frame, visual/collision/inertial origins in link frame (see [urdf-frames.md](urdf-frames.md)).
6. Author links, joints, limits, axes, origins, inertials, and geometry per this contract. Compute derived numbers — inertia tensors, unit conversions, mirrored transforms — with formulas or a helper script; never freehand them (see [inertials.md](inertials.md)).
7. Validate with `cad urdf validate <file.urdf>` and fix findings until clean.
8. Run the rest of the verification recipe in [urdf-checks.md](urdf-checks.md): external tools when available, then a viewer sweep ([Show the model](../SKILL.md#show-the-model)) of every movable joint against the ledger's positive-motion statements.
9. Report smoke tests run, checks skipped, remaining assumptions, and unchecked spatial data.

## File Shape

Every authored `.urdf` follows this shape, in this order:

1. XML declaration: `<?xml version="1.0"?>`.
2. Design-ledger comment block (compact form in [urdf-ledger.md](urdf-ledger.md#in-the-file)).
3. One `<robot name="...">` root element.
4. All `<link>` elements, root link first, then in tree order (parents before children).
5. All `<joint>` elements, in the same tree order as the child links they create.

Keep two-space indentation and one element per line. Do not interleave links and joints arbitrarily; a reader should be able to walk the kinematic tree top-to-bottom.

## Naming

- Links: `<part>_link` for physical links (`base_link`, `forearm_link`), bare descriptive names for frame-only links (`base_footprint`, `tool0`, `camera_optical_frame`).
- Joints: `<child-function>_joint` or `<parent>_to_<child>` (`shoulder_pan_joint`, `wrist_roll`). One convention per file.
- Names are identifiers consumed by SRDF, controllers, and TF; never rename casually. If a rename is required, update every consumer (SRDF groups, group states, disabled collisions) in the same task.

## Links

Use these tags for each link that represents physical robot geometry, in this order:

- `inertial`: mass, center of mass, and inertia tensor used by simulators.
- `visual`: display geometry and optional material.
- `collision`: contact geometry used by physics and planning.

Model them separately when the target consumer needs them. Frame-only links, such as `base_footprint`, optical frames, or tool-center marker frames, are empty (`<link name="tool0" />`), represent no physical mass or geometry, and must be listed as frame-only in the ledger.

For movable physical links, avoid zero or missing mass unless the target simulator explicitly supports that modeling choice. If exact mass properties are unavailable, use a documented approximation and make the approximation easy to replace later. The inertial origin is the center of mass in the link frame — not automatically the visual mesh origin, collision origin, or link origin. All values are computed or copied from source data, never freehanded; see [inertials.md](inertials.md) for formulas, the mesh-script recipe, and sanity gates.

### Collision Geometry

Add collision geometry under each `<link>` that should participate in physics, contact, or collision-aware planning. Do not encode collision behavior on joints.

Use one or more `<collision>` blocks per link. The `<origin>` is expressed in the link frame, just like `<visual>`, and mesh scales must match the units of the exported mesh.

Prefer simplified collision geometry over detailed visual meshes, from simplest to most specific:

- primitive `<box>`, `<cylinder>`, or `<sphere>` geometry when it approximates the part well;
- a coarse, closed collision mesh exported from CAD;
- the visual mesh as a temporary fallback for loading and smoke tests.

## Joints

For every `<joint>`:

- Attributes: `name`, `type` (`fixed`, `revolute`, `continuous`, or `prismatic`; use `floating`/`planar` only when the consumer and validation path support them — the bundled validator rejects them). Supported joint types may vary by consumer.
- Children in order: `<parent>`, `<child>`, `<origin>`, `<axis>` (movable joints), `<limit>` (revolute/prismatic), then optional `<dynamics>`, `<mimic>`, `<calibration>`, `<safety_controller>`.
- `<origin>` is the parent-link-frame transform to the joint frame at zero position; the child link frame coincides with the joint frame.
- `<axis>` is expressed in the joint (child) frame and should be a signed unit vector along a principal axis whenever the mechanism allows (`1 0 0`, `0 -1 0`, ...). A non-principal axis is a red flag: re-check the frame definitions before accepting one.
- `<limit>` carries radians (revolute) or meters (prismatic) plus `effort` and `velocity` when the consumer needs them. `continuous` joints take no lower/upper limits.
- Fixed joints are used for frame relationships and rigid assemblies.

For every joint, confirm:

- parent and child direction are correct;
- joint origin is expressed in the parent link frame and places the child frame at zero position;
- non-fixed joint axis is expressed in the joint frame, preferably a signed unit vector along a principal axis;
- positive motion is stated in words in the ledger ("positive shoulder_pitch raises the arm") — the axis sign is part of the model, not a cosmetic detail;
- revolute limits are radians, prismatic limits are meters;
- continuous joints are not given artificial finite lower/upper limits.

After authoring, the axis-sign check is non-negotiable: sweep the joint in the viewer and compare the motion with the ledger statement. Structural validation cannot catch a flipped sign.

Never encode a kinematic fix by offsetting only the visual mesh; correct the joint/link frames instead, unless the mesh is genuinely offset from the link frame.

A nonlinear four-bar linkage, which standard `<mimic>` cannot close, takes the vendor extension in [urdf-four-bar.md](urdf-four-bar.md).

## Golden Skeleton

Copy this shape for new robots. It shows the ledger, ordering, a frame-only root, one fixed and one revolute joint, mesh + primitive geometry, and a computed inertial:

```xml
<?xml version="1.0"?>
<!--
  robot: example_arm | consumers: CAD Viewer, MoveIt
  units: meters, kilograms, radians | frames: +X forward, +Y left, +Z up (REP-103)
  root: base_footprint | source of dimensions: STEP/example_arm.step
  meshes: 3MF/, exported per-link in link frame, source units mm, scale 0.001
  inertials: primitive-formula approximations at assumed uniform density 1200 kg/m^3
  assumptions:
  - shoulder axis sign chosen so positive motion raises the arm (+Y rotation)
  - base mass 1.2 kg estimated, not weighed
-->
<robot name="example_arm">
  <link name="base_footprint" />
  <link name="base_link">
    <inertial>
      <origin xyz="0 0 0.03" rpy="0 0 0" />
      <mass value="1.2" />
      <!-- solid cylinder r=0.06 l=0.06: ixx=iyy=m(3r^2+l^2)/12, izz=m r^2/2 -->
      <inertia ixx="0.00144" ixy="0" ixz="0" iyy="0.00144" iyz="0" izz="0.00216" />
    </inertial>
    <visual>
      <origin xyz="0 0 0" rpy="0 0 0" />
      <geometry>
        <mesh filename="3MF/base_link.3mf" scale="0.001 0.001 0.001" />
      </geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0.03" rpy="0 0 0" />
      <geometry>
        <cylinder radius="0.06" length="0.06" />
      </geometry>
    </collision>
  </link>
  <link name="shoulder_link">
    <inertial>
      <origin xyz="0 0 0.08" rpy="0 0 0" />
      <mass value="0.6" />
      <!-- solid box 0.06x0.06x0.16: ixx=iyy=m(y^2+z^2)/12, izz=m(x^2+y^2)/12 -->
      <inertia ixx="0.00146" ixy="0" ixz="0" iyy="0.00146" iyz="0" izz="0.00036" />
    </inertial>
    <visual>
      <origin xyz="0 0 0" rpy="0 0 0" />
      <geometry>
        <mesh filename="3MF/shoulder_link.3mf" scale="0.001 0.001 0.001" />
      </geometry>
    </visual>
    <collision>
      <origin xyz="0 0 0.08" rpy="0 0 0" />
      <geometry>
        <box size="0.06 0.06 0.16" />
      </geometry>
    </collision>
  </link>
  <joint name="base_footprint_to_base" type="fixed">
    <parent link="base_footprint" />
    <child link="base_link" />
    <origin xyz="0 0 0" rpy="0 0 0" />
  </joint>
  <joint name="shoulder_pitch" type="revolute">
    <parent link="base_link" />
    <child link="shoulder_link" />
    <origin xyz="0 0 0.06" rpy="0 0 0" />
    <axis xyz="0 1 0" />
    <limit lower="-1.5708" upper="1.5708" effort="8" velocity="2" />
  </joint>
</robot>
```

## Helper Scripts

Direct authoring does not mean freehand numbers. Write a throwaway script whenever:

- inertials come from meshes or CAD solids (mass properties integration);
- more than a handful of transforms share a conversion (mm-to-m tables, mirrored left/right chains);
- disabled-collision or adjacency data must be derived downstream.

For complex or genuinely parametric models, the helper may be kept on disk next to related model source (for example beside the CAD model scripts the meshes come from) and referenced from the ledger. The checked-in `.urdf` is still canonical: regenerating is an explicit editing action, never an implicit build step.
