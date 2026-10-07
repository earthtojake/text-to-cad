---
name: cad
description: Create/edit parametric CAD models, organize CAD projects, export STEP/STL/3MF/GLB files, resolve prompt references, and measure geometry with cadgen. Open and visually review existing STEP/STP, STL, 3MF and GLB files in CAD Viewer.
license: MIT
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
| **Open an existing STEP/STP, STL, 3MF or GLB** | Show it to the user. | [Show the model](#show-the-model) |
| **Review appearance or motion** | Snapshot the saved document; use declared kinematics or animation for poses and clips. | [Snapshots](references/snapshot-review.md), [kinematics](references/kinematics.md) |
| **Diagnose a failure** | Read the error and check the relevant model, geometry or command contract. | [Repair loop](references/repair-loop.md), [version migration](references/migrations.md) |
| **A message says to migrate** | Do the migration now; an unmigrated model silently loses kinematics, materials and animation. | [Version migration](references/migrations.md) |

For 2D DXF drawings use `$dxf`; this skill owns any 3D part the drawing projects.
Use the corresponding robot-description skill for URDF, SRDF or SDF.

## Setup and paths

Run cadgen through [uv](https://docs.astral.sh/uv/), so this skill's commands share
one installation, and its warm build daemon, with the CAD app's server:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.15 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.15 python`

The first run downloads that installation and the first snapshot its headless
browser; later runs reuse both.

`cadgen doctor <skill-dir>` reports the installation in use and checks that it is
the one this skill pins, and that the CAD kernel loads; use it for installation or
kernel load errors. Use the relevant
subcommand's `--help` for additional flags.

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
- Read vendor STEP inputs with `cadgen.read_step`. Every file a build opens is
  an input on its own, whatever reads it (`json.load`, `np.load`,
  `bd.import_step`, a project font): nothing is declared. Never read a model's own
  output as its input. Geometry must not depend on untracked
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

A reference such as `/work/robot/STEP/assembly.step#o1.2.f7` identifies geometry
in a particular saved document. Its file part is the document's absolute path as
the CAD viewer copied it, with the file's real name and extension (in quotes when it
holds a space or `#`). Open that path with `read_scene`, and pass the whole reference
to `resolve()`:

```python
from cadgen import read_scene

scene = read_scene("/work/robot/STEP/assembly.step")
selection = scene.resolve("/work/robot/STEP/assembly.step#o1.2.f7")
face = selection.shape()  # owned native geometry, in document world coordinates
print(selection.ref, face.area)
```

A note from the viewer's Quick Edit reads: what the person wants, then
`File:` (the document it is about), `References:` (one per line, as above) and,
when they sketched on the view, `Sketch: <path>`: a PNG of the view with their
markup (or the image itself, attached). Look at the sketch before changing the model.

For a bare `#o1.2.f7`, use the identified target file. Do not guess between
ambiguous files or labels. Numeric refs belong to that saved revision;
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
snapshot of the resulting STEP or mesh. Snapshots are your own review: always
render and read them yourself, never rely on the viewer for it. Choose additional
views to expose the features under review; see
[snapshot policy and options](references/snapshot-review.md).

```bash
cadgen step snapshot STEP/bracket.step tmp/review.png
cadgen stl snapshot STL/bracket.stl tmp/mesh.png
```

Repair failures in the source and rerun the affected checks. Use geometry and
images for CAD comparisons; path-targeted git status is bookkeeping, not
geometric evidence. `cadgen store why <model>.py` explains unexpected rebuilds;
`python <model>.py --force` forces one model, and `cadgen daemon status` shows
build progress. More diagnostics are in the [model contract](references/step-generation.md).

Include output files, checks actually run, and material assumptions or
limitations in the final response. The user sees the model in the viewer (Show
the model), so don't attach snapshots unless they ask for an image. Explain any
snapshot skip or failure using the cases in the snapshot reference.

### Show the model

Show the user each file you create or change, and any they ask to see. Snapshots and
validation don't replace this.

- If your tools include `cad_show` (your host may prefix it), use it with the file's
  absolute path, and follow its description for when to call it again. `cad_view` reads
  what the user selected; `cad_screenshot` shows you what they see. Neither is a review
  of your own work.
- Otherwise run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --host 127.0.0.1 --json --detach
  ```

  `--detach` returns once the viewer answers requests and leaves it running in the
  background: always pass it, since a foreground viewer never exits (and piping its
  output through `tail` can hide the URL for good). It starts this machine's one viewer,
  or reuses it. Read `url` from its one JSON line (never guess the port), and for each
  file return `url?file=<its URL-encoded absolute path>`. If it fails to launch, say so.

Generate changed artifacts first: the viewer never runs model scripts. Existing
STEP files compile on open when needed. Topology selection and measurement
require STEP; meshes support visual review.
