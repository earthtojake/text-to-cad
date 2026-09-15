# SDF interoperability notes

Use this reference when SDF work touches upstream geometry, robot-description data, Gazebo/libsdformat, model packages, or CAD Viewer.

## Geometry assets

SDF should reference geometry and mesh assets; it should not regenerate them.

When SDF references exported mesh assets, record:

- source geometry file;
- exported mesh path;
- mesh unit convention;
- mesh origin convention;
- visual scale;
- collision simplification decision.

Regenerate geometry and mesh artifacts with their owning workflow before regenerating SDF if geometry changed.

## Robot descriptions

Keep the simulator document aligned with the upstream robot-description source when one exists.

**Derive, don't re-author.** When a robot already has a URDF, the SDF model for that robot is derived from it: same link/joint names, same tree, same limits, same inertials, same mesh assets. Translate mechanically — URDF joint `<origin>` becomes the SDF joint `<pose relative_to="parent_link">`, and each child link gets `<pose relative_to="joint_name">0 0 0 0 0 0</pose>` — or use `gz sdf -p robot.urdf` as a starting point when Gazebo tooling is available, then review its output against this skill's contract. Independently re-authoring the same robot in SDF creates divergence that no validator catches. Record the source URDF (path and revision) in the SDF ledger comment.

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

## Planning metadata

SDF should not define planning groups, end-effectors, group states, or disabled-collision matrices. If the task becomes IK or path-planning work, use the planning metadata workflow that owns those semantics.

## CAD Viewer

CAD Viewer can review `.sdf` files visually through `$cad-viewer` and help catch gross placement or resource issues. It cannot prove simulator dynamics, inertial validity, plugin loading, sensor topics, or joint-axis semantics.

Pass explicit new or modified `.sdf` paths to `$cad-viewer` whenever it is available, and return the live viewer link it prints.

CAD Viewer renders SDF as static structure plus direct inspection controls. It lists plugins, sensors, lights, includes, and nested models as metadata, but does not execute plugins or consume file-authored motion contracts.

## Gazebo / libsdformat

The bundled validator is a lightweight preflight check. Use the target simulator's parser and loader when compatibility matters.

Good checks include:

```bash
gz sdf --check path/to/model.sdf
```

and a real simulator load in the target environment.

## Model packages and URIs

SDF resource resolution is environment-dependent. Record which URI forms the target consumer can resolve:

- relative paths from the `.sdf` file location;
- `model://` paths under the simulator model path;
- `package://` paths under ROS/package resolution;
- `fuel://` resources;
- `http://` or `https://` assets if external fetches are allowed.

The bundled validator can confirm local relative paths, but it cannot prove external simulator resource paths unless the target environment is available.
