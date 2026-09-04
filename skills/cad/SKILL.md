---
name: cad
description: Create, modify, inspect, and validate STEP-first parametric CAD parts and assemblies. Use for natural-language CAD specs, reference images, 2D technical drawings, STEP/STP generation or direct inspection, Python CAD source, source-level joints, selector references, geometry facts, measurements, mating deltas, snapshots, and secondary STL/3MF/native GLB outputs from CAD geometry.
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

The command surface (the `cadgen` console script, installed with the package):

```bash
python <model>.py            # its __main__ calls the @step/@dxf model, which builds it
cadgen step build IN OUT  # re-emit an existing STEP as a new one, with kinematics
cadgen stl build ...      # one door per mesh format; `3mf` and `glb` are the others
cadgen step inspect ...   # refs, measure, align, frame, diff
cadgen step snapshot ...  # PNG visual review packets, for STEP
cadgen stl snapshot ...   # the same, for a mesh file; `3mf` and `glb` again
```

**Scripts are RUN; commands take DOCUMENTS.** `python model.py` is the one
source door — it writes the document, every declared export, and (only when
the model declares kinematics, animation, or exports) its sidecar.
Every command above takes a `.step`/`.stl`/`.dxf` FILE, and one handed a `.py`
says so. Nothing needs a separate cache or import step: each door makes what it
needs. A document that has drifted from its script is refused by name — rerun
`python <script>` rather than looking for a flag.

Generation has NO CLI. A model is a plain Python script whose `__main__`
calls the decorated function:

```python
from cadgen import build123d as bd
from cadgen import step

WIDTH = 10.0


@step()                       # or @dxf() for drawings; out= relocates the artifact
def bracket():
    return bd.Box(WIDTH, 10, 10)

if __name__ == "__main__":
    bracket()
```

The decorator only declares the model. Calling it at the top level (from
`__main__`, with no arguments) builds it: `python bracket.py` writes
`bracket.step` beside the script and the model's result into the store, and a
repeat run of an unchanged model is a fast no-op. Called from inside another
model's body, the same name returns the shape — that is how an assembly
composes its children: the child is built if stale (or loaded from the store),
and its result is linked into the parent's. The
`from cadgen import build123d as bd` idiom is the canonical import: it is a
lazy, transparent re-export of build123d (same names, same behavior), so the
freshness gate and warm-daemon handoff run before any kernel import is paid.
Raw `import build123d` still works but costs ~2.5s per re-run. Per-run flags
ride the script's argv: `--force` (this model only; its children still go
through the freshness gate), `--json`, `--verbose`, `--mesh-tolerance`,
`--mesh-angular-tolerance`.

