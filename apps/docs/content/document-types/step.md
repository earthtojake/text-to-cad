---
title: STEP
description: The standard exchange file for exact CAD geometry, which most CAD programs and suppliers read and write.
---

STEP (`.step`, `.stp`) is the ISO exchange format for exact 3D geometry. It stores solids as true surfaces rather than triangles, so a hole stays a circle and a fillet keeps its radius. Mechanical CAD programs, machine shops and part suppliers use it to pass models around. text-to-cad writes the AP242 flavour.

## Where you meet it

Two ways. You ask your agent for a part and then for a STEP of it, which the engine writes from the model. Or someone gives you a STEP, such as a vendor's motor, and your agent reads it into a model, inspects it, checks it or converts it.

A STEP keeps the assembly with its part names, colours, materials and the names of faces and edges. It does not keep a mechanism: it holds placements only.

## Example

Export from a model, or convert a file you were given:

```bash
cad model export "$ID" STEP/bracket.step
cad step inspect vendor/motor.step
cad step export vendor/motor.step vendor/motor.xbf
```

From Python, a script reads one as an input. A model can also write one on each run with the `@step("bracket.step")` decorator.

```python
from cad import model, step


@model
def rig():
    motor = step.read("vendor/motor.step")
    ...
```

A STEP that names other files as its parts is refused: export it again from the program that made it as a single file.

## Related

[Parts and assemblies](/docs/guides/parts-and-assemblies) covers using vendor files, and [SendCutSend](/docs/guides/sendcutsend) uses STEP as the upload file. [Exports](repo:skills/cad/references/exports.md#formats) lists what each format keeps.
