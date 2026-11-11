---
title: SDF
description: SDFormat, the XML description of a Gazebo world or model, which text-to-cad checks and draws.
---

SDF (`.sdf`) is SDFormat, the Simulation Description Format Gazebo uses for worlds and models. A file can hold worlds, models, links, joints and mesh references. It covers more than a robot: it can describe the scene around one.

## Where you meet it

You meet an SDF when you bring one in, from a Gazebo project or a robot's vendor. text-to-cad does not generate SDF from a model, and no skill teaches writing one. What it does is read the file, check it and draw it, so you and your agent can review it with the same tools as a [URDF](/docs/document-types/urdf).

`validate` checks conformance. Where Gazebo's `gz` command is installed, it also runs `gz sdf --check` on the file. `snapshot` draws the file as the CAD Viewer does, into a PNG.

## Example

```bash
cad sdf validate worlds/arena.sdf
cad sdf snapshot worlds/arena.sdf tmp/arena.png
```

## Related

[Robots](/docs/guides/robots) covers the robot description formats text-to-cad works with. The [robot-simulation skill](repo:skills/robot-simulation/SKILL.md) is the nearest reference, and its [interoperability](repo:skills/robot-simulation/references/interoperability.md) page covers how URDF, SRDF and MJCF fit together.
