# Repair loop

Use the failing command and geometry to localize the problem, correct the
responsible source or arguments, then rerun the failed and affected checks.
Preserve specified features and dimensions; disclose any necessary deviation.

## Source and build failures

- **Syntax or import error:** use the traceback to correct the source or
  dependency. Keep geometry creation inside model functions and their helpers.
- **Script exits without outputs:** confirm `__main__` calls the decorated model,
  that it returns a native shape, and that its decorators declare the intended
  outputs. Function names are not discovered by convention.
- **Unexpected freshness:** run `cadgen store why <model>.py`; check tracked
  inputs and whether the parent was rerun after a child changed. See the
  [model contract](step-generation.md#freshness-cadgen-store-why).
- **Installation or version mismatch:** run `cadgen doctor <skill-dir>` and
  follow the specific error. See [migrations](migrations.md).

## Geometry failures

| Symptom | Useful checks and possible remedies |
| --- | --- |
| Missing or invalid body | Check profile closure, cut placement, zero thickness and the first failing operation. Use the Python diagnostics in [inspection](inspection-and-validation.md). |
| Missing hole/pocket | Check feature mode, selector, cut depth and the intended through-condition against the saved geometry. |
| Wrong scale or extents | Check units, radius versus diameter, primitive alignment and extrusion direction; measure the relevant dimensions. |
| Fillet/chamfer failure | Check edge selection and local space. Consider feature order or equivalent profile construction. Change a required radius only as an explicit design decision. |
| Loft failure or distorted surface | Inspect wire correspondence, winding, self-crossings and disconnected sections. Prefixes or adjacent pairs can localize the problem; a successful pair does not prove a valid full loft. |
| Slow Boolean | Time the suspect operation or inspect a stack sample. Consider simpler surfaces, tool extents, batching or staged cuts while preserving the required feature. |
| Selector no longer matches | Reopen with `read_scene`, enumerate candidates, and measure their geometry. Numeric refs are revision-scoped. |
| Assembly placement mismatch | Check local datums, fixed/moving order, axis direction and transform composition. Measure the required signed gaps and angles on saved geometry. |

Version-specific pitfalls and construction alternatives are in
[build123d modeling](build123d-modeling.md). For assembly corrections, see
[positioning](positioning.md).

## Viewer and snapshots

Use `$cad-viewer` for launcher or review-link troubleshooting. If unavailable or
startup fails, report the failure and use Python geometry checks plus snapshots.
Do not reconstruct viewer URLs from a separate convention here.

Snapshot commands take saved documents, not model scripts. Run the model first
when its output is missing; otherwise verify the input format/path, Chromium
installation and the reported options. Missing derived render data is compiled
on demand; adjacent GLB/topology files are not a prerequisite. Try a single
supported view when isolating a request error, then restore the views needed
for the review. See [snapshot review](snapshot-review.md).

## Check the repair

When a repair could affect other geometry, compare before/after documents using
`read_scene` and the dimensions, volumes or relationships that should remain
invariant. Resolve labels independently in each revision. For shape changes,
native Boolean differences can show both added and removed material.

Report what failed, what was repaired and verified, and which requirements
remain untested or unresolved. Identify any artifact that remains usable.
