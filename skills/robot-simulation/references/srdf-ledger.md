# SRDF planning ledger

Create or update this ledger before writing SRDF XML. The ledger makes planning assumptions explicit and helps prevent plausible but incorrect MoveIt configurations.

## URDF dependency

| Field | Value |
|---|---|
| URDF path | |
| SRDF output path | |
| Robot name | |
| URDF validated? | yes/no; tool/check |
| Root link | |
| Active joints | |
| Fixed joints | |
| Mimic joints | |
| Passive joints | |
| Links used for collision checking | |
| Known URDF limitations | |

## Planning task

| Field | Value |
|---|---|
| Main task | IK / plan-to-pose / gripper / mobile base / dual arm / other |
| Primary planning group | |
| Expected end-effector or TCP | |
| Required solver or planner | |
| Position-only IK? | yes/no; reason |
| Orientation constraints? | yes/no; representation |

## Virtual joints

| Name | Type | Parent frame | Child link | Required? | Rationale |
|---|---|---|---|---|---|
| | fixed / planar / floating | | | | |

Virtual joints describe the robot root pose relative to an external frame. Use fixed for fixed-base manipulators when the planning setup needs a world attachment; use planar/floating only when the robot model requires that planning freedom.

## Passive joints

| Joint | URDF type | Reason passive | Affected groups | Notes |
|---|---|---|---|---|
| | | | | |

Passive joints are unactuated. They should not be treated as controllable planning variables.

## Planning groups

| Group | Representation | Members | Base link | Tip link | Active joints | Excluded joints | Purpose | Solver expectation |
|---|---|---|---|---|---|---|---|---|
| | joints / links / chain / subgroups | | | | | | | |

For serial arms, prefer a chain only when the URDF graph has a real path from base link to tip link. For subgroup groups, check for cycles and duplicate semantics.

## End effectors

| Name | End-effector group | Parent group | Parent link | Target/TCP link | Overlap checked? | Adjacent? | Notes |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

The end-effector group should normally not share links with its parent group. The target/TCP link should be explicit when it differs from the inferred group tip.

## Group states

| State | Group | Joint values | Unit check | Limit check | Purpose |
|---|---|---|---|---|---|
| | | revolute/continuous rad; prismatic m | | | |

Do not store degrees in SRDF group states. Do not set fixed or mimic joints in group states.

## Disabled collisions

| Link 1 | Link 2 | Reason | Source | Evidence | Risk note |
|---|---|---|---|---|---|
| | | Adjacent / Never / Always / Default / Manual | Setup Assistant / sampled / adjacency / user | | |

Do not infer disabled collisions from visual impression. Each pair needs a reason and provenance.

## MoveIt smoke tests

| Test | Group | Target link | Target pose/state | Expected result | Actual result | Notes |
|---|---|---|---|---|---|---|
| IK solve | | | | | | |
| Plan-to-pose | | | | | | |
| Named state | | | | | | |
| Collision check | | | | | | |

## Assumptions to report

List every guessed or inferred value:

- planning group membership;
- chain base/tip;
- target/TCP link;
- virtual joint attachment;
- passive joint classification;
- group-state value;
- disabled collision pair;
- solver or planner setting;
- orientation/position-only IK assumption;
- skipped MoveIt validation.
