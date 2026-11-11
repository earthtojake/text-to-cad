---
title: Netgen
description: The tetrahedral mesher text-to-cad uses to cut a part into the finite elements a stress study solves on.
---

[Netgen](https://ngsolve.org) is an automatic mesher that fills a solid with small tetrahedra. A stress study needs such a mesh before a solver can work on it.

## What it does, and what text-to-cad adds

Netgen already meshes a shape. text-to-cad does not wrap it and offers no command of its own for it. It is one of the two tools behind the `solve` operation of a [STEP](/docs/document-types/step), an [XBF](/docs/document-types/xbf) or a [model](/docs/document-types/model), the other being [CalculiX](/docs/integrations/calculix).

What text-to-cad adds is the study around it. The kernel reads the part, Netgen meshes the part's own faces with curved, second-order elements, and every face stays under its ref, so a load or a fixed support named on a face lands on that face. CalculiX then solves the mesh and the results come back as standard files.

Netgen always runs in a process of its own, because its copy of OpenCASCADE and the kernel's cannot share one.

## How it reaches your computer

You install nothing. The `cad` command makes an environment holding `cad[netgen]` the first time a study needs it, about 11 MB to download, with the kernel and CalculiX beside it. Netgen publishes its package for macOS, Linux on x86-64 and Windows on x86-64, so on another platform, Linux on ARM among them, a study refuses and names the platform.

## Related

[Stress studies](/docs/skills/stress-checks) takes a part from a load case to a safety factor. The [fea skill](repo:skills/fea/SKILL.md) is the reference your agent follows.
