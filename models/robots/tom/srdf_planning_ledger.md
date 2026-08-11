# TOM v2 SRDF planning ledger

## URDF dependency

| Field | tom | tom_double | tom_with_gripper |
|---|---|---|---|
| URDF path | `tom.urdf` | `tom_double.urdf` | `tom_with_gripper.urdf` |
| SRDF output path | `tom.srdf` | `tom_double.srdf` | `tom_with_gripper.srdf` |
| Robot name | `tom_v2` | `tom_v2_double` | `tom_v2_with_gripper` |
| Root link | `base_footprint` | `base_footprint` | `base_footprint` |
| Active arm joints | `base_yaw`, `shoulder_pitch`, `shoulder_roll`, `elbow_pitch`, `elbow_roll`, `wrist_pitch`, `wrist_roll`; v2 rebases the named home pose at `elbow_pitch=-90 deg` | same, with double STS3250 effort on `shoulder_pitch` in URDF | same |
| Fixed joints | `base_footprint_to_base_link` | `base_footprint_to_base_link` | `base_footprint_to_base_link`, `wrist_roll_to_gripper_base` |
| Mimic joints | none | none | `gripper_right_claw_slide`, `gripper_left_claw_slide` mimic `gripper_servo` |
| Passive joints | none | none | none |
| Known URDF limitations | Arm collision geometry is intentionally omitted pending simplified collision models. | same | Gripper collision meshes are present; arm collision geometry is intentionally omitted. |

## Planning task

| Field | Value |
|---|---|
| Main task | Fixed-base arm plan-to-pose / named-state review, plus gripper states for `tom_with_gripper`. |
| Primary planning group | `arm` |
| Expected end-effector or TCP | `wrist_roll_link` for no-gripper variants; `gripper_base_link` via `gripper_tcp` for `tom_with_gripper`. |
| Required solver or planner | Not specified; MoveIt setup remains downstream. |
| Position-only IK | Not specified. |
| Orientation constraints | Not specified. |

## Virtual joints

| Name | Type | Parent frame | Child link | Required? | Rationale |
|---|---|---|---|---|---|
| `fixed_base` | fixed | `world` | `base_footprint` | yes | Matches v1 fixed-base semantics and gives MoveIt an explicit world attachment. |

## Planning groups

| Group | Representation | Members | Base link | Tip link | Purpose |
|---|---|---|---|---|---|
| `arm` | chain | `base_link` to `wrist_roll_link` | `base_link` | `wrist_roll_link` | Main serial manipulator group. |
| `tcp` | link | `gripper_base_link` | n/a | n/a | TCP/end-effector target group for `tom_with_gripper` only. |
| `gripper` | joint | `gripper_servo` | n/a | n/a | Active gripper actuator for `tom_with_gripper` only. |
| `arm_with_gripper` | subgroups | `arm`, `gripper` | n/a | n/a | Convenience group for `tom_with_gripper` only. |

## End effectors

| Name | End-effector group | Parent group | Parent link | Target/TCP link | Notes |
|---|---|---|---|---|---|
| `gripper_tcp` | `tcp` | `arm` | `wrist_roll_link` | `gripper_base_link` | Used only by `tom_with_gripper`; `wrist_roll_to_gripper_base` is the adjacent fixed attachment. |

## Group states

| State | Group | Unit check | Limit check | Purpose |
|---|---|---|---|---|
| `home` | `arm` | revolute/continuous values generated in radians; `elbow_pitch=-90 deg` | within URDF limits | V2 calibrated home pose. |
| `reach_forward` | `arm` | radians; explicit v2 review pose uses `base_yaw=0 deg`, `shoulder_pitch=90 deg`, `shoulder_roll=0 deg`, `elbow_pitch=0 deg`, `elbow_roll=0 deg`, `wrist_pitch=0 deg`, `wrist_roll=0 deg` | within URDF limits | Forward reach review pose selected from viewer review. |
| `inspection` | `arm` | radians; explicit v2 review pose uses `base_yaw=45 deg`, `shoulder_pitch=-27 deg`, `shoulder_roll=66 deg`, `elbow_pitch=-87 deg`, `elbow_roll=121.995 deg`, `wrist_pitch=83 deg`, `wrist_roll=-99 deg` | within URDF limits | Angled inspection pose selected from viewer review. |
| `inspection_mirrored` | `arm` | radians; mirrors the inspection roll joints to `shoulder_roll=-66 deg`, `elbow_roll=-121.995 deg`, `wrist_roll=99 deg` while keeping the other inspection values | within URDF limits | Mirrored inspection pose using the same roll-sign convention as v1. |
| `open` | `gripper` | radians | within URDF limits | Gripper open state for `tom_with_gripper`. |
| `half_closed` | `gripper` | radians | within URDF limits | Gripper mid travel state for `tom_with_gripper`. |
| `closed` | `gripper` | radians | within URDF limits | Gripper closed state for `tom_with_gripper`. |

## Disabled collisions

Disabled collisions are generated from the paired URDF kinematic adjacency list only, excluding the world/base-footprint fixed joint. No sampled self-collision matrix is available yet.

## MoveIt smoke tests

MoveIt Setup Assistant and runtime IK/path planning were not run in this change. The authored SRDFs are validated by the SRDF skill validator against their paired URDFs and handed to CAD Viewer for review links.

## Assumptions to report

- The v2 arm planning group intentionally mirrors the v1 `arm` chain from `base_link` to `wrist_roll_link`.
- `home` keeps the v2-only `elbow_pitch=-90 deg` home offset.
- `reach_forward` is an explicit v2 viewer-selected pose with `elbow_roll=0 deg`.
- `inspection` is an explicit v2 viewer-selected pose, and `inspection_mirrored` flips the roll-joint signs from that pose.
- Collision disables are adjacency-only; no broad manual or sampled-safe collision matrix was added.
- `tom_with_gripper` uses `gripper_base_link` as the TCP target link, matching v1 semantics.
