---
title: build123d
description: The Python CAD library your models are written in, and the OpenCASCADE kernel under it, which the engine also uses to read, write and draw documents.
---

[build123d](https://github.com/gumyr/build123d) is a Python library for modelling solids, sketches and assemblies. It sits on OpenCASCADE, the open source CAD kernel, through the `OCP` bindings. When your agent writes a part, it writes build123d code.

## What it does, and what text-to-cad adds

build123d already gives you the modelling API: boxes, sketches, booleans, fillets, joints and assemblies. Your script uses it as it is.

What text-to-cad adds is the engine around it. A `@model` function that returns build123d geometry becomes a document the engine builds in a warm worker, remembers between edits and names element by element, so a face or an edge can be pointed at. The engine also uses the kernel to read and write STEP, XBF, GLB, STL, 3MF and DXF, to draw snapshots, and to run the manufacturing, interference and stress checks on exact geometry.

## How it reaches your computer

You install nothing. The first time a model or a view needs the kernel, the `cad` command makes an environment for it, about 240 MB to download. A script run with `cad run` that imports `build123d` gets the `cad[build123d]` extra from its imports, and a script header may name `cad[build123d]` to ask for it. It runs inside the Python process that calls it, for a model its warm worker.

To use a Python of your own, `cad requirement build123d` prints the requirement to install. See [what a model runs in](/docs/install#what-a-model-runs-in).

## Related

[Parts and assemblies](/docs/guides/parts-and-assemblies) and [mechanisms](/docs/guides/mechanisms) use it throughout. The [build123d reference](repo:skills/cad/references/build123d-modeling.md) is what your agent reads when it models.
