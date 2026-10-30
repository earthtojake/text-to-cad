---
name: fea
description: Run a linear elastic stress study on a STEP part or an assembly of bonded parts with cadgen, meshed by netgen and solved by CalculiX, reporting peak stress, safety factor and displacement as a colour map. Use when the user asks whether a part is strong enough, how much it bends, where it is most stressed, or asks for FEA or a stress simulation of a part.
license: MIT
---

# FEA: simulate a part or an assembly

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the repository link is only for
provenance and release review.

Use this skill to answer "will it hold, and how far does it move" for one part, or an assembly of
parts bonded where they touch, by simulation. It meshes the saved STEP with netgen, has CalculiX
solve it, and writes a colour-mapped result the Viewer renders. [linear-static.md](references/linear-static.md)
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
| **Check an assembly** | `cadgen fea parts` first, then write the study with a material per part, solve, read the findings by part. | [Assemblies](#assemblies) |
| **Compare variants of a design** | Get the study right on one variant, then map its faces onto each other variant and solve each. | [Compare variants](#compare-variants) |
| **Pick the faces to fix and load** | Prefer face references the user selected in the Viewer (`/work/bracket.step#bracket/face 17`). Otherwise list faces and match by description. | [Face selection](references/linear-static.md#choosing-faces) |
| **Write or edit a study** | One JSON object: material, fixtures, loads, mesh; for an assembly also parts and connections. | [Study file](references/study-file.md) |
| **Choose a material** | The model's own (solve its `.xbf`), or E, ν and yield the user gives. | [Materials](references/materials.md) |
| **Judge the answer** | Compare with a hand estimate, read the peak away from the fixture, refine if it matters. | [Validation](references/linear-static.md#judging-the-answer) |

Modelling the part itself is `$cad`; this skill only reads a saved `.step` or `.xbf` (a model's
`@step` or `@xbf` output, or `cadgen export <id> part.step`). Show the result GLB with
`$cad` (its Show the model step), beside the STEP, so the user sees the colour map.

## Setup

Run cadgen through the `cadgen` command its installation writes, as the `$cad` skill does:
`cadgen fea faces`, `parts` and `solve` share one installation with it and with the CAD app's
server:

- `cadgen` below means `cadgen +0.8.3` (`~/.local/bin/cadgen +0.8.3` where `~/.local/bin` is not on your PATH)
- `python` below means `cadgen +0.8.3 run`

If `cadgen` is not on your PATH, or it says 0.8.3 is not installed, run
`uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command and starts the engine. With the CAD app's server running, nothing else
needs the sandbox's permission: it starts the engine and holds it. Without it, a sandboxed
shell cannot start the engine; when a command says no engine is running, run `cadgen server`
outside the sandbox once.

Solving needs one thing `fea faces` and `fea parts` do not; netgen, which meshes, comes with cadgen
on macOS, Linux x86_64 and Windows x86_64, where netgen publishes wheels (anywhere else, Linux on ARM
among them, `fea solve` refuses, naming the platform). A solve reads the document in its own
process, so it needs no engine running:

- **The solver.** CalculiX (`ccx`) 2.20 or newer, installed by the person: `conda install -c
  conda-forge calculix`, the `calculix-ccx` package on Debian and Ubuntu, or FreeCAD 1.0 or newer
  on macOS or Windows, which carries one. cadgen runs `CADGEN_CCX` when it is set
  (`CADGEN_CCX=/path/to/ccx`), else the first `ccx` (or `ccx_2.2x`) on PATH, else the one inside
  FreeCAD where its installer puts it. A missing
  or older one stops the solve with an error that says how to install it. cadgen downloads nothing
  and has no other solver: ask the user to install CalculiX, or install it yourself with their
  permission, then run the study again. Every result names the CalculiX version that solved it.

Units are fixed: mm for geometry, N for forces, MPa for pressure, modulus and stress, t/mm³ for
density, and g (9.81 m/s²) for gravity and acceleration. Restate every load in those units before
you write it down ([study-file.md](references/study-file.md#units)).

## Workflow

1. **List the faces.** Every study names faces by the engine's refs, the ones the Viewer copies.

   ```bash
   cadgen fea faces part.step
   ```

   Each line is one face: ref, area, centre, surface type and a hint such as `plane, normal -Z,
   largest`. Use the hint and the centre to match the user's words ("the mounting face", "the top of
   the upright") to a ref. A document with several parts refuses with the parts it holds;
   pass the one to list, `cadgen fea faces assembly.step --occurrence post`, or for a whole assembly
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
   cadgen fea solve part.step FEA/part.bracket-load.glb --study study.json --json
   ```

   This writes the GLB it names (the colour map on the deformed shape), and nothing else: one per
   study, so name each for its study. `--json` prints the result as one JSON line: every number,
   the study as given, the material, the faces it named, each fixture's reaction, the mesh and the
   timings. Without it the same result prints as lines.

   When the safety factor comes out under 3 the run meshes again finer (half the element size,
   less on a big model) and solves again, by itself, and reports the finer result
   ([Mesh](references/linear-static.md#mesh)). `--vtu` adds a ParaView file beside the GLB.
   Progress lines (`[fea] reading the parts`, `[fea]
   meshing the glued shape at 6.01 mm`) print to stderr, never into the result on stdout;
   `--verbose` adds mesh and solve detail there. A study with no fixture, a face that is not on the
   part, an unknown key, an out-of-range ref, a zero load or a load on a held face is refused with a
   message naming the field. The result files are replaced only once every one is written: a run
   that fails leaves the previous result as it was.

   The command exits 1 (`"ok": false`) when a finding is an error, as a validator does: the part
   yields or misses a check, and the GLB is written all the same so the user sees where; or the
   study stopped before the solve (`not_connected`), with no GLB. Warnings leave it at 0. Read the
   result either way.

4. **Read the findings.** Every solve prints them after the numbers, one line each, `error:` or
   `warning:` and then what is wrong and what to do (`findings` in `--json`). Read
   them before reporting; see [Read the findings](#read-the-findings).

5. **Report**, in this order, with units: max von Mises (MPa) and where (`max_von_mises_at_mm`;
   say which feature it is near); the safety factor against yield and the yield used; max
   displacement (mm) and where; the applied load and the reaction (they balance: a solve where they
   do not is refused);
   the mesh size, element count and whether a finer re-solve ran. Then say in a sentence or two
   what the model assumes and what would change the answer most (a softer fixture, a fillet at the
   peak, a different material). Open the GLB in the Viewer for the user; the deformation is
   exaggerated by the summary's `deformation_scale`, so say that too. The Viewer draws
   the loads as arrows and the fixed faces as cones on the model; a person can check them against
   what they meant before trusting the numbers.

## Assemblies

A document of several parts is solved as one assembly: the parts that touch are bonded into one
conforming mesh, each part keeps its own material, and the result reports each part's stress
against its own yield. Every part must be joined, through bonded neighbours, to a part that is
fixed. The keys are in [study-file.md](references/study-file.md#assemblies).

1. **List the parts and joints first.**

   ```bash
   cadgen fea parts assembly.step
   ```

   It prints each part (ref, name, volume), then each touching pair with its contact area and gap
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
   a larger joint area (the joint's `area_mm2` is in the result's `connections`). The Viewer's
   Study lists Parts and Connections; a part or joint the user selected there reaches you with its
   ref or refs.

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
longer arm, another material), each version is its own STEP, as `$cad` builds them: one model per
configuration. Run the same study on each, with the faces mapped, and compare.

1. **Get the study right on one variant first** (the baseline): the full [Workflow](#workflow),
   solved and checked.
2. **Map its faces onto every other variant.** Face numbers are not stable between versions: an
   edit renumbers faces, and a ref reused unchecked can land on a different face with no
   error. Run `cadgen fea faces variant.step` and match each face the study names by what it is,
   never by its number: the same surface type and normal, a centre where the edit would move it,
   an area that changed only as the edit explains. When two faces fit equally, or the edit removed
   the face, ask, quoting the candidates. Write one study per variant (`study.<variant>.json`):
   the mapped refs, everything else identical.
3. **Hold the mesh still.** Accuracy follows the mesh, so a difference between variants is only
   the design's when they are meshed alike: give every study the baseline's `mesh.size_mm`.
4. **Solve each to its own result:** `cadgen fea solve variant.step FEA/variant.fea.glb --study
   study.<variant>.json`.
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
- Displacement is what the part moves, before any scale. The GLB positions carry
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
| `peak_at_fixture` | warning | The peak sits on a fixed face or at its edge, where a perfectly rigid clamp exaggerates stress, and a finer solve did not settle it. | Read the stress a little away from the fixed face (the GLB's colours, or a probe in the VTU) before redesigning; if that is still high, the finding beside it stands. |
| `peak_concentration` | warning | The integration-point peak is well above the nodal one: a sharp corner or concentrated load the mesh cannot resolve. | When the safety factor was under 3 the run already solved finer, so refining the whole part again is not the next step: fillet the corner or spread the load over a larger face. Above 3 (a `margin` higher than that), refine once and compare: halve `mesh.size_mm`, or at a fillet or hole set it to a third of the radius (see [Mesh](references/linear-static.md#mesh)). |
| `mesh_not_converged` | warning | The automatic finer solve moved the peak by more than 10 %. In an assembly, only for a part whose safety factor is under 3: a part far from failing is not worth distrusting. | A peak that kept rising sits on a singularity (a sharp corner, the fixed edge): fillet it or judge the stress away from it. Otherwise set a smaller `mesh.size_mm` and solve again before trusting the safety factor. |
| `large_displacement` | warning | It moves more than 1 % of its size. | The small-displacement model is stretched: check the fit against mating parts and whether the deflection is acceptable; stiffen the part if not. |

A `warning:` line that is not a finding (a slow solve past 150 000 degrees of freedom, a finer
solve that was skipped or failed) is about the run itself: read it, and mention it when it bears on
the answer.
