---
name: robot-simulation
description: Robot and world descriptions (URDF, SRDF, SDF, MJCF) for ROS, MoveIt, Gazebo and MuJoCo. Use for ROS robot_description files (links, joints, limits, inertials, meshes), MoveIt planning groups, end effectors, group states and disabled collision pairs, Gazebo/gz models and worlds (sensors, plugins, physics), MuJoCo models (bodies, joints, geoms, default classes, actuators, keyframes), and opening or reviewing a `.urdf`, `.srdf`, `.sdf`, or an MJCF `.xml` or `.mjcf`. Not the 3D CAD part itself, which the `cad` skill makes, nor a part's structural or physics analysis or a simulation run, nor signed-distance fields.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# Robots and worlds for simulation and motion planning

A robot is described for its consumers in XML written by hand: a URDF for its structure (ROS,
RViz, robot_state_publisher), an SRDF beside it for MoveIt's planning semantics, an SDF for
Gazebo and other simulators, and an MJCF for MuJoCo. Each `.urdf`, `.srdf`, `.sdf` and MJCF `.xml` is
the source of truth: author and edit the XML directly; do not build a Python generation pipeline for it. The work is constrained
kinematic modeling, not XML writing: the risks are frame placement, joint-axis semantics, units,
mesh scale, inertial data and planning semantics, and a file can pass every check while placing a
joint in the wrong spot.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Describe a robot's links and joints** (ROS, RViz, TF, MoveIt's model) | The `.urdf` and its ledger, then `cad urdf validate`. | [Authoring](references/urdf-authoring.md), [frames](references/urdf-frames.md), [ledger](references/urdf-ledger.md) |
| **Add MoveIt planning groups, end effectors, named states, collision pairs** | The URDF's link/joint table, then a `.srdf` beside it and `cad srdf validate`. | [Authoring](references/srdf-authoring.md), [end effectors](references/srdf-end-effectors.md), [collisions](references/srdf-disabled-collisions.md), [ledger](references/srdf-ledger.md) |
| **Model or world for Gazebo / gz** | The `.sdf` and its ledger, then `cad sdf validate`. | [Authoring](references/sdf-authoring.md), [frames](references/sdf-frames.md), [examples](references/sdf-examples.md), [ledger](references/sdf-ledger.md) |
| **Model for MuJoCo** | The MJCF (`robot.xml`, and a `scene.xml` that includes it), then `cad mjcf validate --compile required`. | [Authoring](references/mjcf-authoring.md), [checks](references/mjcf-checks.md) |
| **SDF for a robot that has a URDF** | Derive it from the URDF; never re-author it. | [Interoperability](references/interoperability.md#sdf-from-a-urdf) |
| **Link meshes from a CAD model** | One mesh per link in the link's frame: `cad model export <id> link.stl`. | [Meshes](references/meshes.md) |
| **Mass, center of mass, inertia** | A formula or a throwaway script, never intuition. | [Inertials](references/inertials.md) |
| **Close a nonlinear four-bar in the CAD Viewer** | `<tcad:four_bar>` on the derived URDF joint. | [Four-bar](references/urdf-four-bar.md) |
| **See the robot, a pose or a named state** | `cad urdf snapshot`, `cad srdf snapshot`, `cad sdf snapshot` or `cad mjcf snapshot`. | [Snapshots](references/snapshots.md) |
| **Check a change** | The format's `validate` command, then its review. | [Check each change](#check-each-change) |
| **Open an existing URDF, SRDF, SDF or MJCF** | Show it to the person. | [Show the model](#show-the-model) |

## Setup

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor
--check` explains any other failure, changing nothing; `cad doctor` repairs what it reports.

`cad doctor --check` also reports the installation in use and the server's release. Validation needs
nothing beyond the Python standard library; a snapshot draws with the CAD kernel. `cad mjcf validate
--compile required` compiles the model with MuJoCo's headless core, `cad[mujoco]` (about 10 MB), which
the `cad` command fetches into an environment of its own the first time and reuses after. `cad <verb>
--help` gives the complete current interface.

## How the formats fit together

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic
  joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics on top of a valid URDF: virtual joints, passive joints, planning
  groups, group states, end effectors, and disabled collision pairs. It pairs with its URDF by
  colocation and robot name alone: same folder, same `<robot name>`, exactly one such URDF.
- **SDF** owns simulator and world semantics: physics, sensors, lights, plugins, worlds, and
  simulation-specific metadata. A robot that already has a URDF gets its SDF derived from it.
- **MJCF** owns a MuJoCo model: bodies, joints, geoms, default classes, actuators, equalities and
  keyframes, in one file or a `scene.xml` that includes the robot's.
- **Meshes** are owned by the CAD workflow: one asset per link, exported in that link's frame, its
  source units recorded. Fix a wrong export there, never with URDF origins or SDF poses.

Names are identifiers every consumer shares: SRDF groups, controllers and TF read the URDF's link
and joint names, so a rename updates every consumer in the same task, and any URDF edit re-runs
`cad srdf validate` on the SRDF beside it ([Interoperability](references/interoperability.md)).

## Rules for every format

1. Identify the target consumers first: RViz, robot_state_publisher, Gazebo/Ignition, MoveIt, a
   real robot driver, or another simulator, and how strict they are.
2. Before writing XML, establish the ledger (frames, joints, geometry, units, assumptions) and keep
   it as a comment block at the top of the file. Update it in the same edit that changes the
   modeled facts; a stale ledger is worse than none.
3. SI units: meters, kilograms, seconds, radians, unless the target explicitly requires otherwise.
   URDF limits and SRDF group states never hold degrees; an SDF pose avoids `degrees="true"`; an
   MJCF says `<compiler angle="radian"/>`, since MuJoCo's default is degrees.
4. Do not infer spatial transforms, mesh units, handedness, axes, joint signs or planning
   semantics from vague prose or visual impression. Use CAD transforms, dimensioned drawings,
   measured values, existing source data, simulator documentation, or explicit documented
   assumptions ([Guardrails](references/guardrails.md)).
5. Never freehand computed numbers (inertia tensors, centers of mass, unit conversions across many
   links, mirrored transforms, adjacency lists): compute them with closed-form formulas or a
   throwaway helper script. A helper is scaffolding; for complex or parametric models it may be
   kept on disk beside related model source and named in the ledger, and the checked-in XML stays
   canonical: regenerating is an explicit editing action, never an implicit build step.
6. Never encode a kinematic fix by offsetting only a visual mesh; correct the link and joint
   frames, unless the mesh is genuinely offset from its link frame.
7. Regenerate upstream geometry, mesh and robot-description assets with their owning workflows
   before editing a description that references them.
8. Check every created or modified file ([below](#check-each-change)) and report the checks run,
   the checks skipped, the assumptions and the risks
   ([report shape](references/guardrails.md#the-report)).

## URDF

The robot's tree of links and joints. Most URDF errors are frame errors: a joint's `<origin>` is
the parent-link-frame transform to the joint frame at zero position, the child link frame
coincides with the joint frame, `<axis>` is expressed in the joint frame, and the `visual`,
`collision` and `inertial` origins are each expressed in the link frame, independently
([Frames](references/urdf-frames.md)).

1. Identify the `.urdf` and its consumers; read or create the ledger
   ([URDF ledger](references/urdf-ledger.md)).
2. Prepare mesh assets first when links reference meshes ([Meshes](references/meshes.md)).
3. Author the XML per the [authoring contract](references/urdf-authoring.md): links in tree order,
   then joints; physical links carry `inertial`, `visual`, `collision` as the consumer needs them;
   frame-only links (`base_footprint`, `tool0`, optical frames) are empty and listed as frame-only
   in the ledger.
4. Joint types `fixed`, `revolute`, `continuous`, `prismatic` (the validator rejects `floating`
   and `planar`). Revolute limits in radians, prismatic in meters, no lower/upper on
   `continuous`. Every movable joint has a stated positive-motion convention; the axis sign is part
   of the model.
5. Compute the inertials ([Inertials](references/inertials.md)).
6. Check it ([URDF checks](references/urdf-checks.md)): `cad urdf validate`, `check_urdf` when
   installed, then the viewer sweep of every movable joint.

## SRDF

MoveIt planning semantics for an existing valid URDF. The common failure is not invalid XML but a
plausible SRDF with the wrong planning group, tool link, default state, disabled-collision matrix
or joint units. Derive groups, end effectors, states and disabled collisions from the URDF
topology, MoveIt Setup Assistant output, sampled collision analysis, or explicit user data; never
type a link or joint name from memory.

1. **Start from a valid URDF** (`cad urdf validate`), and **extract its table**: robot name, links,
   joints with type, parent, child, limits and mimic flags. Copy every name from it
   ([SRDF authoring](references/srdf-authoring.md#extract-the-urdf-table)).
2. **Identify the planning task**: arm IK, gripper control, mobile base, dual-arm, tool use, or
   local smoke testing. Create or update the [planning ledger](references/srdf-ledger.md) and keep
   a compact copy as a comment block in the `.srdf`.
3. **Pair by colocation**: the `.srdf` in the URDF's folder with the same `<robot name>`. No
   metadata element links the files.
4. **Virtual and passive joints** deliberately, only when the robot model needs them.
5. **Planning groups from URDF topology**: a chain for a serial manipulator whose base and tip form
   a real parent-to-child path (the validator verifies it); joint, link or subgroup members only
   when deliberate.
6. **End effectors** after group membership is known: no links shared with the parent group, and
   the actual target/TCP link recorded ([End effectors](references/srdf-end-effectors.md)).
7. **Group states in URDF-native units**: radians for revolute and continuous, meters for
   prismatic, within URDF limits, never setting fixed, mimic or passive joints.
8. **Disabled collisions from evidence**: URDF adjacency, Setup Assistant sampling, or a
   user-provided matrix, each pair with a truthful reason and provenance; no broad invented lists
   ([Disabled collisions](references/srdf-disabled-collisions.md)).
9. Check it ([SRDF checks](references/srdf-checks.md)), and report incomplete validation, a missing
   MoveIt environment, manually reasoned disables, and inferred target links.

## SDF

SDFormat models and worlds for Gazebo and other simulators: frames, poses, links, joints,
inertials, visuals, collisions, sensors, lights, physics, plugins and includes. SDFormat, not
signed-distance-field geometry, and not planning semantics.

1. Identify the consumer (Gazebo/libsdformat version, another simulator, visualization-only
   tooling, a model package, a world handoff) and the SDFormat version: `version="1.12"` for new
   outputs unless the consumer constrains it.
2. Decide the document kind: model, world, or model-in-world; prefer a model for reusable robot and
   object exports ([SDF authoring](references/sdf-authoring.md)).
3. Read or create the [SDF ledger](references/sdf-ledger.md) before writing poses, frames, axes,
   mesh scales, inertials, sensors or plugins.
4. Write `relative_to` on every nontrivial pose and `expressed_in` on every axis: implicit frame
   defaults are the top SDF failure mode ([SDF frames](references/sdf-frames.md)).
5. A robot with a URDF: derive the SDF from it
   ([Interoperability](references/interoperability.md#sdf-from-a-urdf)).
6. Author per the [worked examples](references/sdf-examples.md). Never invent plugin filenames,
   topics, frame names, namespaces or parameters: copy them from the simulator's documentation and
   cite it.
7. Check it ([SDF checks](references/sdf-checks.md)): `cad sdf validate` (which runs `gz sdf --check`
   whenever `gz` is on PATH), then simulator load, joint motion and plugin/sensor startup.

## MJCF

A MuJoCo model, MuJoCo's XML (`<mujoco>` at its root). The traps are units and defaults: MuJoCo reads
angles in degrees unless `<compiler angle="radian"/>` says otherwise (a keyframe's `qpos` is radians
whatever it says), and a geom or joint takes attributes from the default class it falls under.

1. Identify the consumer (MuJoCo's version, a training stack, a viewer) and whether the robot has a
   URDF to start from ([Interoperability](references/interoperability.md#mjcf)).
2. Split the robot from its world: `robot.xml` with no floor or light, and `scene.xml` that
   `<include>`s it and adds them ([MJCF authoring](references/mjcf-authoring.md)).
3. Set `<compiler angle="radian" meshdir="assets" autolimits="true"/>` explicitly; give the robot
   `<default>` classes, a `visual` one and a `collision` one, and `childclass` on its root body.
4. A body with no joint is welded to its parent; a floating base gets `<freejoint/>`. Leave inertia
   to the compiler from the geoms where it can, else compute an `<inertial>` ([Inertials](references/inertials.md)).
5. Ship a `<key name="home">` whose `qpos` (and `ctrl`) is the model's length.
6. Check it ([MJCF checks](references/mjcf-checks.md)): `cad mjcf validate --compile required`, then
   a snapshot of `home` and of each joint moved.

## Check each change

Each format has its validator and its snapshot:

```bash
cad urdf validate path/to/robot.urdf
cad urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
cad srdf validate path/to/robot.srdf --strict
cad sdf validate path/to/model.sdf --json
cad sdf validate path/to/model.sdf --gz-check required
cad mjcf validate path/to/scene.xml --compile required
cad urdf snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30}'
cad srdf snapshot path/to/robot.srdf review.png --pose arm/ready
cad sdf snapshot path/to/robot.sdf review.png --pose '{"arm::elbow": 45}'
cad mjcf snapshot path/to/scene.xml review.png --pose home
```

| Change | Check it with |
| --- | --- |
| Any `.urdf` | `cad urdf validate` until clean; `check_urdf FILE` (liburdfdom) when installed. |
| A joint origin, axis, sign or limit | The viewer sweep: every movable joint through its limits against the ledger's positive-motion statement, or snapshots at `--pose` values. The only check that catches a flipped sign. |
| A mesh, its scale or its placement | A snapshot: meshes at sane scale and pose; ~1000x too large or small is a `scale` bug. |
| An inertial | The [sanity gates](references/inertials.md#sanity-gates). |
| Any `.srdf` | `cad srdf validate` (it cross-checks every name, chain, state and pair against the paired URDF); named states in a snapshot (`--pose group/state`). |
| A URDF with an SRDF beside it | `cad srdf validate` on that SRDF again, and its group states against the new limits. |
| Any `.sdf` | `cad sdf validate` (`gz sdf --check` included when `gz` is on PATH; `--gz-check required` demands it). |
| Any MJCF | `cad mjcf validate --compile required` (MuJoCo's own compiler, fetched once as `cad[mujoco]`); the `home` key in a snapshot (`--pose home`). |
| SDF dynamics, plugins, sensors | A load in the target simulator, a small positive motion of each joint, plugin and sensor startup ([smoke tests](references/sdf-checks.md#smoke-tests)). |
| A MoveIt or ROS consumer | Its own load when available: RViz, robot_state_publisher's TF tree, a Gazebo load, MoveIt Setup Assistant (IK for the primary group, plan to a named state). |

- One run validates ONE file and collects every finding (severity, code, XML path) with a summary.
  `--strict` treats warnings as failures; `--json` prints one line of `{"ok", "path", "findings":
  [{"severity", "code", "message", "location", "hint"}], "summary"}`, where `location` is the XML
  path. It exits 1 if the target fails its checks, and 2, with nothing checked, for a command line
  it refuses -- a file of another format, one that is not there, an option or a value it does not
  take (`--gz-check` and `--compile` are `auto`, `required` or `never`) -- which `--json` says as one
  `{"ok": false, "error", "reason"}`. Relative targets resolve from the working directory: run
  from the workspace that owns the files.
- A clean check is a guardrail, not proof: it cannot show that a joint origin or axis matches the
  robot, that mesh units match `scale`, that a planning group matches the task, or that a plugin
  loads. Say which validator or smoke test passed, never just that the file is valid.
- Fix the owning file: the URDF for structure, the CAD workflow for a bad mesh export, then re-run
  the check from the top. Report a project-policy failure as policy, not invalidity.
- A file you write is the robot's model, not an export: show it. Visual review cannot prove
  planning correctness or dynamics; the viewer does not execute simulator plugins. Report which
  checks ran and which were skipped.

## Show the model

Show the person each model you create or change, and any model or file they ask to see. If your
tools include `cad_show` (your host may prefix it), call it with the model's id or the file's
absolute path; its description says the rest. Otherwise give the person the page's link once: a
model's page is the `view:` line its run prints, and a file's is the `url` that
`cad viewer --json FILE [FILE ...]` prints for it (never guess the port). A file you export is a
download: give its path. Never screenshot the viewer to check your own work; review with
`cad <type> snapshot`. If it fails to launch, say so.
