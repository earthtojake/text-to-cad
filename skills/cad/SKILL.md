---
name: cad
description: Create, modify, inspect, and validate STEP-first parametric CAD parts and assemblies. Use for natural-language CAD specs, reference images, 2D technical drawings, STEP/STP generation or direct inspection, Python CAD source, source-level joints, selector references, geometry facts, measurements, mating deltas, snapshots, and secondary STL/3MF/native GLB outputs from CAD geometry.
---

# CAD generation, inspection, and validation

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Purpose

Create or modify parametric CAD models from natural-language requirements, generate validated STEP/STP artifacts, inspect geometry references, and return checked outputs. Treat STEP as the primary CAD artifact. Treat STL, 3MF, and native GLB as secondary export workflows that branch from a STEP-first process. For assemblies, prefer `cadgen.assembly.AssemblyHelper` with source-level build123d joints, named mating datums, and native labels when the parts have functional assembly relationships.

There are two ways into the STEP workflow: generate from build123d Python source (the default when designing from scratch or modifying a generated model), or import an existing STEP/STP file directly (when no generator exists or the user explicitly targets the STEP file). Both produce the same inspectable artifacts.

## Use this skill when

Use this skill when the user asks for CAD files, STEP/STP files, build123d source, selector refs such as `#o1.2.f1`, mechanical parts, assemblies, enclosures, brackets, fixtures, holes, counterbores, countersinks, slots, pockets, bosses, standoffs, ribs, fillets, chamfers, shells, source-level joints, mating, or measurements. Also use it when the user supplies reference images or 2D technical drawings of a part to reproduce or take design intent from.

Also use it when the user asks for STL, 3MF, or native GLB output from CAD geometry. Keep those workflows secondary and load `supported-exports.md` for details. For 2D DXF drawings, use the `$dxf` skill; when a DXF projects from a 3D part, this skill owns the STEP geometry and `$dxf` owns the drawing.

Do not use this skill for render-only concept art, CAM toolpaths, engineering certification, FEA conclusions, architectural BIM, or freehand illustration unless the user also needs CAD geometry.

## Default assumptions

Use these defaults unless the user specifies otherwise. These are first-pass modeling defaults, not manufacturability, tolerance, or certification claims:

- Units: millimeters.
- Origin: per the part-type defaults in `references/positioning.md`; center of the main part or assembly when nothing better applies.
- Base plane: XY.
- Up/extrusion axis: positive Z.
- Output geometry: closed, positive-volume solids unless the user requests surfaces or construction geometry.
- STEP structure: one valid solid, a compound of solids, or a labeled assembly compound.
- Assembly structure: fixed root part, part-local frames, named mating datums, `AssemblyHelper` relationships backed by build123d joints where applicable, explicit generated placements, and verbose native labels.
- Small plastic enclosure wall: 2.0-3.0 mm when unspecified.
- Cosmetic fillet: 1.0-3.0 mm when safe for local geometry.
- M3/M4/M5 normal clearance holes: 3.4/4.5/5.5 mm unless another standard is requested.

Ask one focused clarification question only when missing information makes the model impossible, fit-critical, safety-critical, or compliance-bound. Otherwise proceed with explicit assumptions.

## Tools and paths

From the CAD skill directory, the launcher shape is:

```bash
python scripts/gen ...       # render GLB/topology packages from gen_step() Python sources
python scripts/export ...    # STL/3MF/GLB mesh files from Python sources or imported STEP
python scripts/inspect ...   # refs, measure, align, frame, diff
python scripts/snapshot ...  # PNG/GIF visual review packets
python scripts/artifact ...  # debug one on-demand render-package build (imported STEP)
```

Use the active project Python interpreter; treat `python` in examples as an interpreter placeholder. Use `python scripts/<tool> --help` for the complete current command interface; reference docs show recommended workflows, not every flag.

