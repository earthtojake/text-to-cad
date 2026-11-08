---
name: fea
description: Run a linear elastic stress study on a STEP part, a model or an assembly of bonded parts with text-to-cad, meshed by netgen and solved by CalculiX, reporting peak stress, safety factor and displacement as a colour map. Use when the user asks whether a part is strong enough, how much it bends, where it is most stressed, or asks for FEA or a stress simulation of a part.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# FEA: simulate a part or an assembly

Use this skill to answer "will it hold, and how far does it move" for one part, or an assembly of
parts bonded where they touch, by simulation. It meshes the part with netgen, has CalculiX
solve it, and writes its results into a folder you choose: every number as JSON, a picture of the
stress and of the displacement, a coloured GLB any viewer opens, and the fields as a VTU. [linear-static.md](references/linear-static.md)
holds the model's assumptions, hand checks and limits; [study-file.md](references/study-file.md)
holds every key of the study.

It answers one kind of question: linear elastic stress and displacement under forces, pressures,
the part's own weight (`gravity`) and a steady acceleration (`acceleration`), on quadratic
tetrahedra with an isotropic material. It is a first-pass engineering check, not a certification:
small displacements, a linear material below yield, perfectly rigid fixtures (a `fixed` face held
still, a `roller` face free to slide in its plane but not off it) and loads that do not move. In an
assembly every joint is perfectly rigid (bonded) unless the study sets a pair `free`. Say so when
you report.

## What it answers

