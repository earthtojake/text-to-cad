# CAD project structure

Follow an existing project's layout. For a new multi-model project, use the
structure below; a one-off part can use a flat folder. In a larger workspace,
put CAD work in its existing `models/`, `cad/` or `hardware/` area. In a bare CAD
workspace, use the root. cadgen does not infer paths from folder names: each
model declares its outputs.

## Source and output mapping

**One model entrypoint per `.py` file, with matching output stems.** For
example, `src/bracket.py` contains one parameterless decorated model and declares
`STEP/bracket.step`, `STL/bracket.stl`, `GLB/bracket.glb` or `3MF/bracket.3mf`, as
needed. Stacking output decorators still declares one model. Helpers and package
`__init__.py` files are not model entrypoints.

```
<project>/
  src/
    README.md             # model catalog
    plate.py              # one model per entrypoint
    plate_drawing.py       # separate drawing model
    assembly.py           # root assembly
    chassis/              # optional grouping as the project grows
      __init__.py
      frame.py
      strut.py
    purchased/            # optional read_step wrapper models for vendor parts
      servo.py
    lib/                  # shared helpers and parameterized factories
      __init__.py
      holes.py
  STEP/                   # raw artifacts and generated sidecars
    plate.step
    chassis/
      frame.step
      strut.step
    imported/             # external source files
  DXF/  STL/  GLB/  3MF/  # other requested output formats
  checks/                 # reusable checks, or the existing test directory
  tmp/                    # ignored exploratory scripts, snapshots and debug output
```

Keep code and notes outside the format folders. Mirror nested source paths in
output folders so repeated names remain unambiguous:
`src/chassis/frame.py` → `STEP/chassis/frame.step`. For several mesh densities
of the same model, retain the stem in separate variant subfolders, such as
`STL/draft/bracket.stl` and `STL/print/bracket.stl`.

Decorator `out=` paths are relative to the script. For `src/plate.py`:

```python
from cadgen import build123d as bd
from cadgen import step

WIDTH = 10.0


@step(out="../STEP/plate.step")
def plate():
    return bd.Box(WIDTH, 10, 10)


if __name__ == "__main__":
    plate()
```

Run `python src/plate.py` from the project root. An unchanged model is a no-op.
The CAD Viewer catalogs the saved artifacts; the source catalog identifies what
to build before those files exist.

Put exploratory inspection scripts in ignored `tmp/` or system `/tmp`, and
retained checks in `checks/` or the project's test directory. See
[inspection](inspection-and-validation.md) for examples.

## Imports and shared code

Use ordinary Python imports. Flat scripts can import sibling models and
`lib/` directly. For nested scripts, declare the import root with `PYTHONPATH`;
cadgen adds no paths of its own. From the project root:

```bash
PYTHONPATH=src python src/chassis/frame.py
```

Python packages and relative imports are supported. With
`src/chassis/__init__.py`, run the model as a module when it uses relative imports:

```bash
PYTHONPATH=src python -m chassis.frame
```

Direct execution puts the script's directory first on the import path. Avoid a
filename that shadows a package it imports: `frame/frame.py` can hide the `frame`
package when run by path. Use a distinct entrypoint name or module execution.

Keep shared factories, constants and helpers in `src/lib/` or an existing Python
package. Subsystems may import shared models or each other where the dependency
makes sense; avoid circular imports. Alias a module when importing a same-named
model function would otherwise shadow it.

Dependencies are tracked as **models by result, constants by value, functions by file**:

```python
from lib import fasteners  # helper module: tracked by file
from plate import WIDTH    # literal from a model module: tracked by value
from plate import plate    # model: calling it pins its result
```

