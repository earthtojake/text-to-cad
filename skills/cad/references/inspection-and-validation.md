# Inspection and validation

Read this file for every generated STEP artifact and whenever the user asks for geometry facts, references, dimensions, mating, diffing, or frame inspection.

## Contents

- Principle
- Tool
- Relationship to build123d joints
- Validation hierarchy
- Reference discovery
- Measurement checks
- Mating checks
- Frame inspection
- Diff checks
- CAD Viewer handoff
- Validation report content

## Principle

Use programmatic geometry checks as the validation source of truth. Use CAD Viewer links and CAD `scripts/snapshot` outputs for visual review, not as substitutes for measurements, facts, planes, labels, or positioning checks.

## Tool

The launcher lives in the CAD skill directory:

```bash
python scripts/inspect {refs|diff|frame|measure|align|worker|batch} ...
```

Inspection targets are resolved from the command cwd unless absolute. Keep the root model in `SKILL.md` explicit when choosing whether to run from the workspace root or the skill directory.

Common data-output flags on inspection commands:

- `--format json|text`; default is machine-readable output.
- `--quiet`
- `--verbose`

Accepted target forms:

```text
path/to/entry
path/to/entry.step
```

Selector refs are local to the STEP/CAD entry target passed to the command. They do not include file paths:

```text
#o1.2
#o1.2.f1
#f1
```

Pass selector refs as `#...` tokens. The STEP/CAD file path or entry target is a separate CLI argument.

## Relationship to build123d joints

If the source uses `cadpy.assembly.AssemblyHelper` or build123d `Joint` objects, validate the generated STEP exactly as you would validate explicit `Location` placements. Source-level helper relationships and joints express and compute placement during generation; CLI `inspect align` verifies selected exported references by returning a translation delta. Do not confuse CLI `align` with authored mates, helper relationships, or build123d `Joint.connect_to()`. Use `positioning.md` for authoritative source-authoring rules.

## Validation hierarchy

Default validation sequence:

1. Generation completed and the STEP/STP file exists.
2. `refs --facts --planes --positioning` confirms scale, labels, major planes, and placement-ready references.
3. `measure` confirms critical dimensions and offsets.
4. `align` confirms read-only selector-pair alignment deltas for assembly interfaces or ref-to-ref positioning; it does not create source-level build123d joints or authored mates.
5. `frame` confirms world frame for occurrences or selected references.
6. `diff` compares before/after geometry for modifications.
7. Created or modified supported artifacts are handed to `$cad-viewer` for live viewer links when available.
8. Saved CAD `scripts/snapshot` packets are ALWAYS run for visible created or updated primary STEP/STP artifacts unless `snapshot-review.md` documents that no visible geometry changed or no valid artifact exists; when run, every visual concern is followed by a deterministic geometry check before it becomes a validation claim.

## Reference discovery

Compact facts and planes:

```bash
python scripts/inspect refs path/to/model.step \
  --facts --planes --positioning
```

Detailed selector inspection:

```bash
python scripts/inspect refs path/to/model.step '#selector' \
  --detail --positioning
```

Topology enumeration, only when needed:

```bash
python scripts/inspect refs path/to/model.step --topology
```

Plane options:

```bash
--plane-coordinate-tolerance FLOAT
--plane-min-area-ratio FLOAT
--plane-limit INT
```

Use lower plane limits and compact facts for normal validation. Use topology enumeration only for selector discovery, complex debugging, or when a feature cannot be verified through facts/planes/measurements.

## Measurement checks

Use `measure` for bounding distances, clearances, offsets, part spacing, plate thickness, hole-to-face distances, and alignment verification.

```bash
python scripts/inspect measure path/to/model.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis x
```

Axis may be inferred when possible, but specify `x`, `y`, or `z` for deterministic checks.

## Alignment checks

Use CLI `align` when two exported STEP references should be flush or centered. It returns a read-only translation delta; it does not edit source files and does not replace `AssemblyHelper`, authored mates, or native build123d joints in source. When source uses helper or build123d `Joint`/`connect_to()` placement, still validate the resulting exported geometry with `refs --positioning`, `frame`, `measure`, or CLI `align`.

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

Apply any required correction in the Python source using `AssemblyHelper` relationships, build123d joint definitions, `.connect_to()` calls, `Location`, parameter changes, or assembly child placement. Regenerate and re-inspect.

## Frame inspection

Use `frame` to validate occurrence transforms and selected-reference world frames:

```bash
python scripts/inspect frame path/to/model.step '#selector'
```

Frame output is useful for assemblies, part-local-to-world conversion, and placement debugging.

## Diff checks

For modification tasks, compare before and after artifacts:

```bash
python scripts/inspect diff path/to/before.step path/to/after.step --planes
```

Use diff when a repair, feature addition, or source edit could affect unrelated geometry.

## CAD Viewer handoff

For every final response involving a generated or modified supported artifact (`.step`, `.stp`, `.stl`, `.3mf`, `.dxf`, or native `.glb`), hand off the explicit artifact path to `$cad-viewer` when available and return the link it prints. If an important selector was inspected, return the local selector ref beside the owning CAD Viewer link.

Use `snapshot-review.md` to choose packet size and documented skip cases after deterministic checks. For visible created or updated primary STEP/STP artifacts, ALWAYS prefer CAD `scripts/snapshot` over manual viewer or Playwright inspection for visual feedback. Viewer handoff alone does not count as saved snapshot review.

## Validation report content

Report only checks that were actually run or directly supported by tool output.

Use this structure:

```text
Validation:
- STEP generation: passed/partial/failed
- Solids/assembly: <counts and labels>
- Bounding box: <dimensions and units>
- Major planes/refs: <summary>
- Positioning: <frame/measure/align results if relevant>
- Feature checks: <holes, cutouts, bosses, etc.>
- Visual review: `$cad-viewer` viewer link returned; CAD `scripts/snapshot` PNG/GIF included or skipped with reason; follow-up geometry checks for any visual findings
```

Do not claim:

- structural safety
- process certification
- tolerance compliance
- manufacturability beyond geometric plausibility
unless the relevant analysis or manufacturing data was explicitly performed.
