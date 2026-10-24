# CAD project structure

Read this file when starting a CAD project, adding models to one, or deciding where
scripts, inputs and deliverables go.

## Contents

- [Layout](#layout)
- [Starting a project](#starting-a-project)
- [Imports and shared code](#imports-and-shared-code)
- [Assemblies and model boundaries](#assemblies-and-model-boundaries)
- [Naming](#naming)
- [Version control](#version-control)

## Layout

cadgen infers nothing from folder names, so any layout works, and an existing
project's layout is the one to extend. In a larger workspace, CAD work usually lives in
its existing `models/`, `cad/` or `hardware/` area. For a new project of several models
this is a good default; a one-off part can be one script in a flat folder.

```
<project>/
  src/
    plate.py              # one part, or a part's configurations, per script
    standoff.py
    assembly.py           # the root assembly: calls the parts
    exports.py            # optional: the deliverables the person keeps current
    chassis/              # optional grouping as the project grows
      __init__.py
      frame.py
      strut.py
    lib/                  # shared helpers and constants: plain modules
      __init__.py
      holes.py
  vendor/                 # vendor STEP files, each with the xbf converted from it
    motor.step
    motor.xbf
  STEP/  STL/  GLB/  3MF/  DXF/   # files written on request, by cadgen export or exports.py
  tmp/                    # ignored scratch: checks, snapshots
```

Runs write nothing, so the output folders exist only once someone asks for files.
`exports.py` ([standing deliverables](exports.md#standing-deliverables-exportspy)) is the
one script in a project that writes files. The output folders are generated on request
and gitignored by default; commit them only when the person asks for the files in the
repository (a repository published for people who print or order the parts).

## Starting a project

One part, `src/plate.py`:

```python
import build123d as bd
from cadgen import model

WIDTH = 60.0
DEPTH = 40.0
THICKNESS = 4.0


@model
def plate():
    body = bd.Box(WIDTH, DEPTH, THICKNESS)
    body.label = "plate"
    return body


if __name__ == "__main__":
    plate()
```

```bash
python src/plate.py
```

and a `.gitignore` beside `src/`:

```gitignore
/STEP/
/STL/
/GLB/
/3MF/
/DXF/
/tmp/
__pycache__/
```

A second run replays the model and changes nothing. Then a part with configurations,
`src/standoff.py`, and the assembly that places two of them on the plate,
`src/assembly.py`, as in [models](model-contract.md#assemblies-call-their-parts):

```bash
python src/assembly.py
cadgen inspect "$ID"
```

Running the root builds its children in the same run, each keeping its own document;
running a child alone leaves the root as it was until the root runs. `cadgen inspect`
prints what the root's document was built from.

| Need | Add |
| --- | --- |
| A file of a model | `cadgen export "$ID" STEP/assembly.step` when asked; `exports.py` when the person keeps files current. See [exports](exports.md). |
| A variant | Another `@model` calling the part's helper with other values. |
| Shared factory or hole pattern | A plain helper under `src/lib/`, with `src/lib/__init__.py`. |
| Left/right geometry | Mirror inline, or separate models for independent files and reuse. |
| Subassembly | A model that calls its child models. |
| Motion | build123d joints in the assembly's body, then `cadgen.ap242`. See [kinematics](kinematics.md). |
| An explode or a showcase | `cadgen.gltf`'s `animation()`. See [animation](animation.md). |
| Materials | `part.material = materials.aluminium_6061`. See [colour and materials](build123d-modeling.md#colour-and-materials). |
| 2D drawing | A separate drawing script using `$dxf`. |
| Vendor CAD | The vendor STEP under `vendor/`, converted once with `cadgen export vendor/motor.step vendor/motor.xbf` and read with `read_xbf` (an anchored path). |

## Imports and shared code

Models use ordinary Python imports. A script's folder is first on the module search
path, so flat scripts import their siblings and `lib/` directly. A script inside a
package (`src/chassis/` holds an `__init__.py`) is that package's module: its relative
imports work, and the folder above its topmost package is on the path too, so
`src/chassis/frame.py` imports `lib.holes` as well. Both run alike:

```bash
python src/chassis/frame.py
cd src && python -m chassis.frame
```

Without packages, `PYTHONPATH` names the import root (`PYTHONPATH=src python
src/chassis/frame.py`); cadgen adds no paths of its own. A module and a same-named
model function shadow each other on import; an alias separates them.

What a run re-runs follows what the code reaches: an edit to a `lib/` helper re-runs the
bodies that call it and leaves the rest replaying, a constant edit re-runs the bodies
that read it, and a comment re-runs nothing
([what a run runs](model-contract.md#what-a-run-runs)).

## Assemblies and model boundaries

A parent calls its child models inside its body, and each child builds in the same run:
**running the root is the whole rebuild** (`python src/assembly.py`). Running a child
alone rebuilds the child and leaves the assemblies that use it as they were.

A child model has its own document and page; a helper runs within its caller and is no
document. A sub-assembly needs no folder of its own. Mirrored geometry can stay inline or
become separate left and right models.

A big assembly stays fast to edit without splitting: the worker replays what an edit
does not reach, and a sub-assembly stage marked `@memo` is replayed whole
([`@memo`](model-contract.md#memo-marks-stages)). Separate root scripts
run at once, each in its own worker, so subsystem scripts let several agents build and
check their parts before the root takes them in.

## Naming

- A model a parent imports needs an importable Python identifier as its script's stem;
  an external part number that is not one can go in a label.
- A file a model is exported to carries its model's name (`standoff_m3` →
  `STL/standoff_m3.stl`), so each file traces back to its source.
- Filenames distinguished only by case collide on case-insensitive filesystems.
- Vendor files are inputs, not outputs, and need no script.

## Version control

Every exported file is reproducible from the code and its inputs, so the project's
`.gitignore` ([starting a project](#starting-a-project)) keeps the output folders out
unless the person asks for the files in the repository.

Vendor STEP files are irreplaceable inputs: commit them. The xbf converted from one is
made again by one `cadgen export`. A file that starts with `version https://git-lfs` is a
Git LFS pointer, not CAD data: `git lfs checkout` restores objects already in the local
cache, and missing ones need fetching from the project's LFS remote.
