---
title: XBF
description: The file the engine writes of a model, text-to-cad's own document format, which keeps names, colours, materials and the build closure.
---

An XBF (`.xbf`) is text-to-cad's own document saved as a file. It holds an OpenCASCADE document in its binary form, BinXCAF, together with its build closure, the record of what built it.

## Where you meet it

You get one when the engine writes it for a model: a script declares it with `@xbf("XBF/arm.xbf")`, or you export one with `cad model export`. It keeps the parts and their placements, names, colours, materials, element names and the mechanism, so reading it back loses nothing.

Think of it as Save As. Use it to hand a model to someone without its code, or to reuse a model in another project. It is also the fast way to use a vendor file: convert a STEP once, then read the XBF, which loads many times faster than parsing the STEP again.

## Example

```bash
cad step export vendor/motor.step vendor/motor.xbf
cad xbf export vendor/motor.xbf GLB/motor.glb
cad xbf snapshot vendor/motor.xbf tmp/motor.png
```

In a script, read it back as an input:

```python
from cad import xbf

motor = xbf.read("vendor/motor.xbf")
```

An XBF read into a model brings its geometry, names, colours and materials. Its joints, mechanism states and animations are not imported, so a part from an XBF is a part.

## Related

[Parts and assemblies](/docs/skills/parts-and-assemblies) covers composing models from files. The details of what an XBF holds are in [exports](repo:skills/cad/references/exports.md#the-xbf-is-save-as). The type that an XBF is a file of is the [model](/docs/document-types/model).
