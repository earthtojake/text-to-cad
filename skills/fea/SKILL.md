---
name: fea
description: Run a linear static stress study on a STEP part, or a bonded assembly of parts, with cadgen — fix faces, apply forces or pressures, choose a material — and report max von Mises stress, safety factor against yield and displacement, with a colour-mapped result the CAD Viewer shows. Use when the user asks whether a part or an assembly is strong enough, how much it deflects, where it is most stressed, or wants a "stress analysis", "FEA", "simulation" or "load case" on a part.
license: MIT
---

# FEA: linear static stress on a part or a bonded assembly

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to answer "will it hold, and by how much" for one part, or an
assembly of parts bonded where they touch, under static loads. It meshes the saved STEP with quadratic tetrahedra, solves
isotropic linear elasticity, and writes a result the Viewer renders. It is a
first-pass engineering check, not a certification: it assumes small
displacements, a linear material below yield, perfectly rigid fixtures and
loads that do not move. In an assembly every joint is also perfectly rigid
(bonded): bolts, pins and contact are not modelled yet. Say so when you report.

## Start with the task

| Task | First action | Reference |
| --- | --- | --- |
| **Check a part under a load** | List its faces, write the study, solve, report. The workflow below. | [Linear static checklist](references/linear-static.md) |
| **Check an assembly** | `cadgen fea parts` first, then write the study with a material per part, solve, read the findings by part. | [Assemblies](#assemblies) |
| **Pick the faces to fix and load** | Prefer face references the user selected in the Viewer (`part.step#o1.f17`). Otherwise list faces and match by description. | [Face selection](references/linear-static.md#choosing-faces) |
| **Write or edit a study** | One JSON object: material, fixtures, loads, mesh; for an assembly also parts and connections. | [Study file](references/study-file.md) |
| **Choose a material** | Use the table by name, or give E, ν and yield explicitly. | [Materials](references/materials.md) |
| **Judge the answer** | Compare with a hand estimate, refine once, read the peak away from the fixture. | [Validation](references/linear-static.md#judging-the-answer) |

Modelling the part itself is `$cad`; this skill only reads a saved `.step`.
Show the result GLB with `$cad` (its Show the model step), beside the STEP, so
the user sees the colour map.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/). `cadgen fea faces` and `cadgen fea parts` share
one installation with the `$cad` skill and the CAD app's server; `cadgen fea
solve` needs the `fea` extra, so it runs from its own installation, made the
first time it is needed (below):

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.17 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.17 python`

Solving needs cadgen's opt-in `fea` extra, which brings the mesher (netgen) and
the solver (scikit-fem, pyamg). `cadgen fea faces` and `cadgen fea parts` work without it. The first
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
   the one to list, `cadgen fea faces assembly.step --occurrence #o2`. For a
   whole assembly, follow [Assemblies](#assemblies) below.
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

## Assemblies

A document of several parts is solved as one assembly: the parts that touch
are bonded into one conforming mesh, each part keeps its own material, and the
result reports each part's stress against its own yield. Every part must be
joined, through bonded neighbours, to a part that is fixed.

1. **List the parts and joints first.**

   ```bash
   cadgen fea parts assembly.step
   ```

   It prints each part (ref, name, volume), then each touching pair with its
   contact area and gap and what it will be: `bonded`, or `not connected` for
   a near miss (up to 1 mm apart, beyond `contact_tolerance_mm`), or
   `overlapping · N mm³` when the solids share volume (an interference: such
   parts are never bonded). Read it against what you know of the design: is
   each detected joint a real joint, and is a joint you expect missing (a gap,
   or an overlap where the parts should touch)? `--contact-tolerance-mm` tries another tolerance; `--json`
   prints the same for scripting. Names can repeat (two parts called `bar`):
   use the ref (`#o1.2.1`) whenever a name is ambiguous.

2. **Write the study** (schema in [study-file.md](references/study-file.md)).
   `material` stays the default; give `parts` a material for each part whose
   material you know from the user or the model, by name or ref, and leave the
   rest to the default. Do not guess a material to silence a finding: the
   default is reported, and asking the user is better. Add `connections` only
   to override a detection (`free` for a pair that must not be glued, such as
   a part that only sits near another); touching pairs are bonded without it.
   Fixtures and loads name faces on any part (`#o1.4.f23`), but not a face
   that is wholly a bonded joint (a face another part only partly covers is
   fine: it holds or loads the area left uncovered).

3. **Solve** exactly as for a part. The summary leads with the weakest part
   (lowest safety factor), then lists every part's peak stress, safety factor
   and displacement. `--occurrence REF` solves one part alone through the
   single-part path instead, ignoring the study's `parts` and `connections`
   (it says so), and every face named must be on that part.

4. **Read the findings by part.** Each finding names its part ("The post
   yields: ..."). Fix the named part, not the assembly in general: a thicker
   section, a fillet, a different material in `parts`, a larger joint area
   (the joint's `area_mm2` is in the sidecar's `connections`). The Viewer's
   Study lists Parts and Connections; a part or joint the user selected there
   reaches you with its ref or refs.

Findings an assembly adds:

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `not_connected` | error | A part (or group of parts) has no bonded chain to a fixed part; the solve did not run. The message names the nearest part and its distance. | Fix the model so the parts touch, fix a face on the group, raise `contact_tolerance_mm` if the gap is within what you would call touching (it closes the gap), or set the study right: a part that is meant to be loose is not part of this model. |
| `default_material` | warning | A part got the study's default material because `parts` does not name it. | Ask the user or read the model's own material, then name it in `parts`; if the default is right, say so in the report. |
| `overlapping_parts` | warning | Two parts' solids overlap. They are not bonded, and real parts can't overlap. | Fix the geometry so they touch, or mark the pair `free` in `connections` if the overlap is an accepted modelling shortcut (it silences this). A part held only through the overlap is reported `not_connected`. |
| `gap_closed` | warning | Two parts a little apart (within the tolerance) were bonded anyway, moving geometry up to the gap. | Check the gap is a modelling clearance and not a real one the joint should have; the stress at that joint is the model's closing, not the part's. |
| `bonded_edge_peak` | warning | The peak sits on the edge of a bonded joint, where a rigid bond exaggerates stress. Appears only under the study's `margin`. | Read the stress a little away from the joint before redesigning; a bolted or welded joint is softer than this model. |

A `fixture` or `load` on a face that is wholly a joint (the foot of a post)
is refused before the solve with an error naming the face: move it to a face
that is not covered. On a face only partly covered it applies to the exposed
area alone. `bolt` and `contact`
connection types are refused ("not yet"); a pair set `free` inside a group
that is glued through other parts is refused too. When the weakest part's
safety factor is under 3 the run meshes again at half the size, as for one
part.

## What the result means

- **Nodal von Mises** is the reported peak. **Gauss-point von Mises** is the
  raw element value and is always higher; a gap of more than 50 % means a
  stress concentration the mesh has not resolved, usually at a fixed edge or
  a sharp inside corner. A finding says so when it matters.
- A clamped face is stiffer than any real bolt or weld, and the stress at its
  edge is a singularity: it grows with every refinement and never converges.
  Read the peak away from the fixture when the fixture edge is the maximum.
- Fixing a whole hole wall is stiffer than a real screw with a washer, so peaks
  at fixed holes read high.
- A sharp inside corner (a shoulder, a step) makes a peak that keeps rising as
  the mesh refines: add a fillet there rather than trusting the number.
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
when the safety factor is under the study's `margin` and the peak was not
resolved (a finer solve that moved it under 10 % settles it); above the margin
they would not change the answer.

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `yields` | error | The peak stress is above the material's yield strength. | Make the part stronger where the peak is (thicker, deeper, a fillet or rib there), choose a stronger material, or confirm the load with the user; solve again. If a `peak_at_fixture` or `peak_concentration` finding sits beside it, read that first: the peak may be the model's, not the part's. |
| `low_margin` | warning | It holds, but under the study's `margin`. | Strengthen it as for `yields`, or tell the user the margin it has and let them decide; never lower `margin` just to clear the finding. |
| `peak_at_fixture` | warning | The peak sits on a fixed face or at its edge, where a perfectly rigid clamp exaggerates stress, and a finer solve did not settle it. | Read the stress a little away from the fixed face (the GLB's colours, or a probe in the VTU) before redesigning; if that is still high, the finding beside it stands. |
| `peak_concentration` | warning | The Gauss-point peak is well above the nodal one: a sharp corner or concentrated load the mesh cannot resolve. | When the safety factor was under 3 the run already solved at half the mesh size, so refining the whole part again is not the next step: fillet the corner or spread the load over a larger face. Above 3 (a `margin` higher than that), halve `mesh.size_mm` once and compare. |
| `mesh_not_converged` | warning | The automatic finer solve moved the peak by more than 10 %. | A peak that kept rising sits on a singularity (a sharp corner, the fixed edge): fillet it or judge the stress away from it. Otherwise set a smaller `mesh.size_mm` and solve again before trusting the safety factor. |
| `large_displacement` | warning | It moves more than 1 % of its size. | The small-displacement model is stretched: check the fit against mating parts and whether the deflection is acceptable; stiffen the part if not. |
| `no_load` | warning | The peak stress is zero: no load reaches the part. | Check that the loaded faces are on the part and connected to the fixed ones, and that the force is not zero. |

A `warning:` line that is not a finding (a slow solve, reactions that do not
balance, a finer solve that failed) is about the run itself: read it, and
mention it when it bears on the answer.
