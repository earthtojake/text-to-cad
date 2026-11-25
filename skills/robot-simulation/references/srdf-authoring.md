# SRDF authoring

Read this before writing or editing a `.srdf`. An SRDF is always written by hand, over a URDF that
already validates (`cad urdf validate`): it refers to that URDF's links, joints and limits and can
repair none of them. Its checks are in [srdf-checks.md](srdf-checks.md).

## URDF pairing

An SRDF plans for the one `.urdf` in its own folder whose `<robot name>` is its own.

- Nothing inside the SRDF names the URDF, and file names do not pair them: `arm_dual.srdf` and
  `arm_precise.srdf` both plan for the `.urdf` beside them whose robot is `arm`.
- No such URDF, or more than one, is an error from `cad srdf validate` (`no_paired_urdf`,
  `ambiguous_paired_urdf`) and a refusal from the viewer and `cad srdf snapshot`.
- `cad srdf validate robot.srdf --urdf elsewhere/robot.urdf` checks against the URDF it is given,
  in any folder and under any robot name. That result says nothing of the pairing, which the viewer
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
  radians or metres, within the URDF's limits. Call the rest pose `home`: the viewer and
  `cad srdf snapshot` open there.
- **`<end_effector name parent_link group parent_group>`**: [End effectors](#end-effectors).
- **`<virtual_joint name type parent_frame child_link>`** ties the root link to a frame outside the
  robot (`world`, `odom`): `fixed` for a bolted arm, `planar` or `floating` only for a base that
  moves. A wheel's joint is in no group unless the planner drives it. A mobile base's group lists
  its virtual joint, as MoveIt expects, and `cad srdf validate` then reports that name as missing: a
  limit of the check, not a fault of the file ([srdf-checks.md](srdf-checks.md#the-validator)).
- **`<passive_joint name>`**: a URDF joint that nothing drives, which no group state may set.
- **`<disable_collisions link1 link2 reason>`**: [Disabled collisions](#disabled-collisions).

## End effectors

```xml
<end_effector name="gripper_eef" parent_link="tool0" group="gripper" parent_group="arm" />
```

`cad srdf validate` holds each one to this:

- `group` is a group of this SRDF, as is `parent_group` where one is given, and `parent_link` is a
  link of the URDF.
- The two groups share no link. A group's links are the ones it lists and the child link of each of
  its joints, so a chain holds its tip and not its base.
- `parent_link` is a link of `parent_group`, where one is given, and is in the end-effector group or
  joined to one of its links by a joint.

An `<end_effector>` says where the tool attaches, not where it acts, and no check knows the tool
point. Record the TCP link in [the ledger](#the-ledger), and name it when
handing the SRDF on wherever it is not the tip a consumer would take from the group.

## Disabled collisions

A planner never checks a disabled pair, so a wrong one hides a real collision: each pair comes from
evidence, never from how the robot looks.

```xml
<disable_collisions link1="base_link" link2="shoulder_link" reason="Adjacent" />
```

### Where a pair comes from

- **Adjacency**: two links one URDF joint joins, listed from the URDF's joints (a few lines of
  script on a large robot).
- **Sampling**: MoveIt Setup Assistant's self-collision matrix, or collision sampling in a known
  MoveIt configuration, dense enough to cover the poses the task reaches.
- **A matrix the person gives.**
- **A pair reviewed by hand**, with what was reviewed written in its reason.

A matrix goes stale when geometry, limits or group membership change: derive it again.

### What the validator reads in a reason

`cad srdf validate` requires a `reason` on every pair, and refuses a pair of one link with itself
and a pair given twice, in either order. Then it reads the reason's words:

- One that contains `adjacent` is held to the URDF: a warning where no joint joins the two links.
- One that contains none of `adjacent`, `never`, `always`, `default`, `sample`, `setup`, `assistant`
  or `assum` counts as reasoned by hand (`User`, `Manual: fixture is outside the workspace`). 25 or
  more of those warn: regenerate the matrix by sampling instead.

So write the reason that is true: Setup Assistant's own word where it made the pair (`Adjacent`,
`Never`, `Always`, `Default`), and `assumed` only where the person asked for a provisional SRDF and
the report says so.

## The ledger

The ledger is a comment block that opens the file, as a URDF's does
([urdf-authoring.md](urdf-authoring.md#the-ledger)), for what the SRDF's XML cannot say: what the
semantics are for, and where each choice came from.

```xml
<?xml version="1.0"?>
<!--
  srdf: example_arm | urdf: example_arm.urdf | task: arm IK and gripper control
  groups: arm (chain base_link -> tool0, the IK group), gripper (finger_joint)
  tcp: tool0, on the flange face
  states: arm/home, the rest pose (radians, within the URDF's limits)
  disabled collisions: URDF-adjacent pairs only (reason Adjacent)
  assumptions: tool0 is the TCP; no sampled collision matrix yet
-->
```

What each line answers for:

- **task**: what is planned (arm IK, a plan to a pose, a gripper, a mobile base, two arms), the
  primary group, the solver or planner expected, and whether IK constrains orientation or position
  alone.
- **groups**: what each is for, and why its base and tip or its members. Also why each virtual and
  passive joint is there.
- **tcp**: the link a pose target means ([End effectors](#end-effectors)).
- **states**: what each named pose is for.
- **disabled collisions**: where the pairs came from ([Disabled collisions](#disabled-collisions)).
- **assumptions**: one line for every choice that was inferred: a group's member, a chain's end, the
  TCP, a virtual joint's frame, a joint taken as passive, a state's values, a pair disabled by hand,
  a solver setting, a MoveIt check that was not run.
