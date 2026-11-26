---
name: fea
description: Checks whether a part, or an assembly of bonded parts, is strong enough under its loads, as a linear static stress study (FEA). Use when the person asks whether a part will hold, break or bend too much, where it is most stressed, how much load it takes, how to make it stronger or lighter, or for FEA, a stress analysis or a strength simulation. Reports peak stress, safety factor against yield and deflection. Static loads only, not vibration, buckling, heat, fatigue or impact.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# FEA: will it hold, and how far does it move

A study holds some faces of a part, loads others, and solves the linear elastic response: stress and
displacement under forces, pressures, the part's own weight and steady accelerations, with an
isotropic material below yield, rigid fixtures and loads that do not move. An assembly's parts are
bonded where they touch. It is a first-pass engineering check, not a certification: say so in the
report. Vibration, buckling, heat, fatigue, impact and sliding contact are outside it, and a static
safety factor is no answer to them (a drop or a braking load can be estimated as a steady g-load:
[body loads](references/linear-static.md#body-loads-gravity-and-acceleration)).

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| Check a part under a load | `cad step solve part.step` lists its faces; write the study; solve into a folder | [Workflow](#workflow), [linear static](references/linear-static.md) |
| Check an assembly | `cad step solve assembly.step` lists the parts and the pairs that touch | [Assemblies](#assemblies) |
| Write or edit a study | One JSON object: fixtures and loads, then material, mesh, margin and checks | [Study file](references/study-file.md) |
| Choose a material | The model's own, or the E, ν and yield the person gives | [Materials](references/materials.md) |
| Judge the answer | `result.json` and its findings, against a hand estimate | [Findings](#findings), [judging the answer](references/linear-static.md#judging-the-answer) |
| Find the load a part takes | Solve at any load: the model is linear, so yield comes at the loads applied, all scaled by the safety factor | [`checks`](references/study-file.md#checks) |
| Answer what the summary does not | `result.vtu`, read with meshio | [Your own questions](#your-own-questions) |
| Compare design variants | The same study on each, faces mapped, mesh size held | [Compare variants](#compare-variants) |

The study reads a saved `.step` or `.xbf`, or a model the server holds by its id
(`cad model solve <id>`), and solves the whole document: to study one part of an assembly alone,
export it as a document of its own.

## Setup

Written for `cad==0.11.18`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

The mesher and the solver are fetched by `cad` the first time a study needs them, nothing to install:
the `netgen` integration (`cad[netgen]`, about 11 MB; macOS, Linux x86_64 and Windows x86_64 only, and
a solve elsewhere refuses, naming the platform) and the `calculix` integration (`cad[calculix]`,
CalculiX 2.23, about 13 MB). The solve runs headless on one thread, so the same study gives the same
numbers on every run. `cad run ccx ARGS` runs the same `ccx` on a deck of your own. A `ccx` on PATH is
never run; where the fetched one does not run on a computer, `CAD_CCX` names another (2.20 or newer).

Units are fixed: mm, N, MPa (pressure, modulus and stress), t/mm³ for density (steel 7.85e-9) and g
(9.81 m/s²) for gravity and acceleration. Restate every load in them before writing it down.

## Workflow

1. **List the faces.** With no study, `solve` prints the setup and writes nothing: the parts, the
   pairs that touch, then each face with its ref, area, centre, surface type and a hint such as
   `plane, normal -Z, largest`.

   ```bash
   cad step solve part.step
   ```

   Match the person's words ("the mounting face") to a ref by the hint and the centre; a hole is a
   `cylinder`. A face they picked in the viewer arrives as a ref already
   (`/work/bracket.step#bracket/face 17`). A document of several parts lists faces once one is named
   (`--occurrence post`). A face number is a position in the saved document, so list again after the
   part is edited.

2. **Write the study** ([study file](references/study-file.md)):

   ```json
   {
     "fixtures": [{"faces": ["bracket/face 17"], "type": "fixed"}],
     "loads": [{"faces": ["bracket/face 22"], "type": "force", "vector_N": [0, -500, 0]}]
   }
   ```

   `fixed` holds a face still; `roller` lets it slide in its plane (a frictionless support, a symmetry
   cut). A `force` is the total over its faces; a `pressure` is in MPa, positive into the surface;
   `gravity` and `acceleration` take `vector_g` and no faces, and need the material's density.
   `margin` is the safety factor the part should keep (default 2). `checks` adds a `displacement`
   limit when the person gave one. Leave `mesh` out on the first run.

3. **Solve into a folder**, one per study:

   ```bash
   cad step solve part.step --study study.json --out /tmp/bracket-load --json
   ```

   | File | What it is for |
   | --- | --- |
   | `result.json` | The answer, which `--json` also prints. Read this first |
   | `stress.png`, `displacement.png` | The deformed part coloured by each field, the deformation exaggerated by `deformation_scale`. They show whether the load points the way you meant and which faces are held |
   | `result.glb` | The same coloured surface, for `cad viewer` or any glTF viewer |
   | `result.vtu` | The volume mesh with `displacement` (mm) and `von_mises` (MPa) at its corner nodes |
   | `ccx.inp` | With `--deck`: the input CalculiX solved, to run or edit yourself (`cad run ccx -i ccx`, in that folder) |

   `result.json` holds `ok`, `findings` and `measurements`: the peak stress and where
   (`max_von_mises_MPa`, `max_von_mises_at_mm`), `yield_MPa`, `safety_factor`,
   `max_displacement_mm`, the applied force against the reactions, the mesh, and `refined` when the
   run solved twice ([what comes out](references/study-file.md#what-comes-out)).

   - A safety factor under 3 makes the run mesh finer and solve again by itself; the finer result is
     the one written ([mesh](references/linear-static.md#mesh)).
   - A malformed study is refused before meshing, naming the field. A part free to move, a load that
     reaches nothing, or reactions that do not balance the load are refused by the solve.
   - The exit status is 1 when a finding is an error (the part yields or misses a check, results
     written all the same; or `not_connected`, nothing written). Warnings leave it at 0.
   - Where the server cannot draw (Linux with no display) the pictures are left out and a
     `solver_note` says so.

4. **Report with units**: the peak von Mises and the feature it is near, the safety factor and the
   yield it is against, the largest displacement and where, the applied load against the reaction,
   the mesh size and whether a finer solve ran; then the findings, what the model assumes and what
   would change the answer most. Show `stress.png`, saying its deformation is exaggerated.

## Your own questions

For what the summary does not answer (the stress at the mounting holes, the sag along an edge, how
much of the part is above some stress), read `result.vtu` rather than solving again:

```python
# cad run --with meshio read-stress.py
import meshio, numpy as np

mesh = meshio.read("/tmp/bracket-load/result.vtu")
xyz, stress = mesh.points, mesh.point_data["von_mises"]          # mm, MPa
moved = np.linalg.norm(mesh.point_data["displacement"], axis=1)  # mm
near = np.linalg.norm(xyz - [42, 12, 3], axis=1) < 5             # within 5 mm of a point
print(stress[near].max(), moved[xyz[:, 2] > 49].max())
```

It holds the tetrahedra's corner nodes, inside the part as well as on its skin. The reported peak
also counts mid-edge nodes, so it can be a little above the VTU's maximum. An assembly's cells carry
their `part`, the index into the summary's `parts`.

## Assemblies

A document of several parts is solved as one: parts that touch are bonded into one mesh, each keeps
its own material, and each is judged against its own yield. Every part must reach a fixed part
through bonded neighbours ([study file](references/study-file.md#assemblies)).

- **Read the setup against the design.** It lists each pair as `bonded` (with its contact area and
  gap), `not connected` (a near miss, up to 1 mm), or `overlapping` (never bonded, unless the overlap
  is within the tolerance: an interference, bonded and closed like a gap). Is each detected joint
  real, and is an expected one missing? A wider gap is bonded by setting `contact_tolerance_mm`
  (default 0.1).
- **Materials**: each part uses its model's own; `parts` in the study gives one the person's numbers;
  a part with neither is refused by name.
- **`connections`** only overrides a detection (`free` for a pair that must not be glued). Parts that
  press, slide or are bolted are not modelled.
- **Faces** are named on any part (`post/face 23`), by its ref where names repeat (`frame/bar.2`). A
  face wholly covered by a bonded joint cannot be held or loaded.
- **Reading the result**: `yield_MPa` and `safety_factor` are the weakest part's (`weakest_part`),
  while `max_von_mises_MPa` and `max_displacement_mm` span the assembly, so never divide one by the
  other; each part's own numbers are in `parts`. Each finding names its part: fix that part.

## Compare variants

Each version of a design is its own document: run the same study on each into its own folder and
compare the `result.json`s. Face numbers are not stable between versions, and a ref reused unchecked
lands on a different face with no error, so list each variant's faces and map the baseline's by
surface type, normal, centre and area. Hold `mesh.size_mm` at the baseline's so a difference is the
design's and not the mesh's, and give the mapping with the table so the person can check it.

## Findings

Two von Mises peaks are reported. The **nodal** peak (`max_von_mises_MPa`, the one the safety factor
uses) is extrapolated from each element's integration points to its nodes and averaged; it is usually
the higher of the two. The **integration-point** peak (`max_von_mises_gauss_MPa`) is the raw element
value: more than 50 % above the nodal one, it means a concentration the mesh has not resolved. The
edge of a rigid fixture or bonded joint and a sharp inside corner are singularities, where the peak
grows with every refinement and never converges: read the stress a little away from them.

An error makes the part unfit as modelled; a warning is a judgment to weigh and explain. Most carry
the face and the point in mm.

| Finding | Severity | Means | Do |
| --- | --- | --- | --- |
| `yields` | error | The nodal peak is above yield | Strengthen where the peak is, change the material, or confirm the load. A `peak_at_fixture` or `peak_concentration` beside it comes first: the peak may be the model's, not the part's |
| `low_margin` | warning | It holds, but under the study's `margin` | As for `yields`, or report the margin it has. Never lower `margin` to clear it |
| `displacement_over_limit` | error | A `displacement` check is past its `limit_mm` | Stiffen the part, or confirm the limit |
| `peak_at_fixture` | warning | The peak sits on a fixed face or its edge, and a finer solve did not settle it | Read the stress a little away from the face before redesigning |
| `peak_concentration` | warning | The integration-point peak is well above the nodal one: a sharp corner or concentrated load | Fillet the corner or spread the load. Under a safety factor of 3 the run already refined once; above it (a high `margin`), refine once yourself and compare |
| `mesh_not_converged` | warning | The finer solve moved the peak by more than 10 % | A peak that keeps rising is a singularity: fillet it or judge away from it. Otherwise set a smaller `mesh.size_mm` |
| `large_displacement` | warning | It moves more than 1 % of its size: the small-displacement model is stretched | Check the fit against mating parts; stiffen if the deflection matters |
| `not_connected` | error | A part has no bonded chain to a fixed part; nothing was solved | Make the parts touch, fix a face on the group, or raise `contact_tolerance_mm` |
| `overlapping_parts` | warning | Two solids overlap beyond the tolerance and are not bonded | Fix the geometry, or mark the pair `free` when the overlap is an accepted shortcut |
| `gap_closed` | warning | Two parts within the tolerance were bonded by moving geometry that far | Confirm it is a modelling clearance; the stress at that joint is the closing's, not the part's |
| `bonded_edge_peak` | warning | The peak sits on the edge of a bonded joint | Read the stress a little away; a bolted or welded joint is softer than this model |
| `solver_note` | warning | About the run: a slow solve, a finer solve skipped, pictures not drawn | Mention it when it bears on the answer |

`peak_at_fixture` and `peak_concentration` appear only when the safety factor is under the `margin`
and no finer solve settled the peak.
