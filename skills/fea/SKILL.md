---
name: fea
description: Run finite element and multiphysics studies on STEP parts and assemblies with cadgen, covering strength, vibration, buckling, heat, flow, sound, cracks, fatigue, drops, electromagnetics, piezo, rotors and more. Pick the analysis from the table; each has its own reference page. Use when the user asks whether a part is strong enough, how much it bends, where it is most stressed, or asks for FEA or a simulation of a part.
license: MIT
---

# FEA: simulate a part or an assembly

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to answer engineering questions about one part, or an assembly
of parts bonded where they touch, by simulation. It meshes the saved STEP,
solves the analysis the study names, and writes a colour-mapped result the
Viewer renders. This page is a router: [Choose the analysis](#choose-the-analysis)
maps the user's question to an analysis and its reference page, which holds
that analysis's schema, hand checks and limits. Every analysis in the table
runs today; for a question none of them answers, follow [When the question
needs an analysis that is not here](#when-the-question-needs-an-analysis-that-is-not-here).

The default, `static`, answers "will it hold, and by how much" under forces,
pressures, the part's own weight (`gravity`) and a steady acceleration
(`acceleration`), with quadratic tetrahedra and linear elasticity (isotropic,
or orthotropic where the material gives its directions). It is a first-pass
engineering check, not a certification: small displacements, a linear material
below yield, perfectly rigid fixtures (a `fixed` face held still, a `roller`
face free to slide in its plane but not off it) and loads that do not move. In
an assembly every joint is perfectly rigid (bonded) unless the study names
`contact` pairs or `bolt`s. Say so when you report.

## Choose the analysis

Match the user's question to an analysis first. The `analysis` key of the
study names it; left out, it is `static`.

| The user asks | `analysis` | Plain word | Status | Reference |
| --- | --- | --- | --- | --- |
| "Will it hold", "is it strong enough", "how much does it bend" | `static` | Strength | **Runs today** | [Linear static](references/linear-static.md) |
| The same under its own weight, or while it speeds up, brakes or turns (a steady g-load) | `static` with a `gravity` or `acceleration` load | Strength | **Runs today** | linear-static.md, section "Body loads: gravity and acceleration" |
| "Will it rattle", "will it resonate", "what frequency does it ring at" | `modal` | Vibration | **Runs today** | [modal.md](references/modal.md) |
| "Will this column or thin wall buckle" | `buckling` | Buckling | **Runs today** | [buckling.md](references/buckling.md) |
| "How hot does it get" (settled, steady running) | `thermal` | Heat | **Runs today** | [thermal.md](references/thermal.md) |
| "How hot during a warm-up or a duty cycle" | `thermal_transient` | Heat over time | **Runs today** | [thermal-transient.md](references/thermal-transient.md) |
| "It gets hot: does that stress or warp it" | `thermal_stress` | Heat stress | **Runs today** | [thermal-stress.md](references/thermal-stress.md) |
| "How hot does it get" when it radiates: a hot part, a dull part in still air, in a vacuum, fins or plates that see each other | `thermal` (or `thermal_transient`, or `thermal_stress` for the stress it causes) with `radiation` | Heat | **Runs today** (grey, diffuse; view factors computed between faces with `surface_to_surface`) | thermal.md, section "Radiation" |
| "On a shaker", "across a motor's speed range", a sine sweep | `harmonic` | Shaking | **Runs today** | [harmonic.md](references/harmonic.md) |
| A transport or vibration spec in g²/Hz | `random_vibration` | Random vibration | **Runs today** | [random-vibration.md](references/random-vibration.md) |
| A shock spec, a shock response spectrum (SRS) | `shock` | Shock | **Runs today** | [shock.md](references/shock.md) |
| A load that changes over time, a hammer blow | `transient` | Over time | **Runs today** | [transient.md](references/transient.md) |
| "How long will it last", "how many cycles" | `fatigue` | Fatigue life | **Runs today** from a static load case (`"from": "static"`), a shaker dwell (`"from": "harmonic"`, `dwell_s`) or a random vibration spec (`"from": "random_vibration"`, `duration_s`) | [fatigue.md](references/fatigue.md) |
| "What if I drop it" (a quick answer) | `drop` | Drop (estimate) | **Runs today** (an estimate; `"dynamic": true` adds a transient check) | [drop.md](references/drop.md) |
| "What if I drop it" (a deeper check, after `drop`) | `impact` | Drop impact | **Runs today** (lite: rigid floor, linear tets, elastic unless plasticity is given) | [impact.md](references/impact.md) |
| Flow through or around it, pressure drop, the push of air or water on it | `cfd` | Flow | **Runs today** (lite: laminar, steady, incompressible) | [cfd.md](references/cfd.md) |
| The same when the flow is fast (past Re 2000 in a pipe, Re 1000 around a body): water in a pipe, air in a duct or past a body | `cfd_turbulent` | Turbulent flow | **Runs today** (lite: steady RANS, k-omega SST, wall functions, incompressible) | [cfd-turbulent.md](references/cfd-turbulent.md) |
| "How hot does it run with this coolant", a liquid cold plate, a cooling channel, "how warm does the water come out", the heat transfer coefficient a flow gives | `conjugate_heat` | Cooled by flow | **Runs today** (lite: steady, the flow not changed by the heat, constant properties; laminar or turbulent) | [conjugate-heat.md](references/conjugate-heat.md) |
| "Does the flow bend it, and does the bend change the flow", a flexible flap, valve reed or fin in a stream, a soft tube or hose that swells under its own flow | `fsi` | Flow and bending | **Runs today** (lite: steady two-way coupling, linear elastic part, small-to-moderate deflection, ALE mesh motion; no flutter) | [fsi.md](references/fsi.md) |
| "Does it bend for good", "at what load does it give way", rubber or other stretchy parts | `nonlinear` | Permanent bend / Stretch | **Runs today** (lite: small-strain metal plasticity, Neo-Hookean rubber) | [nonlinear.md](references/nonlinear.md) |
| "Does it slowly stretch or sag under a load held for years, hot", "does the clamp relax" | `creep` | Creep | **Runs today** (lite: Norton power law, steady creep; needs the grade's creep data) | [creep.md](references/creep.md) |
| "Will this carbon or glass fibre plate hold", "which ply fails first", a layup | `composite` | Composite | **Runs today** (lite: flat plates of even thickness, classical laminate theory, first ply failure; no delamination) | [composite.md](references/composite.md) |
| Parts pressing or sliding on each other, "how hard do they press", a part resting on a floor | `contact` | Contact | **Runs today** (lite: small sliding, node-to-surface, static, elastic parts) | [contact.md](references/contact.md) |
| A bolted joint: "is the bolt strong enough", "does the joint open", "does it slip", tightening torque to preload | `bolt` | Bolted joint | **Runs today** (lite: a pretensioned spring per bolt, frictional contact between the clamped parts, linear elastic, no thread) | [bolt.md](references/bolt.md) |
| "Will it arc", capacitance, resistance, Joule heating from a current, a coil's magnetic field, inductance or magnet force | `electromagnetic` | Magnetic / electric | **Runs today** (lite: static and DC, linear materials) | [electromagnetic.md](references/electromagnetic.md) |
| Eddy currents, skin effect, AC resistance, a coil's impedance at a frequency, induction heating, the loss in a part near an AC field | `electromagnetic` with `"mode": "ac_magnetic"` | Magnetic / electric | **Runs today** (lite: time-harmonic at one frequency, linear materials, stranded coils; no saturation, hysteresis or waves) | electromagnetic.md, section "AC magnetic fields (`ac_magnetic`)" |
| Fast gas flow (past about Mach 0.3, 100 m/s in air): a nozzle, valve or orifice under a real pressure ratio, "does it choke", "what Mach number", "where is the shock" | `cfd_compressible` | Fast gas flow | **Runs today** (lite: steady ideal gas, adiabatic, an inviscid core past the laminar range, shocks captured; no supersonic outlet) | [cfd-compressible.md](references/cfd-compressible.md) |
| "Make it lighter", "where can I take material out", "what shape should this bracket be", the stiffest part from 30 % of the material, or the least material that still holds | `topology` | Lighten it | **Runs today** (lite: SIMP density method on a fixed linear-tet design mesh, linear elastic, one part; the result is a shape to rebuild in CAD, then check with `static`) | [topology.md](references/topology.md) |
| "What frequencies does this box, duct or room boom at", the air's own resonances | `acoustic` | Sound | **Runs today** (lite: linear acoustics, rigid walls, no flow) | [acoustic.md](references/acoustic.md) |
| "How loud is it", a speaker or a point source in a cavity or out in open air, "how much does lining this face help", what a microphone hears across a sweep | `acoustic` with `sources` and `sweep_Hz` | Sound | **Runs today** (lite: linear acoustics, lumped absorption, a first-order absorbing boundary for open air) | acoustic.md |
| "How much noise does this vibrating part make", the sound a shaken panel sends out or into the box it closes | `acoustic` with `"from": "harmonic"` | Sound | **Runs today** (lite: one-way, the harmonic's surface velocity drives the air; no flow) | acoustic.md, section "The study" |
| A piezo actuator, sensor or buzzer: "how far does it move at this voltage", "how hard can it push", "what voltage does this sensor make", its capacitance, resonance and anti-resonance, coupling, the current it draws across a band | `piezo` | Piezo | **Runs today** (lite: linear piezoelectricity, small signal; static, resonance and a driven sweep; no depolarisation or hysteresis) | [piezo.md](references/piezo.md) |
| "Will this crack grow", "how big a crack can it take", a flaw found in inspection, "how many cycles until it breaks" with a crack | `fracture` | Cracks | **Runs today** (lite: linear-elastic fracture mechanics on a crack the study describes, K against K_IC, Paris crack growth; no ductile tearing) | [fracture.md](references/fracture.md) |
| A spinning shaft, spindle, rotor, fan or disc: "will it run through a critical speed", a Campbell diagram, "how big is the orbit with this unbalance", "is the whirl stable", the spinning stress in a disc | `rotordynamics` | Spinning | **Runs today** (lite: a Timoshenko rotor line cut from the CAD with gyroscopic terms, linear bearings, bending whirl only; the spinning stress on the solid) | [rotordynamics.md](references/rotordynamics.md) |
| Liquid inside the part moving over time: "will it spill when the tank is shaken or brakes", how high the water climbs the walls, the sloshing force on the tank and its frequency, filling or draining a cavity, a rising bubble | `multiphase` | Two fluids | **Runs today** (lite: laminar, incompressible, the interface a few elements thick; no evaporation, boiling or mixing) | [multiphase.md](references/multiphase.md) |

Each reference holds its analysis's full schema. A test keeps this table and
the study file's `analysis` table in step with what cadgen registers.

### When the question needs an analysis that is not here

([planned-next.md](references/planned-next.md) says the same: nothing is registered as planned.)

- Tell the user plainly, in their words: "That is not in this version." Do
  not write a study for it.
- Do not pass a static result off as the answer. A static safety factor says
  nothing about resonance, buckling, temperature, fatigue life, flow or parts
  sliding on each other.
- Offer a static study only where it honestly answers part of the question,
  and say which part:
  - **A drop.** Both run today: `impact` simulates the part hitting a rigid
    floor ([impact.md](references/impact.md)), and the quicker `drop`
    estimate is exactly a static study: the faces that hit the
    floor held fixed, and an `acceleration` load of G g pointing away from the
    floor (opposite those faces' outward normal), with G = drop height /
    stopping distance (1000 mm stopping in 2 mm is 500 g). Run `drop`
    ([drop.md](references/drop.md)). Report it as an estimate, never as an
    impact simulation, and say what stopping distance you assumed.
  - **Its own weight, or a steady g-load** (a vehicle braking, a part on a
    spinning arm at a known g): that is `static` already.
- When the user wants a number now and no static study fits, a hand estimate,
  labelled as one, is better than nothing. Work in the study's units (mm, N,
  MPa, t/mm³), where these come out directly:
  - Buckling of a column (Euler): P = π² E I / (K L)², with K = 2 for one end
    fixed and one free, 1 for both ends pinned, 0.5 for both ends fixed.
  - First natural frequency of a cantilever: f = 0.560 √(E I / (ρ A L⁴)) Hz.

## Say what the run did

These rules hold for every analysis; each one applies as soon as its analysis
runs.

- **Every adapted step.** A model too big for the machine's memory or time
  target is adapted, not refused (below). The CLI prints one `adapted:` line
  per step, and the sidecar's `fit` lists them, each with its accuracy note
  ("peak stress moved 2.1 % between passes"). Report every one, with its note,
  in the user's words. Never hide a step, and never report an adapted result as
  if it were not.
- **Estimates.** A `drop` result, or a static study standing in for one, is an
  estimate of an equivalent steady load, not a simulation of the impact. Say
  "estimate" every time you quote it.
- **Lite limits.** An analysis whose Status in the table says "lite" is a lite
  solver with stated limits, listed in its row and its reference page and
  carried by its result. Quote the limits the result carries whenever you quote
  its numbers.
- **A lightened design.** `topology` is lite too: say it is a concept shape from a
  fixed design mesh, quote the mass saved and the verified design's stress and
  displacement as a guide, and point the user to the design STL to rebuild in CAD
  and re-check with `static` ([topology.md](references/topology.md)).
- **The Reynolds warning.** When a flow result warns that its Reynolds number
  is past the laminar range, say so with its number: the real flow is likely
  turbulent, the pressure drop is a lower bound and the flow pattern may be
  wrong. Then run the same study as `cfd_turbulent`
  ([cfd-turbulent.md](references/cfd-turbulent.md)) and report that answer.
- **A coupling that did not settle.** When an `fsi` result says the flow and the
  bending did not settle, say so first: its numbers are the last state, not an
  answer. Offer the fixes in [fsi.md](references/fsi.md#when-it-does-not-settle).

## Big models: run first, then report what was adapted

Never ask the user to shrink, simplify or defeature a model before running it.
Run it as it is. When it does not fit the memory or time target, the run
adapts by itself: an iterative solver, a mesh kept fine at the peak and coarse
away from it, small fillets far from every load left out, simpler elements,
half a symmetric part. Then report what was adapted, as above. Nothing is
refused for being big or slow; when every step is used and it still misses the
target, the run goes ahead and says how long and how much memory to expect.

Use the study's `fit` key ([study-file.md](references/study-file.md#fit)) only
when the user rules a simplification out ("do not leave any fillets out":
leave `defeature` out of `fit.allow`) or names a memory or time budget.

## Start with the task

| Task | First action | Reference |
| --- | --- | --- |
| **Pick the analysis** | Match the question to a row of the table above; every analysis in it runs today, and its row says whether it is an estimate or lite. | [Choose the analysis](#choose-the-analysis) |
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

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.20 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.20 python`

Solving needs cadgen's opt-in `fea` extra, which brings the mesher (netgen) and
the solver (scikit-fem, pyamg). `cadgen fea faces` and `cadgen fea parts` work without it. The first
time a study runs, `cadgen fea solve` fails with "cadgen's fea extra is not
installed"; that is a missing install, not a modelling error. Its `pip install`
hint does not apply under uv: run the same command again with the extra in the
requirement, and keep using that form for `fea solve` from then on:

```bash
uvx --no-config --managed-python --python 3.13 --from "cadgen[fea]==0.7.20" cadgen fea solve part.step --study study.json
```

The first run downloads the mesher and solver (large); later runs reuse them.

Units are fixed: mm for geometry, N for forces, MPa for pressure, modulus and
stress, t/mm³ for density, and g (9.81 m/s²) for gravity and acceleration.
Restate every load in those units before you write it down. The full table,
including the heat and flow units the other analyses take, is in
[study-file.md](references/study-file.md#units).

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

   A fixture is `fixed` (held still) or `roller` (slides in its plane, never
   off it: a frictionless support, or a symmetry plane cut through the part;
   [fixtures](references/study-file.md#fixtures)). A `force` is the total force over its faces; a `pressure` is in MPa and
   pushes into the surface. Add `{"type": "gravity", "vector_g": [0, 0, -1]}`
   when the part's own weight matters (a long arm, a heavy casting), and
   `{"type": "acceleration", "vector_g": [5, 0, 0]}` when the part is speeding
   up, braking or turning at a known g; neither names faces, and both need the
   material's density ([Body loads](references/linear-static.md#body-loads-gravity-and-acceleration)).
   Leave `analysis` out (it is `static`). Leave `mesh` out on the first run; the default
   element size is a fortieth of the part's bounding diagonal, and small
   features (thin walls, fillets, chamfers, small holes) make the elements
   finer where they are, so they, not only the bounding box, can set the
   element count. `margin` is
   the safety factor the part should keep (default 2, at least 1): set it
   higher for a polymer, a fatigue load or a part that must not fail, lower
   only when the user says the load is known exactly.

   Add a `view` to pick what the Viewer's Study shows for the result: its
   checks, its sections and the controls the user will want to drag, each
   from a closed vocabulary ([The result's view](references/study-file.md#view)).
   Without one the verdict is the stress check and the controls are the
   field and deformation.

   - **Checks**, from what the user asked: "will it break", "is it strong
     enough": `stress`. "How much does it sag or deflect", or a stiffness
     spec: a `displacement` check with their limit (`limit_mm`), on the
     faces they mean, labelled in their words ("Tip sag"). Keep `stress` too
     unless they only care about stiffness.
   - **Controls**: leave them out unless the user asked something a control
     answers. The default, Show (stress or displacement) and Exaggerate, is
     what most results need, and every extra control is more to read.
     Declaring `controls` replaces that default, so list Show and Exaggerate
     with what you add: `{"drives": "field", "label": "Show"}` and
     `{"drives": "deformation", "label": "Exaggerate"}`, the deformation with
     no range (the solve picks its scale, so a fixed `max` can pin it):
     - a `load_scale` slider named for the load ("Rider weight") only when
       they ask how much it can take or what a heavier load does, with
       `when: failing` when it only helps a part that fails;
     - a `threshold` only when they asked where the stress is over a limit,
       its `default` that limit, so it does something when the result opens;
     - `field` opening on `displacement` only for a study about deflection.
   - **Presets** only for two or more load cases the user named ("landing"
     and "cruise"). A single case is the load slider's default, not a preset,
     and a preset that only moves one slider repeats it.
   - **Sections** only to leave something out (`["verdict", "controls"]` for
     a quick look); the default shows all.

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
   element size (and half the size at fillets and holes too) and solves again,
   by itself; the finer result is the one
   written and reported, and the sidecar's `refined` block records both
   sizes and peaks. The finer size is capped to keep the solve under the
   degrees-of-freedom budget, so a part near the limit takes longer (minutes)
   and may get a smaller refinement than half. A model too big for the
   machine is adapted to fit rather than refused, and each step prints an
   `adapted:` line ([Big models](#big-models-run-first-then-report-what-was-adapted)). `--vtu` adds a ParaView file. `--json` prints the result as one JSON line
   for scripting. Progress lines (`[fea] reading the parts`, `[fea] meshing
   the glued shape at 6.01 mm`) print to stderr, never into the result on
   stdout; `--verbose` adds mesh and solve detail there. A study
   with no fixture, a face that is not on the part, or an out-of-range
   selector is refused with a message naming the field.

4. **Read the findings.** Every solve prints them after the numbers, one
   line each, `error:` or `warning:` and then what is wrong and what to do
   (`findings` in `--json` and the sidecar). Read them before reporting; see
   [Read the findings](#read-the-findings).

5. **Report.** Quote, in this order: max von Mises (MPa) and where it is,
   safety factor against yield, max displacement (mm) and where, the applied
   load and the reaction (they balance, or the run warns), the mesh size and
   element count, and every `adapted:` step with its accuracy note. Then say
   what the model assumes. Open the GLB in the Viewer
   for the user; the deformation is exaggerated by the `deformation_scale`
   the sidecar records, so say that too. The Viewer draws the loads as
   arrows and the fixed faces as cones on the model; a person can check
   them against what they meant before trusting the numbers.

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
   `overlapping · N mm³` when the solids share volume (such parts are never
   bonded). An overlap no thicker than `contact_tolerance_mm` (a thin layer,
   where a face sits a little into another; a corner sunk in on every axis is
   a lump, measured by its full depth) is an
   interference instead (a press fit, or a modelling slip): it is listed
   `bonded` with `interference N mm`, and the solve closes it like a gap. The
   header counts touching pairs apart from near misses and overlaps. Read it against what you know of the design: is
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

4. **Read the findings by part.** Each finding names its part ("'post'
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
| `gap_closed` | warning | Two parts a little apart, or a little into each other (an interference), within the tolerance were bonded anyway, moving geometry up to that far. | Check the gap is a modelling clearance and not a real one the joint should have, or that the interference is a slip and not a press fit whose preload matters; the stress at that joint is the model's closing, not the part's. |
| `bonded_edge_peak` | warning | The peak sits on the edge of a bonded joint, where a rigid bond exaggerates stress. Appears wherever the part misses the study's `margin`, even when a finer mesh agreed: a rigid bond's edge is singular, so two meshes agreeing proves nothing there. | Read the stress a little away from the joint before redesigning; a bolted or welded joint is softer than this model. |

A `fixture` or `load` on a face that is wholly a joint (the foot of a post)
is refused before the solve with an error naming the face: move it to a face
that is not covered. On a face only partly covered it applies to the exposed
area alone. `contact` connections run under the `contact` analysis and `bolt`
connections under `bolt`; every other analysis refuses them ("not yet supported"); a pair set `free` inside a group
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
- In an assembly the summary's `yield_MPa` and `safety_factor` are the weakest
  part's, beside `weakest_part` and `weakest_part_peak_MPa`; `max_von_mises_*`
  and `max_displacement_mm` are the whole assembly's, wherever they fall. The
  assembly's peak can be in a stronger part, so do not divide one by the other:
  quote the weakest part's peak with its safety factor, and each part's own
  numbers from `parts`.

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
| `peak_concentration` | warning | The Gauss-point peak is well above the nodal one: a sharp corner or concentrated load the mesh cannot resolve. | When the safety factor was under 3 the run already solved at half the mesh size, so refining the whole part again is not the next step: fillet the corner or spread the load over a larger face. Above 3 (a `margin` higher than that), refine once and compare: halve `mesh.size_mm`, or at a fillet or hole set it to a third of the radius (see [Mesh](references/linear-static.md#mesh)). |
| `mesh_not_converged` | warning | The automatic finer solve moved the peak by more than 10 %. In an assembly, only for a part whose safety factor is under 3: a part far from failing is not worth distrusting. | A peak that kept rising sits on a singularity (a sharp corner, the fixed edge): fillet it or judge the stress away from it. Otherwise set a smaller `mesh.size_mm` and solve again before trusting the safety factor. |
| `large_displacement` | warning | It moves more than 1 % of its size. | The small-displacement model is stretched: check the fit against mating parts and whether the deflection is acceptable; stiffen the part if not. |
| `no_load` | warning | The peak stress is zero: no load reaches the part. | Check that the loaded faces are on the part and connected to the fixed ones, and that the force is not zero. |

A `warning:` line that is not a finding (a slow solve, reactions that do not
balance, a finer solve that failed) is about the run itself: read it, and
mention it when it bears on the answer.

An `info` finding whose kind starts `fit_` (`fit_local_refine`,
`fit_defeature`) is one adapted step, the same as its `adapted:` line: report
it with its accuracy note, as [Say what the run did](#say-what-the-run-did)
asks.
