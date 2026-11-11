---
title: Robotics and simulation
description: The robot-simulation skill generates or writes URDF, SRDF and MuJoCo MJCF robot descriptions, then checks them and shows them.
---

The `robot-simulation` skill makes the files that describe a robot to software, and checks them. A URDF (Unified Robot Description Format) gives a robot's links and joints to ROS tools such as RViz. An SRDF (Semantic Robot Description Format) sits beside it and adds planning groups and named poses for MoveIt. An MJCF is the model file for the MuJoCo physics engine. All three are XML.

There are two routes. If the robot is a text-to-cad model, the description is generated from the model's joints, materials and frames, so frames, limits, masses, inertias and meshes come from the geometry and the file is regenerated, never edited. If there is no model, or the file already exists, your agent writes and edits the XML directly.

## What it makes

- Generated files where you point the export: an MJCF or URDF, the meshes as binary STL in metres, and a `scene.xml`.
- A hand-written `.urdf` or `.srdf` with a comment block of frames, joints, units and assumptions.
- A report of which checks ran and which did not.

A URDF or SRDF opens in the [viewer](/docs/viewer). An MJCF opens in MuJoCo Studio, and the viewer shows the CAD model it came from.

## How it works

The CAD model declares what the geometry determines: joints (build123d `RevoluteJoint`, `LinearJoint` and others), a pose named `home`, materials so each link gets an exact mass and inertia, and helpers such as `frame()`, `limits()`, `mass()`, `point_mass()` and `link()`.

`cad` runs the model, finds joint stops where the parts meet (each joint is swept alone), then writes the file. The suffix picks the format:

```bash
cad run src/gripper.py
cad model ranges "$ID"
cad model export "$ID" sim/gripper.xml
cad model export "$ID" description/gripper.urdf --zero home
```

`$ID` is the `id:` line the run printed, and `--zero home` counts every joint from the named pose. An MJCF export also writes a `scene.xml` beside it with a floor, a light and a skybox, unless one exists. In the export's log, a mass of 0 or a missing joint means the model needs fixing.

The plain export holds no chosen collision shape, joint dynamics or actuator. For a simulation, a MuJoCo function replaces it: a Python script that turns the model into a `mujoco.MjSpec` with `spec()` and chooses collision shapes (`fit` for a box, sphere, cylinder or capsule; `decompose` for a concave part), friction, joint damping and actuators.

An SRDF is written by hand against a valid URDF, with every link and joint name copied from the URDF's table: planning groups, end effectors, named states, disabled collision pairs.

Every file is then checked:

```bash
cad urdf validate path/to/robot.urdf
cad srdf validate path/to/robot.srdf --strict
cad mujoco check path/to/scene.xml
```

Each run checks one file and collects every finding. `--strict` fails on warnings and `--json` prints machine-readable output.

| Command | Checks |
| --- | --- |
| `cad urdf validate` | One root, a connected tree, joint types and limits, axes, inertial tensors, mimic joints, geometry, mesh paths |
| `cad srdf validate` | Its own structure, then every group, chain, state and disabled pair against the paired URDF |
| `cad mujoco check` | MuJoCo's own compile, model health, and what collides and what is excluded |

MuJoCo's model-health findings include contacts at rest, mass counted twice, a suspect scale (millimetres read as metres) and joints outside their range at rest. They are cleared before any physics is tuned.

`cad urdf snapshot` and `cad srdf snapshot` draw a robot at a pose (`--pose '{"shoulder_pitch": 30}'` takes degrees). For an MJCF, `cad run mujoco-studio --model path/to/scene.xml` starts MuJoCo Studio and prints the URL to open.

## What it needs

- A URDF or SRDF check needs nothing beyond text-to-cad. Snapshots and generated descriptions use the CAD kernel.
- `cad mujoco check` and `cad run mujoco-studio` use MuJoCo's headless core and Studio's web viewer (`cad[mujoco]`, about 20 MB). The `cad` command fetches it into its own environment the first time.
- `decompose()` uses CoACD (`cad[coacd]`, about 4 MB), fetched the first time a part is decomposed. It is refused, naming the extra, where CoACD has no wheel, such as an Intel Mac, Windows on ARM or a musl Linux.

## Ask for it

- "Export my gripper model as a MuJoCo file with a scene I can open in MuJoCo Studio."
- "Generate a URDF for the arm, with the home pose as zero and effort and velocity limits from the servo datasheet."
- "Find the joint limits from where the parts collide and write them into the model."
- "Add an SRDF for MoveIt with a planning group for the arm and one for the gripper."
- "Check this MJCF and clear the model-health warnings before we tune anything."

## Limits

- The skill writes and checks descriptions. It does not run a simulation, and the viewer does not play one.
- A clean check is a guardrail. It cannot show that a joint axis matches the real robot, that a gain is right, or that a planning group suits your task. A flipped joint sign shows only when each joint is swept through its limits or snapshotted at poses.
- Your agent does not infer axes, signs or mesh units from a picture, so tell it each joint's positive direction and the controller's zero.
- MuJoCo Studio listens on every network interface with no authentication, so use it on this computer or a trusted network.
- A vendor STEP has no mechanism, so it is articulated in a model first.

## The skill

The skill is [`robot-simulation`](repo:skills/robot-simulation/SKILL.md). Its most useful references:

- [Generating from a vendor STEP](repo:skills/robot-simulation/references/from-a-vendor-step.md)
- [The MuJoCo environment](repo:skills/robot-simulation/references/mujoco-environment.md)
- [URDF checks](repo:skills/robot-simulation/references/urdf-checks.md), [SRDF authoring](repo:skills/robot-simulation/references/srdf-authoring.md) and [MJCF checks](repo:skills/robot-simulation/references/mjcf-checks.md)

Related pages: the document types [`urdf`](/docs/document-types/urdf) and [`srdf`](/docs/document-types/srdf), the [MuJoCo](/docs/integrations/mujoco) and [CoACD](/docs/integrations/coacd) integrations, [mechanisms and animation](/docs/skills/parts-and-assemblies#mechanisms-and-animation) for where a robot's joints and poses are declared, and [the viewer](/docs/viewer).
