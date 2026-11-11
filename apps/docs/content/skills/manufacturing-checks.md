---
title: Manufacturing checks
description: The dfm check of the cad skill says whether a part can be machined, cut and bent, molded or 3D printed, and points each finding at the geometry.
---

Manufacturing checks are part of the `cad` skill. The `dfm` check (design for manufacture) measures a part against the rules of one fabrication process and says whether it can be made that way as drawn. You get a verdict and, for each problem, the feature, the number, the limit and what to change.

The rules are general practice from published design guides, plus text-to-cad's own floors where no guide states a limit. They are not any shop's.

## What it checks

| Process | What is measured |
| --- | --- |
| CNC milling and turning | Holes, pockets, internal corners against tool radius, walls, tool access, setups, undercuts |
| Sheet cutting and bending | Bends, flanges, reliefs, holes and their distances to edges and bends, on the unfolded part |
| Injection molding | Draft, undercuts, wall thickness, ribs, bosses, projected area, clamp force |
| 3D printing | Walls, overhangs, bridges, clearances, trapped volume, build-volume fit |

It checks a model by its id, or a file: `cad step dfm`, `cad xbf dfm`, `cad stl dfm`, `cad threemf dfm` and `cad glb dfm`. A mesh is checked for printing only. A cut file is checked with `cad dxf dfm` ([DXF profiles](/docs/skills/parts-and-assemblies#dxf-profiles-and-flat-patterns)).

## How it works

The check runs when your request names a process, or asks whether a part can be made by one. A named process is a requirement, so your agent builds its limits in from the first line, such as draft along the pull or radii in pocket corners. A material alone names no process, but "2 mm steel" means sheet.

The material in the model carries the process (`metals.aluminum(process=machined())`), and the shop's flags go in the docstring, so every edit runs the same check:

```python
"""A motor mount, CNC milled from 6061 on 3 axes.

Check: cad model dfm "$ID" --tools 3,6,10
"""
```

The check runs after every change, on the part's own id:

| Process | Example |
| --- | --- |
| CNC | `cad model dfm "$ID" --process cnc --material aluminum --tools 3,6,10` |
| Sheet | `cad model dfm "$ID" --process sheet --material aluminum --bend-radius 2 --k-factor 0.42` |
| Molding | `cad model dfm "$ID" --process molding --pull y --material pc --cavities 4` |
| Printing | `cad model dfm "$ID" --process printing --technology sla --build-volume 145x145x185` |

The last line of the output leads with one of three states, and the exit status matches:

| State | Exit | Meaning |
| --- | --- | --- |
| `OK` | 0 | Everything was measured and no finding is an error. Warnings may remain |
| `FAILED` | 1 | A finding is an error: the process cannot make the part as drawn |
| `NOT CHECKED` | 3 | Something was not judged, such as an open shell. It is never a pass |

Exit 2 means the command itself was refused, and `--strict` fails on a warning too. `--json` holds every measurement and every rule with its outcome.

Each finding carries a rule id, the measured `value`, the `limit`, the `source` of the rule and the face or edge refs involved. Your agent resolves a ref with `cad model inspect`, edits the code that made it, and repeats the check until no error remains. A feature you specified is never dropped or shrunk to clear a finding: your agent says so instead. `--candidates` ranks molding pulls or print orientations but judges nothing, so the chosen one is checked again.

## Ask for it

- "Can this bracket be CNC milled from 6061 on a 3-axis mill? My shop has 3, 6 and 10 mm end mills."
- "Check the cover for injection molding in ABS, pulling along Z, with 4 cavities."
- "Will this housing print in resin on a 145 by 145 by 185 mm printer?"
- "I want this tab in 2 mm steel, laser cut and bent. Does it work, and what should I change?"

## Limits

- It is not a shop's limits and not an approval. A shop's own numbers go in as options (`--tools`, `--thickness`, `--bend-radius`, `--build-volume` and others), and a specification you supply overrides the rules.
- A rule with no figure for your material or technology is `not_evaluated`, which is not a pass. A mesh cannot be checked for holes, pins or fine detail.
- Left to you: holder collisions, fixturing and tolerances for CNC; bend order, tooling access and grain for sheet; gates, weld lines, cooling and shrinkage for molding; lattices and tolerance stack-ups for printing.
- It does not say whether a part holds under load. That is a [stress check](/docs/skills/stress-checks).
- Slicing and printing are covered under [3D printing](/docs/skills/fabrication-services#3d-printing), and ordering cut parts under [SendCutSend](/docs/skills/fabrication-services#sendcutsend).

## The skill

This is the `cad` skill's "Can it be made?" section ([SKILL.md](repo:skills/cad/SKILL.md#can-it-be-made)). Its references, one per process:

- [CNC machining](repo:skills/cad/references/manufacturing-cnc.md)
- [Sheet metal](repo:skills/cad/references/manufacturing-sheet-metal.md)
- [Injection molding](repo:skills/cad/references/manufacturing-injection-molding.md)
- [3D printing](repo:skills/cad/references/manufacturing-printing.md)
- [Reading a review](repo:skills/cad/references/manufacturing-review.md), and [every rule](repo:packages/cad/src/cad/_internal/dfm/README.md)

Related pages: [parts and assemblies](/docs/skills/parts-and-assemblies), the [build123d](/docs/integrations/build123d) and [trimesh](/docs/integrations/trimesh) integrations.
