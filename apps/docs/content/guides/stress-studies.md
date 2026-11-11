---
title: Stress studies
description: Ask whether a part holds or how far it bends and get a linear static study solved with CalculiX, with stress, safety factor and deflection drawn on the part.
---

A stress study holds some faces of a part, loads others, and has CalculiX solve how the material responds. CalculiX is an open-source finite element solver. Your agent writes the study, runs it on a STEP file, an `.xbf` or a model, and reports the answer. You end up with the peak stress, a safety factor against yield, the deflection, and pictures of both on the deformed part.

It is a first-pass engineering check, not a certification.

## What to ask

- "Will this bracket hold 500 N pulling down on its end face, with the base bolted down? It is 6061 aluminium."
- "How much does this arm sag with 20 N at the tip? I need under 0.5 mm."
- "Check the post and base assembly with 1000 N sideways on the post."
- "Estimate a 1 m drop onto the bottom face, stopping in about 2 mm."

## What your agent does

1. **Lists the faces.** With no study, the solve is a setup and writes nothing:

   ```bash
   cad step solve part.step
   ```

   It prints the parts, the pairs that touch, and each face with its reference, area, centre, surface type and a hint such as `plane, normal -Z, largest`. Your agent matches "the mounting face" to a reference from that list. A face you picked in the CAD Viewer arrives as a reference already.
2. **Writes the study**, one JSON object. Units are fixed: millimetres, newtons, MPa, tonnes per cubic millimetre for density and g for acceleration. Your agent restates your loads in them.

   ```json
   {
     "fixtures": [{"faces": ["bracket/face 17"], "type": "fixed"}],
     "loads": [{"faces": ["bracket/face 22"], "type": "force", "vector_N": [0, -500, 0]}],
     "checks": [{"kind": "displacement", "limit_mm": 0.5, "faces": ["bracket/face 22"], "label": "Tip sag"}]
   }
   ```

   A `fixed` fixture holds a face still, and a `roller` lets it slide in its plane. A `force` is the total over its faces, and `gravity` and `acceleration` act on the whole part and need a density. `margin` is the safety factor to keep, 2 by default.
3. **Sets the material.** A part solved from a model or its `.xbf` uses the material the model set, at the low end of its yield range. A STEP carries a material's name and density but not its strength, so for a STEP your agent solves the model's `.xbf` or uses your datasheet's `E_MPa`, `nu` and `yield_MPa`.
4. **Solves into a folder.**

   ```bash
   cad step solve part.step --study study.json --out /tmp/bracket-load --json
   ```

   `cad model solve` takes a model's id, and `cad xbf solve` an `.xbf`. The first study installs the tools it needs, netgen for the mesh and CalculiX for the solve. If the safety factor comes out under 3, the run meshes again at half the element size and the finer result is the one written.
5. **Judges the answer.** Your agent reads `result.json` and compares it with a hand estimate, such as beam bending for a cantilever. Within about 20 per cent, the model is doing what was asked. Off by a factor, it checks the load, the fixture and the units. It then reports the peak von Mises stress and where it is, the safety factor against yield, and the largest displacement.

## What you get

Files land in the `--out` folder, which your agent can put in the project so you keep them:

| File | What it holds |
| --- | --- |
| `result.json` | The answer, with findings and measurements |
| `result.glb` | The deformed surface coloured by stress; opens in the CAD Viewer |
| `result.vtu` | The volume mesh with displacement and von Mises stress, for meshio, PyVista or ParaView |
| `stress.png`, `displacement.png` | Stills of each field with a colour bar |
| `ccx.inp` | The CalculiX input, with `--deck` |

Findings are listed errors first. The common ones are `yields` (the peak is past yield, an error), `low_margin` (it holds but under your margin, a warning), `displacement_over_limit` (an error), and `peak_at_fixture`, which says the peak sits on a rigid support where stress reads high. A part that yields or misses a check exits 1, with the files written all the same. A study that would give a wrong answer, such as a zero load, is refused and names the field.

An assembly is solved as one, with parts bonded where they touch and each judged against its own yield. The setup lists each pair, so your agent checks that every real joint is found.

## Limits

- **Linear static only.** Small displacements, an isotropic material below yield, perfectly rigid fixtures and loads that do not move. Vibration, buckling, heat, flow, fatigue, impact and parts that slide on each other are not in this version. A drop can be estimated as a steady g-load, and is reported as an estimate.
- **Bonded assemblies.** Touching parts carry load as if welded, with no slip, clearance, preload or bolt stiffness. A bonded joint is stiffer than a bolted one.
- **No moments, remote loads or bolt preloads.**
- **Singularities.** A rigid fixture's edge and a sharp inside corner give a peak that grows with every refinement. Your agent reads the stress a little away and suggests a fillet.
- **Directional materials.** Printed layers, wood and fibre are modelled as isotropic, so treat the answer as rough.
- **Platforms.** netgen is available on macOS, Linux x86_64 and Windows x86_64 only. Elsewhere a solve refuses and names the platform.

## Go deeper

- [Parts and assemblies](/docs/guides/parts-and-assemblies) covers making the part, [manufacturing checks](/docs/guides/manufacturing-checks) whether it can be made, and the [CAD Viewer](/docs/guides/cad-viewer) opens `result.glb`.
- Integrations: [CalculiX](/docs/integrations/calculix) and [netgen](/docs/integrations/netgen). Document types: [GLB](/docs/document-types/glb) and [STEP](/docs/document-types/step).
- In the repository: [the fea skill](repo:skills/fea/SKILL.md), [the study file](repo:skills/fea/references/study-file.md), [linear static](repo:skills/fea/references/linear-static.md), [materials](repo:skills/fea/references/materials.md) and [the library's section](repo:packages/cad/README.md#stress-studies).
