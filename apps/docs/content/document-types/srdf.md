---
title: SRDF
description: The Semantic Robot Description Format, an XML file that adds MoveIt planning groups, named states and disabled collision pairs to a URDF.
---

An SRDF (`.srdf`) is MoveIt's semantic robot description. It sits beside a [URDF](/docs/document-types/urdf) and says what the URDF does not: which joints form a planning group, where the end effectors are, what the named group states are (such as `ready`), which pairs of links never collide, and any virtual joints.

## Where you meet it

You ask for MoveIt planning on a robot. Your agent reads the robot's URDF, then writes the SRDF by hand, since nothing generates it from a model. The SRDF names links, joints and chains of the URDF, so a rename or a changed limit there can leave it out of step.

For that reason the check reads the SRDF against its URDF: every name, chain, state and disabled pair. Run it again whenever the URDF changes.

## Example

```bash
cad srdf validate description/arm.srdf --strict
cad srdf snapshot description/arm.srdf tmp/ready.png --pose arm/ready
```

The `--pose arm/ready` form draws the group state `ready` of the group `arm`, so you can see a named state before MoveIt uses it.

## Related

[Robots](/docs/guides/robots) shows the whole path from a CAD model to a URDF and an SRDF. The [SRDF authoring](repo:skills/robot-simulation/references/srdf-authoring.md) reference covers groups and states, and [disabled collisions](repo:skills/robot-simulation/references/srdf-disabled-collisions.md) covers the collision pairs.
