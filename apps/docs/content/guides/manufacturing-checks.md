---
title: Manufacturing checks
description: The dfm check says whether a part can be CNC machined, cut and bent, injection molded or 3D printed, and points each finding at the geometry to change.
---

The `dfm` check (design for manufacture) measures a part against the rules of one fabrication process and says whether it can be made that way as drawn. Your agent runs it when you name a process, or ask whether a part can be made by one. You end up with a verdict, and for each problem the feature, the number, the limit and what to change.

The rules are general practice from published design guides, plus text-to-cad's own floors where no guide states a limit. They are not any shop's.

## What to ask

- "Can this bracket be CNC milled from 6061 on a 3-axis mill? My shop has 3, 6 and 10 mm end mills."
- "Check the cover for injection molding in ABS, pulling along Z, with 4 cavities."
- "Will this housing print in resin on a 145 by 145 by 185 mm printer?"
- "I want this tab in 2 mm steel, laser cut and bent. Does it work, and what should I change?"

## What your agent does

1. **Designs for the process from the first line** when your request names one. Machined, bent, molded or printed is a requirement, so the agent builds in the limits: drafted walls along the pull, a bend's inside radius, radii in pocket corners, walls at the material's minimum. A material alone names no process, but "2 mm steel" means sheet.
2. **Records the process in the model.** The material carries it (`metals.aluminum(process=machined())`), and the shop's flags go in the docstring so every edit runs the same check:

   ```python
   """A motor mount, CNC milled from 6061 on 3 axes.

   Check: cad model dfm "$ID" --tools 3,6,10
   """
   ```

3. **Runs the check after every change**, on the part's own id:

   | Process | Example |
   | --- | --- |
   | CNC milling and turning | `cad model dfm "$ID" --process cnc --material aluminum --tools 3,6,10` |
   | Sheet cutting and bending | `cad model dfm "$ID" --process sheet --material aluminum --bend-radius 2 --k-factor 0.42` |
   | Injection molding | `cad model dfm "$ID" --process molding --pull y --material pc --cavities 4` |
   | 3D printing | `cad model dfm "$ID" --process printing --technology sla --build-volume 145x145x185` |

   A STEP is checked with `cad step dfm part.step --process ...`, and `cad xbf dfm`, `cad stl dfm`, `cad threemf dfm` and `cad glb dfm` take those files. A mesh is checked for printing only. A cut file is `cad dxf dfm part.dxf`.
4. **Reads the verdict.** The last line leads with one of three states, and the exit status matches:

   | State | Exit | Meaning |
   | --- | --- | --- |
   | `OK` | 0 | Everything was measured and no finding is an error. Warnings may remain |
   | `FAILED` | 1 | A finding is an error: the process cannot make the part as drawn |
   | `NOT CHECKED` | 3 | Something was not judged, such as an open shell. It is never a pass |

   Exit 2 means the command itself was refused. `--strict` fails on a warning too.
5. **Follows each finding to the geometry.** A finding carries a rule id, the measured `value`, the `limit`, the `source` of the rule and the face or edge refs involved. Your agent resolves one with `cad model inspect "$ID" 'plate/face 9'` and edits the code that made it. It repeats the check with the same flags until no error remains. A feature you specified is never dropped or shrunk to clear a finding. Your agent says so instead.
6. **Compares options.** `--candidates` ranks molding pulls or print orientations. It judges nothing, so your agent checks again with the one chosen.

## What you get

- **A verdict and a count**, for example `FAILED part: 4 error(s), 2 warning(s); ...; failed: cnc.internal_corner_sharp x4`.
- **Facts beside the verdicts.** `--json` holds every measurement, every rule with its outcome, and what the source could not measure.
- **A handoff** that names the process, the material used, the findings left and the rules not evaluated.
- **What is measured**, by process:
  - CNC: holes, pockets, internal corners against tool radius, walls, tool access, setups and undercuts.
  - Sheet: bends, flanges, reliefs, holes and their distances to edges and bends, measured on the unfolded part.
  - Molding: draft, undercuts, wall thickness, ribs, bosses, projected area and clamp force.
  - Printing: walls, overhangs, bridges, clearances, trapped volume and build-volume fit.

## What it does not do

- It is not a shop's limits and not an approval. A shop's own numbers go in as options (`--tools`, `--thickness`, `--bend-radius`, `--build-volume` and others), and a specification you supply overrides the rules.
- A rule with no figure for your material or technology is `not_evaluated`, which is not a pass. A mesh cannot be checked for holes, pins or fine detail.
- By hand: holder collisions, fixturing and tolerances for CNC. Bend order, tooling access and grain for sheet. Gates, weld lines, cooling and shrinkage for molding. Lattices and tolerance stack-ups for printing.
- Slicing and printing belong to [3D printing](/docs/guides/3d-printing), and ordering cut parts to [SendCutSend](/docs/guides/sendcutsend).

## Go deeper

- [DXF profiles and flat patterns](/docs/guides/dxf-profiles) covers cut files. [Parts and assemblies](/docs/guides/parts-and-assemblies) covers the models being checked. [Stress studies](/docs/guides/stress-studies) answer whether a part holds, which this check does not.
- Integrations: [build123d](/docs/integrations/build123d) and [trimesh](/docs/integrations/trimesh).
- In the repository: [the cad skill](repo:skills/cad/SKILL.md#can-it-be-made), [CNC](repo:skills/cad/references/manufacturing-cnc.md), [sheet metal](repo:skills/cad/references/manufacturing-sheet-metal.md), [injection molding](repo:skills/cad/references/manufacturing-injection-molding.md), [3D printing](repo:skills/cad/references/manufacturing-printing.md), [the review reference](repo:skills/cad/references/manufacturing-review.md), [the library's section](repo:packages/cad/README.md#manufacturing-checks) and [every rule](repo:packages/cad/src/cad/_internal/dfm/README.md).
