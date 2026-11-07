# How URDF, SRDF and SDF fit together

Use this reference when work touches more than one description of the same robot, or upstream geometry, Gazebo/libsdformat, model packages, or the CAD Viewer.

## Format boundary

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics: virtual joints, passive joints, planning groups, group states, end effectors, and disabled collision pairs.
- **SDF** owns simulator/world semantics: physics, sensors, lights, plugins, worlds, and simulation-specific metadata.

Do not place geometry, inertials, joint origins, link poses, mesh references, physical joint limits, transmissions, or `ros2_control` interfaces in SRDF. SDF should not define planning groups, end-effectors, group states, or disabled-collision matrices: if the task becomes IK or path-planning work, that is the SRDF's job ([SKILL.md](../SKILL.md#srdf)).

## Ownership

- CAD or mesh workflows own mesh generation and per-link splitting/export ([meshes.md](meshes.md)).
- The URDF owns its references, scales, placements, and structure.
- SRDF/MoveIt workflows own semantic groups, named joint poses via `<group_state>`, and planning metadata. Renaming links or joints in the URDF breaks them; update both in the same task.
- An SRDF pairs with its URDF by colocation and robot name alone ([srdf-authoring.md](srdf-authoring.md#urdf-pairing-non-negotiable)).

## When the URDF changes

Renamed links or joints, changed limits, or restructured chains invalidate the SRDF silently. After any URDF edit, re-run the SRDF validator on the paired `.srdf`, and re-check group states against the new limits. Treat URDF+SRDF as a pair in every task that touches either. A derived SDF is re-derived too ([below](#sdf-from-a-urdf)).

## SDF from a URDF

Keep the simulator document aligned with the upstream robot-description source when one exists.

**Derive, don't re-author.** When a robot already has a URDF, the SDF model for that robot is derived from it: same link/joint names, same tree, same limits, same inertials, same mesh assets. Translate mechanically — URDF joint `<origin>` becomes the SDF joint `<pose relative_to="parent_link">`, and each child link gets `<pose relative_to="joint_name">0 0 0 0 0 0</pose>` (the frame-graph pattern in [sdf-examples.md](sdf-examples.md#two-link-model-with-an-explicit-joint-frame)) — or use `gz sdf -p robot.urdf` as a starting point when Gazebo tooling is available, then review its output against this skill's contract. Independently re-authoring the same robot in SDF creates divergence that no validator catches. Record the source URDF (path and revision) in the SDF ledger comment.

Joint names colliding with link names break URDF-to-SDF conversion; `cad urdf validate` warns about them.

Upstream robot-description data usually owns:

- link and joint structure used by robot-state publishing;
- physical joint limits;
- inertials and visual/collision geometry when that source is authoritative;
- control-related structure and runtime interfaces.

Use SDF for simulator/world concerns:

- simulator plugins;
- sensors requiring simulator-specific XML;
- surfaces/contact/friction;
- lights, terrain, physics, and worlds;
- nested models and includes;
- simulator-specific metadata.

Do not use SDF to paper over a wrong upstream frame tree unless the task explicitly targets a simulator-only model.

## Gazebo / libsdformat

The bundled validator is a lightweight preflight check. Use the target simulator's parser and loader when compatibility matters.

Good checks include:

```bash
gz sdf --check path/to/model.sdf
```

and a real simulator load in the target environment ([sdf-checks.md](sdf-checks.md#smoke-tests)).

## CAD Viewer

CAD Viewer can review `.urdf`, `.srdf` and `.sdf` files visually and help catch gross placement or resource issues. It cannot prove simulator dynamics, inertial validity, plugin loading, sensor topics, joint-axis semantics, or planning correctness.

After creating or modifying a file, show it ([Show the model](../SKILL.md#show-the-model)). Report any failure explicitly.

CAD Viewer renders SDF as static structure plus direct inspection controls. It draws a model nested in the model with it (its links and joints named by scope, `arm::elbow`), lists plugins, sensors, lights and includes as metadata (an included model is not drawn), and does not execute plugins or consume file-authored motion contracts. An SRDF is drawn as its paired URDF's geometry, opened at its `home` group state when it declares one ([snapshots.md](snapshots.md)).