| The user asks | The study | Reference |
| --- | --- | --- |
| "Will it hold", "is it strong enough", "how much does it bend", "where is it most stressed" | fixtures and face loads | [Linear static](references/linear-static.md) |
| The same under its own weight, or while it speeds up, brakes or turns (a steady g-load) | a `gravity` or `acceleration` load | [Body loads](references/linear-static.md#body-loads-gravity-and-acceleration) |

### When the question needs an analysis that is not here

Vibration, buckling, heat, flow, fatigue, impact, contact and the rest are not in this version.

- Tell the user plainly, in their words: "That is not in this version." Do not write a study for it.
- Do not pass a static result off as the answer. A static safety factor says nothing about
  resonance, buckling, temperature, fatigue life, flow or parts sliding on each other.
- Offer a static study only where it honestly answers part of the question, and say which part:
  - **Its own weight, or a steady g-load** (a vehicle braking, a part on a spinning arm at a known
    g): that is `static` already.
  - **A drop, as an estimate.** Hold the faces that hit the floor `fixed` and add an
    `acceleration` load of G g pointing away from the floor (opposite those faces' outward normal),
    with G = drop height / stopping distance (1000 mm stopping in 2 mm is 500 g). Report it as an
    estimate of an equivalent steady load, never as an impact simulation, and say what stopping
    distance you assumed.
- When the user wants a number now and no static study fits, a hand estimate, labelled as one, is
  better than nothing. Work in the study's units (mm, N, MPa, t/mm³), where these come out directly:
  - Buckling of a column (Euler): P = π² E I / (K L)², with K = 2 for one end fixed and one free, 1
    for both ends pinned, 0.5 for both ends fixed.
  - First natural frequency of a cantilever: f = 0.560 √(E I / (ρ A L⁴)) Hz.

## Start with the task

| Task | First action | Reference |
| --- | --- | --- |
| **Check a part under a load** | List its faces, write the study, solve, report. The workflow below. | [Linear static checklist](references/linear-static.md) |
| **Check an assembly** | `cad step solve assembly.step` (the setup) first, then write the study with a material per part, solve, read the findings by part. | [Assemblies](#assemblies) |
| **Compare variants of a design** | Get the study right on one variant, then map its faces onto each other variant and solve each. | [Compare variants](#compare-variants) |
| **Pick the faces to fix and load** | Prefer face references the user selected in the Viewer (`/work/bracket.step#bracket/face 17`). Otherwise list faces and match by description. | [Face selection](references/linear-static.md#choosing-faces) |
| **Write or edit a study** | One JSON object: material, fixtures, loads, mesh; for an assembly also parts and connections. | [Study file](references/study-file.md) |
| **Choose a material** | The model's own (solve its `.xbf`), or E, ν and yield the user gives. | [Materials](references/materials.md) |
| **Judge the answer** | Compare with a hand estimate, read the peak away from the fixture, refine if it matters. | [Validation](references/linear-static.md#judging-the-answer) |

This skill studies a part, it does not model one: build or fix the model first. It reads a saved
`.step` or `.xbf` (a model's `@step` or `@xbf` output), or a model the engine holds by its document id
(`cad model solve <id>`).

## Setup

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor
--check` explains any other failure, changing nothing; `cad doctor` repairs what it reports.

A study is an operation of the document's type, `solve`: `cad step solve` for a `.step`, `cad xbf
solve` for an `.xbf`, `cad model solve` for a model the engine holds. With no `--study` it lists the
study's setup; with one it solves and writes its results into the folder `--out` names. Both
tools a solve needs are integrations the `cad` command installs, with the CAD kernel the study reads the
part with, the first time a study needs them (nothing for you to install), and `cad run` gives a script
that calls `cad.step.solve` their environment when its header names them:

- **netgen**, which meshes, is the `netgen` integration (`cad[netgen]`, about 10 MB). netgen publishes
  it for macOS, Linux x86_64 and Windows x86_64 alone; anywhere else (Linux on ARM among them) a solve
  refuses, naming the platform.
- **CalculiX** (`ccx`), which solves, is the `calculix` integration (`cad[calculix]`: the ccx package,
  CalculiX's own program for each platform, about 10 MB). A person's own CalculiX is never run unless
  `CAD_CCX` names it (the file itself, named `ccx` or `ccx_2.2x`, 2.20 or newer). It runs headless, on
  one thread, in a private folder, and every result names the CalculiX version that solved it.
  `cad run ccx ARGS` runs that same `ccx` on a deck of your own.

A study of a file reads it in its own process, so it needs no model built; a model's is written to an
`.xbf` the study reads.

Units are fixed: mm for geometry, N for forces, MPa for pressure, modulus and stress, t/mm³ for
density, and g (9.81 m/s²) for gravity and acceleration. Restate every load in those units before
you write it down ([study-file.md](references/study-file.md#units)).

## Workflow

1. **List the faces.** Every study names faces by the engine's refs, the ones the Viewer copies.

   ```bash
   cad step solve part.step
   ```

   With no study it is the study's setup, and writes nothing: the parts, the pairs that touch, and
   then each face of the part, one a line: ref, area, centre, surface type and a hint such as `plane,
   normal -Z, largest`. Use the hint and the centre to match the user's words ("the mounting face",
   "the top of the upright") to a ref. A document with several parts lists no faces and says how;
   name the part to list, `cad step solve assembly.step --occurrence post`, or for a whole assembly
   follow [Assemblies](#assemblies). When two faces fit equally, ask, quoting both refs. A face
   the user selected in the Viewer arrives as `/work/bracket.step#bracket/face 17` and needs no lookup.

2. **Write the study** as `study.json` beside the part (schema in
   [study-file.md](references/study-file.md)):

   ```json
   {
     "fixtures": [{"faces": ["bracket/face 17"], "type": "fixed"}],
     "loads": [{"faces": ["bracket/face 22"], "type": "force", "vector_N": [0, -500, 0]}]
   }
   ```

   A fixture is `fixed` (held still) or `roller` (slides in its plane, never off it: a
   frictionless support, or a symmetry plane cut through the part;
   [fixtures](references/study-file.md#fixtures)). A `force` is the total force over its faces; a
   `pressure` is in MPa and pushes into the surface. Add `{"type": "gravity", "vector_g": [0, 0,
   -1]}` when the part's own weight matters (a long arm, a heavy casting), and `{"type":
   "acceleration", "vector_g": [5, 0, 0]}` when the part is speeding up, braking or turning at a
   known g; neither names faces, and both need the material's density ([Body
   loads](references/linear-static.md#body-loads-gravity-and-acceleration)). Leave `mesh` out on the first run ([Mesh](references/linear-static.md#mesh)).
   `margin` is the safety factor the part should keep (default 2, at least 1): higher for a
   polymer, a fatigue load or a part that must not fail.

   Add `checks` only for what the user asked ([checks](references/study-file.md#checks)):
   `stress` for "will it break", a `displacement` check with their limit for a sag or stiffness
   spec. Without them the verdict is the stress check alone.

3. **Solve.**

   ```bash
   cad step solve part.step --study study.json --out /tmp/bracket-load --json
   ```

   `--out` is a folder, any you like (a temporary one is fine; put it in the project when the user
   should keep the files), made when missing. One folder per study: a solve replaces its own files
   there and touches nothing else. It holds:

   | File | What it is for |
   | --- | --- |
   | `result.json` | the answer: what `--json` prints. Read this first. |
   | `stress.png`, `displacement.png` | the deformed part coloured by each field (blue low, red high, the deformation exaggerated by `deformation_scale`), a colour bar under it giving the field, its units and its range. Look at them: they show at a glance whether the load points the way you meant and which faces are held. Show the stress one to the user. |
   | `result.glb` | the same coloured part, for any glTF viewer or `cad viewer` |
   | `result.vtu` | the volume mesh with `displacement` (mm) and `von_mises` (MPa) at its corner nodes, for a question the summary does not answer ([Your own questions](#your-own-questions)) |
   | `ccx.inp` | with `--deck`: the input CalculiX solved (the finer solve's when there were two), to read or run again with `cad run ccx -i ccx` in that folder |

   Where the engine cannot draw (a Linux machine with no display), the pictures are left out and a
   `solver_note` says so; everything else is written.

   `--json` prints the result as one JSON line, a check's shape: `ok`, `findings` (each with its
   `severity`, `code`, `message`, `location` and `hint`), and `measurements`, every number -- the study
   as given, the material, the faces it named (`named_faces`), each fixture's reaction, the mesh and the
   timings -- with `written`, the files the solve wrote. Without it the same result prints as lines.

   When the safety factor comes out under 3 the run meshes again finer (half the element size,
   less on a big model) and solves again, by itself, and reports the finer result
   ([Mesh](references/linear-static.md#mesh)).
   Progress lines (`[fea] reading the parts`, `[fea]
   meshing the glued shape at 6.01 mm`) print to stderr, never into the result on stdout;
   `--verbose` adds mesh and solve detail there. A study with no fixture, a face that is not on the
   part, an unknown key, an out-of-range ref, a zero load or a load on a held face is refused with a
   message naming the field. The folder's files are replaced only once every one is written: a run
   that fails leaves the previous results as they were.

   The command exits 1 (`"ok": false`) when a finding is an error, as a validator does: the part
   yields or misses a check, and the result is written all the same so the user sees where; or the
   study stopped before the solve (`not_connected`), with nothing written. Warnings leave it at 0. Read the
   result either way.

4. **Read the findings.** Every solve prints them after the numbers, one line each, `error:` or
   `warning:`, the finding's code and where, then what is wrong and, after `Hint:`, why (`findings`
   in `--json`). Read
   them before reporting; see [Read the findings](#read-the-findings).

5. **Report**, in this order, with units: max von Mises (MPa) and where (`max_von_mises_at_mm`;
   say which feature it is near); the safety factor against yield and the yield used; max
   displacement (mm) and where; the applied load and the reaction (they balance: a solve where they
   do not is refused);
   the mesh size, element count and whether a finer re-solve ran. Then say in a sentence or two
   what the model assumes and what would change the answer most (a softer fixture, a fillet at the
   peak, a different material). Show the user `stress.png` (or open `result.glb` with `cad viewer`);
   the deformation is exaggerated by the summary's `deformation_scale`, so say that too.

## Your own questions

The summary answers the usual ones. For anything else (the stress at the mounting holes, the sag
along an edge, how much of the part is above some stress), read `result.vtu` with a few lines of
Python rather than solving again. meshio or PyVista read it as it is (`uv run --with meshio`):

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
assembly's elements carry their part (`part`, the index into the summary's `parts`).

## Assemblies

A document of several parts is solved as one assembly: the parts that touch are bonded into one
conforming mesh, each part keeps its own material, and the result reports each part's stress
against its own yield. Every part must be joined, through bonded neighbours, to a part that is
fixed. The keys are in [study-file.md](references/study-file.md#assemblies).

1. **List the parts and joints first.**

   ```bash
   cad step solve assembly.step
   ```

   The setup prints each part (ref, name, volume), then each touching pair with its contact area and gap
   and what it will be: `bonded`, or `not connected` for a near miss (up to 1 mm apart, beyond
   `contact_tolerance_mm`), or `overlapping · N mm³` when the solids share volume (such parts are
   never bonded). An overlap no thicker than `contact_tolerance_mm` (a thin layer, where a face
   sits a little into another; a corner sunk in on every axis is a lump, measured by its full
   depth) is an interference instead (a press fit, or a modelling slip): it is listed `bonded` with
   `interference N mm`, and the solve closes it like a gap. The header counts touching pairs apart
   from near misses and overlaps. Read it against what you know of the design: is each detected
   joint a real joint, and is a joint you expect missing (a gap, or an overlap where the parts
   should touch)? The listing judges by the 0.1 mm default; a study that should bond a wider gap
   sets its own `contact_tolerance_mm`, from the gap printed. `--json` prints the same for
   scripting. Names can repeat (two parts called `bar`): use the ref (`frame/bar.2`) whenever a name is
   ambiguous.

2. **Write the study.** Each part is solved with its model's own material; give `parts` numbers
   only for a part whose numbers the user gives (by name or ref). A part with no material in its
   model and none in the study is refused, naming it: ask the user what it is made of and set it in
   the model, never pick one to make the study run. Add `connections` only to override a detection (`free` for a pair that must not be
   glued, such as a part that only sits near another); touching pairs are bonded without it. Fixtures and loads name faces on any part
   (`post/face 23`), but not a face that is wholly a bonded joint (refused before the solve, naming the
   face: move it to a face that is not covered); on a face another part only partly covers they apply to the uncovered area alone.

3. **Solve** exactly as for a part; the finer re-solve runs when the weakest part's safety factor
   is under 3. The summary leads with the weakest part (lowest safety factor), then lists every
   part's peak stress, safety factor and displacement. To study one part alone, solve that part's
   own model: export it (or write it) as a document of its own, and give it its own study.

4. **Read the findings by part.** Each finding names its part ("'post' yields: ..."). Fix the named
   part, not the assembly in general: a thicker section, a fillet, a different material in `parts`,
   a larger joint area (the joint's `area_mm2` is in the result's `connections`).

Findings an assembly adds:

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `not_connected` | error | A part (or group of parts) has no bonded chain to a fixed part; the solve did not run. The message names the nearest part and its distance. | Fix the model so the parts touch, fix a face on the group, raise `contact_tolerance_mm` if the gap is within what you would call touching (it closes the gap), or set the study right: a part that is meant to be loose is not part of this model. |
| `overlapping_parts` | warning | Two parts' solids overlap. They are not bonded, and real parts can't overlap. | Fix the geometry so they touch, or mark the pair `free` in `connections` if the overlap is an accepted modelling shortcut (it silences this). A part held only through the overlap is reported `not_connected`. |
| `gap_closed` | warning | Two parts a little apart, or a little into each other (an interference), within the tolerance were bonded anyway, moving geometry up to that far. | Check the gap is a modelling clearance and not a real one the joint should have, or that the interference is a slip and not a press fit whose preload matters; the stress at that joint is the model's closing, not the part's. |
| `bonded_edge_peak` | warning | The peak sits on the edge of a bonded joint, where a rigid bond exaggerates stress. Appears wherever the part misses the study's `margin`, even when a finer mesh agreed: a rigid bond's edge is singular, so two meshes agreeing proves nothing there. | Read the stress a little away from the joint before redesigning; a bolted or welded joint is softer than this model. |

Parts that press and slide on each other and bolted joints are not in this version: a connection
is `bonded` or `free`. A pair set `free` inside a group that is glued through other parts is
refused too.

## Compare variants

When the user wants one question answered for several versions of a design (a thicker wall, a
longer arm, another material), each version is its own STEP: one model per
configuration. Run the same study on each, with the faces mapped, and compare.

1. **Get the study right on one variant first** (the baseline): the full [Workflow](#workflow),
   solved and checked.
2. **Map its faces onto every other variant.** Face numbers are not stable between versions: an
   edit renumbers faces, and a ref reused unchecked can land on a different face with no
   error. Run `cad step solve variant.step` and match each face the study names by what it is,
   never by its number: the same surface type and normal, a centre where the edit would move it,
   an area that changed only as the edit explains. When two faces fit equally, or the edit removed
   the face, ask, quoting the candidates. Write one study per variant (`study.<variant>.json`):
   the mapped refs, everything else identical.
3. **Hold the mesh still.** Accuracy follows the mesh, so a difference between variants is only
   the design's when they are meshed alike: give every study the baseline's `mesh.size_mm`.
4. **Solve each into its own folder:** `cad step solve variant.step --study study.<variant>.json --out
   /tmp/fea/variant`, and read each `result.json`.
5. **Report one table**, a row per variant: max von Mises and where, safety factor, max
   displacement, whether a finer re-solve ran, and the face mapping used (`baseline bracket/face 17
   → bracket/face 21, the mounting face`) so the user can check it. Say which variant answers their
   question best, and by how much.

## What the result means

- **Nodal von Mises** is the reported peak: each element's stress at its integration points,
  extrapolated to its nodes and averaged over the elements at a node (in an assembly, over each
  part's own elements, so stress jumps across a change of material). It is usually the higher of
  the two maxima. **Integration-point von Mises** (`max_von_mises_gauss_MPa`) is the raw element
  value before that. When the integration-point peak stands more than 50 % above the nodal one, the
  mesh has not resolved a concentration, usually at a fixed edge or a sharp inside corner; a
  finding says so when it matters.
- A clamped face is stiffer than any real bolt or weld, and the stress at its edge is a
  singularity: it grows with every refinement and never converges. Read the peak away from the
  fixture when the fixture edge is the maximum; peaks at fixed holes read high too. A sharp inside
  corner (a shoulder, a step) makes a peak that keeps rising as the mesh refines: add a fillet
  there rather than trusting the number.
- Safety factor = yield / max nodal von Mises of the solve that is written (the finer one when the
  run solved twice). Below 1 the part yields in this model; under the study's `margin` (default 2)
  is marginal for a first pass; above it is a comfortable first answer for a static load on a
  ductile metal. Polymers and fatigue need more margin than that. Do not certify a design from one
  run.
- Displacement is what the part moves, before any scale. The result's positions carry
  `deformation_scale` times that; the result has the true number.
- In an assembly the summary's `yield_MPa` and `safety_factor` are the weakest part's, while the
  `max_*` peaks are the whole assembly's, wherever they fall: do not divide one by the other
  ([What comes out](references/study-file.md#what-comes-out)).

## Read the findings

Every solve checks its own result as an engineer would and lists findings, errors first. An
**error** makes the part unfit to use: fix it before you call the part done. A **warning** is a
suggestion: weigh it as an engineer would, act on it or tell the user why not. A clean part has no
findings. Most findings point at where they apply: the face (`bracket/face 12`, the original part's
ref) when the point is on one, and the point in the part's mm. A peak inside the part and
`large_displacement` have a point but no face.

The two peak findings, `peak_at_fixture` and `peak_concentration`, appear only when the safety
factor is under the study's `margin` and the peak was not resolved (a finer solve that moved it
under 10 % settles it); above the margin they would not change the answer.

| Finding | Severity | What it means | What to do |
| --- | --- | --- | --- |
| `yields` | error | The peak stress is above the material's yield strength. | Make the part stronger where the peak is (thicker, deeper, a fillet or rib there), choose a stronger material, or confirm the load with the user; solve again. If a `peak_at_fixture` or `peak_concentration` finding sits beside it, read that first: the peak may be the model's, not the part's. |
| `low_margin` | warning | It holds, but under the study's `margin`. | Strengthen it as for `yields`, or tell the user the margin it has and let them decide; never lower `margin` just to clear the finding. |
| `peak_at_fixture` | warning | The peak sits on a fixed face or at its edge, where a perfectly rigid clamp exaggerates stress, and a finer solve did not settle it. | Read the stress a little away from the fixed face (the result's colours, or a probe in the VTU) before redesigning; if that is still high, the finding beside it stands. |
| `peak_concentration` | warning | The integration-point peak is well above the nodal one: a sharp corner or concentrated load the mesh cannot resolve. | When the safety factor was under 3 the run already solved finer, so refining the whole part again is not the next step: fillet the corner or spread the load over a larger face. Above 3 (a `margin` higher than that), refine once and compare: halve `mesh.size_mm`, or at a fillet or hole set it to a third of the radius (see [Mesh](references/linear-static.md#mesh)). |
| `mesh_not_converged` | warning | The automatic finer solve moved the peak by more than 10 %. In an assembly, only for a part whose safety factor is under 3: a part far from failing is not worth distrusting. | A peak that kept rising sits on a singularity (a sharp corner, the fixed edge): fillet it or judge the stress away from it. Otherwise set a smaller `mesh.size_mm` and solve again before trusting the safety factor. |
| `large_displacement` | warning | It moves more than 1 % of its size. | The small-displacement model is stretched: check the fit against mating parts and whether the deflection is acceptable; stiffen the part if not. |

A `solver_note` warning (a slow solve past 150 000 degrees of freedom, a finer solve that was
skipped or failed) is about the run itself: read it, and mention it when it bears on
the answer.