**Snapshot inputs.** This skill's snapshot renders `.step`/`.step.py`, `.stp`, `.3mf`, `.glb` and `.stl`. Implicit models and robot descriptions are rendered by the `implicit-cad` and `urdf`/`srdf`/`sdf` skills; the CLI refuses them rather than rendering something it should not.

**Theme and display.** Theme settings live under one `--theme`, display settings under one `--display` — the viewer's two tabs, one option each. The default theme is `snapshot`: Workbench Light with the ground grid and origin axis removed, because in a still image those read as geometry rather than as orientation. Pass `--theme workbench-light` for the viewer's own look. Projection is a theme trait honoured by every format, so a snapshot frames the same way the viewport does.

**Streams.** stdout carries the result; stderr carries progress, timing, and failures. Every tool answers on stdout — `gen` prints `<outcome> <package path>` per target — so `2>/dev/null` leaves something parseable and `>/dev/null` leaves a readable log. JSON on stdout is always compact; pipe through `jq .` to read it. The two never interleave, so `2>/dev/null` leaves a clean parseable result and `>/dev/null` leaves a readable log. For machine-readable output: `gen`, `export`, and `snapshot` take `--json`; `inspect` already emits JSON and takes `--format text` for prose. `--verbose` adds stage timing (and full tracebacks) on stderr. Output volume does not grow with model size — a 600-occurrence assembly logs the same dozen lines a single part does.

**Failures** print the exception and the frames *in your own generator*, not the runtime's:

```text
[scripts/gen] FAILED: ValueError: bad radius
[scripts/gen]   models/step/parts/widget.step.py:9 in gen_step
[scripts/gen]       return _profile(radius)
[scripts/gen] re-run with --verbose for the full traceback
```

**A build waits for a concurrent build of the same model** rather than racing it, and says so on stderr (`waiting for another run to finish building ...`), repeating while it waits. Pass `--lock-timeout SECONDS` to give up instead and report `{"ok":true,"contended":true}`. With `--json`, each target's `outcome` is `built`, `current`, `skipped-peer` (the peer finished and its package is current), or `contended` (the peer is still building and this run declined to wait).

Target paths resolve from the command's current working directory, not from the skill directory. Run commands from the workspace that owns the artifacts and pass cwd-relative target paths so project CAD files never resolve accidentally under the skill directory. Keep a STEP output and its Python generator in the same directory with the same basename unless the user explicitly requests otherwise.

CAD references are `#...` selector tokens local to a target, for example `#o1.2` or `#o1.2.f1`. Pass the STEP/CAD file as a separate target argument when using CAD CLIs.

## Required workflow

Scale depth to the task: a simple part needs a short brief and few spec-driven checks; assemblies and fit-critical work need full positioning and alignment validation.

1. **Classify the task.** New part, new assembly, source modification, direct STEP/STP inspection, reference selection, measurement/alignment check, snapshot review, or secondary output request.
2. **Load only the needed references.** Use the triggers below instead of reading the whole reference set.
3. **Write a natural-language CAD brief.** Extract dimensions, units, coordinate convention, feature intent, output paths, assumptions, and validation targets from all provided inputs — prose, reference images, technical drawings. Use `references/cad-brief.md`.
4. **Check named purchasable components.** When an assembly includes named off-the-shelf actuators, servos, motors, electronics boards, connectors, or other purchasable components, search `$step-parts` before creating simplified placeholder geometry. If no exact match is found, record the miss and then use a documented envelope.
5. **Plan before coding.** Define parameters, intent labels, source paths, expected bounding boxes, and any mating/positioning datums before editing.
6. **Edit source, not generated artifacts.** Author build123d Python with `gen_step()`, naming a buildable entry generator `<name>.step.py` (helper/library modules stay `<name>.py`; see `references/step-generation.md`). When a Python generator exists, run `scripts/gen` on the generator, never on its exported STEP. Imported STEP/STP files (no generator) need no build step: inspect, snapshot, and the CAD Viewer generate their render artifacts on demand, and `scripts/export` accepts them directly.
7. **Generate explicit targets.** Run `scripts/gen` on explicit generator targets only; do not run directory-wide generation. Add `--write` when the user needs the `.step` file itself, and use `scripts/export` when they need STL/3MF/GLB mesh files.
8. **Validate geometrically.** Run `scripts/inspect refs <step-or-cad-target> --facts --planes --positioning` as the baseline, then verify the dimensions and relationships the user's spec calls out with targeted `measure`, `align`, `frame`, or `diff` checks. Run `scripts/inspect validate <step-or-cad-target>` for geometry soundness: `refs --facts` reports counts and bounds, and its `ok` field covers ref resolution only — an open shell and an inverted solid both pass it.
9. **Snapshot the primary STEP — snapshot validation is mandatory.** After creating or visibly updating a primary STEP/STP part or assembly, ALWAYS run CAD `scripts/snapshot` against it and review the output; deterministic checks passing is not a reason to skip. The only skip cases are documented in `references/snapshot-review.md` (no visible geometry changed, or no valid artifact exists); report the reason when skipping.
10. **Repair and rerun.** If a check fails, change the smallest responsible source section, regenerate, and rerun the failed validation.

