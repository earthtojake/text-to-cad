# SRDF authoring

Read this before writing or editing a `.srdf`. An SRDF is always written by hand, over a URDF that
already validates (`cad urdf validate`): it refers to that URDF's links, joints and limits and can
repair none of them. Its ledger is in [srdf-ledger.md](srdf-ledger.md), its checks in
[srdf-checks.md](srdf-checks.md).

## URDF pairing (non-negotiable)

An SRDF plans for the one `.urdf` in its own folder whose `<robot name>` is its own.

- Nothing inside the SRDF names the URDF, and file names do not pair them: `arm_dual.srdf` and
  `arm_precise.srdf` both plan for the `.urdf` beside them whose robot is `arm`.
- No such URDF, or more than one, is an error from `cad srdf validate` (`no_paired_urdf`,
  `ambiguous_paired_urdf`) and a refusal from the CAD Viewer and `cad srdf snapshot`.
- `cad srdf validate robot.srdf --urdf elsewhere/robot.urdf` checks against the URDF it is given,
  in any folder and under any robot name. That result says nothing of the pairing, which the Viewer
  and the snapshot still make by folder and name.

## The URDF's table

Before any SRDF XML, read out of the URDF (a few lines of `xml.etree.ElementTree` on a large robot)
its robot name, every link, every joint with its type, parent, child, limits and whether it carries
a `<mimic>`, the root, and the chains from it. Every name in the SRDF is copied from that table: the
near miss (`wrist_roll` for `wrist_roll_joint`) is the usual SRDF defect. A name the table lacks
means the URDF or the plan is wrong, and the URDF is settled first.

## Elements

- **`<group name>`**: a serial arm is one `<chain base_link tip_link>`, from its mount to its flange
  or tool link. The two must be a parent-to-child path in the URDF, in that order. A gripper or a
  head lists its `<joint>`s (or `<link>`s, each of which brings the joint above it), and two arms or
  a whole body list `<group>` subgroups, where a joint reached through two of them goes unreported.
  A group plans with its moving joints that carry no `<mimic>`: fixed and mimic joints are never
  planning variables.
- **`<group_state name group>`**: a `<joint name value>` for each of the group's planning joints, in
  radians or metres, within the URDF's limits. Call the rest pose `home`: the Viewer and
  `cad srdf snapshot` open there.
- **`<end_effector name parent_link group parent_group>`**:
  [srdf-end-effectors.md](srdf-end-effectors.md).
- **`<virtual_joint name type parent_frame child_link>`** ties the root link to a frame outside the
  robot (`world`, `odom`): `fixed` for a bolted arm, `planar` or `floating` only for a base that
  moves. A wheel's joint is in no group unless the planner drives it. A group that names a virtual
  joint fails the check ([srdf-checks.md](srdf-checks.md#the-validator)).
- **`<passive_joint name>`**: a URDF joint that nothing drives, which no group state may set.
- **`<disable_collisions link1 link2 reason>`**:
  [srdf-disabled-collisions.md](srdf-disabled-collisions.md).