Rules the decorator enforces: importing a model module never builds; a model
file without a `__main__` call never builds either — always end the script with
`if __name__ == "__main__": <model>()`; a top-level call takes no arguments (the
declared output is the model's one configuration); composition returns
geometry only — a child's sidecar (mates, kinematics, animation) never rides up
into a parent, so an assembly declares its own relations; a model function takes
**no parameters** — parametric geometry lives in a plain factory function the
model calls with its values, and a different configuration is a different
model with its own file; one `@step`/`@dxf` model per file.

Use the active project Python interpreter; treat `python` in examples as an interpreter placeholder. Every operational verb is a `cadgen` subcommand (warm-by-default; `python -m cadgen.cli <verb>` is the PATH-independent equivalent). Use `cadgen <verb> --help` for the complete current interface; reference docs show recommended workflows, not every flag. Install per `requirements.txt`; `cadgen doctor <skill-dir>` verifies the installed cadgen matches this skill's pin (docs drift silently on a mismatched install).

**Snapshot inputs.** One format, one door, and the same `TARGET [OUT]` grammar `build` uses. `cadgen step snapshot` renders `.step`/`.stp` documents — nothing else (a model script is refused by name: run `python <model>.py`, then snapshot the STEP it wrote). A mesh file goes to its own door: `cadgen stl snapshot`, `cadgen 3mf snapshot`, `cadgen glb snapshot`. A mesh has no CAD topology, so the STEP-only options (`--focus`/`--hide`, `--display`, `--kinematics`, `--animation`/`--time`, `--mode section`) are not on those commands at all — check `--help` and the door tells you what it can do. Robot descriptions belong to the `urdf`/`srdf`/`sdf` skills. Each door refuses what is not its own, and names the door that takes it.

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

**Streams.** stdout carries the result; stderr carries progress, timing, and failures. Every tool answers on stdout — a model run prints `<outcome> <package path>` — and the two never interleave, so `2>/dev/null` leaves a clean parseable result and `>/dev/null` leaves a readable log. JSON on stdout is always compact; pipe through `jq .` to read it. For machine-readable output: model runs, the `build` doors (`step`, `stl`, `3mf`, `glb`) and `snapshot` take `--json`; `inspect` already emits JSON and takes `--format text` for prose. `--verbose` adds stage timing (and full tracebacks) on stderr. Output volume does not grow with model size — a 600-occurrence assembly logs the same dozen lines a single part does.

**Reporting progress from a model.** A long build spends most of its wall time inside
the decorated function, which the pipeline calls with no arguments. Import the reporter
— it binds to whichever build is running, and does nothing when there is none:

```python
from cadgen import report, track, step

@step()
def housing():
    report("bearing housing")                              # name the current phase
    for rib in track(ribs, label=lambda r: r.name):        # count through a work list
        ...
```

`track()` advances the count when an item's work is DONE and labels the item in flight, so a
reader sees "3 finished, now on engines". Without this a multi-minute assembly says nothing
during its longest phase.

It surfaces in two places, and neither is ordinary stderr output: a **live inline line** on a
terminal, and the **CAD Viewer's advisory progress badge** while a CLI build is in flight
(the viewer never builds; it reads the build's progress record). The inline line is
deliberately silent when stderr is not a tty, so a redirected log keeps the lines rather than
the repainting — do not conclude the calls are doing nothing because `2>file` shows no labels.
Silent generators are unaffected.

**Failures** print the exception and the frames *in your own generator*, not the runtime's:

```text
[cadgen] FAILED: ValueError: bad radius
[cadgen]   src/widget.py:9 in bracket
[cadgen]       return _profile(radius)
[cadgen] re-run with --verbose for the full traceback
```

**Concurrent builds of one model both run**; nothing waits and nothing locks. Each publishes its result and the store keeps the one whose sources match the files as they are now, so the disk ends at the newer source. With `--json`, each target's `outcome` is `built`, `current`, or `skipped-peer` (a concurrent run finished first and its result is current). A parent's children build in parallel as its body calls them; the build tree on stderr shows each model's state (`submitted`, `building · phase`, `current`, `✓ time`) and `--json` or a non-TTY gets one JSON line per transition instead.

Target paths resolve from the command's current working directory, not from the skill directory. Run commands from the workspace that owns the artifacts and pass cwd-relative target paths so project CAD files never resolve accidentally under the skill directory. By default a model's STEP is its sibling with the same stem; the artifact→source link is recorded in the store's record for the model, so relocating outputs with `out=` is safe.

CAD references are `#...` selector tokens local to a target, for example `#o1.2` or `#o1.2.f1`. Pass the STEP/CAD file as a separate target argument when using CAD CLIs.

## Required workflow

Scale depth to the task: a simple part needs a short brief and few spec-driven checks; assemblies and fit-critical work need full positioning and alignment validation.

1. **Classify the task.** New part, new assembly, source modification, direct STEP/STP inspection, reference selection, measurement/alignment check, snapshot review, or secondary output request.
2. **Load only the needed references.** Use the triggers below instead of reading the whole reference set.
3. **Write a natural-language CAD brief.** Extract dimensions, units, coordinate convention, feature intent, output paths, assumptions, and validation targets from all provided inputs — prose, reference images, technical drawings. Use `references/cad-brief.md`.
4. **Check named purchasable components.** When an assembly includes named off-the-shelf actuators, servos, motors, electronics boards, connectors, or other purchasable components, search `$step-parts` before creating simplified placeholder geometry. If no exact match is found, record the miss and then use a documented envelope.
5. **Plan before coding.** Define parameters, intent labels, source paths, expected bounding boxes, and any mating/positioning datums before editing.
6. **Edit source, not generated artifacts.** Author a plain `.py` model script with one `@step`-decorated function (underscore-prefixed helper modules carry shared code; see `references/step-generation.md`). When a model script exists, run IT, never hand-edit its exported STEP. Imported STEP/STP files (no script) are handed straight to `cadgen step inspect`, `step snapshot` and the mesh doors — each makes whatever it needs on demand.
7. **Generate explicit targets.** Run each model script directly (`python <model>.py`); do not sweep directories. Every run writes the model's `.step` (sibling `<stem>.step` by default; `out=` in the decorator relocates it); declare `@stl`/`@threemf`/`@glb` exports on the model, or run `cadgen stl|3mf|glb build` for one-off mesh files. For multi-model project structure, see the `$cad-project` skill.
8. **Validate geometrically.** Run `cadgen step inspect refs <step-or-cad-target> --facts --planes --positioning` as the baseline, then verify the dimensions and relationships the user's spec calls out with targeted `measure`, `align`, `frame`, or `diff` checks. Run `cadgen step inspect validate <step-or-cad-target>` for geometry soundness: `refs --facts` reports counts and bounds, and its `ok` field covers ref resolution only — an open shell and an inverted solid both pass it.
9. **Snapshot the primary STEP — snapshot validation is mandatory.** After creating or visibly updating a primary STEP/STP part or assembly, ALWAYS run CAD `cadgen step snapshot` against it and review the output; deterministic checks passing is not a reason to skip. The only skip cases are documented in `references/snapshot-review.md` (no visible geometry changed, or no valid artifact exists); report the reason when skipping.
10. **Repair and rerun.** If a check fails, change the smallest responsible source section, regenerate, and rerun the failed validation.

## Handoff

After completing CAD work that creates or modifies `.step`, `.stp`, `.stl`, `.3mf`, or native `.glb` artifacts, you must ALWAYS hand the explicit file path(s) to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include those live viewer link(s) in the final response. If `$cad-viewer` is unavailable or startup fails, report that and rely on CLI inspection plus snapshots instead of silently omitting the handoff. This rule applies to every workflow in this skill, including secondary STL/3MF/GLB outputs.

When verification snapshots are generated, include the saved PNG snapshot(s) in the final response. If no snapshot applies, or if snapshot generation fails, say why and report the deterministic validation that still ran.

## Non-negotiables

- Keep STEP as the primary validated CAD artifact. Generated STEP/STP, STL, 3MF, GLB/topology outputs, and render sidecars are derived artifacts; STL/3MF are secondary unless the user explicitly says otherwise.
- Use named parameters, closed solids, verbose native build123d labels, and source-controlled geometry intent.
- Author assembly positioning in source. `references/positioning.md` is authoritative for `AssemblyHelper`, build123d joints, explicit `Location` transforms, and alignment validation.
- Do not use `git status`, `git diff`, or file-size churn as CAD comparison for large exported STEP/STP, GLB/topology, STL, or 3MF artifacts. Compare source changes, `cadgen step inspect` summaries, snapshots, or generated topology output instead; use path-limited git status only for bookkeeping.
- Report only checks that actually ran or are directly supported by tool output.

## Progressive references

Load these files only when their trigger applies:

- `references/cad-brief.md` — converting prose, reference images, and technical drawings into a CAD brief.
- `references/build123d-modeling.md` — build123d modeling patterns, topology, selectors, features, labels.
- `references/step-generation.md` — STEP generation from Python source, direct STEP/STP imports, and post-generation steps.
- `references/inspection-and-validation.md` — validation sequence, selector refs, facts, planes, measurements, alignment, diff, frame, and validation reporting.
- `references/snapshot-review.md` — mandatory snapshot policy, packet sizing, targeted views, and converting visual findings into geometry checks.
- `references/positioning.md` — part-local datums and origins, assembly transforms, build123d joints, CLI alignment validation, and positioning reports.
- `references/kinematics.md` — articulating, posing, or animating a STEP model: geometry parameters (the function signature), typed mates (`kinematics=` on the export decorators — mates, couplings, pose presets, export-at-pose), and the `.anim.js` choreography contract.
- `references/supported-exports.md` — STL/3MF/native GLB mesh export workflows: declared exports and the `cadgen stl|3mf|glb build` doors.
- `references/repair-loop.md` — diagnosis and repair procedures.
- `references/migrations.md` — the tooling disagreeing with a model you believe is correct: recognizing a project authored against an older cadgen, and where the migration guides live.

Final responses should include generated files, returned `$cad-viewer` viewer links, verification snapshots, validation actually run, assumptions, and caveats. Use `references/inspection-and-validation.md` for report structure.
