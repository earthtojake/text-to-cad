---
name: cad
description: Create/edit parametric CAD models, organize CAD projects, export STEP/STL/3MF/GLB files, resolve prompt references, and measure geometry with cadgen. Open and visually review existing STEP/STP, STL, 3MF and GLB files in CAD Viewer.
license: MIT
---

# CAD modeling and inspection

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files for the current interface.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Create or edit a part or assembly** | The project's model script, or a new one (below). | [Model contract](references/step-generation.md), [build123d](references/build123d-modeling.md), [positioning](references/positioning.md) |
| **Organize a CAD project** | The project's existing layout. | [Project layout](references/project-layout.md), [starters](references/project-template.md) |
| **Export STL, 3MF or GLB** | A mesh decorator on the model, or a format's `build` command on a saved STEP. | [Mesh exports](references/supported-exports.md) |
| **Resolve a reference from a prompt** | `read_scene` on its document, then `scene.resolve(ref)` (below). | [Reference syntax](references/inspection-and-validation.md#reference-syntax) |
| **Measure or check geometry** | A Python script using build123d and `cadgen.geometry`. | [Inspection](references/inspection-and-validation.md) |
| **See a model, a pose or a clip** | `cadgen step snapshot`, or a mesh format's `snapshot`. | [Snapshots](references/snapshot-review.md) |
| **Articulate or animate a model** | `kinematics=` or `animation=` on the model's decorator. | [Kinematics and animation](references/kinematics.md) |
| **Open an existing STEP/STP, STL, 3MF or GLB** | Show it to the user. | [Show the model](#show-the-model) |
| **A message names a sidecar schema or a retired interface** | Its migration: until then the model renders as a plain part, without kinematics, materials or animation. | [Migrations](references/migrations.md) |

For 2D DXF drawings use `$dxf`; this skill owns any 3D part the drawing projects.
Use the corresponding robot-description skill for URDF, SRDF or SDF.

## Setup and paths

Run cadgen through [uv](https://docs.astral.sh/uv/), so this skill's commands share
one installation, and its warm build daemon, with the CAD app's server:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.19 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.19 python`

`cadgen doctor <skill-dir>` reports the installation in use, whether it is the one
this skill pins, and whether the CAD kernel loads. Each command's `--help` lists
its flags.

CLI paths and `read_scene`/`read_step` paths are relative to the working
directory, as are a model's own file reads unless anchored on `__file__`.
Decorator `out=` paths are **relative to the model script**.

## Create or edit a model

A model is a plain Python script whose parameterless decorated function returns
a build123d shape; running the script builds it. For example, `src/bracket.py`:

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

- A run rebuilds what changed and is a no-op otherwise. Export and snapshot
  commands read saved files and never run source.
- The viewer, snapshots and mesh exports read model units as millimetres, +Z up.
- A configuration is a plain factory the model calls with its values; a second
  configuration is a second model. cadgen runs a model file's top level to check
  whether it is current, and so does every parent that imports it, so a top level
  of imports, constants and definitions keeps that check cheap. The lazy `bd`
  import above (with `from __future__ import annotations` when annotations name
  `bd` types) lets a current model finish without loading the CAD kernel.
- An assembly calls its child models in its body and places their results.
  `.moved()` and `Location * shape` copy the shape, and everything under it, on
  every call, so a pass that walks a finished assembly to re-place or rewrite it
  re-copies the whole tree on every build; changing geometry where it is defined
  (the part, its factory or its child model) does not. Rebuilding a child does not
  rebuild the assemblies that use it: run the parent. Refs, mates and clips can
  name parts by their labels.
- Rebuilds are per model: an unchanged model is skipped whole, a changed one runs
  whole, and any edit to a file makes every model in it stale. Child models in
  their own files keep a big assembly's iterations fast, and each child also runs
  on its own.
- `cadgen.read_step` reads a vendor STEP with its colours, warm from the store when
  it can. Every file a build opens is a tracked input, whatever opens it; nothing
  is declared. A model that reads its own output is never current, and geometry
  that depends on time, randomness, environment variables or the working
  directory is invisible to the cache.
- `$step-parts` finds real vendor models of purchasable parts such as fasteners,
  bearings and servos.
- A STEP's sidecar (`<name>.step.json`: kinematics, materials, animation
  keyframes) is a build output, rewritten by every run.

## Mesh exports

Stack `@stl`, `@threemf` or `@glb` on a model for meshes every run maintains; a
model may declare meshes and no STEP. A one-off export from a saved STEP:

```bash
cadgen stl build STEP/bracket.step STL/bracket.stl
cadgen 3mf build STEP/bracket.step 3MF/bracket.3mf
cadgen glb build STEP/bracket.step GLB/bracket.glb
```

Omitting OUT writes a sibling file with the format's extension. See
[mesh exports](references/supported-exports.md) for tolerances and animated GLB.

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
markup (or the image itself, attached).

A bare `#o1.2.f7` belongs to the document the conversation is about. Numeric refs
belong to one saved revision, and a rebuild can renumber them. There is no inspect
CLI: checks are Python scripts, and the
[inspection reference](references/inspection-and-validation.md) covers label
aliases, enumeration and measurement.

## Checks and diagnostics

`read_scene` and `read_step` read the saved document, so a check through them
tests what was written:

```python
from cadgen import read_scene

scene = read_scene("STEP/assembly.step")
for occurrence in scene.leaves():  # every placed part
    print(occurrence.ref, occurrence.label)
bracket = scene.resolve("#bracket").shape()  # exact geometry, world coordinates
print(bracket.bounding_box().size, bracket.volume, len(bracket.faces()))
```

- A mesh-only model has no STEP; called from plain Python, it returns its
  geometry.
- A snapshot renders a saved document as the viewer draws it
  (`cadgen step snapshot STEP/bracket.step tmp/review.png`; each mesh format has
  the same verb). It shows arrangement and appearance, not dimensions.
- Every build prints where its time went, split into model code and cadgen. A
  rise in model code comes from the model's newest code, and
  `python <model>.py --profile` shows where.
  `cadgen store why <model>.py` explains an unexpected rebuild or no-op, and
  `--force` rebuilds one model. More in the
  [model contract](references/step-generation.md#progress-and-runtime-diagnostics).

### Show the model

Show the user each file you create or change, and any they ask to see. Snapshots and
validation don't replace this.

- If your tools include `cad_show` (your host may prefix it), use it with the file's
  absolute path, and follow its description for when to call it again. `cad_view` reads
  what the user selected; `cad_screenshot` shows you what they see.
- Otherwise run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --host 127.0.0.1 --json --detach
  ```

  `--detach` returns once the viewer answers requests and leaves it running in the
  background: always pass it, since a foreground viewer never exits (and piping its
  output through `tail` can hide the URL for good). It starts this machine's one viewer,
  or reuses it. Read `url` from its one JSON line (never guess the port), and for each
  file return `url?file=<its URL-encoded absolute path>`. If it fails to launch, say so.

The viewer never runs model scripts: it shows what was last generated. Existing
STEP files compile on open when needed. Topology selection and measurement
require STEP; meshes are visual only.
