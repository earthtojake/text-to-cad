---
name: fea
description: Run a linear static stress study on a STEP part with cadgen — fix faces, apply forces or pressures, choose a material — and report max von Mises stress, safety factor against yield and displacement, with a colour-mapped result the CAD Viewer shows. Use when the user asks whether a part is strong enough, how much it deflects, where it is most stressed, or wants a "stress analysis", "FEA", "simulation" or "load case" on a part.
---

# FEA: linear static stress on a part

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

Use this skill to answer "will it hold, and by how much" for one part under
static loads. It meshes the saved STEP with quadratic tetrahedra, solves
isotropic linear elasticity, and writes a result the Viewer renders. It is a
first-pass engineering check, not a certification: it assumes small
displacements, a linear material below yield, perfectly rigid fixtures and
loads that do not move. Say so when you report.

## Start with the task

| Task | First action | Reference |
| --- | --- | --- |
| **Check a part under a load** | List its faces, write the study, solve, report. The workflow below. | [Linear static checklist](references/linear-static.md) |
| **Pick the faces to fix and load** | Prefer face references the user selected in the Viewer (`part.step#o1.f17`). Otherwise list faces and match by description. | [Face selection](references/linear-static.md#choosing-faces) |
| **Write or edit a study** | One JSON object: material, fixtures, loads, mesh. | [Study file](references/study-file.md) |
| **Choose a material** | Use the table by name, or give E, ν and yield explicitly. | [Materials](references/materials.md) |
| **Judge the answer** | Compare with a hand estimate, refine once, read the peak away from the fixture. | [Validation](references/linear-static.md#judging-the-answer) |

Modelling the part itself is `$cad`; this skill only reads a saved `.step`.
Hand the result GLB to `$cad-viewer` when it is installed: open the `.glb`
beside the STEP so the user sees the colour map.

## Setup

`requirements.txt` pins `cadgen[fea]`; install it in the project environment
before the first run. The `fea` extra brings the mesher (netgen) and the solver
(scikit-fem, pyamg). A run that fails with "cadgen's fea extra is not
installed" is that missing install, not a modelling error.

Units are fixed: mm for geometry, N for forces, MPa for pressure, modulus and
stress. Restate every load in those units before you write it down.

## Workflow

1. **List the faces.** Every study names faces by the Viewer's selector.

   ```bash
   cadgen fea faces part.step
   ```

   Each line is one face: selector, area, centre, surface type and a hint such
   as `plane, normal -Z, largest`. Use the hint and the centre to match the
   user's words ("the mounting face", "the top of the upright") to a selector.
   When two faces fit equally, ask, quoting both selectors. A face the user
   selected in the Viewer arrives as `part.step#o1.f17` and needs no lookup.

2. **Write the study** as `study.json` beside the part (schema in
   [study-file.md](references/study-file.md)):

   ```json
   {
     "material": "aluminum-6061-t6",
     "fixtures": [{"faces": ["#o1.f17"], "type": "fixed"}],
     "loads": [{"faces": ["#o1.f22"], "type": "force", "vector_N": [0, -500, 0]}]
   }
   ```

   A `force` is the total force over its faces; a `pressure` is in MPa and
   pushes into the surface. Leave `mesh` out on the first run; the default
   element size is a fortieth of the part's bounding diagonal.

3. **Solve.**

   ```bash
   cadgen fea solve part.step --study study.json
   ```

   This writes `part.fea.glb` (the colour map on the deformed shape) and
   `part.fea.json` (every number, the study, the mesh and timings) beside the
   part. Name the outputs to keep several studies:

   ```bash
   cadgen fea solve part.step FEA/part.bracket-load.glb --study study.json --vtu
   ```

   `--vtu` adds a ParaView file. `--json` prints the result as one JSON line
   for scripting. `--verbose` shows mesh and solve progress on stderr. A study
   with no fixture, a face that is not on the part, or an out-of-range
   selector is refused with a message naming the field.

4. **Report.** Quote, in this order: max von Mises (MPa) and where it is,
   safety factor against yield, max displacement (mm) and where, the applied
   load and the reaction (they balance, or the run warns), the mesh size and
   element count. Then say what the model assumes. Open the GLB in the Viewer
   for the user; the deformation is exaggerated by the `deformation_scale`
   the sidecar records, so say that too.

## What the result means

- **Nodal von Mises** is the reported peak. **Gauss-point von Mises** is the
  raw element value and is always higher; a gap of more than 50 % means a
  stress concentration the mesh has not resolved, usually at a fixed edge or
  a sharp inside corner. The run warns when that happens.
- A clamped face is stiffer than any real bolt or weld, and the stress at its
  edge is a singularity: it grows with every refinement and never converges.
  Read the peak away from the fixture when the fixture edge is the maximum.
- Safety factor = yield / max nodal von Mises. Below 1 the part yields in
  this model; 1 to 2 is marginal for a first pass; above 2 is a comfortable
  first answer for a static load on a ductile metal. Polymers and fatigue
  need more margin than that. Do not certify a design from one run.
- Displacement is what the part moves, before any scale. The GLB positions
  carry `deformation_scale` times that; the sidecar has the true number.
