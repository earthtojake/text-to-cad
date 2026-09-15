# Project scaffold template

Create these files verbatim (rename `demo`/`plate` to the real project/part),
then run `python src/assembly.py` from the project root to verify the loop.
The finished tree at the end shows the whole project after that first build.

The project root, `demo/` below, is the workspace root when the workspace is
bare, and otherwise sits inside the workspace's existing home for models —
`<workspace>/models/demo/`, or `cad/`, `hardware/`, whatever it already uses;
`models/` is only the conventional name. Everything under `demo/` is the same
either way.

The template is one of everything: a part (`plate`), a drawing of it
(`plate_drawing`), a print-only mesh part (`standoff`), a mirrored pair built
from one factory (`bracket_left`/`bracket_right`), a sub-assembly that places
one child twice (`frame`), and the root assembly (`assembly`).

## `src/plate.py`

```python
"""Demo part: a mounting plate with corner holes."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import holes

WIDTH = 60.0
DEPTH = 40.0
THICKNESS = 4.0


HOLE_D = 4.5


@step(out="../STEP/plate.step")
def plate():
    body = bd.Box(WIDTH, DEPTH, THICKNESS)
    return holes.corner_holes(body, WIDTH, DEPTH, THICKNESS, HOLE_D)


if __name__ == "__main__":
    plate()
```

## `src/plate_drawing.py`

```python
"""Demo drawing: the plate's flat pattern (outline + corner holes)."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

from lib import holes
from plate import DEPTH, WIDTH  # constants from a model: tracked by value; importing never builds


HOLE_D = 4.5


@dxf(out="../DXF/plate_drawing.dxf")
def plate_drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(WIDTH, DEPTH)
        with bd.Locations(*holes.corner_hole_centers(WIDTH, DEPTH)):
            bd.Circle(HOLE_D / 2, mode=bd.Mode.SUBTRACT)
    return cut.sketch  # a bare shape is the CUT layer


if __name__ == "__main__":
    plate_drawing()
```

A `@dxf` function returns build123d 2D geometry and the engine writes the DXF —
the same division of labor `@step` has. Return `{layer: shape}` instead when a
drawing genuinely has more than one CAM operation. See the `$dxf` skill.

## `src/standoff.py`

```python
"""Demo print-only part: a standoff that exists as a mesh, never a STEP."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import stl

HEIGHT = 12.0
OUTER_D = 8.0
BORE_D = 3.4


@stl(out="../STL/standoff.stl")
def standoff():
    return bd.Cylinder(OUTER_D / 2, HEIGHT) - bd.Cylinder(BORE_D / 2, HEIGHT)


if __name__ == "__main__":
    standoff()
```

`@stl` alone declares a model whose outputs are meshes: same store record,
same no-op, and it composes into `frame` below like any part. Add `@step` above
it later if a STEP is ever wanted; nothing else changes.

## `src/bracket_left.py`

```python
"""Demo part: the left-hand side bracket."""

from __future__ import annotations

from cadgen import step

from lib.bracket_shape import side_bracket


@step(out="../STEP/bracket_left.step")
def bracket_left():
    return side_bracket()


if __name__ == "__main__":
    bracket_left()
```

## `src/bracket_right.py`

```python
"""Demo part: the right-hand side bracket — the left one's mirror image."""

from __future__ import annotations

from cadgen import step

from lib.bracket_shape import side_bracket


@step(out="../STEP/bracket_right.step")
def bracket_right():
    return side_bracket(mirrored=True)


if __name__ == "__main__":
    bracket_right()
```

STEP cannot express a reflection, so a mirrored part is its own model: the
shape lives once, in the factory, and each hand is a one-line model with its
own STEP, its own record and its own place in the assembly.

## `src/frame.py`

```python
"""Demo sub-assembly: the plate carrying two standoffs."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from plate import THICKNESS, WIDTH, plate   # the model (by result) and two constants (by value)
from standoff import standoff

PITCH = WIDTH / 2


@step(out="../STEP/frame.step")
def frame():
    base = plate()                                  # built if stale, else loaded; LINKED
    base.label = "plate"
    post = standoff()                               # a mesh-only child links like any other
    left = bd.Pos(-PITCH / 2, 0.0, THICKNESS / 2) * post    # placed: one link …
    left.label = "standoff_left"
    right = bd.Pos(PITCH / 2, 0.0, THICKNESS / 2) * post    # … placed again: a second link, one tree
    right.label = "standoff_right"
    return bd.Compound(children=[base, left, right], label="frame")


if __name__ == "__main__":
    frame()
```

