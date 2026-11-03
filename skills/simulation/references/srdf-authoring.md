# SRDF Authoring Contract

Use this reference when writing or editing SRDF XML directly. The `.srdf` file is the source of truth and must be auditable on its own: planning intent and provenance live in the file, and the paired URDF is found by convention.

## Extract the URDF Table

Do this before writing any SRDF XML. Parse the paired URDF (read it, or run a three-line ElementTree script for large robots) and write down:

- robot `name` (the SRDF must match it exactly);
- every link name;
- every joint: name, type, parent link, child link, lower/upper limits, and whether it has `<mimic>`;
- the root link and the main serial chains (walk parent→child).

Every name that appears in the SRDF is **copied from this table**. If a name you want is not in the table, the URDF is wrong or your assumption is — resolve that first, in the URDF. This single habit eliminates the most common SRDF failure class: plausible near-miss names and chains that do not exist in the tree.

## Edit Loop

1. Confirm the URDF is valid (`cad urdf check`) and extract the URDF table.
2. Read or create the planning ledger ([srdf-ledger.md](srdf-ledger.md)); keep the compact form as a comment block in the `.srdf`.
3. Author or edit the SRDF XML directly per this contract, in element order: virtual joints, groups, group states, end effectors, passive joints, disabled collisions. Save it next to the URDF with the same robot name — colocation plus name match is how every consumer pairs the files.
4. Derive — do not invent — disabled collisions ([srdf-disabled-collisions.md](srdf-disabled-collisions.md)) and group-state values (URDF-native units, within limits).
5. Validate with `cad srdf check <file.srdf>`; fix findings until clean ([srdf-checks.md](srdf-checks.md)).
6. Show the result for review ([Show the model](../SKILL.md#show-the-model)).
7. Run MoveIt smoke tests when a MoveIt environment is available; otherwise report them skipped.
8. Report assumptions: inferred TCP links, manual collision pairs, unverified planner behavior.

## File Shape

Every authored `.srdf` follows this shape, in this order:

1. XML declaration: `<?xml version="1.0"?>`.
2. Planning-ledger comment block (compact form of [srdf-ledger.md](srdf-ledger.md)).
3. One `<robot>` root with the **same `name` as the paired URDF**: `<robot name="...">`.
4. `<virtual_joint>` elements, then `<group>`, `<group_state>`, `<end_effector>`, `<passive_joint>`, `<disable_collisions>` — grouped by element type, in that order.

Keep two-space indentation. Comment nontrivial decisions inline (why a chain tip, why a pair is disabled).

## URDF Pairing (non-negotiable)

An SRDF pairs with its URDF by **colocation and robot name** — nothing else:

- Save the `.srdf` in the **same folder** as the `.urdf` it describes.
- Both files declare the identical `<robot name="...">`.
- Exactly one `.urdf` in that folder may declare that robot name; the validator and the CAD Viewer resolve the pairing by scanning the folder, and they error when zero or several URDFs match.
- Matching basenames (`so101.srdf` next to `so101.urdf`) are conventional and recommended for readability, but the robot name is what pairs the files. Multiple SRDF planning variants for one robot (`so101_dual.srdf`, `so101_precise.srdf`) all pair with the same URDF through its name.
- There is no link element: an SRDF pairs with the same-folder URDF whose robot name matches.

## Names Come From the URDF Table

Every `link`, `joint`, `base_link`, `tip_link`, `parent_link`, and group-state joint name must be copied from the extracted URDF table ([below](#extract-the-urdf-table)). Never type a name from memory or from a similar robot; near-miss names (`wrist_roll` vs `wrist_roll_joint`) are the most common SRDF defect and validation will reject them.

## Element Contract

- `<group>`: prefer exactly one `<chain base_link tip_link>` for a serial manipulator — base to tip must be a real parent→child path in the URDF tree. Use explicit `<joint>`/`<link>` members for non-chain groups (grippers, heads), and `<group>` subgroups for unions (dual-arm, whole-body). Do not mix representations in one group without reason.
- `<group_state name group>`: one `<joint name value>` per **movable, non-mimic** joint in the group. Radians for revolute/continuous, meters for prismatic, values within URDF limits.
- `<end_effector name parent_link group parent_group>`: the EE group must not share links with `parent_group`; `parent_link` belongs to the parent group (or is adjacent to the EE group) and is typically the attachment/flange link ([srdf-end-effectors.md](srdf-end-effectors.md)).
- `<virtual_joint name type parent_frame child_link>`: attaches the robot root to an external frame (`world`). `fixed` for fixed-base arms; `planar`/`floating` only when planning genuinely needs that freedom.
- `<passive_joint name>`: unactuated joints that planners must not command.
- `<disable_collisions link1 link2 reason>`: evidence-backed only; see [srdf-disabled-collisions.md](srdf-disabled-collisions.md). No duplicate or reversed-duplicate pairs.

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

## Helper Scripts

Adjacent-pair lists, subgroup unions for many-jointed robots, and degree-to-radian tables are computations: derive them with a short throwaway script over the URDF rather than by hand when the robot has more than a handful of joints. The script is scaffolding; the checked-in `.srdf` remains canonical.

## Group Design

- **Serial manipulator** → one chain group, `base_link` at the mount, `tip_link` at the flange/TCP link. The validator rejects chains that are not a real parent→child path.
- **Gripper / hand** → joint-member group listing its actuated joints; it becomes the end-effector group.
- **Dual-arm / whole-body** → subgroup unions. Check for duplicate semantics (a joint reachable through two subgroups) and cycles.
- **Mobile base** → typically a planar/floating virtual joint plus a group for the base; do not model wheel joints as planning DOF unless the planner consumes them.

Fixed and mimic joints are never planning variables: they do not belong in group states, and chain-derived groups exclude them automatically.

When the URDF changes, the SRDF is checked again: see [interoperability.md](interoperability.md#when-the-urdf-changes).
