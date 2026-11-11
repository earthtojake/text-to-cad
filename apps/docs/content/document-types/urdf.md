---
title: URDF
description: The Unified Robot Description Format, an XML file of a robot's links, joints, inertials and meshes that ROS tools read.
---

A URDF (`.urdf`) is the Unified Robot Description Format, the XML file ROS uses to describe a robot's structure: its links, its joints and their limits, each link's mass and inertia, and the meshes that draw it. Tools such as RViz and `robot_state_publisher` read it.

## Where you meet it

There are two routes. If you have a model with a mechanism, your agent exports a URDF from it: the mechanism becomes links and joints, the materials give exact masses and inertias, and each part's mesh is written as an STL in metres in a `meshes/` folder beside the file. The model stays the source, so you change it and export again rather than editing the file.

If the robot has no CAD model here, or you already have a URDF, your agent writes or edits the file by hand and checks it. A URDF has no named poses, so those go in an [SRDF](/docs/document-types/srdf).

## Example

```bash
cad model export "$ID" description/arm.urdf
cad urdf validate description/arm.urdf
cad urdf snapshot description/arm.urdf tmp/review.png --pose '{"shoulder_pitch": 30}'
```

`validate` checks structure, joints, inertials and mesh references. `snapshot` draws the robot, optionally in a pose.

## Related

[Robots](/docs/guides/robots) covers both routes, and [mechanisms](/docs/guides/mechanisms) explains the joints a model declares. The [URDF authoring](repo:skills/robot-simulation/references/urdf-authoring.md) reference is the one to read for a hand-written file.
