# CAD project structure

cadgen does not infer paths from folder names: each model declares its outputs,
so any layout works, and an existing project's layout is the one to extend. For
a new multi-model project the structure below is a good default; a one-off part
can use a flat folder, and [minimal starters](project-template.md) show a part
and a small assembly. In a larger workspace, CAD work usually lives in its
existing `models/`, `cad/` or `hardware/` area.

## Source and output mapping

A script's stem carried into its outputs (`src/bracket.py` declaring
`STEP/bracket.step`, `STL/bracket.stl`, `GLB/bracket.glb` or `3MF/bracket.3mf`)
keeps each artifact traceable to its source. Stacking output decorators still
declares one model. Helpers and package `__init__.py` files are not model
entrypoints.

```
<project>/
  src/
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
  tmp/                    # ignored scratch: exploratory scripts, snapshots
```

Mirroring nested source paths in output folders keeps repeated names
unambiguous: `src/chassis/frame.py` → `STEP/chassis/frame.step`. Several mesh
densities of the same model can keep the stem in variant subfolders, such as
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

`python src/plate.py` builds it from the project root; an unchanged model is a
no-op.

## Imports and shared code

Models use ordinary Python imports. Flat scripts can import sibling models and
`lib/` directly. For nested scripts, `PYTHONPATH` declares the import root;
cadgen adds no paths of its own. From the project root:

```bash
PYTHONPATH=src python src/chassis/frame.py
```

Python packages and relative imports are supported. With
`src/chassis/__init__.py`, a model that uses relative imports runs as a module:

```bash
PYTHONPATH=src python -m chassis.frame
```

Direct execution puts the script's directory first on the import path, so
`frame/frame.py` run by path hides a `frame` package it imports; a distinct
entrypoint name or module execution avoids that. A module and a same-named model
function shadow each other on import; an alias separates them.

Dependencies are tracked as **models by result, constants by value, functions by reach**:

```python
from lib import fasteners  # helper module: tracked by what the model can run in it
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
whole build** (`python src/assembly.py`). Rebuilding a child alone
does NOT rebuild the assemblies that use it.

A child model has its own record, outputs and reusable result; a helper executes
within its caller. A subassembly needs no folder of its own. Mirrored geometry can
stay inline or become separate left/right models; see
[mirroring and caching](step-generation.md#mirrored-geometry-and-reusable-models).
A print-only part can declare `@stl`, `@glb` or `@threemf` without `@step` and
still compose into an assembly.

Independent roots can run concurrently, subject to the runtime's CPU and memory
admission. Subsystem entrypoints let several agents build and check their parts
of an assembly before the root incorporates them.

## Naming

- A model a parent imports needs an importable Python identifier as its stem; an
  external part number that is not one can go in a label.
- A drawing is a separate model: `plate_drawing.py` → `DXF/plate_drawing.dxf`.
- Filenames distinguished only by case collide on case-insensitive filesystems.
- Imported sources (here, under the format's `imported/` folder) are inputs, not
  generated outputs, and need no script.
- Changing `out=`, renaming a script or deleting a model leaves its previous
  artifacts (STEP, sidecar, meshes) where they were.

## Version control

Generated outputs are reproducible from their sources, and kernel upgrades can
change their bytes without changing geometry, so a new project can ignore them and
keep authored code and irreplaceable inputs. A pinned deliverable is the
exception.

Every sidecar (`<name>.step.json`) is rebuilt by its model script, or by the
`cadgen step build` command that annotated an imported STEP, from that command
and any `--kinematics` or `--materials` JSON it reads. Baked animation keyframes
can run a sidecar to hundreds of kilobytes. A STEP committed as a pinned
deliverable carries its kinematics, materials and animation in its sidecar, so
the two belong together.

Example ignore patterns for that default:

```gitignore
*.step.json
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
`imported/` exceptions. A file that starts with `version https://git-lfs` is a
Git LFS pointer, not CAD data: `git lfs checkout` restores objects already in the
local cache, and missing ones need fetching from the project's LFS remote.