Place children with `Pos/Rot/Location * child` or `child.moved(loc)` — never
`child.located(loc)`, which copies the geometry and turns the link into a
duplicate component.

## `src/assembly.py`

```python
"""Demo root assembly: the frame between its two brackets."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from bracket_left import bracket_left
from bracket_right import bracket_right
from frame import frame
from plate import DEPTH, THICKNESS

SPAN = DEPTH / 2 + 6.0


@step(out="../STEP/assembly.step")
def assembly():
    core = frame()                                  # a sub-assembly: its tree, linked
    core.label = "frame"
    left = bd.Pos(0.0, -SPAN, THICKNESS) * bracket_left()
    left.label = "bracket_left"
    right = bd.Pos(0.0, SPAN, THICKNESS) * bracket_right()
    right.label = "bracket_right"
    return bd.Compound(children=[core, left, right], label="assembly")


if __name__ == "__main__":
    assembly()
```

Running `python src/assembly.py` builds every stale model beneath it — the
brackets, the frame, and through the frame the plate and the standoff — in
parallel, and links their results. Rebuilding a part alone does not rebuild
this root; rerun it to pick up the change.

## `src/lib/__init__.py`

```python
"""Shared helpers for the demo project: hole patterns and the bracket factory."""
```

`src/lib/` is a regular package, so this file is never omitted — one line naming
what the package holds is the whole file.

## `src/lib/holes.py`

```python
"""Shared hole helpers (plain module: no @step here)."""

from __future__ import annotations

from cadgen import build123d as bd

INSET = 6.0


def corner_hole_centers(width: float, depth: float):
    """The four corner-hole centers, shared by the part and its drawing."""
    return [
        (sx * (width / 2 - INSET), sy * (depth / 2 - INSET))
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


def corner_holes(body, width: float, depth: float, thickness: float, hole_d: float):
    for x, y in corner_hole_centers(width, depth):
        body -= bd.Pos(x, y, 0) * bd.Cylinder(hole_d / 2, thickness * 2)
    return body
```

## `src/lib/bracket_shape.py`

```python
"""The side-bracket factory: one shape, two hands (plain module: no @step here)."""

from __future__ import annotations

from cadgen import build123d as bd

LENGTH = 40.0
HEIGHT = 10.0
THICKNESS = 6.0
HOLE_D = 5.0


def side_bracket(mirrored: bool = False) -> bd.Shape:
    body = bd.Box(LENGTH, THICKNESS, HEIGHT)
    body -= bd.Pos(LENGTH / 4, 0.0, 0.0) * bd.Rot(90, 0, 0) * bd.Cylinder(HOLE_D / 2, THICKNESS * 2)
    return bd.mirror(body, about=bd.Plane.YZ) if mirrored else body
```

A helper in `lib/` is part of the SOURCE of every model that imports it: any
edit here rebuilds both brackets (and, on their next run, the assemblies that
use them). That is the right behaviour for a factory — and the reason shared
code that is really a sub-assembly should be a model file instead.

## `src/README.md`

```markdown
# demo models

| Script           | Artifact               | Description                           |
|------------------|------------------------|---------------------------------------|
| plate.py         | STEP/plate.step        | Mounting plate, `HOLE_D` corner holes |
| plate_drawing.py | DXF/plate_drawing.dxf  | Plate flat pattern                    |
| standoff.py      | STL/standoff.stl       | Print-only standoff (mesh only)       |
| bracket_left.py  | STEP/bracket_left.step | Left side bracket                     |
| bracket_right.py | STEP/bracket_right.step| Right side bracket (mirror image)     |
| frame.py         | STEP/frame.step        | Plate + two standoffs (sub-assembly)  |
| assembly.py      | STEP/assembly.step     | Frame + both brackets (root)          |

Build: `python src/assembly.py` builds the root and whatever is stale beneath
it; `python src/plate_drawing.py` for the drawing; unchanged models are no-ops.
Imported sources: STEP/imported/servo.step (committed, no script).
```

