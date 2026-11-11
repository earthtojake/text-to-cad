---
title: trimesh
description: The Python library for triangle meshes, which text-to-cad uses to check that a mesh can be 3D printed.
---

[trimesh](https://trimesh.org) is a Python library for loading, measuring and analysing triangle meshes.

## What it does, and what text-to-cad adds

trimesh already loads, queries and measures triangle meshes. text-to-cad does not rename any of it. If a script of yours wants trimesh for its own work, it imports it and uses it as it is.

What text-to-cad adds is a manufacturing check on top. For a [STL](/docs/document-types/stl), a [3MF](/docs/document-types/threemf) or a [GLB](/docs/document-types/glb), it measures the mesh with trimesh and judges the numbers against general, cited rules for 3D printing: walls, overhangs and support. Machining, sheet metal and moulding checks need exact geometry, so they use a STEP or a model, not a mesh. The findings come back in the shape every manufacturing check uses, so a print check reads like a machining check.

## How it reaches your computer

You install nothing. The first time a mesh check runs, the `cad` command makes an environment holding `cad[trimesh]`, about 40 MB to download, and keeps it. A script run with `cad run` that imports `trimesh` gets the same extra. It runs inside the Python process that calls it.

## Example

```bash
cad stl dfm stand.stl --process printing --technology fdm --material petg
```

## Related

[Manufacturing checks](/docs/guides/manufacturing-checks) covers every process, and [3D printing](/docs/guides/3d-printing) takes a checked part to a slicer.
