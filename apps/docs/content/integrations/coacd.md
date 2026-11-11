---
title: CoACD
description: Approximate convex decomposition of a mesh, which text-to-cad uses to give a robot part collision shapes that keep its pockets.
---

[CoACD](https://github.com/SarahWeiii/CoACD) cuts a triangle mesh into a small set of convex pieces, or hulls. Simulators such as [MuJoCo](/docs/integrations/mujoco) collide convex shapes quickly, and a part with a pocket collides wrongly as a single hull.

## What it does, and what text-to-cad adds

CoACD already does the decomposition. text-to-cad offers nothing you call by name for it. It backs one helper, `decompose`, in a [MuJoCo](/docs/integrations/mujoco) function: a part of a robot collides as the hulls CoACD cuts its mesh into, while its visual shape stays whole. A printed bracket with a pocket for a servo keeps the pocket this way.

What text-to-cad adds is the surrounding behaviour. The decomposition always runs in a process of its own, because CoACD's threading library and the CAD kernel cannot share one, and the hulls are kept in the engine's cache by the mesh's digest. The first run takes from a few seconds to about a minute per part, and only a part you changed is cut again.

## How it reaches your computer

You install nothing and your script names nothing. The first time a part is decomposed, the engine fetches `cad[coacd]` into an environment of its own, about 4 MB, and reuses it after. A header never needs to name it.

## Related

[Robots](/docs/guides/robots) covers collision shapes for a simulation. The [meshes reference](repo:skills/robot-simulation/references/meshes.md) says how the hulls are written beside the model.
