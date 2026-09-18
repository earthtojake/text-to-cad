---
name: cad
description: Create/edit parametric CAD models, organize CAD projects, export STEP/STL/3MF/GLB files, resolve prompt references, and measure geometry with cadgen.
---

# CAD modeling and inspection

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files for the current interface.

## Start with the task

Read only the references needed for the request.

| Task | First action | Reference |
| --- | --- | --- |
| **Create or edit a part or assembly** | Find the existing Python model, or create a decorated model below; edit source and run `python <model>.py`. | [Model contract](references/step-generation.md), [shape construction](references/build123d-modeling.md); [positioning](references/positioning.md) for assemblies |
| **Organize a CAD project** | Follow its existing layout; for a new multi-model project use `src/`, format output folders, and a model catalog. | [Project layout](references/project-layout.md), [minimal starters](references/project-template.md) |
| **Export STL, 3MF or GLB** | Add a mesh decorator for a maintained output, or run the format's `build INPUT.step OUT` command for a one-off export. | [Mesh exports](references/supported-exports.md) |
| **Resolve a reference from a prompt** | Identify its saved STEP/STP document, open it with `read_scene`, and call `scene.resolve(ref)` as shown below. | [Reference syntax and inspection](references/inspection-and-validation.md#reference-syntax) |
| **Measure or check geometry** | Write a Python check using native build123d geometry and, where useful, `cadgen.geometry`. | [Inspection and validation](references/inspection-and-validation.md) |
| **Model from an image or drawing** | Extract the specified dimensions and record meaningful assumptions. | [Interpreting the request](references/cad-brief.md) |
| **Review appearance or motion** | Snapshot the saved document; use declared kinematics or animation for poses and clips. | [Snapshots](references/snapshot-review.md), [kinematics](references/kinematics.md) |
| **Diagnose a failure** | Read the error and check the relevant model, geometry or command contract. | [Repair loop](references/repair-loop.md), [version migration](references/migrations.md) |

For 2D DXF drawings use `$dxf`; this skill owns any 3D part the drawing projects.
Use the corresponding robot-description skill for URDF, SRDF or SDF.

## Setup and paths

Install this skill's `requirements.txt` with the active project interpreter.
Rendering also needs Chromium:

```bash
python -m pip install -r /path/to/installed/cad/requirements.txt
python -m playwright install chromium
```

Treat `python` in examples as the active interpreter. `cadgen doctor <skill-dir>`
checks the skill's package pin and CAD kernel; use it for installation or OCP
load errors. `python -m cadgen.cli` is the PATH-independent equivalent of
`cadgen`. Use the relevant subcommand's `--help` for additional flags.

Run project commands from the CAD project root. CLI input/output paths and
`read_scene`/`read_step` paths are working-directory-relative; decorator `out=`
paths are **relative to the model script**. Anchor file inputs on `__file__`
when the model must run from any directory.

## Create or edit a model

A model is a plain Python script with a parameterless decorated function
returning a build123d shape. Use one model per entrypoint, with the script and
its declared outputs sharing a filename stem. For example, `src/bracket.py`:

```python
from cadgen import build123d as bd
from cadgen import step

WIDTH = 40.0


@step(out="../STEP/bracket.step")
def bracket():
    body = bd.Box(WIDTH, 20, 6)
    body.label = "bracket"
    return body


if __name__ == "__main__":
    bracket()
```

```bash
python src/bracket.py
```

- Edit the model source when it exists, then run it to regenerate its outputs.
  Document export and snapshot commands take saved files and never run source.
- Keep meaningful dimensions explicit. Use millimeters and XY/+Z unless the
  task or project specifies another convention; choose a useful functional datum.
  Prefer closed, positive-volume solids for physical parts, while honoring
  requests for surfaces or construction geometry.
- Put parameterized geometry in ordinary factory functions; a decorated model
  selects a configuration. Keep module bodies cheap: create geometry and read
  CAD inputs inside the model or its helpers. Use the lazy `bd` import above;
  use postponed annotations when annotations mention `bd` types.
- Call child models inside the assembly model. Place their results with
  `.moved()` or `Location * shape` to preserve shared geometry. Use meaningful
  occurrence labels and source-defined placements. Rerun the parent assembly
  to incorporate a changed child.
- Read vendor STEP inputs with `cadgen.read_step`; it records the file as a
  build input. Declare other data inputs with `cadgen.declare_input`. Never
  read a model's own output as its input. Geometry must not depend on untracked
  time, random values, environment variables or the working directory.
- When named purchasable parts are needed, search `$step-parts` before making
  placeholders. Record an unsuccessful search and any placeholder assumptions.

For unfamiliar dimensions or interfaces, record the assumptions needed to model
and verify them. Ask for missing information when it materially affects the
requested result. Inspection and export requests do not need a modeling brief.

## Mesh exports

Stack `@stl`, `@threemf` or `@glb` on the model for outputs that should be
maintained on every run. A model may declare only meshes; STEP is optional.
For a one-off export from an existing generated or imported STEP:

```bash
cadgen stl build STEP/bracket.step STL/bracket.stl
cadgen 3mf build STEP/bracket.step 3MF/bracket.3mf
cadgen glb build STEP/bracket.step GLB/bracket.glb
```

Omitting OUT writes one sibling file with the requested extension. It does
not discover declared model variants. See [mesh exports](references/supported-exports.md)
for decorator examples, mesh tolerances and animated GLB.

## Prompt references and inspection

A reference such as `assembly.step#o1.2.f7` identifies geometry in a particular
saved document. Use the prompt's file context to select that document:

```python
from cadgen import read_scene

scene = read_scene("STEP/assembly.step")
selection = scene.resolve("assembly.step#o1.2.f7")
face = selection.shape()  # owned native geometry, in document world coordinates
print(selection.ref, face.area)
```

For a bare `#o1.2.f7`, use the identified target file. For a model-script prefix,
find its declared STEP output and resolve the `#...` portion there. Do not guess
between ambiguous files or labels. Numeric refs belong to that saved revision;
reopen and reselect after rebuilding. The [inspection reference](references/inspection-and-validation.md)
covers label aliases, enumeration, measurements and small reusable operations.

There is no inspect CLI. Put exploratory checks in the project's ignored
`tmp/` (or system `/tmp/`); retain reusable checks in `checks/` or its existing
test directory. Keep them outside model-source and raw-output folders.

## Verify and hand off

Choose checks from the requested dimensions, clearances and topology. For STEP
outputs, check the saved artifact with `read_scene` or `read_step`. For mesh-only
models, check the model's returned native geometry and review the mesh output;
do not add a STEP solely to satisfy the workflow. Report units, thresholds,
selected geometry and untested requirements. A failed computation is not a pass.

After creating or visibly changing geometry, generate and review at least one
snapshot of the resulting STEP or mesh. Choose additional views to expose the
features under review; see [snapshot policy and options](references/snapshot-review.md).

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
cadgen stl snapshot STL/bracket.stl tmp/mesh.png
```

Repair failures in the source and rerun the affected checks. Use geometry and
images for CAD comparisons; path-targeted git status is bookkeeping, not
geometric evidence. `cadgen store why <model>.py` explains unexpected rebuilds;
`python <model>.py --force` forces one model, and `cadgen daemon status` shows
build progress. More diagnostics are in the [model contract](references/step-generation.md).

For created or modified STEP/STP, STL, 3MF and GLB files, hand their explicit
paths to `$cad-viewer` when installed and include its returned live links.
If unavailable or startup fails, report that and use geometry checks and
snapshots. Include output files, reviewed PNGs, checks actually run, and
material assumptions or limitations in the final response. Explain any snapshot
skip or failure using the cases in the snapshot reference.
