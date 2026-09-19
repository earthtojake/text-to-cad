# Inspection and validation

Read this file for every generated STEP artifact and whenever the user asks for geometry facts, references, dimensions, mating, diffing, or frame inspection.

## Principle

Deterministic geometry checks decide pass/fail; mandatory snapshot review (see `snapshot-review.md`) catches semantic errors the deterministic checks did not encode. Scale the deterministic checks to the user's spec: every dimension, clearance, or relationship the user specified — including dimensions taken from a technical drawing — must be verified with `measure`, `align`, or `frame`. The facts/planes/positioning baseline runs for every generated artifact regardless of spec.

## Tool

The launcher lives in the CAD skill directory:

```bash
cadgen step inspect {refs|diff|frame|measure|align} ...
```

Targets take native path semantics, like every other cadgen path argument: a relative target resolves against the command cwd, an absolute target works from anywhere, and `~` expands. A target naming a file that does not exist reports file-not-found for that path. Prefer cwd-relative targets from the workspace that owns the artifact anyway — reports name a target by its cwd-relative path when it is inside the cwd, and by its bare file name when it is not, so cwd-relative targets read better in a report. Common data-output flags: `--format json|text` (default is machine-readable), `--quiet`, `--verbose`.

Accepted target forms:

```text
path/to/document.step
path/to/document.stp
```

Targets are documents, spelled with their extension: a bare `<name>` and a `.py`
model script are refused (run `python <model>.py`, then inspect the STEP it
wrote). A door never opens the scripts beside a document to learn which one
wrote it.

Selector-backed queries (`refs --facts`, planes, measures) resolve from the document's tree in the store — its per-component `.surf` objects — on demand; a document with no tree yet is compiled from its bytes first, generated or imported alike. There is no separate topology sidecar to build or invalidate, and a document is never refused for being behind its script.

Selector refs are local to the STEP/CAD entry target passed to the command:

```text
#o1.2
#o1.2.f1
#f1
```

Pass selector refs as `#...` tokens. The STEP/CAD file path or entry target is a separate CLI argument.

An occurrence ref may name a **subassembly** as well as a part — the same `#o1.4` the CAD
Viewer copies, `snapshot --focus` takes, and a kinematics mate poses. A subassembly owns no
geometry of its own, so it resolves as the parts beneath it: `refs` reports one entry per
part (each tagged `fromGroup`), and `measure`/`align` use the branch's combined extent.
`frame` answers for the branch — its name from the instance tree, plus the extent and
center of its parts; a subassembly has no transform of its own, because group placement is
baked into each part's absolute transform. Counts (`occurrenceCount`, `refs --facts`) stay
leaf-based. An occurrence ref that names nothing lists what the document does have at that
depth.

### File-prefixed refs (the CAD Viewer copy format)

A ref copied from the CAD Viewer carries the file it came from, so it stays meaningful in a
prompt that spans several files:

```text
bracket#o1.2.f1               the generator src/bracket.py
imported_housing.step#o1.3    a raw STEP, STEP/imported/imported_housing.step
mounting_plate.stl#           a whole mesh file
```

The prefix is the **shortest path suffix that names exactly one file**, plus as many leading
directories as it takes to be unique. A prefix with no selectors after the `#` names the whole
file.

A `.py` generator shows as a bare stem, because generators are what you normally work in
and the common case deserves the shortest name. Everything else keeps its suffix:

| File | Prefix |
| --- | --- |
| `bracket.py` | `bracket` |
| `bracket.step`, `bracket.stp` | `bracket.step`, `bracket.stp` |
| `plate.stl`, `plate.3mf`, `plate.glb`, `outline.dxf` | unchanged |

Keeping those suffixes is what makes the stripping safe: `bracket` (the generator) stays
distinct from `bracket.step` (its export) and from `bracket.stl` (a mesh of it).

**These CLIs do not resolve prefixes. You do.** When you receive a file-prefixed ref:

1. Split it at the first `#`. The left side is the file prefix; the right side is the ref.
2. Resolve the prefix to a real path. A bare stem is **not** a literal path suffix, so expand
   it before searching:
   - `<name>` with no extension → the model script `<name>.py`; its DOCUMENT (the sibling
     `<name>.step` by default, or the decorator's `out=` target) is what the commands take
   - anything carrying a suffix (`.step`, `.stp`, `.stl`, `.3mf`, `.glb`, `.dxf`) → use as-is

   Match on **segment boundaries**, so `plate.stl` names `STL/plate.stl` and never
   `STL/mounting_plate.stl`.
3. Pass the resolved document as the entry/input argument and the `#...` part as the ref,
   exactly as you would for a bare ref.

```bash
# received: bracket#o1.2.f1   ->  expand the bare stem, then search
git ls-files '*/bracket.py'
cadgen step inspect refs STEP/bracket.step '#o1.2.f1'
```

If the search returns more than one file the prefix was ambiguous — ask rather than guess; the
Viewer only emits prefixes that were unique when it copied them.

Passing the prefixed ref through unsplit also works **when the prefix names the file the
command already targets** — the CLI strips it, and it accepts every spelling of that file
(`bracket`, `bracket.py`, `bracket.step`). A prefix naming a *different* file is a hard
error, never ignored: silently inspecting the file the command was pointed at would produce a
confident answer about geometry nobody asked about.

```text
ref 'other_part#o1.2' names file 'other_part' but this command targets
'STEP/bracket'; pass the file as the entry argument and the '#...' part as the ref
```

Bare `#...` refs are unchanged and work everywhere they always did.

### Referencing a part by its label

A part's build123d label can stand in for its occurrence id anywhere a ref is accepted:

```text
#eye_shank             the part labelled eye_shank
#eye_shank.f45         a face on it
#eye_shank.f45,f46     two faces on it -- the label carries forward like an occurrence id
```

Numeric refs are unchanged and always work; labels are an additional spelling, not a
replacement. `snapshot --mode list` shows each part's `name`, and `inspect refs` reports the
exact ref to paste as `labelRef`.

A label may contain letters, digits, `_` and `:`, and may not start with a digit. Parts whose
label cannot be spelled that way, or which collides with the numeric grammar (`f12`, `o1`,
`m2`), are addressable by their numeric ref only.

When several parts share a label -- two wheels, one `cast_rim:5spoke` -- each gets a numbered
ref in tree order and the bare label refuses to resolve rather than guessing:

```text
$ cadgen step snapshot motorbike.step --focus '#cast_rim:5spoke'
selection.focus label 'cast_rim:5spoke' matches 2 occurrences;
use one of: #cast_rim:5spoke_1 (o1.7.2), #cast_rim:5spoke_2 (o1.14.2)
```

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
cadgen step inspect validate models/part/part.step
cadgen step inspect validate models/part/part.step --refs o1.2      # one subassembly
cadgen step inspect validate models/panel/panel.step --allow-open   # surfaces intended
cadgen step inspect validate models/rig/rig.step --out validate.json  # keep a partial on a kill
```

It reports any of `invalidTopology`, `openShell`, `nonPositiveVolume`,
`noSolid`, `selfIntersecting`, and exits non-zero when any occurrence fails.
Each `parts` entry is one finding on one shape: `ref`/`name` is the placement
the checks ran on, and `occurrences` lists every placement the finding applies
to (`failureCount` counts occurrences, `prototypeCount` unique shapes).

Two subtleties worth knowing. `BRepCheck_Analyzer` returns **true** for a
reversed solid, so topological validity alone cannot catch an inverted body —
only the sign of the volume can. And volume is measured per solid, never
aggregated: a `+1000` and a `-1000` inside one compound sum to zero, so any
check reading a compound's total volume sees nothing wrong.

Large assemblies: a part placed a hundred times is ONE shape with a hundred
locations, so topology, closure, solid presence and volume are checked once per
unique shape, in parallel across a process pool (`CADGEN_VALIDATE_WORKERS`
sizes it; `1` runs in-process). The self-intersection test is numeric and can
differ by placement — the same bolt has failed at 15° and 30° of tilt and passed
upright — so by default it runs once per shape at its first placement and the
report says so (`"selfIntersectionCheck": "first-placement"`). Pass
`--every-placement` to run it on every copy (a `selfIntersecting` entry then
lists exactly the placements that failed), or `--skip-self-intersection` to drop
the test when it dominates runtime. Progress paints on stderr per shape;
`--out PATH` also writes the report after every shape with `"partial": true`
until the run completes, so a run that is killed (out of memory, a lost daemon
worker) leaves the findings it reached.

`validate` and `interfere` measure the document ON DISK: it is loaded as
written and runs no Python, even when its script has changed since — a door
never rebuilds a model. Rerun the script first when you want the new geometry
measured. A document the store has never seen (one edited or written by another
tool) is compiled from its bytes on demand, like an import.

### `interfere`: do two parts occupy the same space?

```bash
cadgen step inspect interfere STEP/arm.step --tolerance 0.01
cadgen step inspect interfere STEP/arm.step --refs o1.7            # inside one subassembly
cadgen step inspect interfere STEP/arm.step --refs o1.3,o1.9       # two named parts, as wholes
```

`interfere` intersects every candidate pair of solids (a world-bbox reject runs
first) and reports the pairs whose common volume exceeds `--tolerance` in mm^3.
Touching faces yield hairline slivers, so the default is 1 mm^3; go lower for
small parts.

The unit of the verdict is the **part**: a direct component of the document
root, or of the ref you name with `--refs` (the deepest common ancestor when you
name several). A purchased servo arrives as a sub-assembly whose motor sits
inside its case by construction, and a weldment is several solids in one
product — bodies of one part overlap and always will, and a STEP document
cannot tell a vendor sub-assembly from one you authored. So overlaps between
bodies of the same part are still computed but reported separately, as
`intraPartOverlaps` in `--json` and a per-part summary in text; they never
fail the check. `clashes` — the ones that fail it — are between two different
parts. To test a part's own bodies against each other, name that part alone:
`--refs o1.18`.

Fewer than two bodies, or all bodies in one part, is `INCONCLUSIVE` with
`ok:false`, not a pass: nothing that could fail was tested.

## Reference discovery

Compact facts and planes:

```bash
cadgen step inspect refs path/to/model.step \
  --facts --planes --positioning
```

Detailed selector inspection:

```bash
cadgen step inspect refs path/to/model.step '#selector' \
  --detail --positioning
```

Topology enumeration, only when needed:

```bash
cadgen step inspect refs path/to/model.step --topology
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
cadgen step inspect measure path/to/model.step \
  --from '#selector_a' \
  --to '#selector_b' \
  --axis x
```

Axis may be inferred when possible, but specify `x`, `y`, or `z` for deterministic checks.

## Alignment checks

Use `align` when two exported STEP references should be flush or centered. It returns a translation delta between the selected refs; apply any required correction in the build123d source (see `positioning.md`), regenerate, and re-inspect.

```bash
cadgen step inspect align path/to/assembly.step \
  --moving '#moving_selector' \
  --target '#target_selector' \
  --mode flush \
  --axis z
```

## Frame inspection

Use `frame` to validate occurrence transforms and selected-reference world frames:

```bash
cadgen step inspect frame path/to/model.step '#selector'
```

Frame output is useful for assemblies, part-local-to-world conversion, and placement debugging.

## Diff checks

For modification tasks, compare before and after artifacts:

```bash
cadgen step inspect diff path/to/before.step path/to/after.step --planes
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
- Visual review: `$cad-viewer` viewer link returned; CAD `cadgen step snapshot` PNG included or skipped with reason; follow-up geometry checks for any visual findings
```

Do not claim:

- structural safety
- process certification
- tolerance compliance
- manufacturability beyond geometric plausibility
unless the relevant analysis or manufacturing data was explicitly performed.
