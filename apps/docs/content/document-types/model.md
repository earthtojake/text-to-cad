---
title: Model
description: The one document type with no file, a model built from code and held by the engine, addressed by its document id.
---

A model is what your agent builds when it writes a part, an assembly or a drawing as Python. It is the one document type with no file behind it: the engine builds it from the script and holds it in memory, and you or your agent address it by its document id.

## Where you meet it

Your agent writes a function marked `@model` that returns build123d geometry, then runs the script with `cad run`. The run prints an `id:` line. That id is the model's name for every later command, and the CAD Viewer opens the model by it. A script that calls the function gets a handle back, which stands for the same document.

No file of yours is written until you ask for one.

## What you do with it

You look at it in the CAD Viewer, take snapshots, inspect its parts, check it can be made, run a stress study, and export it. Each export writes a detached copy in another type: [STEP](/docs/document-types/step), [STL](/docs/document-types/stl), [3MF](/docs/document-types/threemf), [GLB](/docs/document-types/glb), [DXF](/docs/document-types/dxf) or [XBF](/docs/document-types/xbf).

## Example

```python
import build123d as bd
from cad import model


@model
def bracket():
    return bd.Box(60, 40, 5)


if __name__ == "__main__":
    bracket()
```

```bash
cad run src/bracket.py
cad model export "$ID" STEP/bracket.step STL/bracket.stl
```

`$ID` is the `id:` line the run printed.

## Related

[Parts and assemblies](/docs/skills/parts-and-assemblies) shows models from the first request to the finished export, and [your first model](/docs/first-model) walks through one. The rules for writing a model are in the [model contract](repo:skills/cad/references/model-contract.md).
