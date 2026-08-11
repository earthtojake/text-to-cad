# Repair loop

Read this file when generation, export, inspection, positioning, snapshot review, CAD Viewer setup, or documentation validation fails.

## Loop

1. Read the failing command output.
2. Classify the failure.
3. Make the smallest responsible source or command change.
4. Rerun the failed command.
5. Rerun any dependent validation checks.
6. Report remaining risk or deliberate deviations.

## Failure classes and fixes

### Multi-section loft: "Failed to create valid loft" / "Recovery failed"

The message names neither the station nor the cause. Two checks, in this order:

1. **Loft increasing PREFIXES** (`faces[:5]`, `[:10]`, `[:20]`, …) to bracket
   where it breaks, and watch the reported volume as well as the exception — a
   loft that "succeeds" with an absurd volume is already failing.
2. **Loft every ADJACENT PAIR.** If every pair succeeds but the full set fails,
   the sections are individually fine and the problem is global — almost always
   that sections disagree on POINT COUNT. Guarantee a fixed sample count per
   section.

Two silent causes worth ruling out before either:

- **A section that is genuinely disconnected** (two closed regions — e.g. a
  station cutting two separate nacelles, or crossing an open slot) produces a
  `Face` that raises nothing and reports a plausible area; only `Face.is_valid`
  is False. The loft then fails dozens of stations away. End the loft at the last
  connected station, or bridge the gap in the section and cut it back afterwards.
  (`Face.is_valid` is a PROPERTY — calling `f.is_valid()` raises
  `TypeError: 'bool' object is not callable`, which reads like a corrupt object.)
- **Samples dropped where a component does not exist** make counts vary station
  to station. Carry a value rather than dropping the sample.

### Boolean against a large lofted surface never returns

A subtract against a single large B-spline surface costs a full-surface
classification PER TOOL and grows superlinearly in tool count — measured on one
~4,900-control-point skin: 1 tool 24 s, 4 tools 70 s, 41 tools did not finish in
15 minutes, and a 44-tool build ran over seven hours without completing. Batching
into one list operand does NOT help; the cost is per tool, not per accumulation.

Confirm rather than guess: the process stays at ~100 % CPU with the progress file
frozen on its first phase, and a stack sample shows `Extrema_ExtPS::Perform` with
`BSplSLib_Cache::BuildCache` rebuilding on nearly every evaluation.

Fix by not cutting: shallow cosmetic recesses do not need to be booleans at all.
At 19 m rendered to 1920 px, 1 px is ~10 mm, so a 4 mm groove is sub-pixel and
reads only because the edge overlay draws feature edges. Keep booleans for
openings that change the silhouette, and build the rest additively.

### Source import or syntax failure

Likely causes:

- invalid Python syntax
- missing import
- wrong build123d symbol
- function not named `gen_step()`
- executable code outside the intended function has side effects

Fix:

- correct imports and syntax
- ensure `gen_step()` returns the STEP-ready shape or compound
- keep output paths in CLI commands, not inside `gen_step()`

### Invalid or missing geometry

Likely causes:

- open sketch
- subtractive profile outside target
- zero thickness
- boolean operation failed
- construction geometry used as exported geometry

Fix:

- close profiles intended to become faces
- verify dimensions are positive
- make subtractive tools pass through when through-cuts are intended
- simplify the failing feature and rebuild incrementally

### Fillet or chamfer failure

Likely causes:

- radius/length exceeds local geometry
- selected edges include tiny or unintended edges
- boolean operation created complex edge topology

Fix:

- reduce radius/length
- filter selected edges more narrowly
- apply fillets later in the model
- split edge groups by feature intent

### Wrong scale or bounding box

Likely causes:

- units mismatch
- mistaken diameter/radius
- extrusion direction or amount wrong
- part not centered as assumed
- direct imported STEP uses unexpected units

Fix:

- check parameter values
- inspect facts and planes
- measure critical extents
- correct source dimensions or import handling

### Missing feature

Likely causes:

- wrong `Mode.ADD`/`Mode.SUBTRACT`
- feature profile not inside target
- blind cut too shallow
- selector changed after prior operation

Fix:

- confirm feature mode
- increase cut length for through-cuts
- inspect topology or planes
- regenerate and measure/check feature-specific refs

### Selector fragility

Likely causes:

- arbitrary index selection
- topology changed after fillet or boolean
- similar faces/edges are indistinguishable

Fix:

- select by axis, plane, position, normal, or inspected reference
- use `refs --facts --planes --positioning` to rediscover stable references
- add construction datums or simplify operations if needed

### Positioning or joint mismatch

Likely causes: wrong part-local origin or datum, reversed `AssemblyHelper` fixed/moving order, `.connect_to()` moving the wrong part, inverted joint axis, sign errors in symmetric placement, an explicit `Location` not recomputed after a parameter change, or a joint defined in world coordinates when a part-local datum was intended.

Fix:

- inspect `refs --positioning`, then `frame` and `align` on the relevant selectors
- verify the source-level `AssemblyHelper` target order, joint labels, and `joint_location` definitions
- apply the smallest source correction from the list in `positioning.md` (Source-level positioning corrections)
- regenerate the assembly from the Python source and rerun the failed check

### CAD Viewer startup or link failure

Likely causes:

- Node/npm unavailable
- CAD Viewer app not built or cannot start
- Viewer URL path is not the project's absolute model directory
- returned link is missing `?file=`, or its `file=` is not relative to that directory

Fix:

- rebuild each link as `<viewer-origin><absolute-model-directory>?file=<path relative to it>`
- return one documented Viewer link per requested file
- if unresolved, report the startup failure and rely on CLI facts/measurements plus snapshots for validation

### CAD `scripts/snapshot` failure

Likely causes:

- target input path is wrong, missing, or not a STEP/STP file or same-stem Python generator
- adjacent CAD Viewer GLB/topology artifact missing
- invalid render flags

Fix:

- generate STEP first, then snapshot the primary `.step`/`.stp` artifact
- retry only with simpler supported snapshot jobs, starting with a single `view` output before wireframe display or `section`
- choose modes and packet size per `snapshot-review.md`

## Diff after repair

Use `diff` when the fix might have affected unrelated geometry:

```bash
python scripts/inspect diff path/to/before.step path/to/after.step --planes
```

## Reporting failed repairs

If a check cannot be repaired in the current environment, report:

```text
- what failed
- what was tried
- which artifact is still usable
- which validation claims cannot be made
- what the next source-level correction should be
```
