# SRDF end effectors

Use this reference when creating or editing `<end_effector>` entries.

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

## Handoff

When handing an SRDF to another tool or reviewer, state the intended target/TCP link explicitly whenever it differs from the inferred group tip — target choice is a semantic decision no consumer can infer.
