# Inspection and validation

Read this file for every generated STEP artifact and whenever the user asks for geometry facts, references, dimensions, mating, diffing, or frame inspection.

## Principle

Deterministic geometry checks decide pass/fail; mandatory snapshot review (see `snapshot-review.md`) catches semantic errors the deterministic checks did not encode. Scale the deterministic checks to the user's spec: every dimension, clearance, or relationship the user specified — including dimensions taken from a technical drawing — must be verified with `measure`, `align`, or `frame`. The facts/planes/positioning baseline runs for every generated artifact regardless of spec.

## Tool

The launcher lives in the CAD skill directory:

```bash
python scripts/inspect {refs|diff|frame|measure|align|worker|batch} ...
```

Inspection targets resolve from the command cwd; prefer cwd-relative target paths. Absolute paths are accepted when they point under the command cwd (they are relativized); an absolute path outside the cwd fails with an explicit error — run the command from the workspace that owns the artifact. Common data-output flags: `--format json|text` (default is machine-readable), `--quiet`, `--verbose`.

Accepted target forms:

```text
path/to/entry
path/to/entry.step
path/to/entry.step.py
```

A `<name>.step.py` generator target resolves to the same entry as its logical `<name>.step`, and keeps resolving to the generator entry even when a same-stem exported `.step` file exists beside it.

Selector-backed queries (`refs --facts`, planes, measures) on generated assemblies extract whole-model topology on demand and cache it as `topology.glb` inside the entry's render package; repeat queries read the cache (seconds instead of a full re-extraction) until the package is rebuilt, which invalidates the sidecar.

Selector refs are local to the STEP/CAD entry target passed to the command. They do not include file paths:

```text
#o1.2
#o1.2.f1
#f1
```

Pass selector refs as `#...` tokens. The STEP/CAD file path or entry target is a separate CLI argument.

## Validation sequence

1. Generation completed and the STEP/STP file exists.
2. `refs --facts --planes --positioning` confirms scale, labels, major planes, and placement-ready references. Run this for every generated artifact.
3. `validate` confirms the geometry is sound: valid topology, closed shells, no self-intersection, and positive volume on every solid. Run this for every generated artifact.
4. Spec-driven checks: `measure` for every user-specified dimension, offset, or clearance; `align` for interfaces that should be flush or centered; `frame` for orientation and occurrence-placement expectations; `diff` for modifications that could affect unrelated geometry.
5. Snapshot the primary STEP/STP per `snapshot-review.md`, then convert every visual concern into a deterministic geometry check before it becomes a validation claim.

### `refs --facts` "ok" is not a geometry claim

`refs --facts` reports counts, bounds, labels and references. Its `ok` field is
a command-success flag: it is true when every requested ref resolved, and it
says nothing about whether the geometry is sound. A five-face open box reports
`"ok": true` with `"faceCount": 5`, and a solid with inverted orientation —
which renders as a hole in the world — reports `"ok": true` as well.

Use `validate` for that question:

```bash
python scripts/inspect validate models/part/part.step.py
python scripts/inspect validate models/part/part.step.py --refs o1.2      # one subassembly
python scripts/inspect validate models/panel/panel.step.py --allow-open   # surfaces intended
```

It reports, per occurrence, any of `invalidTopology`, `openShell`,
`nonPositiveVolume`, `noSolid`, `selfIntersecting`, and exits non-zero when any
occurrence fails.

Two subtleties worth knowing. `BRepCheck_Analyzer` returns **true** for a
reversed solid, so topological validity alone cannot catch an inverted body —
only the sign of the volume can. And volume is measured per solid, never
aggregated: a `+1000` and a `-1000` inside one compound sum to zero, so any
check reading a compound's total volume sees nothing wrong.

Pass `--skip-self-intersection` on large assemblies if the boolean test
dominates runtime.

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

Use lower plane limits and compact facts for normal validation. Use topology enumeration only for selector discovery, complex debugging, or when a feature cannot be verified through facts/planes/measurements; it can be expensive on large models.

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

Use `align` when two exported STEP references should be flush or centered. It returns a translation delta between the selected refs; apply any required correction in the build123d source (see `positioning.md`), regenerate, and re-inspect.

```bash
python scripts/inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

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

## Validation report content

Report only checks that were actually run or directly supported by tool output. If an important selector was inspected, return the local selector ref beside the owning CAD Viewer link.

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
