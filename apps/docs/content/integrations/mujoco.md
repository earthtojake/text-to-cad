---
title: MuJoCo
description: The physics engine text-to-cad uses to turn a model into a MuJoCo spec, check an MJCF file with its compiler and show it in MuJoCo Studio.
---

[MuJoCo](https://mujoco.org) is a physics engine for simulating robots and contact. Its model file is an MJCF, an XML file, and its Python API builds one as an `MjSpec`.

## What it does, and what text-to-cad adds

MuJoCo already compiles, simulates and visualises a model, and its own API and MuJoCo Studio stay yours. text-to-cad leaves them alone. An MJCF is MuJoCo's file and not a [document type](/docs/document-types): no `cad` command draws one.

What it adds is the tie to your CAD model. `cad.mujoco.spec` makes a model with a mechanism an `MjSpec`, so a script can choose collision shapes, joint dynamics and actuators in MuJoCo's own API, then save the result. `cad mujoco check` compiles an MJCF with MuJoCo and reports what MuJoCo refuses or warns of, what collides as what, and the contact excludes, in the result shape every check shares. `cad run mujoco-studio --model scene.xml` serves a model in Studio for you to open in a browser.

## How it reaches your computer

You install nothing. The `cad` command fetches `cad[mujoco]` the first time you check a model, about 20 MB: MuJoCo's headless core and Studio's web viewer. A script run with `cad run` that imports `mujoco` gets the same extra.

## Example

```bash
cad mujoco check sim/scene.xml
cad run mujoco-studio --model sim/scene.xml
```

## Related

[Robots](/docs/skills/robotics-and-simulation) covers the route from a CAD model to a simulation. [CoACD](/docs/integrations/coacd) backs the convex collision shapes a spec can use. The [MJCF checks](repo:skills/robot-simulation/references/mjcf-checks.md) reference lists what `cad mujoco check` reports.