`cadgen store why src/<model>.py` explains freshness. Importing a model never
builds it; calling it inside an assembly does. See the
[model contract](step-generation.md#models-inside-a-package) for package execution
and dependency details.

## Assemblies and model boundaries

A parent calls its child models inside its body. The runtime builds stale children
or reuses their cached results and links them into the parent: **running the root is the
whole build**. Run `python src/assembly.py`; rebuilding a child alone
does NOT rebuild the assemblies that use it, so rerun the parent to incorporate
the change.

Give a subassembly its own model when it needs independent outputs, reuse or a
separate cache boundary. Local construction can remain inline or in an ordinary
helper. A helper executes within its caller; a child model has its own record
and reusable result. Separate folders are useful as the project grows, but a
subassembly does not require one. Group related files for navigation without
forcing the directory tree to reproduce every assembly level.

Mirror inline for geometry local to a model; use separate left/right models
when independent outputs or reuse justify them. See
[mirroring and caching](step-generation.md#mirrored-geometry-and-reusable-models).
A print-only part can declare `@stl`, `@glb` or `@threemf` without `@step` and
still compose into an assembly.

Use factory arguments for configurations, with one entrypoint per independently
exported model. Geometry must not depend on untracked environment variables,
working-directory state, time or random values; the cache cannot detect those
changes. Declare external file inputs as described in the
[model contract](step-generation.md).

## Naming

- Use an importable Python identifier for the model script's stem, and retain
  that stem in its declared outputs. Put an external part number in a label or
  catalog entry if it cannot serve as the shared filename stem.
- A drawing is a separate model: `plate_drawing.py` → `DXF/plate_drawing.dxf`.
- Avoid filenames distinguished only by case; many filesystems ignore case.
- Preserve upstream filenames for imported sources under the format's
  `imported/` folder. They are inputs, not generated model outputs, and do not
  need a matching script.

## Renaming or retiring outputs

Changing `out=` or deleting a model does not remove its previous artifacts.
Before a rename, record the old output paths, any `.step.json` sidecar and
declared meshes. Rename the entrypoint and its matching outputs, rebuild and
verify the new files, then remove only the obsolete generated files by exact
path. Preserve imported sources and unrelated artifacts.

## Building many models

Running a root builds its dependencies. For independent outputs, run the
catalog's entrypoints; independent roots can run concurrently, subject to the
runtime's CPU and memory admission. Avoid duplicate simultaneous exports of the
same document. Batch snapshot views in one JSON job when they share scene settings.

When several agents work on an assembly, independent subsystem entrypoints let
them build and verify their work before the root incorporates it.

## Model catalog

For a multi-model project, keep `src/README.md` short and update it when the
entrypoints or outputs change:

```markdown
# Models

| Script | Output | Purpose |
| --- | --- | --- |
| plate.py | STEP/plate.step | Mounting plate |
| plate_drawing.py | DXF/plate_drawing.dxf | Plate flat pattern |
| assembly.py | STEP/assembly.step | Plate with standoffs |

Build: `python src/assembly.py` from the project root builds the assembly and
its dependencies. Run independent entrypoints separately. Unchanged models are current.
Imported source: STEP/imported/servo.step.
```

## Version control

Follow the repository's existing ignore, artifact and Git LFS policies, and the
user's commit instructions. For a new project, a useful default is to retain
authored code, reusable checks and irreplaceable inputs, while ignoring
reproducible outputs and scratch files. Keep pinned fixtures or deliverables
when the project requires them; kernel upgrades can change bytes without
changing geometry.

Example ignore patterns for that default:

```gitignore
/STEP/*
!/STEP/imported/
/DXF/*
!/DXF/imported/
/STL/*
!/STL/imported/
/GLB/*
!/GLB/imported/
/3MF/*
!/3MF/imported/
/tmp/
__pycache__/
```

The `*` forms allow Git to descend into the format folders and honor the
`imported/` exceptions. Git LFS is optional unless the repository requires it;
use it for large binary inputs when appropriate. See the
[starter](project-template.md#project-bookkeeping) for an LFS example.

## Scaffolding a new project

Choose a [minimal starter](project-template.md): a single part or a small
assembly. Add other formats, helpers, groups and imported files only as needed.
Build the selected entrypoint, check its geometry and review its snapshot.
