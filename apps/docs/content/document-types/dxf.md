---
title: DXF
description: A 2D drawing file of flat geometry in layers, the usual input for laser, waterjet and sheet cutting.
---

DXF (`.dxf`) is a 2D drawing format. It holds lines, arcs and circles on named layers, and cutting services and CAM programs use it as a cut file. text-to-cad writes one in millimetres.

## Where you meet it

You ask for a flat part, such as a gasket, a plate or a panel with holes and slots. Your agent writes a model that returns 2D geometry lying on the z=0 plane, then exports it. The export refuses a solid and any geometry off the plane, and it runs the drawing checks first. The viewer reads the written file itself, so the file a shop receives is the file the viewer draws.

One shape becomes one layer, `CUT`. A drawing with more than one operation uses a layer per part, for example `CUT` and `ENGRAVE`, and bend or fold lines go on layers named with `bend` or `fold`. Text is written as outlines, not DXF text, because cutting tools read geometry.

You can also hand your agent a DXF you already have, to look at or to check as a cut file.

## Example

```bash
cad run src/gasket.py
cad model export "$ID" DXF/gasket.dxf
cad dxf snapshot DXF/gasket.dxf tmp/gasket.png
cad dxf dfm DXF/gasket.dxf --process sheet --material aluminum --thickness 3 --kerf 0.2
```

## Related

[DXF profiles](/docs/guides/dxf-profiles) covers drawings in full, and [SendCutSend](/docs/guides/sendcutsend) prepares files for that service. See [2D profiles and DXF](repo:skills/cad/references/2d-profiles-and-dxf.md) for the rules a drawing follows.
