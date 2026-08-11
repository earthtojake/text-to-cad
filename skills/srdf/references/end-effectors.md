# SRDF end effectors

Use this reference when creating or editing `<end_effector>` entries or preparing MoveIt2 pose-target handoffs for `$cad-viewer`.

## Concept

An end effector is a semantic designation for a tool, gripper, sensor head, or other terminal group. It is typically connected to a parent planning group through a fixed joint or attachment link.

Typical shape:

```xml
<group name="gripper">
  <joint name="finger_joint"/>
</group>

<end_effector
  name="gripper_eef"
  parent_link="tool0"
  group="gripper"
  parent_group="manipulator"/>
```

## Required ledger fields

Record:

- end-effector name;
- end-effector group;
- parent planning group;
- parent link where the end effector attaches;
- target/TCP link used for IK and planning;
- whether the end-effector group overlaps the parent group;
- whether the parent link is adjacent to the end-effector group in the URDF graph.

## Checks

Before authoring:

- The end-effector group exists.
- The parent group exists when specified.
- The parent link exists in the URDF.
- The end-effector group and parent group do not share links.
- The parent link is in the parent group or adjacent to the end-effector group.
- The target/TCP link is explicit when it differs from the inferred group tip.

The current runtime enforces several of these checks, but target/TCP choice remains a semantic decision. Do not rely on inference when planning to a tool center point.

## CAD Viewer MoveIt2 target link

When handing an SRDF to `$cad-viewer` for optional MoveIt2 controls, make the intended target link explicit when possible:

```json
{
  "protocolVersion": 1,
  "type": "srdf.solvePose",
  "payload": {
    "file": "robot.srdf",
    "target": {
      "endEffector": "gripper_eef",
      "targetLink": "tool0",
      "frame": "base_link",
      "xyz": [0.4, 0.0, 0.2],
      "quat_xyzw": [0, 0, 0, 1]
    },
    "moveit2": {
      "planningGroup": "manipulator",
      "targetLink": "tool0"
    }
  }
}
```

Use position-only IK only when orientation is intentionally unconstrained. CAD Viewer owns the local MoveIt2 server startup and protocol details.
