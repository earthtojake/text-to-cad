---
title: 3MF
description: A 3D Manufacturing Format package of triangle meshes that keeps parts, colours and materials, for slicers and printing.
---

3MF (`.3mf`) is a modern 3D printing format. Where an STL is one bare surface, a 3MF is a package that keeps each part as its own object, with its placement, colours and materials. Slicers and print services read it. In text-to-cad the id is `threemf`, because an id has to be a valid Python name.

## Where you meet it

You ask for a 3MF when you print a part or a small assembly and want the parts and colours to survive. The engine writes one from a model, a STEP or an XBF, in millimetres: an object per part and a build item per placement. A mesh converts to another mesh format (an STL, a GLB), but never back to exact geometry.

As with an STL, a print with fits and clearances should ask for a finer mesh with `--tolerance`, in millimetres. A 3MF does not draw transmission, so a transmissive material is written at a preview opacity.

## Example

```bash
cad model export "$ID" 3MF/standoff.3mf --tolerance 0.02
cad threemf snapshot 3MF/standoff.3mf tmp/standoff.png
cad stl export scan.stl scan.3mf
```

In a model, `@threemf("standoff.3mf", tolerance=0.02)` writes one on each run.

## Related

[3D printing](/docs/skills/fabrication-services#3d-printing) slices a 3MF or an STL, and [manufacturing checks](/docs/skills/manufacturing-checks) checks the mesh can be printed. The [print3d skill](repo:skills/print3d/SKILL.md) covers slicing.
