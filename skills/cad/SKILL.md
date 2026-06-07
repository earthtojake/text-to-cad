---
name: cad
description: Create, modify, inspect, and validate STEP-first build123d/Python CAD parts and assemblies. Use for natural-language CAD specs, STEP/STP generation or direct inspection, build123d source, build123d source-level joints, selector references, geometry facts, measurements, mating deltas, CAD Viewer handoffs, snapshots, and secondary DXF/STL/3MF/native GLB outputs from CAD geometry.
---

# CAD generation, inspection, and validation

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Purpose

Create or modify parametric CAD models from natural-language requirements, generate validated STEP/STP artifacts, inspect geometry references, and return checked outputs. Treat STEP as the primary CAD artifact. Treat DXF, STL, 3MF, and native GLB as secondary workflows that branch from, or accompany, a STEP-first process. For assemblies, prefer `cadpy.assembly.AssemblyHelper` with source-level build123d joints, named mating datums, and native labels when the parts have functional assembly relationships.

## Use this skill when

Use this skill when the user asks for CAD files, STEP/STP files, build123d source, selector refs such as `#o1.2.f1`, mechanical parts, assemblies, enclosures, brackets, fixtures, holes, counterbores, countersinks, slots, pockets, bosses, standoffs, ribs, fillets, chamfers, shells, source-level joints, mating, or measurements.

Also use it when the user asks for DXF, STL, 3MF, or native GLB output from CAD geometry. Keep those workflows secondary and load `dxf.md` or `supported-exports.md` for details.

Do not use this skill for render-only concept art, CAM toolpaths, engineering certification, FEA conclusions, architectural BIM, or freehand illustration unless the user also needs CAD geometry.

## Default assumptions

Use these defaults unless the user specifies otherwise. These are first-pass modeling defaults, not manufacturability, tolerance, or certification claims:

- Units: millimeters.
- Origin: center of the main part or assembly unless a mating interface or fixed root component suggests a better origin.
- Base plane: XY.
- Up/extrusion axis: positive Z.
- Output geometry: closed, positive-volume solids unless the user requests surfaces or construction geometry.
- STEP structure: one valid solid, a compound of solids, or a labeled assembly compound.
- Assembly structure: fixed root part, part-local frames, named mating datums, `AssemblyHelper` relationships backed by build123d joints where applicable, explicit generated placements, and verbose native labels.
- Small plastic enclosure wall: 2.0-3.0 mm when unspecified.
- Cosmetic fillet: 1.0-3.0 mm when safe for local geometry.
- M3/M4/M5 normal clearance holes: 3.4/4.5/5.5 mm unless another standard is requested.

Ask one focused clarification question only when missing information makes the model impossible, fit-critical, safety-critical, or compliance-bound. Otherwise proceed with explicit assumptions.

## Natural-language specs only

Do not ask the user to provide a JSON specification and do not make JSON the user-facing workflow. Convert the user's prose into an internal CAD brief with dimensions, features, assumptions, output paths, and validation criteria. Use `references/natural-language-specs.md` for brief-writing patterns.

## Root model

Keep these roots separate:

- **CAD skill directory**: this folder. Tool launchers live here as `scripts/step`, `scripts/snapshot`, `scripts/inspect`, and `scripts/dxf`.
- **Tool process cwd**: relative CAD targets are resolved from the command's current working directory. Use absolute target paths when running from the skill directory, or run from the workspace root and invoke the launchers with a path to this skill directory.

Short command examples in this skill use launcher paths relative to the CAD skill directory. Adapt the launcher path or target path so project CAD files resolve from the intended workspace, not accidentally under the skill directory.

Prefer keeping a STEP output and its Python generator in the same directory so the source stays easy to discover. Unless the user explicitly requests otherwise, keep the STEP basename and generator basename the same even when they cannot live side by side.

## Available tools

From the CAD skill directory, the launcher shape is:

```bash
python scripts/step ...
python scripts/snapshot ...
python scripts/inspect ...
python scripts/dxf ...
```

Use the active project Python interpreter. Treat `python` in examples as an interpreter placeholder; if bare `python` is unavailable or lacks dependencies, substitute `python3`, a project virtualenv interpreter, or the configured interpreter path while keeping the root model above explicit.

Use `python scripts/<tool> --help` for the complete current command interface; reference docs show recommended workflows, not every flag.

CAD references are `#...` selector tokens, for example `#o1.2` or `#o1.2.f1`. Pass the STEP/CAD file as a separate target argument when using CAD CLIs.

## Required workflow

