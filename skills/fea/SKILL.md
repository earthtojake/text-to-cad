---
name: fea
description: Run a linear static stress study on a STEP part with cadgen — fix faces, apply forces or pressures, choose a material — and report max von Mises stress, safety factor against yield and displacement, with a colour-mapped result the CAD Viewer shows. Use when the user asks whether a part is strong enough, how much it deflects, where it is most stressed, or wants a "stress analysis", "FEA", "simulation" or "load case" on a part.
license: MIT
---

# FEA: linear static stress on a part

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

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
Show the result GLB with `$cad` (its Show the model step), beside the STEP, so
the user sees the colour map.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/). `cadgen fea faces` shares
one installation with the `$cad` skill and the CAD app's server; `cadgen fea
solve` needs the `fea` extra, so it runs from its own installation, made the
first time it is needed (below):

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.17 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.17 python`

Solving needs cadgen's opt-in `fea` extra, which brings the mesher (netgen) and
the solver (scikit-fem, pyamg). `cadgen fea faces` works without it. The first
time a study runs, `cadgen fea solve` fails with "cadgen's fea extra is not
installed"; that is a missing install, not a modelling error. Its `pip install`
hint does not apply under uv: run the same command again with the extra in the
requirement, and keep using that form for `fea solve` from then on:

```bash
uvx --no-config --managed-python --python 3.13 --from "cadgen[fea]==0.7.17" cadgen fea solve part.step --study study.json
```

The first run downloads the mesher and solver (large); later runs reuse them.

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
   A document with several parts refuses with the occurrences it holds; pass
   the one to study, `cadgen fea faces assembly.step --occurrence #o2`, and
   every face the study names must be on that part.
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
   element size is a fortieth of the part's bounding diagonal. `margin` is
   the safety factor the part should keep (default 2, at least 1): set it
   higher for a polymer, a fatigue load or a part that must not fail, lower
   only when the user says the load is known exactly.

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

   When the safety factor comes out under 3 the run meshes again at half the
   element size and solves again, by itself; the finer result is the one
   written and reported, and the sidecar's `refined` block records both
   sizes and peaks. The finer size is capped to keep the solve under the
   degrees-of-freedom budget, so a part near the limit takes longer (minutes)
   and may get a smaller refinement than half. `--vtu` adds a ParaView file. `--json` prints the result as one JSON line
   for scripting. `--verbose` shows mesh and solve progress on stderr. A study
   with no fixture, a face that is not on the part, or an out-of-range
   selector is refused with a message naming the field.

4. **Read the findings.** Every solve prints them after the numbers, one
   line each, `error:` or `warning:` and then what is wrong and what to do
   (`findings` in `--json` and the sidecar). Read them before reporting; see
   [Read the findings](#read-the-findings).

5. **Report.** Quote, in this order: max von Mises (MPa) and where it is,
   safety factor against yield, max displacement (mm) and where, the applied
   load and the reaction (they balance, or the run warns), the mesh size and
   element count. Then say what the model assumes. Open the GLB in the Viewer
   for the user; the deformation is exaggerated by the `deformation_scale`
   the sidecar records, so say that too.

## What the result means

- **Nodal von Mises** is the reported peak. **Gauss-point von Mises** is the
  raw element value and is always higher; a gap of more than 50 % means a
  stress concentration the mesh has not resolved, usually at a fixed edge or
  a sharp inside corner. A finding says so when it matters.
- A clamped face is stiffer than any real bolt or weld, and the stress at its
  edge is a singularity: it grows with every refinement and never converges.
  Read the peak away from the fixture when the fixture edge is the maximum.
- Safety factor = yield / max nodal von Mises of the solve that is written (the
  finer one when the run solved twice). Below 1 the part yields in
  this model; under the study's `margin` (default 2) is marginal for a first
  pass; above it is a comfortable first answer for a static load on a ductile
  metal. Polymers and fatigue need more margin than that. Do not certify a
  design from one run.
- Displacement is what the part moves, before any scale. The GLB positions
  carry `deformation_scale` times that; the sidecar has the true number.

## Read the findings

Every solve checks its own result as an engineer would and lists findings,
errors first. An **error** makes the part unfit to use: fix it before you call
the part done. A **warning** is a suggestion: weigh it as an engineer would,
act on it or tell the user why not. A clean part has no findings. Most
findings point at where they apply: the face (`#o1.f12`, the original part's
selector) when the point is on one, and the point in the part's mm. A peak
inside the part and `large_displacement` have a point but no face; `no_load`
has neither.

The two peak findings, `peak_at_fixture` and `peak_concentration`, appear only
when the safety factor is under the study's `margin`; above it they would not
change the answer.

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `yields` | error | The peak stress is above the material's yield strength. | Make the part stronger where the peak is (thicker, deeper, a fillet or rib there), choose a stronger material, or confirm the load with the user; solve again. If a `peak_at_fixture` or `peak_concentration` finding sits beside it, read that first: the peak may be the model's, not the part's. |
| `low_margin` | warning | It holds, but under the study's `margin`. | Strengthen it as for `yields`, or tell the user the margin it has and let them decide; never lower `margin` just to clear the finding. |
| `peak_at_fixture` | warning | The peak sits on a fixed face, where a perfectly rigid clamp exaggerates stress. | Read the stress a little away from the fixed face (the GLB's colours, or a probe in the VTU) before redesigning; if that is still high, the finding beside it stands. |
| `peak_concentration` | warning | The Gauss-point peak is well above the nodal one: a sharp corner or concentrated load the mesh cannot resolve. | When the safety factor was under 3 the run already solved at half the mesh size, so refining the whole part again is not the next step: fillet the corner or spread the load over a larger face. Above 3 (a `margin` higher than that), halve `mesh.size_mm` once and compare. |
| `mesh_not_converged` | warning | The automatic finer solve moved the peak by more than 10 %. | A peak that kept rising sits on a singularity (a sharp corner, the fixed edge): fillet it or judge the stress away from it. Otherwise set a smaller `mesh.size_mm` and solve again before trusting the safety factor. |
| `large_displacement` | warning | It moves more than 1 % of its size. | The small-displacement model is stretched: check the fit against mating parts and whether the deflection is acceptable; stiffen the part if not. |
| `no_load` | warning | The peak stress is zero: no load reaches the part. | Check that the loaded faces are on the part and connected to the fixed ones, and that the force is not zero. |

A `warning:` line that is not a finding (a slow solve, reactions that do not
balance, a finer solve that failed) is about the run itself: read it, and
mention it when it bears on the answer.
