# URDF Frame Semantics

Use this reference whenever editing origins, axes, visual placement, collision placement, or inertials. Most URDF authoring errors are frame errors.

## Core Semantics

URDF represents a robot as a tree of links connected by joints.

For a joint:

- `<parent link="...">` names the parent link.
- `<child link="...">` names the child link.
- `<origin xyz="..." rpy="...">` is the transform from the parent link frame to the joint frame.
- The child link frame is coincident with the joint frame.
- `<axis xyz="...">` for a movable joint is expressed in the joint frame, not automatically in the world frame and not in the visual mesh frame.

For link subelements:

- `<visual><origin ...>` is expressed in the link frame.
- `<collision><origin ...>` is expressed in the link frame.
- `<inertial><origin ...>` is the center-of-mass/inertial frame expressed in the link frame.

These origins are independent. A mesh can be offset from its link frame, and the center of mass can be offset differently.

## Units and Angles

Use:

- meters for length;
- kilograms for mass;
- radians for angles;
- seconds for time;
- right-handed coordinate frames unless the project documents an exception.

Do not store revolute limits in degrees in URDF. Convert degrees to radians before writing them.

Do not use finite lower/upper limits for a `continuous` joint unless the project is intentionally not using URDF continuous-joint semantics.

## Joint Axis Checklist

For every non-fixed joint, confirm:

1. the axis is present;
2. the axis vector has three finite numbers;
3. the vector is nonzero;
4. the vector is normalized or intentionally normalized by helper code;
5. the vector is expressed in the joint frame;
6. positive motion is documented.

Examples:

```xml
<joint name="shoulder_pan_joint" type="revolute">
  <parent link="base_link" />
  <child link="shoulder_link" />
  <origin xyz="0 0 0.24" rpy="0 0 0" />
  <axis xyz="0 0 1" />
  <limit lower="-3.14159" upper="3.14159" effort="40" velocity="2" />
</joint>
```

This means the child link frame is at `z = 0.24` in `base_link`, and positive joint motion rotates about +Z of the joint/child frame.

## Visual and Collision Placement Checklist

For every visual or collision block, confirm:

1. the origin is relative to the owning link frame;
2. mesh scale converts the mesh source units into meters;
3. visual and collision geometry are intentionally the same or intentionally different;
4. collision geometry is simple enough for the intended physics/planning consumer;
5. mesh paths are stable from the URDF file's location or use an intended package URI.

Example:

```xml
<link name="forearm_link">
  <visual>
    <origin xyz="0 0 0" rpy="0 0 0" />
    <geometry>
      <mesh filename="package://robot_description/meshes/forearm.stl" scale="0.001 0.001 0.001" />
    </geometry>
  </visual>
  <collision>
    <origin xyz="0.12 0 0" rpy="0 1.57079632679 0" />
    <geometry>
      <cylinder radius="0.035" length="0.24" />
    </geometry>
  </collision>
</link>
```

This places the visual mesh at the link frame and uses a simplified collision cylinder offset in the same link frame.

## Inertial Placement Checklist

For every physical link with inertial data, confirm:

1. mass is positive and finite;
2. inertial origin is the center of mass in the link frame;
3. inertia tensor values are in SI units;
4. tensor values correspond to the inertial frame being declared;
5. approximations are documented.

Do not infer inertial origin from visual or collision origin unless the source data proves they coincide.
