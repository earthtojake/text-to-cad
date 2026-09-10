---
name: cad
description: Create, modify, inspect, and validate parametric CAD parts and assemblies authored as cadgen model scripts. Use for natural-language CAD specs, reference images, 2D technical drawings, STEP/STP generation or direct inspection, Python CAD source, source-level joints, selector references, geometry facts, measurements, mating deltas, snapshots, and STL/3MF/native GLB outputs from CAD geometry. Also covers project structure for multi-part CAD work - src/ for model scripts and shared code, format folders (STEP/, DXF/, STL/) for raw outputs, naming, and commit policy for projects with several @step/@dxf model scripts and imported source files; use it when starting a CAD project with more than a couple of models, when asked how to organize CAD code and artifacts, or when growing a flat folder of models into a project.
---

# CAD generation, inspection, and validation

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Setup

This skill's commands are thin entrypoints over the `cadgen` distribution, which
carries the Python build runtime and the JavaScript it executes. Install it once:

```bash
python -m pip install -r requirements.txt
```

Rendering additionally needs a browser, which pip cannot supply:

```bash
python -m playwright install chromium
```

## Purpose

Create or modify parametric CAD models from natural-language requirements, build validated STEP/STP (or mesh) outputs, inspect geometry references, and return checked outputs. STEP is the default output of CAD geometry and the one the inspection tools read; STL, 3MF, and native GLB are mesh outputs a model declares beside it — or instead of it, when the part is print-only. For assemblies, prefer `cadgen.assembly.AssemblyHelper` with source-level build123d joints, named mating datums, and native labels when the parts have functional assembly relationships.

There are two ways into the STEP workflow: build from a build123d model script (the default when designing from scratch or modifying a generated model), or import an existing STEP/STP file directly (when no script exists or the user explicitly targets the STEP file). Both are inspected, snapshotted and exported the same way.

## Use this skill when

Use this skill when the user asks for CAD files, STEP/STP files, build123d source, selector refs such as `#o1.2.f1`, mechanical parts, assemblies, enclosures, brackets, fixtures, holes, counterbores, countersinks, slots, pockets, bosses, standoffs, ribs, fillets, chamfers, shells, source-level joints, mating, or measurements. Also use it when the user supplies reference images or 2D technical drawings of a part to reproduce or take design intent from.

Also use it when the user asks for STL, 3MF, or native GLB output from CAD geometry; load `supported-exports.md` for details. For 2D DXF drawings, use the `$dxf` skill; when a DXF projects from a 3D part, this skill owns the part and `$dxf` owns the drawing.

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

The command surface (the `cadgen` console script, installed with the package):

```bash
python <model>.py            # its __main__ calls the model, which builds it
cadgen step build IN OUT     # re-emit an existing STEP as a new one, with kinematics
cadgen stl build ...         # one door per mesh format; `3mf` and `glb` are the others
cadgen step inspect ...      # refs, measure, align, frame, diff
cadgen step snapshot ...     # PNG visual review packets, for STEP
cadgen stl snapshot ...      # the same, for a mesh file; `3mf` and `glb` again
cadgen store why <model>.py  # why the model is stale or current, clause by clause
cadgen daemon status         # the warm workers and the jobs they are running
```

**Scripts are RUN; commands take DOCUMENTS.** `python model.py` is the one
source door — it writes every output the model declares and (only when the
model declares kinematics, animation, or mesh exports) its sidecar. Every
command above takes a `.step`/`.stl`/`.dxf` FILE, and one handed a `.py` says
so. A door asks one question of a document: does the store have a tree for
this file's bytes? If so it reads it; if not it compiles one from the bytes as
a job in the pool — generated or imported alike. **A door never refuses a
document and never runs a script.** Whether a document is behind its script
is the model's business (`cadgen store why`), not the door's.

Use the active project Python interpreter; treat `python` in examples as an interpreter placeholder. Every operational verb is a `cadgen` subcommand (`python -m cadgen.cli <verb>` is the PATH-independent equivalent). Use `cadgen <verb> --help` for the complete current interface; reference docs show recommended workflows, not every flag. Install per `requirements.txt`; `cadgen doctor <skill-dir>` verifies the installed cadgen matches this skill's pin (docs drift silently on a mismatched install).

Target paths resolve from the command's current working directory, not from the skill directory. Run commands from the workspace that owns the artifacts and pass cwd-relative target paths so project CAD files never resolve accidentally under the skill directory.

CAD references are `#...` selector tokens local to a target, for example `#o1.2` or `#o1.2.f1`. Pass the STEP/CAD file as a separate target argument when using CAD CLIs.