## Handoff

After completing CAD work that creates or modifies `.step`, `.stp`, `.stl`, `.3mf`, or native `.glb` artifacts, you must ALWAYS hand the explicit file path(s) to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include those live viewer link(s) in the final response. If `$cad-viewer` is unavailable or startup fails, report that and rely on CLI inspection plus snapshots instead of silently omitting the handoff. This rule applies to every workflow in this skill, including secondary STL/3MF/GLB outputs.

When verification snapshots are generated, include the saved PNG/GIF snapshot(s) in the final response. If no snapshot applies, or if snapshot generation fails, say why and report the deterministic validation that still ran.

## Non-negotiables

- Keep STEP as the primary validated CAD artifact. Generated STEP/STP, STL, 3MF, GLB/topology outputs, and render sidecars are derived artifacts; STL/3MF are secondary unless the user explicitly says otherwise.
- Use named parameters, closed solids, verbose native build123d labels, and source-controlled geometry intent.
- Author assembly positioning in source. `references/positioning.md` is authoritative for `AssemblyHelper`, build123d joints, explicit `Location` transforms, and alignment validation.
- Do not use `git status`, `git diff`, or file-size churn as CAD comparison for large exported STEP/STP, GLB/topology, STL, or 3MF artifacts. Compare source changes, `scripts/inspect` summaries, snapshots, or generated topology output instead; use path-limited git status only for bookkeeping.
- Report only checks that actually ran or are directly supported by tool output.

## Progressive references

Load these files only when their trigger applies:

- `references/cad-brief.md` — converting prose, reference images, and technical drawings into a CAD brief.
- `references/build123d-modeling.md` — build123d modeling patterns, topology, selectors, features, labels.
- `references/step-generation.md` — STEP generation from Python source, direct STEP/STP imports, and post-generation steps.
- `references/inspection-and-validation.md` — validation sequence, selector refs, facts, planes, measurements, alignment, diff, frame, and validation reporting.
- `references/snapshot-review.md` — mandatory snapshot policy, packet sizing, targeted views, and converting visual findings into geometry checks.
- `references/positioning.md` — part-local datums and origins, assembly transforms, build123d joints, CLI alignment validation, and positioning reports.
- `references/parameters.md` — parameterizing or animating a STEP model: source parameters, JS parameter/animation sidecars declared via gen_step params, viewer controls, and animation design.
- `references/supported-exports.md` — STL/3MF/native GLB mesh export workflows via `scripts/export`.
- `references/repair-loop.md` — diagnosis and repair procedures.

Final responses should include generated files, returned `$cad-viewer` viewer links, verification snapshots, validation actually run, assumptions, and caveats. Use `references/inspection-and-validation.md` for report structure.
