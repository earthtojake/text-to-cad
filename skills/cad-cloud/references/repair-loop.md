# Repair loop

Use the failing result and the geometry to localize the problem, correct the
responsible source, then build again with `base` and only the corrected files.
Preserve specified features and dimensions, and disclose any necessary deviation.
Never resubmit unchanged source expecting a different result.

## Build failures

A failed build reports the error with its file, line and message, and the tail
of the build log. Read both before editing. An error from the model comes back
with the file and line of the innermost frame in your own scripts.

| Symptom | Likely cause and fix |
| --- | --- |
| `ModuleNotFoundError` for your own module | The file was not sent, or its folder is not on the import path. Send it, keep helpers beside or below the entry's folder, or set `pythonpath`. |
| `ModuleNotFoundError` for a third-party package | It is not installed and builds have no network. Use the standard library, build123d and what cadgen carries, or write the function. |
| `FileNotFoundError` for a STEP or data file | A build reads only the files you sent. Add the file to `files` and anchor its path on `__file__`. |
| "No viewable CAD file was written" | `__main__` does not call the decorated model, the model declares no outputs, or `out=` points somewhere else. Function names are not discovered by convention. |
| Syntax or import error | Use the traceback's file and line. Keep geometry creation inside model functions and their helpers. |
| A model refused its return or parameters | A model returns a bare build123d shape and takes no arguments: move parameters into a factory function. |
| "ran out of time" | The job hit its time cap, which a nearly spent daily allowance also shortens. Make the model cheaper (fewer features, coarser detail), split a heavy part into its own model, or do less per call. |
| "dropped (not CAD outputs)" | A build keeps CAD documents, meshes, drawings, sidecar JSON, images and text such as CSV. Other files a script writes are dropped. |
| "tried to use the network" | The sandbox has none. Send the data as files. |
| "could not run" or "stopped reporting" | The server failed, not the model. Build again with the same files; only a model's own failure comes back for an identical submission. Say so if it repeats. |
| "already have a build running" | One build at a time, and one snapshot or inspection at a time, per user. Wait for it with `cad_status`, then send the request again. |
| An error naming a cap (files, size, daily allowance) | Drop files the build does not read, or tell the user when the allowance resets (the message says). Do not retry before then. |
| "The link cannot show the model yet" | The build succeeded but its viewer export failed (the message says why). Outputs, snapshots and inspections still work; tell the user the link is not ready. |

## Geometry failures

| Symptom | Useful checks and possible remedies |
| --- | --- |
| Missing or invalid body | Check profile closure, cut placement, zero thickness and the first failing operation. Use the diagnostics in [inspection](inspection.md). |
| Missing hole or pocket | Check the feature mode, selector, cut depth and the intended through-condition against the saved geometry. |
| Wrong scale or extents | Check units, radius versus diameter, primitive alignment and extrusion direction; measure the dimensions. |
| Fillet or chamfer failure | Check edge selection and local space. Consider feature order or an equivalent profile construction. Change a required radius only as an explicit design decision. |
| Loft failure or distorted surface | Inspect wire correspondence, winding, self-crossings and disconnected sections. Prefixes or adjacent pairs can localize the problem; a successful pair does not prove a valid full loft. |
| Slow Boolean | Time the suspect operation. Consider simpler surfaces, tool extents, batching or staged cuts while preserving the required feature. |
| Selector no longer matches | Resolve again in the new build, enumerate candidates and measure them: numeric refs belong to one build. |
| Assembly placement mismatch | Check local datums, fixed and moving order, axis direction and transform composition. Measure the signed gaps and angles on the saved geometry. |

Construction pitfalls are in [model files](model-files.md#construction-notes).

## Snapshot and inspection failures

- A snapshot takes a saved output. Check `file` against the build's file list
  (`cad_files`) and the flags against [snapshots](snapshots.md): the error names
  the refused value. Try one supported view to isolate a request error, then
  restore the views the review needs.
- An inspection that runs out of time does too much in one call. Check one
  subassembly, filter candidate pairs with `bounding_box(optimal=False)`, or
  split the script across calls.

## Check the repair

When a repair could affect other geometry, compare the builds before and after:
resolve labels independently in each, and compare the dimensions, volumes or
relationships that should stay the same. For shape changes, native Boolean
differences show both added and removed material.

Report what failed, what was repaired and verified, and which requirements
remain untested or unresolved. Name any output that remains usable.
