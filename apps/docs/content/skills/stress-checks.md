---
title: Stress checks
description: The fea skill checks whether a part or a bonded assembly holds under load, solved with CalculiX, with stress, safety factor and deflection drawn on the part.
---

The `fea` skill answers whether a part holds under its loads and how far it bends. It writes a stress study for a STEP file, an `.xbf` or a model, has CalculiX (an open-source finite element solver) solve it, and reports the peak stress, a safety factor against yield and the deflection, with pictures of both on the deformed part. It is a first-pass engineering check, not a certification.

## What it answers

- **Whether it holds**: the peak von Mises stress against the material's yield, as a safety factor, judged against the margin you want to keep (2 by default).
- **How far it moves**: the largest displacement, and whether a face stays within a limit you give.
- **Where it is most stressed**: the location of the peak, drawn on the part.
- **Whether an assembly holds**: it is solved as one, with parts bonded where they touch and each judged against its own yield.

## How it works

With no study, a solve is a setup that writes nothing. It lists the parts, the pairs that touch, and each face with its reference, area and a hint such as `plane, normal -Z, largest`:

```bash
cad step solve part.step
```

Your agent matches "the mounting face" to a reference from that list; a face you picked in the CAD Viewer arrives as one already.

The study is one JSON object, in fixed units: millimetres, newtons, MPa, tonnes per cubic millimetre for density and g for acceleration. Your agent restates your loads in them.

```json
{
  "fixtures": [{"faces": ["bracket/face 17"], "type": "fixed"}],
  "loads": [{"faces": ["bracket/face 22"], "type": "force", "vector_N": [0, -500, 0]}],
  "checks": [{"kind": "displacement", "limit_mm": 0.5, "faces": ["bracket/face 22"], "label": "Tip sag"}]
}
```

A `fixed` fixture holds a face still and a `roller` lets it slide in its plane. A `force` is the total over its faces; `gravity` and `acceleration` act on the whole part.

A model or its `.xbf` brings the material the model set, at the low end of its yield range. A STEP carries no strength, so your agent solves the model's `.xbf` instead or uses your datasheet's `E_MPa`, `nu` and `yield_MPa`.

The solve writes into a folder:

```bash
cad step solve part.step --study study.json --out /tmp/bracket-load --json
```

`cad model solve` takes a model's id, and `cad xbf solve` an `.xbf`. The first study installs netgen for the mesh and CalculiX for the solve. If the safety factor comes out under 3, the run meshes again at half the element size and the finer result is the one written.

| File | What it holds |
| --- | --- |
| `result.json` | The answer, findings and measurements |
| `result.glb` | The deformed surface coloured by stress; opens in the CAD Viewer |
| `result.vtu` | The volume mesh and its fields, for meshio, PyVista or ParaView |
| `stress.png`, `displacement.png` | Stills of each field with a colour bar |
| `ccx.inp` | The CalculiX input, with `--deck` |

Findings are listed errors first: `yields` (the peak is past yield, an error), `low_margin` (it holds but under your margin, a warning), `displacement_over_limit` (an error), and `peak_at_fixture`, which says the peak sits on a rigid support where stress reads high. A part that yields or misses a check exits 1, with the files written all the same. A study that would give a wrong answer, such as a zero load, is refused.

Your agent compares `result.json` with a hand estimate, such as beam bending for a cantilever. Within about 20 per cent, the study is doing what was asked; a result off by a factor sends your agent back to the load, the fixture and the units.

## Ask for it

- "Will this bracket hold 500 N pulling down on its end face, with the base bolted down? It is 6061 aluminium."
- "How much does this arm sag with 20 N at the tip? I need under 0.5 mm."
- "Check the post and base assembly with 1000 N sideways on the post."
- "Estimate a 1 m drop onto the bottom face, stopping in about 2 mm."

## Limits

- **Linear static only.** Small displacements, an isotropic material below yield, rigid fixtures and loads that do not move. No vibration, buckling, heat, flow, fatigue, impact or sliding parts. A drop is a steady g-load, reported as an estimate.
- **Bonded assemblies.** Touching parts carry load as if welded, with no slip, clearance or bolt stiffness, so a bonded joint is stiffer than a bolted one.
- **No moments, remote loads or bolt preloads.**
- **Singularities.** A rigid fixture's edge or a sharp inside corner gives a peak that grows with every refinement, so the stress is read a little away and a fillet suggested.
- **Directional materials.** Printed layers, wood and fibre are modelled as isotropic, so the answer is rough.
- **Platforms.** netgen is available on macOS, Linux x86_64 and Windows x86_64 only. Elsewhere a solve refuses and names the platform.

## The skill

This is the `fea` skill ([SKILL.md](repo:skills/fea/SKILL.md)). Its references:

- [The study file](repo:skills/fea/references/study-file.md)
- [Linear static](repo:skills/fea/references/linear-static.md)
- [Materials](repo:skills/fea/references/materials.md)
- [The library's section](repo:packages/cad/README.md#stress-studies)

Related pages: [parts and assemblies](/docs/skills/parts-and-assemblies), [manufacturing checks](/docs/skills/manufacturing-checks), the [CAD Viewer](/docs/viewer) (which opens `result.glb`), the [CalculiX](/docs/integrations/calculix) and [netgen](/docs/integrations/netgen) integrations, and the [GLB](/docs/document-types/glb) and [STEP](/docs/document-types/step) document types.