`STEP/imported/servo.step` stands for any source file brought in from outside
(a vendor download, a supplier's model) under its upstream name: no script
produces it, so it is committed, and a model script that composes it reads it
with `cadgen.read_step` anchored on the script's own location — scripts build
from any working directory, so the path is
`Path(__file__).parent / "../STEP/imported/servo.step"`, never a bare relative
string (the `$cad` skill covers `read_step`, and how to wrap an import in a
model of its own so assemblies can link to it).

## `.gitignore`

```gitignore
/STEP/*
!/STEP/imported/
!/STEP/*.step.js
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

The `*` forms matter: ignoring the directory itself (`/STEP/`) would make the
`imported/` negation dead — git never descends into an ignored directory. The
`!/STEP/*.step.js` line keeps render modules (the authored choreography beside
a document, `arm.step.js` beside `arm.step`) committed while everything
generated around them stays ignored. A project whose folders mirror the
product tree (groups, sub-assembly folders, `purchased/`) needs the negations
at every depth, because git never descends into an ignored directory:

```gitignore
/STEP/*
!/STEP/imported/
!/STEP/*.step.js
!/STEP/*/
/STEP/*/*
!/STEP/*/*.step.js
!/STEP/*/*/
/STEP/*/*/*
!/STEP/*/*/*.step.js
```

One `!/STEP/*/`, `/STEP/*/*`, `!/STEP/*/*.step.js` triple per nesting level
(the same for `DXF/`, `STL/`, `GLB/`, `3MF/`). Pin any other file deliberately
with its own negation line or `git add -f`.

## `.gitattributes`

```gitattributes
# Imported sources are binaries you did not write: keep them out of plain git history.
STEP/imported/** filter=lfs diff=lfs merge=lfs -text
DXF/imported/**  filter=lfs diff=lfs merge=lfs -text
STL/imported/**  filter=lfs diff=lfs merge=lfs -text
GLB/imported/**  filter=lfs diff=lfs merge=lfs -text
3MF/imported/**  filter=lfs diff=lfs merge=lfs -text

# Authored text beside the documents stays plain git.
*.step.js text
*.step.json text
```

A per-project file at the project root, next to `.gitignore`. The `imported/`
folders hold vendor STEPs, supplier DXFs and other files you did not author;
tracking them with Git LFS keeps those binaries out of plain git history while
the render modules and sidecars beside the documents stay diffable text. Run
`git lfs install` once per machine. If a file under `imported/` is a few lines
of text beginning `version https://git-lfs...`, it is an LFS pointer whose
object was not fetched: `read_step` fails on it, and
`git lfs checkout STEP/imported` (or the folder in question) is the fix.

## Verify

```bash
python src/assembly.py                   # builds the root and, beneath it, frame, plate, standoff, both brackets
python src/assembly.py                   # "current" — the no-op gate works
python src/plate_drawing.py              # builds DXF/plate_drawing.dxf (the drawing is not under the root)
cadgen store why src/frame.py            # the frame's record: its two children, pinned and current
cadgen step snapshot STEP/assembly.step tmp/assembly.png
```

## The finished tree

After the verify loop, the project is complete and looks like this — the one
exemplar this structure needs:

```
demo/
  .gitignore
  .gitattributes
  src/                          # committed — the only thing anyone edits
    README.md
    plate.py
    plate_drawing.py
    standoff.py
    bracket_left.py
    bracket_right.py
    frame.py
    assembly.py
    lib/
      __init__.py
      holes.py
      bracket_shape.py
  STEP/
    plate.step                  # generated by src/plate.py — ignored
    bracket_left.step
    bracket_right.step
    frame.step
    assembly.step
    assembly.step.js            # the render module beside assembly.step — authored, committed
    imported/
      servo.step                # brought in from outside — committed
  STL/
    standoff.stl                # generated by src/standoff.py — ignored
  DXF/
    plate_drawing.dxf           # generated by src/plate_drawing.py — ignored
  tmp/
    assembly.png                # the snapshot: scratch — ignored
```

No model here declares kinematics or a mesh export beside its STEP, so no
`.step.json` sidecar is written; a model that does gets one beside its
document, generated with it and ignored with it. `assembly.step.js` is the
other file beside a document: the render module (choreography — see the cad
skill's kinematics reference). Nothing generates it and no build reads it; the
viewer loads it by name, so it is authored like `src/` and committed like
`imported/`.

`git status` in this tree shows exactly `.gitignore`, `.gitattributes`, `src/`,
`STEP/assembly.step.js` and `STEP/imported/servo.step`: authored code, the
authored choreography, and the one input code cannot regenerate. Everything
else is rebuilt by running the scripts, so a fresh clone that runs
`python src/assembly.py && python src/plate_drawing.py` arrives at this same
tree.
