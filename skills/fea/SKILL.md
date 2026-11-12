---
name: fea
description: Checks whether a part or an assembly of bonded parts holds under its loads, as a linear static stress study of a STEP, an xbf or a text-to-cad model, meshed by netgen and solved by CalculiX, giving peak von Mises stress, safety factor against yield and deflection drawn on the part. Use when the person asks whether a part will hold, break or is strong enough, how much it bends or sags, where it is most stressed, how much load it takes, how to make it stronger or lighter without failing, or for FEA, a stress analysis or a strength simulation. Static loads and steady g-loads only.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# FEA: will it hold, and how far does it move

A study holds some faces of a part, loads others, and has CalculiX solve the linear elastic
response on a netgen mesh of quadratic tetrahedra: stress and displacement under forces,
pressures, the part's own weight and a steady acceleration, with an isotropic material below
yield, perfectly rigid fixtures and loads that do not move. An assembly's parts are bonded where
they touch. It is a first-pass engineering check, not a certification; say so when you report.
Vibration, buckling, heat, flow, fatigue, impact and parts that slide on each other are not in
this version: say so plainly, and do not pass a static safety factor off as an answer to them. A
drop or a braking load can be estimated as a steady g-load
([Body loads](references/linear-static.md#body-loads-gravity-and-acceleration)).

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Check a part under a load** | `cad step solve part.step` lists its faces; write the study; solve into a folder. | [Workflow](#workflow), [Linear static](references/linear-static.md) |
| **Check an assembly** | `cad step solve assembly.step` lists the parts and the pairs that touch. | [Assemblies](#assemblies) |
| **Write or edit a study** | One JSON object: fixtures and loads, then material, mesh, margin and checks; parts and connections for an assembly. | [Study file](references/study-file.md) |
| **Choose a material** | The model's own (solve the model or its `.xbf`), or the E, ν and yield the user gives. | [Materials](references/materials.md) |
| **Judge the answer** | `result.json` and its findings, against a hand estimate. | [Findings](#findings), [Judging the answer](references/linear-static.md#judging-the-answer) |
| **Answer a question the summary does not** | `result.vtu`, read with meshio. | [Your own questions](#your-own-questions) |
| **Compare variants of a design** | The same study on each, faces mapped, mesh size held. | [Compare variants](#compare-variants) |

This skill studies a part; it does not model one. It reads a saved `.step` or `.xbf`, or a model the
engine holds by its document id (`cad model solve <id>`), and solves the whole document: to study one
part of an assembly alone, export it as a document of its own.

## Setup

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor
--check` explains any other failure, changing nothing; `cad doctor` repairs what it reports. Tell the
person any next step `cad setup` prints.

The study is the `solve` operation of the document's type: `cad step solve`, `cad xbf solve`,
`cad model solve`. With no `--study` it lists the study's setup and writes nothing; with `--study`
and `--out DIR` it solves and writes its results into `DIR`. Its two tools are integrations the
`cad` command installs the first time a study needs them, nothing for you to install; `cad run`
gives a script that calls `cad.step.solve` both, with the kernel that reads the part.

- **netgen**, the mesher: the `netgen` integration (`cad[netgen]`, about 11 MB). netgen publishes
  it for macOS, Linux x86_64 and Windows x86_64 alone; elsewhere (Linux on ARM among them) a solve
  refuses, naming the platform.
- **CalculiX** (`ccx`), the solver: the `calculix` integration (`cad[calculix]`: the cad-ccx
  package, CalculiX 2.23 for each platform, about 13 MB). A person's own CalculiX is never run
  unless `CAD_CCX` names the file (2.20 or newer). It runs headless, on one thread, in a private
  folder, so the same study gives the same numbers every run, and every result names the version
  that solved it. `cad run ccx ARGS` runs that same `ccx` on a deck of your own.

Units are fixed: mm, N, MPa (pressure, modulus and stress), t/mm³ for density (steel 7.85e-9) and
g (9.81 m/s²) for gravity and acceleration. Restate every load in them before you write it down.

## Workflow

1. **List the faces.** A study names faces by the engine's refs, the ones the CAD Viewer copies; a
   face the user picked there arrives as `/work/bracket.step#bracket/face 17` and needs no lookup.

   ```bash
   cad step solve part.step
   ```

   With no study this is the setup, and writes nothing: the parts, the pairs that touch, then each
   face of the part, one a line: ref, area, centre, surface type and a hint such as `plane, normal
   -Z, largest`. Match the user's words ("the mounting face") to a ref by the hint and the centre;
   a hole is a `cylinder`. A document of several parts lists no faces until one is named:
   `cad step solve assembly.step --occurrence post`. A face number is a position in the saved
   document, so a part edited and written again is listed again before its study is re-run.

2. **Write the study** ([study-file.md](references/study-file.md)):

   ```json
   {
     "fixtures": [{"faces": ["bracket/face 17"], "type": "fixed"}],
     "loads": [{"faces": ["bracket/face 22"], "type": "force", "vector_N": [0, -500, 0]}]
   }
   ```

   `fixed` holds a face still; `roller` lets it slide in its plane but not off it (a frictionless
   support, or a symmetry cut). A `force` is the total over its faces; a `pressure` is in MPa,
   positive into the surface; `gravity` and `acceleration` take `vector_g` in g and no faces, and
   need the material's density. `margin` is the safety factor the part should keep (default 2, at
   least 1). `checks` adds a `displacement` check with the user's limit when they gave a sag or
   stiffness spec; left out, the stress check alone judges the part. Leave `mesh` out on the first
   run.

3. **Solve into a folder.**

   ```bash
   cad step solve part.step --study study.json --out /tmp/bracket-load --json
   ```

   `--out` is any folder, a temporary one included, made when missing; put it in the project when
   the user should keep the files. One folder per study: a solve replaces its own files there,
   touches nothing else, and a run that fails leaves the previous results as they were. It holds:

   | File | What it is for |
   | --- | --- |
   | `result.json` | the answer, what `--json` prints. Read this first. |
   | `stress.png`, `displacement.png` | the deformed part coloured by each field (blue low, red high), the deformation exaggerated by `deformation_scale`, with a colour bar giving the field, its units and its range. They show whether the load points the way you meant and which faces are held. Show the stress one to the user. |
   | `result.glb` | the same coloured surface, for any glTF viewer or `cad viewer` |
   | `result.vtu` | the volume mesh with `displacement` (mm) and `von_mises` (MPa) at its corner nodes ([Your own questions](#your-own-questions)) |
   | `ccx.inp` | with `--deck`: the input CalculiX solved (the finer solve's when there were two), for `cad run ccx -i ccx` in that folder |

   Where the engine cannot draw (Linux with no display) the pictures are left out and a
   `solver_note` says so; everything else is written.

   The result is a check's: `ok`, `findings` (each with `severity`, `code`, `message`, `location`
   and `hint`), `written`, and `measurements`: the study as given, the material, the faces it
   named (`named_faces`), the summary's figures (`max_von_mises_MPa` and `max_von_mises_at_mm`,
   `max_von_mises_gauss_MPa`, `yield_MPa`, `safety_factor`, `max_displacement_mm` and
   `max_displacement_at_mm`, `applied_force_N`, `reaction_force_N`, `deformation_scale`, `checks`;
   an assembly's `weakest_part` and `parts`), each fixture's reaction, `mesh` (size, elements,
   degrees of freedom, `straightened`, `solver`), `timings`, and `refined`, the first solve's size
   and peak when the run solved twice. Without `--json` the same prints as lines.

   - When the safety factor comes out under 3 the run meshes again finer (half the element size,
     less on a big model) and solves again by itself; the finer result is the one written
     ([Mesh](references/linear-static.md#mesh)).
   - Progress (`[fea] meshing ...`) goes to stderr, never into the result; `--verbose` adds mesh
     and solve detail there.
   - A malformed study (an unknown key, a face not on the part, a zero load, a load on a held
     face, no fixture) is refused before meshing, naming the field. A part the fixtures leave free
     to move, or that no load reaches, is refused by the solve; so is a solve whose reactions do
     not balance the applied load.
   - The command exits 1 (`"ok": false`) when a finding is an error: the part yields or misses a
     check, with the results written all the same; or the study stopped before the solve
     (`not_connected`), with nothing written. Warnings leave it at 0. Read the result either way.

4. **Report** with units: the peak von Mises and which feature it is near, the safety factor and
   the yield it is against (the low end of the model material's range), the max displacement and
   where, the applied load against the reaction, the mesh size and whether a finer re-solve ran;
   then the findings, what the model assumes, and what would change the answer most. Show
   `stress.png`, saying the deformation is exaggerated by `deformation_scale`.

## Your own questions

For anything the summary does not answer (the stress at the mounting holes, the sag along an
edge, how much of the part is above some stress), read `result.vtu` rather than solving again.
meshio or PyVista read it as it is (`uv run --with meshio`):

```python
import meshio, numpy as np

mesh = meshio.read("/tmp/bracket-load/result.vtu")
xyz, stress = mesh.points, mesh.point_data["von_mises"]          # mm, MPa
moved = np.linalg.norm(mesh.point_data["displacement"], axis=1)  # mm
near = np.linalg.norm(xyz - [42, 12, 3], axis=1) < 5             # within 5 mm of a point
print(stress[near].max(), moved[xyz[:, 2] > 49].max())
```

It holds the corner nodes of the tetrahedra, inside the part as well as on its skin; the reported
peak also counts the mid-edge nodes, so it can be a little higher than the VTU's own maximum. An
assembly's cells carry their part (`part`, the index into the summary's `parts`).

## Assemblies

A document of several parts is solved as one assembly: the parts that touch are bonded into one
conforming mesh, each keeps its own material, and each part's stress is judged against its own
yield. Every part must reach a fixed part through bonded neighbours. The keys are in
[study-file.md](references/study-file.md#assemblies).

The setup (`cad step solve assembly.step`) prints each part (ref, name, volume), then each pair:
`bonded`, with its contact area and gap; `not connected` for a near miss (a gap up to 1 mm, beyond
`contact_tolerance_mm`); `overlapping · N mm³` where the solids share volume, which is never
bonded. An overlap no deeper than the tolerance is an interference (a press fit, or a modelling
slip): it is listed `bonded` with `interference N mm` and closed like a gap. Read the listing
against the design: is each detected joint a real one, and is a joint you expect missing? It
judges by the 0.1 mm default; a study that should bond a wider gap sets `contact_tolerance_mm`
from the gap printed. Names can repeat (two parts called `bar`): use the ref (`frame/bar.2`) when
one does.

Each part is solved with its model's own material; `parts` gives a part the numbers the user
gives, and a part with no material in its model and none in the study is refused, naming it
([Materials](references/materials.md)). `connections` only overrides a detection (`free` for a
pair that must not be glued); touching pairs are bonded without it, and a pair set `free` inside a
group glued through other parts is refused. Fixtures and loads name faces on any part
(`post/face 23`), but not a face wholly covered by a bonded joint (refused, naming the face); a
face another part only partly covers is held or loaded on its uncovered area. Connections are
`bonded` or `free`: parts that press and slide on each other, and bolts, are not in this version.

The finer re-solve runs when the weakest part's safety factor is under 3. The summary's
`yield_MPa` and `safety_factor` are the weakest part's (`weakest_part`, `weakest_part_peak_MPa`),
while `max_von_mises_MPa` and `max_displacement_mm` span the whole assembly: the highest stress
can sit in a stronger part, so do not divide one by the other; each part's own numbers are in
`parts`. Each finding names its part ("'post' yields: ..."): fix that part (a thicker section, a
fillet, its material in `parts`, a larger joint, whose `area_mm2` is in the result's
`connections`), not the assembly in general.

## Compare variants

Each version of a design is its own document; run the same study on each into its own folder and
compare the `result.json`s. Face numbers are not stable between versions: an edit renumbers them,
and a ref reused unchecked lands on a different face with no error, so list each variant's faces
and map the baseline's by surface type, normal, centre and area, asking when two fit. Give every
study the baseline's `mesh.size_mm`, so a difference is the design's and not the mesh's, and give
the mapping (`baseline bracket/face 17 → bracket/face 21, the mounting face`) with the table so the
user can check it.

## Findings

Two von Mises peaks are reported. The **nodal** peak (`max_von_mises_MPa`, the one the safety factor
uses) is each element's stress at its integration points, extrapolated to its nodes and averaged
over the elements at a node, per part in an assembly; it is usually the higher of the two. The
**integration-point** peak (`max_von_mises_gauss_MPa`) is the raw element value; more than 50 %
above the nodal one, it means a concentration the mesh has not resolved. Safety factor = yield /
nodal peak of the solve that is written. The edge of a perfectly rigid fixture or bonded joint and
a sharp inside corner are singularities: the peak there grows with every refinement and never
converges, so the findings below say when to read the stress a little away from it instead.

Findings list errors first: an error makes the part unfit to use, a warning is a judgment to weigh
and act on or explain. Most carry the face (`bracket/face 12`, the original part's ref) when the
point is on one, and the point in mm. `peak_at_fixture` and `peak_concentration` appear only when
the safety factor is under the study's `margin` and a finer solve did not settle the peak (moved
it under 10 %); above the margin they would not change the answer.

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `yields` | error | The nodal peak is above the material's yield. | Strengthen the part where the peak is, change the material, or confirm the load; a `peak_at_fixture` or `peak_concentration` beside it comes first: the peak may be the model's, not the part's. |
| `low_margin` | warning | It holds, but under the study's `margin`. | As for `yields`, or report the margin it has; never lower `margin` to clear the finding. |
| `displacement_over_limit` | error | A `displacement` check's largest displacement (over its faces, else the whole model) is past its `limit_mm`. | Stiffen the part, or confirm the limit with the user. |
| `peak_at_fixture` | warning | The peak sits on a fixed face or its edge, where a rigid clamp exaggerates stress, and a finer solve did not settle it. | Read the stress a little away from the face (the colours, or a probe in the VTU) before redesigning; if that is still high, the finding beside it stands. |
| `peak_concentration` | warning | The integration-point peak is well above the nodal one: a sharp corner or a concentrated load the mesh cannot resolve. | Under a safety factor of 3 the run already solved finer, so refining the whole part again is not the next step: fillet the corner or spread the load over a larger face. Above 3 (a high `margin`), refine once and compare ([Mesh](references/linear-static.md#mesh)). |
| `mesh_not_converged` | warning | The automatic finer solve moved the peak by more than 10 %. In an assembly, only for a part whose safety factor is under 3. | A peak that kept rising sits on a singularity: fillet it or judge the stress away from it. Otherwise set a smaller `mesh.size_mm` before trusting the safety factor. |
| `large_displacement` | warning | It moves more than 1 % of its size: the small-displacement model is stretched. | Check the fit against mating parts, and stiffen the part if the deflection is not acceptable. |
| `not_connected` | error | A part, or a group of parts, has no bonded chain to a fixed part; the solve did not run. The message names the nearest part and its distance. | Make the parts touch, fix a face on the group, or raise `contact_tolerance_mm` when the gap is one you would call touching. |
| `overlapping_parts` | warning | Two parts' solids overlap by more than the tolerance; they are not bonded. | Fix the geometry, or mark the pair `free` in `connections` when the overlap is an accepted shortcut (that silences it). A part held only through an overlap is `not_connected`. |
| `gap_closed` | warning | Two parts a little apart, or a little into each other, within the tolerance were bonded by moving geometry that far. | Check the gap is a modelling clearance and not a real one, or the interference a slip and not a press fit whose preload matters; the stress at that joint is the model's closing, not the part's. |
| `bonded_edge_peak` | warning | The peak sits on the edge of a bonded joint, where a rigid bond exaggerates stress; two meshes agreeing proves nothing there. | Read the stress a little away from the joint; a bolted or welded joint is softer than this model. |
| `solver_note` | warning | About the run itself: a slow solve past 150 000 degrees of freedom, a finer solve skipped or failed, pictures not drawn. | Mention it when it bears on the answer. |