## A model

Generation has NO CLI. A model is a plain Python script: one parameterless
decorated function, built by calling it from `__main__`:

```python
from cadgen import build123d as bd
from cadgen import step

WIDTH = 10.0


@step                      # or @step(out="../STEP/bracket.step") to relocate the output
def bracket():
    return bd.Box(WIDTH, 10, 10)


if __name__ == "__main__":
    bracket()
```

The rules, each enforced by the decorator or the build:

- **The decorator only declares; a call builds.** Importing a model module
  never builds; a file without `if __name__ == "__main__": <model>()` never
  builds either — always end the script that way. `python bracket.py` writes
  `bracket.step` beside the script and the model's result into the store; an
  unchanged model is a fast no-op. `--force` rebuilds this model only.
- **A model takes no parameters** and its function is called with no
  arguments. Parametric geometry lives in a plain factory the model calls
  with its values (`def _bracket(width, thickness): ...`); another
  configuration is another model in another file, the way two part numbers
  are two parts.
- **The return is a bare build123d `Shape`** — a solid, a compound, or a
  labeled assembly compound. Never a dict, never a path.
- **Outputs are exactly what the decorators declare.** `@step` writes the
  `.step`; `@stl`/`@threemf`/`@glb` stacked on it write meshes. **STEP is not
  required**: a function with only `@stl` (or `@glb`, `@threemf`) — no `@step`
  — is a full model with the same tree, record, build and no-op, whose outputs
  are the meshes and which writes no `.step` and no sidecar. Use it for
  print-only parts and render assets. `references/supported-exports.md`.
- **Decorator arguments never change the geometry.** They decide where the
  files land (`out=`), how they are written (`mesh_tolerance=`,
  `mesh_angular_tolerance=`) and what the sidecar declares (`kinematics=`).
  The geometry is the return value and nothing else: a `Compound` placing
  children is packaged as occurrences, a single solid as one component, and
  `part`/`assembly` is read off the tree. There is no `kind=` and no bake
  point — a posed or differently configured export is authored geometry, or
  another model.
- **A sidecar only when strictly necessary.** `<name>.step.json` is written
  only when the model declares `kinematics=`; a model that declares none has
  no sidecar, and a rebuild that dropped the declaration deletes the stale
  file. What a model declares about its outputs lives in its record, not in
  a file beside the geometry.
- **One model per file, as a rule of thumb.** A model's identity is its file
  plus its function (`plate.py::plate`); a file holding one model is named by
  its path alone. A file MAY hold several (a small family of variants): each is
  its own record, output and job (a sole model writes `<file>.step`; models sharing a
  file write `<function>.step`), but
  they share the file's closure, so editing one rebuilds them all — which is
  why one per file is the recommendation.
- **Composition is a call.** Import a sibling model and call it inside your
  body (`from arm import arm` … `arm()`); it returns the child's geometry.
  `references/step-generation.md` has the whole composition contract.
- **`from cadgen import build123d as bd`** is the canonical import — a lazy,
  transparent re-export of build123d (same names, same behaviour) — so the
  freshness gate and the warm-worker handoff run before any kernel import is
  paid. Raw `import build123d` works but costs ~2.5s on every re-run.
- Per-run flags ride the script's argv: `--force`, `--json`, `--verbose`,
  `--mesh-tolerance`, `--mesh-angular-tolerance`.

## Composition, freshness and builds

The essentials; `references/step-generation.md` has the code and the edge cases.

- **Children are models you call.** A parent's body imports sibling models
  and calls them; each call returns that child's geometry (built if stale,
  loaded from the store if current), and the parent's result LINKS to the
  child's — stored once, shared by every parent. Place a child with
  `Pos/Rot/Location * child` or `child.moved(loc)`; never `child.located(loc)`
  (it deep-copies the geometry, so the parent owns a copy instead of linking).
- **Every build is parallel.** A child call submits the child's build and
  returns at once; siblings build on their own workers while the body keeps
  going; the parent waits when it first reads the geometry — normally the
  closing `bd.Compound(children=[...])`. Nothing to configure, nothing to
  annotate.
- **Builds never wait on or cancel each other.** Two runs of one model both
  run; the store keeps the result whose sources match the files as they are
  now, so the disk ends at the newer source. Editing a child while its parent
  builds leaves the parent finished against the child it pinned.
- **A rebuilt part does not update the assemblies that use it.** Dependency
  is pull: rebuild the parent (`python assembly.py`) to pick up a child's
  change. A child edit that yields identical geometry leaves parents current.
