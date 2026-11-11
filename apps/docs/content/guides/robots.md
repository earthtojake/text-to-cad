---
title: Robots and simulation
description: Generate URDF, SRDF and MuJoCo MJCF robot descriptions from CAD or write them by hand, then check and view them.
---

A robot is described for software in XML. A URDF (Unified Robot Description Format) gives its links and joints to ROS tools such as RViz. An SRDF (Semantic Robot Description Format) sits beside it and adds planning groups and named poses for MoveIt. An MJCF is the model file for the MuJoCo physics engine.

There are two routes. If the robot is a text-to-cad model, your agent generates the description from the model's joints, materials and frames, so frames, limits, masses, inertias and meshes come from the geometry and the file is regenerated, never edited. If there is no model, or the file already exists, your agent writes and edits the XML directly.

## What to ask

- "Export my gripper model as a MuJoCo file with a scene I can open in MuJoCo Studio."
- "Generate a URDF for the arm, with the home pose as zero and effort and velocity limits from the servo datasheet."
- "Find the joint limits from where the parts collide and write them into the model."
- "Add an SRDF for MoveIt with a planning group for the arm and one for the gripper."
- "Check this MJCF and clear the model-health warnings before we tune anything."

## What your agent does

1. Declares what the geometry determines in the CAD model: joints (build123d `RevoluteJoint`, `LinearJoint` and others), a pose named `home`, materials so each link gets an exact mass and inertia, and helpers such as `frame()`, `limits()`, `mass()`, `point_mass()` and `link()`.
2. Runs the model, finds stops where they are the parts' (each joint is swept alone until its parts meet), then writes the file. The suffix picks the format:

   ```bash
   cad run src/gripper.py
   cad model ranges "$ID"
   cad model export "$ID" sim/gripper.xml
   cad model export "$ID" description/gripper.urdf --zero home
   ```

   `$ID` is the `id:` line the run printed. `--zero home` counts every joint from the named pose. An MJCF export also writes a `scene.xml` beside it with a floor, a light and a skybox, unless one exists. Your agent reads the export's log first: a mass of 0 or a missing joint means the model needs fixing.
3. For MuJoCo, writes a MuJoCo function, a plain Python script that turns the model into a `mujoco.MjSpec` with `spec()` and makes the simulation's choices: collision shapes (`fit` for a box, sphere, cylinder or capsule; `decompose` for a concave part), friction, joint damping, actuators. The plain export holds no chosen collision shape, joint dynamics or actuator, so this function replaces it for a simulation.
4. Writes an SRDF by hand against a valid URDF, copying every link and joint name from the URDF's table: planning groups, end effectors, named states, disabled collision pairs.
5. Validates:

   ```bash
   cad urdf validate path/to/robot.urdf
   cad srdf validate path/to/robot.srdf --strict
   cad mujoco check path/to/scene.xml
   ```

   Each run checks one file and collects every finding. `--strict` fails on warnings and `--json` prints machine-readable output.
6. Looks at the result: `cad urdf snapshot` and `cad srdf snapshot` draw a robot at a pose (`--pose '{"shoulder_pitch": 30}'` takes degrees), and the CAD Viewer opens them. For an MJCF, your agent runs `cad run mujoco-studio --model path/to/scene.xml` and gives you the URL it prints.

## What each check covers

| Command | Checks |
| --- | --- |
| `cad urdf validate` | One root, a connected tree, joint types and limits, axes, inertial tensors, mimic joints, geometry, mesh paths |
| `cad srdf validate` | Its own structure, then every group, chain, state and disabled pair against the paired URDF |
| `cad mujoco check` | MuJoCo's own compile, model health, and what collides and what is excluded |

MuJoCo's model-health findings include contacts at rest, mass counted twice, a suspect scale (millimetres read as metres) and joints outside their range at rest. Clear them before tuning any physics, then change one parameter at a time.

## What you need

- A URDF or SRDF check needs nothing beyond text-to-cad. Snapshots and generated descriptions use the CAD kernel.
- `cad mujoco check` and `cad run mujoco-studio` use MuJoCo's headless core and Studio's web viewer (`cad[mujoco]`, about 20 MB). The `cad` command fetches it into its own environment the first time.
- `decompose()` uses CoACD (`cad[coacd]`, about 4 MB), fetched the first time a part is decomposed. It is refused, naming the extra, where CoACD has no wheel, such as an Intel Mac, Windows on ARM or a musl Linux.

## What you get

- Generated files where you point the export: an MJCF or URDF, the meshes as binary STL in metres, and a `scene.xml`.
- A hand-written `.urdf` or `.srdf` with a comment block of frames, joints, units and assumptions.
- A report of which checks ran and which did not.
- A URDF or SRDF opens in the CAD Viewer. An MJCF does not: the CAD Viewer shows the CAD model it came from, and MuJoCo Studio shows the MJCF.

## Limits

- This writes and checks descriptions. It does not run a simulation, and the viewer does not play one.
- A clean check is a guardrail. It cannot show that a joint axis matches the real robot, that a gain is right, or that a planning group suits your task. A flipped joint sign shows only when each joint is swept through its limits or snapshotted at poses.
- Your agent does not infer axes, signs or mesh units from a picture, so tell it each joint's positive direction and the controller's zero.
- MuJoCo Studio listens on every network interface with no authentication, so use it on this computer or a trusted network.
- A vendor STEP has no mechanism, so it is articulated in a model first.

## Go deeper

- [The robot-simulation skill](repo:skills/robot-simulation/SKILL.md), with [generating from a vendor STEP](repo:skills/robot-simulation/references/from-a-vendor-step.md), [the MuJoCo environment](repo:skills/robot-simulation/references/mujoco-environment.md), [URDF checks](repo:skills/robot-simulation/references/urdf-checks.md), [SRDF authoring](repo:skills/robot-simulation/references/srdf-authoring.md) and [MJCF checks](repo:skills/robot-simulation/references/mjcf-checks.md).
- Document types [`urdf`](/docs/document-types/urdf) and [`srdf`](/docs/document-types/srdf), and the [MuJoCo](/docs/integrations/mujoco) and [CoACD](/docs/integrations/coacd) integrations.
- [Mechanisms](/docs/guides/mechanisms), where a robot's joints and poses are declared.
- [Parts and assemblies](/docs/guides/parts-and-assemblies) and [the CAD Viewer](/docs/guides/cad-viewer).
