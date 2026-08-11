# SRDF Authoring Contract

Use this reference when writing or editing SRDF XML directly. The `.srdf` file is the source of truth and must be auditable on its own: planning intent and provenance live in the file, and the paired URDF is found by convention.

## File Shape

Every authored `.srdf` follows this shape, in this order:

1. XML declaration: `<?xml version="1.0"?>`.
2. Planning-ledger comment block (compact form of `references/planning-ledger.md`).
3. One `<robot>` root with the **same `name` as the paired URDF**: `<robot name="...">`.
4. `<virtual_joint>` elements, then `<group>`, `<group_state>`, `<end_effector>`, `<passive_joint>`, `<disable_collisions>` — grouped by element type, in that order.

Keep two-space indentation. Comment nontrivial decisions inline (why a chain tip, why a pair is disabled).

## URDF Pairing (non-negotiable)

An SRDF pairs with its URDF by **colocation and robot name** — nothing else:

- Save the `.srdf` in the **same folder** as the `.urdf` it describes.
- Both files declare the identical `<robot name="...">`.
- Exactly one `.urdf` in that folder may declare that robot name; the validator, the CAD Viewer, and the local MoveIt2 server all resolve the pairing by scanning the folder, and they error when zero or several URDFs match.
- Matching basenames (`so101.srdf` next to `so101.urdf`) are conventional and recommended for readability, but the robot name is what pairs the files. Multiple SRDF planning variants for one robot (`so101_dual.srdf`, `so101_precise.srdf`) all pair with the same URDF through its name.
- There is no link element. Older files carried `<tcad:urdf path="..."/>` (or legacy `<explorer:urdf/>`) metadata; that element is retired, ignored by all consumers, and flagged by the validator as `deprecated_urdf_link` — remove it when you touch such a file.

## Names Come From the URDF Table

Every `link`, `joint`, `base_link`, `tip_link`, `parent_link`, and group-state joint name must be copied from the extracted URDF table (see `references/srdf-workflow.md`). Never type a name from memory or from a similar robot; near-miss names (`wrist_roll` vs `wrist_roll_joint`) are the most common SRDF defect and validation will reject them.

## Element Contract

- `<group>`: prefer exactly one `<chain base_link tip_link>` for a serial manipulator — base to tip must be a real parent→child path in the URDF tree. Use explicit `<joint>`/`<link>` members for non-chain groups (grippers, heads), and `<group>` subgroups for unions (dual-arm, whole-body). Do not mix representations in one group without reason.
- `<group_state name group>`: one `<joint name value>` per **movable, non-mimic** joint in the group. Radians for revolute/continuous, meters for prismatic, values within URDF limits.
- `<end_effector name parent_link group parent_group>`: the EE group must not share links with `parent_group`; `parent_link` belongs to the parent group (or is adjacent to the EE group) and is typically the attachment/flange link.
- `<virtual_joint name type parent_frame child_link>`: attaches the robot root to an external frame (`world`). `fixed` for fixed-base arms; `planar`/`floating` only when planning genuinely needs that freedom.
- `<passive_joint name>`: unactuated joints that planners must not command.
- `<disable_collisions link1 link2 reason>`: evidence-backed only; see `references/disabled-collisions.md`. No duplicate or reversed-duplicate pairs.

## Golden Skeleton

```xml
<?xml version="1.0"?>
<!--
  srdf: example_arm | urdf: example_arm.urdf | task: arm IK + gripper control
  groups: arm (chain base_link->tool0), gripper (joint members)
  states: home, ready (radians, within URDF limits)
  disabled collisions: URDF-adjacent pairs only (reason Adjacent)
  assumptions: tool0 is the TCP; no sampled collision matrix yet
-->
<robot name="example_arm">
  <virtual_joint name="world_to_base" type="fixed" parent_frame="world" child_link="base_footprint" />
  <group name="arm">
    <chain base_link="base_link" tip_link="tool0" />
  </group>
  <group name="gripper">
    <joint name="finger_joint" />
  </group>
  <group_state name="home" group="arm">
    <joint name="shoulder_pitch" value="0" />
    <joint name="elbow_pitch" value="0" />
    <joint name="wrist_roll" value="0" />
  </group_state>
  <end_effector name="gripper_eef" parent_link="tool0" group="gripper" parent_group="arm" />
  <disable_collisions link1="base_link" link2="shoulder_link" reason="Adjacent" />
</robot>
```

Repository fixtures under `models/robots/` (for example `so101.srdf`, `juno.srdf`) are full worked examples.

## Helper Scripts

Adjacent-pair lists, subgroup unions for many-jointed robots, and degree-to-radian tables are computations: derive them with a short throwaway script over the URDF rather than by hand when the robot has more than a handful of joints. The script is scaffolding; the checked-in `.srdf` remains canonical.
