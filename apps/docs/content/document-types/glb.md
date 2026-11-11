---
title: GLB
description: A binary glTF scene of triangle meshes, the file for renderers, Blender and the web, carrying parts, colours and animations.
---

A GLB (`.glb`) is the binary form of glTF 2.0, a scene format used by web viewers, game engines and Blender. It holds triangle meshes, not exact geometry, so it is for looking at a model and not for machining or editing it.

## Where you meet it

You ask for a GLB when you want to render a model or show it somewhere else. The engine writes one from a model, a STEP or an XBF. It has one mesh per part, with the assembly's tree as nodes, a material per look, and each of the model's motions and animations as a clip. Units are metres.

A GLB is the viewer's mesh unless you say otherwise. For a close camera or a path tracer, ask for a finer one with `--tolerance` (millimetres) and `--angle` (degrees, 1 to 28.5). Finer meshes cost more triangles, so the file grows.

A mesh never turns back into STEP or XBF: it has no exact geometry. A GLB converts to STL or 3MF.

## Example

```bash
cad model export "$ID" GLB/hero.glb --tolerance 0.05 --angle 5
cad glb snapshot GLB/hero.glb tmp/hero.png
```

## Related

[Renders](/docs/guides/renders) loads a GLB into [Blender](/docs/integrations/blender) for photoreal images and video, and [mechanisms](/docs/guides/mechanisms) explains the motions a GLB carries as animations. The options are in [a GLB for another renderer](repo:skills/cad/references/exports.md#a-glb-for-another-renderer).