- **What a rebuild tracks — models by result, constants by value, functions by
  file.** Importing a model function tracks that model by its result;
  importing a module-level literal (`from plate import WIDTH`) tracks the
  value; importing anything else from a file (a helper function, a `bd.`
  object) makes that whole file part of your model's source, so any edit to it
  rebuilds you. Shared constants may live in a model file or in `lib/`.
- **The environment is not an input.** Model and `lib/` code takes no
  parameter from `os.environ`, the working directory, the current time or a
  random source: the gate tracks source by hash, constants by value and children by
  result, and cannot see any of those — a value that changes geometry through
  them leaves a stale result reading as current. A configuration is a factory
  argument; another configuration is another model.
- **A mirrored part is its own model.** STEP cannot express a reflection, so
  a right-hand part is a separate model file calling the same factory with
  `mirror=True` (or mirroring the factory's result), not a mirrored child.
- **`read_step` files are inputs, not models.** Replacing the file makes the
  reader stale. To make an imported part first-class, wrap it:
  `@step def servo(): return read_step(...)`.
- **`cadgen store why <model>.py`** is the freshness door: it prints the
  gate's verdict clause by clause (record, closure files, constants, each
  child's pinned vs current tree, tree objects, declared outputs). Reach for
  it whenever a model did or did not rebuild when you expected it to.

**Workers.** A warm daemon is on by default: each model gets a persistent
worker (a second, an *extra*, when the model is asked for while already
building); spares stand by so a new model never pays the import; idle workers
unbind after ten minutes. Running builds are limited to one per core
(`CADGEN_JOBS` overrides); a parent waiting on its children holds no slot.
`CADGEN_DAEMON=0` uses transient workers spawned for that one run — still
parallel, still the same store — and is the mode for tests and debugging.
`cadgen daemon status` lists workers, spares and the running/queued jobs.

**Debugging notes.** Do not alternate `CADGEN_DAEMON=0` and daemon runs of one
model while a daemon build of it is in flight (the two are unbrokered; each
publishes what it built, and the publish rule keeps the newer source). **One
project, one store.** A build under another `CADGEN_CACHE_DIR` (a temp store,
a test) rewrites the same output files; the first store's records then see
outputs whose bytes they did not write, so its gate reports the model stale
(`output changed: …`) and every parent `child stale: …` — nothing is wrong,
the two stores simply disagree, and the next build under either settles it.
**Module bodies stay cheap.** A model file is imported on every rerun, before
the gate: a module-level `read_step` (computing a layout from a vendor STEP at
import) pays the kernel and the parse each time even when the model is
current — call `read_step` inside the body or a function it calls; the
`hint:` printed on such a run names the import site. **Resets, smallest
first:** `python model.py --force` rebuilds one model now; `cadgen store
forget <model.py>` drops its record so the *next* run rebuilds it (children
untouched); `cadgen store forget <file.step>` drops the tree entry for that
file's bytes so the next open or door call compiles it again; `cadgen store
gc` sweeps unreachable objects; **clearing the store (`rm -rf
~/.cache/cadgen`, or `$CADGEN_CACHE_DIR`) is always safe** — every model
reads as stale and rebuilds, and no project file is touched. The gate has no
cadgen-version clause, so a model built by a cadgen with a bug stays current
after the fix: `forget` the affected models (or the parents that link them),
or clear the store.

**The store** (`~/.cache/cadgen`, `CADGEN_CACHE_DIR` overrides) holds
`objects/` — immutable, content-addressed components and trees — and `index/`
— the per-model records the gate reads, the op memo, and the mesh ledger. It
contains only derived results. The full contract is `STORE.md` in the
installed `cadgen` package.

## Streams, progress and failures

**Streams.** stdout carries the result; stderr carries progress, timing, and failures. A model run prints `<outcome> <document path>` on stdout (`built`, `current`, or `skipped-peer` when a concurrent build of the same model finished first), and the two streams never interleave, so `2>/dev/null` leaves a clean parseable result and `>/dev/null` leaves a readable log. JSON on stdout is always compact; pipe through `jq .` to read it. For machine-readable output: model runs, the `build` doors (`step`, `stl`, `3mf`, `glb`) and `snapshot` take `--json`; `inspect` already emits JSON and takes `--format text` for prose. A model run's `--json` line carries `outcome`, `document` and `tree` (the result's hash). `--verbose` adds stage timing (and full tracebacks) on stderr. Output volume does not grow with model size.

**The build tree.** On a terminal, stderr shows the graph as the body's child calls reveal it — one refreshed block, each model `submitted`, `queued`, `building · <phase> n/total`, `current`, or `✓ <time>`, finished subtrees folded to one line. With `--json` or a non-TTY, one JSON line per model transition (`model`, `parent`, `state`, `phase`, `progress`, `elapsed`) on stderr replaces the drawing; the result line on stdout comes last. After publishing, the root re-runs its gate once and says `already stale: <child> changed during the build; rerun` if it did.

**Reporting progress from a model.** A long build spends most of its wall time inside
the model body. Import the reporter — it binds to whichever build is running, and does
nothing when there is none:

```python
from cadgen import report, track, step

@step
def housing():
    report("bearing housing")                              # name the current phase
    for rib in track(ribs, label=lambda r: r.name):        # count through a work list
        ...
```

`track()` advances the count when an item's work is DONE and labels the item in flight, so a
reader sees "3 finished, now on engines". The phase surfaces on the model's line in the build
tree and — through the daemon's job ledger — as `compiling · <phase>` in the CAD Viewer for any
document the job writes, whoever started the job. Without this a multi-minute assembly says
nothing during its longest phase.

**Failures** print the exception and the frames *in your own model*, not the runtime's:

```text
[cadgen] FAILED: ValueError: bad radius
[cadgen]   src/widget.py:9 in bracket
[cadgen]       return _profile(radius)
[cadgen] re-run with --verbose for the full traceback
```

A failed child raises at the site in the parent that first read its geometry, naming the call and carrying the child worker's output.

## Snapshots

**Snapshot inputs.** One format, one door, and the same `TARGET [OUT]` grammar `build` uses. `cadgen step snapshot` renders `.step`/`.stp` documents — nothing else (a model script is refused by name: run `python <model>.py`, then snapshot the STEP it wrote). A mesh file goes to its own door: `cadgen stl snapshot`, `cadgen 3mf snapshot`, `cadgen glb snapshot`. A mesh has no CAD topology, so the STEP-only options (`--focus`/`--hide`, `--display`, `--kinematics`, `--animation`/`--time`, `--mode section`) are not on those commands at all — check `--help` and the door tells you what it can do. Robot descriptions belong to the `urdf`/`srdf`/`sdf` skills. Each door refuses what is not its own format, and names the door that takes it.

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
cadgen stl snapshot  STL/bracket.stl   tmp/mesh.png
```

**Snapshot output.** The path you name is the path you get:

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
# then Read tmp/review.png
```

OUT is written exactly as given (a relative path against the current working directory), cleared before the render and written atomically after it — so reuse one name while iterating, name the iterations (`tmp/before.png`, `tmp/after.png`) when you need to compare, and treat a missing file as the failure signal: there is never an older image at the path to mistake for output. A directory (`tmp/`) is the don't-care case and gets a generated timestamped name inside it, printed on the `saved snapshot:` line. The same rule applies per output in a JSON packet.

**Theme and display.** Theme settings live under one `--theme`, display settings under one `--display` — the viewer's two tabs, one option each. The default theme is `snapshot`: Workbench Light with the ground grid and origin axis removed, because in a still image those read as geometry rather than as orientation. Pass `--theme workbench-light` for the viewer's own look. Projection is a theme trait honoured by every format, so a snapshot frames the same way the viewport does.

## Required workflow

Scale depth to the task: a simple part needs a short brief and few spec-driven checks; assemblies and fit-critical work need full positioning and alignment validation.

1. **Classify the task.** New part, new assembly, source modification, direct STEP/STP inspection, reference selection, measurement/alignment check, snapshot review, or mesh output request.
2. **Load only the needed references.** Use the triggers below instead of reading the whole reference set.
3. **Write a natural-language CAD brief.** Extract dimensions, units, coordinate convention, feature intent, output paths, assumptions, and validation targets from all provided inputs — prose, reference images, technical drawings. Use `references/cad-brief.md`.
4. **Check named purchasable components.** When an assembly includes named off-the-shelf actuators, servos, motors, electronics boards, connectors, or other purchasable components, search `$step-parts` before creating simplified placeholder geometry. If no exact match is found, record the miss and then use a documented bounding volume.
5. **Plan before coding.** Define the constants and factory arguments, intent labels, source paths, expected bounding boxes, and any mating/positioning datums before editing.
6. **Edit source, not generated artifacts.** Author a plain `.py` model script with one decorated function (shared code lives in plain helper modules; see `references/step-generation.md`). When a model script exists, run IT, never hand-edit its exported STEP. Imported STEP/STP files (no script) are handed straight to `cadgen step inspect`, `step snapshot` and the mesh doors — each compiles whatever it needs on demand.
7. **Build explicit targets.** Run each model script directly (`python <model>.py`); do not sweep directories. A parent builds its children as it calls them, so running the root is the whole build. Declare `@stl`/`@threemf`/`@glb` outputs on the model, or run `cadgen stl|3mf|glb build` for one-off mesh files. For multi-model project structure, read `references/project-layout.md`.
8. **Validate geometrically.** Run `cadgen step inspect refs <step-or-cad-target> --facts --planes --positioning` as the baseline, then verify the dimensions and relationships the user's spec calls out with targeted `measure`, `align`, `frame`, or `diff` checks. Run `cadgen step inspect validate <step-or-cad-target>` for geometry soundness: `refs --facts` reports counts and bounds, and its `ok` field covers ref resolution only — an open shell and an inverted solid both pass it.
9. **Snapshot the primary STEP — snapshot validation is mandatory.** After creating or visibly updating a STEP/STP part or assembly, ALWAYS run `cadgen step snapshot` against it and review the output; deterministic checks passing is not a reason to skip. The only skip cases are documented in `references/snapshot-review.md` (no visible geometry changed, or no valid artifact exists); report the reason when skipping. A mesh-only model is reviewed with its format's snapshot door.
10. **Repair and rerun.** If a check fails, change the smallest responsible source section, rebuild, and rerun the failed validation.

## Handoff

After completing CAD work that creates or modifies `.step`, `.stp`, `.stl`, `.3mf`, or native `.glb` artifacts, you must ALWAYS hand the explicit file path(s) to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include those live viewer link(s) in the final response. If `$cad-viewer` is unavailable or startup fails, report that and rely on CLI inspection plus snapshots instead of silently omitting the handoff. This rule applies to every workflow in this skill, including mesh outputs.

When verification snapshots are generated, include the saved PNG snapshot(s) in the final response. If no snapshot applies, or if snapshot generation fails, say why and report the deterministic validation that still ran.

## Non-negotiables

- The model script is the source of truth. Every written file — STEP/STP, STL, 3MF, GLB, the sidecar — is a derived output; edit and rerun the script, never the outputs. Where a model declares a STEP, the STEP is the artifact that is inspected and snapshotted.
- Use named constants, closed solids, verbose native build123d labels, and source-controlled geometry intent.
- Author assembly positioning in source. `references/positioning.md` is authoritative for `AssemblyHelper`, build123d joints, explicit `Location` transforms, and alignment validation.
- Do not use `git status`, `git diff`, or file-size churn as CAD comparison for large exported STEP/STP, GLB, STL, or 3MF artifacts. Compare source changes, `cadgen step inspect` summaries, or snapshots instead; use path-limited git status only for bookkeeping.
- Report only checks that actually ran or are directly supported by tool output.

## Progressive references

Load these files only when their trigger applies:

- `references/cad-brief.md` — converting prose, reference images, and technical drawings into a CAD brief.
- `references/build123d-modeling.md` — build123d modeling patterns, topology, selectors, features, labels.
- `references/step-generation.md` — the model contract in full: composition (linked children, `read_step` inputs), what a rebuild tracks, mirrored parts, factories, the daemon and workers, imported STEP/STP files, and post-build steps.
- `references/inspection-and-validation.md` — validation sequence, selector refs, facts, planes, measurements, alignment, diff, frame, and validation reporting.
- `references/snapshot-review.md` — mandatory snapshot policy, packet sizing, targeted views, and converting visual findings into geometry checks.
- `references/positioning.md` — part-local datums and origins, assembly transforms, build123d joints, CLI alignment validation, and positioning reports.
- `references/kinematics.md` — articulating, posing, or animating a STEP model: typed mates (`kinematics=` on the decorators — mates, couplings, pose presets, export-at-pose), and the render module beside the document (`<name>.step.js`: the choreography contract, loaded by the viewer, read by no build).
- `references/supported-exports.md` — STL/3MF/native GLB outputs: declared exports, mesh-only models, and the `cadgen stl|3mf|glb build` doors.
- `references/repair-loop.md` — diagnosis and repair procedures.
- `references/project-layout.md` — project structure for anything bigger than a couple of loose models: `src/` for model scripts and shared code, format folders (`STEP/`, `DXF/`, `STL/`) for raw outputs, naming, and commit policy; `references/project-template.md` is the copyable exemplar. Read them when a project has more than a couple of models or when asked how to organise CAD code and artifacts.
- `references/migrations.md` — the tooling disagreeing with a model you believe is correct: recognizing a project authored against an older cadgen, and where the migration guides live.

Final responses should include generated files, returned `$cad-viewer` viewer links, verification snapshots, validation actually run, assumptions, and caveats. Use `references/inspection-and-validation.md` for report structure.