1. **Classify the task.** Identify whether this is a new part, new assembly, source modification, direct STEP/STP inspection, reference selection, measurement/alignment check, snapshot review, or secondary output request.
2. **Load only the needed references.** Use the triggers below instead of reading the whole reference set.
3. **Create a natural-language CAD brief.** Extract dimensions, units, coordinate convention, feature intent, output paths, assumptions, and validation targets.
4. **Check named purchasable components.** When an assembly includes named off-the-shelf actuators, servos, motors, electronics boards, connectors, or other purchasable components, search `$step-parts` before creating simplified placeholder geometry. If no exact match is found, record the miss and then use a documented envelope.
5. **Plan before coding.** Define parameters, intent labels, source paths, expected bounding boxes, and any mating/positioning datums before editing.
6. **Edit source, not generated artifacts.** Prefer build123d Python with `gen_step()` for STEP generation.
7. **Generate explicit targets.** Use `scripts/step` for STEP/STP generation, GLB/topology artifacts, and sidecars. When a Python generator exists, its GLB/topology artifact is Python-backed even when the STEP is also written. Use `--kind part` or `--kind assembly` only for direct STEP/STP imports. Use `--skip-step-write` only when explicitly generating a Python-backed GLB/topology artifact without writing STEP. Do not run directory-wide generation.
8. **Validate geometrically.** Use `scripts/inspect refs <step-or-cad-target> --facts --planes --positioning`, then targeted `measure`, `align`, `frame`, or `diff` when needed.
9. **Verify primary STEP visually with snapshots.** After creating or visibly updating a primary STEP/STP part or assembly, ALWAYS run CAD `scripts/snapshot` against the primary STEP/STP artifact for visual verification/review. Do not skip snapshots for speed, convenience, confidence, or because deterministic checks passed. Skip only when `references/snapshot-review.md` says no visible geometry changed or no valid artifact exists, and report that reason. Use PNGs for static reviews and GIFs for motion/animation reviews; `scripts/inspect`, measurements, alignment checks, frames, and diffs are complementary, not replacements.
10. **Repair and rerun.** If a check fails, change the smallest responsible source section, regenerate, and rerun the failed validation.

## Handoff

After completing CAD work that creates or modifies `.step`, `.stp`, `.stl`, `.3mf`, `.dxf`, or native `.glb` artifacts, you must ALWAYS hand the explicit file path(s) to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include those live viewer link(s) in the final response. If `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

When verification snapshots are generated, also include the saved PNG/GIF snapshot(s) in the final response. If no snapshot applies, or if snapshot generation fails, say why and report the deterministic validation that still ran.

## Non-negotiables

- Treat generated STEP/STP, STL, 3MF, GLB/topology, DXF outputs, and render sidecars as derived artifacts.
- Keep STEP as the primary validated CAD artifact; DXF/STL/3MF are secondary unless the user explicitly says otherwise.
- When a Python generator exists, run `scripts/step` on the generator. Use a direct STEP/STP target only when the generator is unavailable or the user explicitly identifies that STEP/STP file as the target.
- Use named parameters, closed solids, verbose native build123d labels, and source-controlled geometry intent.
- Author assembly positioning in source with `cadpy.assembly.AssemblyHelper` when available. Define part-local datums as native build123d joints, connect them through semantic helper methods such as `face_to_face`, `coaxial`, `revolute`, or `linear`, and fall back to explicit parameterized `Location` transforms only for simple static layouts. Treat CLI `inspect align` as read-only selector-pair alignment validation, not as a source-editing API or an authored mate feature.
- Do not use `git status`, `git diff`, or file-size churn as CAD comparison for large exported STEP/STP, GLB/topology, STL, 3MF, or DXF artifacts. Compare source changes, `scripts/inspect` summaries, primary STEP/STP CAD `scripts/snapshot` outputs, or generated topology output instead; use path-limited git status only for bookkeeping.
- Report only checks that actually ran or are directly supported by tool output.
- If `$cad-viewer` is unavailable or fails, say so and rely on CLI inspection for validation.

## Progressive references

Load these files only when their trigger applies:

- `references/natural-language-specs.md` — converting prose requirements into a CAD brief without requiring user JSON.
- `references/parameters.md` — parameter, control, and animation design best practices.
- `references/step-generation.md` — STEP generation, direct STEP/STP targets, part-vs-assembly behavior, and post-generation inspection.
- `references/inspection-and-validation.md` — validation gates, selector refs, facts, planes, topology, measurements, alignment, diff, frame, and final validation reporting.
- `references/snapshot-review.md` — risk-based snapshot triggers, small snapshot packets, targeted visual views, multimodal critique, and converting visual findings into geometry checks.
- `references/positioning.md` — part-local datums, assembly transforms, build123d joints, CLI alignment validation, and positioning reports.
- `references/dxf.md` — secondary DXF workflow.
- `references/supported-exports.md` — secondary STL/3MF/native GLB sidecar workflows.
- `references/build123d-modeling.md` — build123d modeling patterns, topology, selectors, features, assemblies.
- `references/repair-loop.md` — diagnosis and repair procedures.

Final responses should include generated files, returned `$cad-viewer` viewer links, verification snapshots, validation actually run, assumptions, and caveats. Use `references/inspection-and-validation.md` for report structure.
