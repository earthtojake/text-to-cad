---
title: STL
description: A binary STL of one triangle mesh, the long-standing file for 3D printing and for scans.
---

STL (`.stl`) is the oldest and simplest 3D printing format: a single surface made of triangles, with no colours, names or units stored. text-to-cad writes binary STL in millimetres.

## Where you meet it

You ask your agent for a part to print and it exports an STL from the model. You may also have an STL from elsewhere, such as a scan or a downloaded part. A mesh is measured, checked and drawn, but never turned into a model: it has no exact geometry, so a script reads one with `stl.read` as data (vertices, triangles and a bounding box).

For a print with tight fits, ask for a finer mesh. The viewer's mesh can sit up to 0.2 mm inside a curved surface, which is as much as a typical clearance. The export takes an absolute tolerance in millimetres, about a tenth of the smallest clearance.

## Example

```bash
cad model export "$ID" STL/hopper.stl --tolerance 0.02
cad stl dfm STL/hopper.stl --process printing --technology fdm --material petg
```

The second command checks the mesh can be printed, using the [trimesh](/docs/integrations/trimesh) integration.

## Related

[3D printing](/docs/guides/3d-printing) takes a part from model to sliced file, and [manufacturing checks](/docs/guides/manufacturing-checks) covers the printing check. See [print tolerance](repo:skills/cad/references/exports.md#print-tolerance) for how to choose a value.
