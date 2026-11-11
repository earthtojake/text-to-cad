---
title: CalculiX
description: The finite element solver text-to-cad runs for stress studies, installed as a package and never taken from your own copy.
---

[CalculiX](https://www.calculix.de) is an open source finite element program. Its solver, `ccx`, reads an input deck of a meshed part, its material, its supports and its loads, and writes back the stresses and displacements.

## What it does, and what text-to-cad adds

CalculiX already solves the model. text-to-cad writes the input for it from a study you and your agent have described, runs it headless on one thread in a private folder, and reads its answer. The same study then gives the same numbers on every run, and each result names the version that solved it.

Around the solve it adds what a solver alone does not report. Each part's peak stress and safety factor are worked out, a part that yields fails the study, and the results are written as a folder of standard files, with stress and displacement pictures. The mesh comes from [Netgen](/docs/integrations/netgen).

## How it reaches your computer

You install nothing. The `cad` command makes an environment with `cad[calculix]` the first time a study needs it, about 13 MB, alongside the kernel and Netgen that a study also uses. The extra is the `cad-ccx` package, which carries CalculiX 2.23 for each platform. A CalculiX you installed yourself is never run, unless you set `CAD_CCX` to a `ccx` of version 2.20 or newer.

## Related

[Stress studies](/docs/skills/stress-checks) shows a study from request to result. See the [linear static](repo:skills/fea/references/linear-static.md) reference for what a study can and cannot say.
