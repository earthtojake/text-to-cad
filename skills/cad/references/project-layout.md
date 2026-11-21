# CAD project structure

Read this file when starting a CAD project, adding models to one, or deciding where
scripts, inputs and deliverables go.

## Layout

text-to-cad infers nothing from folder names, so any layout works, and an existing
project's layout is the one to extend. For a new project of several models this is a good
default; a one-off part can be one script in a flat folder.

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
  STEP/  STL/  GLB/  3MF/  DXF/   # written on request, each file named for its model (STL/standoff_m3.stl)
  tmp/                    # ignored scratch: checks, snapshots
```

Runs write nothing, so the output folders exist only once someone asks for files.
`exports.py` ([standing deliverables](exports.md#standing-deliverables-exportspy)) is the
one script in a project that writes files.

A child model has its own document, id and page, so it can be inspected, drawn and
exported alone; a helper runs within its caller and is no document. Separate root scripts
build at once, each in its own worker, so subsystem scripts let several agents build and
check their parts before the root assembly takes them in.

## Imports and shared code

Models use ordinary Python imports. A run puts the script's folder on the module search
path, last, after everything installed: flat scripts import their siblings and `lib/` by
name, and a sibling named like an installed module is not the one imported. Without an
`__init__.py`, a script in a subfolder reaches the project's modules through `PYTHONPATH`
(`PYTHONPATH=src cad run src/chassis/frame.py`), a relative entry read from the folder
the command runs in.

A script inside a package (`src/chassis/` holds an `__init__.py`) runs as that package's
module, from the folder above the package: its relative imports work, and that folder is
on the path, so `chassis/frame.py` imports `lib.holes` as well:

```bash
cad run -m chassis.frame           # in src/
```

Run by its path instead (`cad run src/chassis/frame.py`), such a script's relative
imports and its imports through the folder above can fail as they do in plain Python.

## Version control

Every exported file is reproducible from the code and its inputs, so the output folders
are ignored unless the person asks for the files in the repository (one published for
people who print or order the parts). A `.gitignore` beside `src/`:

```gitignore
/STEP/
/STL/
/GLB/
/3MF/
/DXF/
/tmp/
__pycache__/
```

Vendor STEP files are irreplaceable inputs: commit them. The xbf converted from one is
made again by one `cad step export`.
