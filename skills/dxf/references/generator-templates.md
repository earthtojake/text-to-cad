# DXF drawing templates

Read this file when creating a new `<name>.py` drawing script. Copy the
template for the workflow that applies and replace the TODO markers.

Every template follows one contract: **the parameterless `@model` function returns
build123d 2D geometry on z=0, and `cadgen export <id> <name>.dxf` writes the DXF.**
You never construct a document, name a file in the model, or think about entities.

- Return **one shape** for a single-operation drawing: it lands on the `CUT`
  layer.
- Return a **`Compound` of labelled children** when the drawing genuinely has more
  than one CAM operation: each child's label is its layer (`CUT`, `ENGRAVE`,
  `SCORE`).
- Geometry must lie on **z=0**. A face derived from a solid is at that solid's
  height, so relocate it (`flatten.flatten_face`, or
  `bd.Location((0, 0, -z)) * face`). The export refuses a solid, and an edge with a
  point more than 1e-6 mm off z=0, rather than silently writing its XY shadow.
- The drawing checks run when the DXF is exported, before the file is written: cut
  layers must hold closed profiles, and open geometry belongs on a
  bend/engrave/reference-named layer.
- Decoration only declares: the script's `__main__` block calls the drawing, and
  `python <name>.py` builds what it calls and prints each drawing's id. Then
  `cadgen export <id> DXF/<name>.dxf` writes the file.

## 1. Standalone drafting (DXF from scratch)

For pure 2D outputs (gaskets, panels, templates, cut layouts) with no 3D model
behind them. Keep meaningful dimensions as named constants.

```python
"""Standalone 2D drawing: <description>."""

import build123d as bd
from cadgen import model

# TODO: named dimension constants
WIDTH_MM = 40.0
HEIGHT_MM = 20.0
HOLE_D_MM = 4.5


@model
def drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(WIDTH_MM, HEIGHT_MM)
        bd.Circle(HOLE_D_MM / 2, mode=bd.Mode.SUBTRACT)
    return cut.sketch


if __name__ == "__main__":
    drawing()
```

Two layers, when the part is both cut and marked:

```python
"""Standalone 2D drawing with a marking layer."""

import build123d as bd
from cadgen import model

WIDTH_MM = 40.0
HEIGHT_MM = 20.0


@model
def drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(WIDTH_MM, HEIGHT_MM)
    with bd.BuildSketch() as mark:
        bd.Text("REV B", font_size=6)
    profile, text = cut.sketch, mark.sketch
    profile.label, text.label = "CUT", "ENGRAVE"
    return bd.Compound(children=[profile, text], label="drawing")


if __name__ == "__main__":
    drawing()
```

Text is engraved **outlines**, not DXF `TEXT` entities: cut and marking
toolchains consume geometry, and font rendering inside CAM is unreliable.

## 2. Flat pattern of a modelled part

For a profile of a `$cad` model. The drawing imports the model and calls it,
exactly as an assembly composes a child: importing a model never builds it, and
the call inside the drawing's run builds the part in the same run and returns its
geometry. An edit to the part re-runs the drawing's body on its next run; a constant
imported from the part counts by its value.

```python
"""Flat-pattern DXF drawing for <name>; geometry reused from <name>.py."""

from cadgen import flatten, model

from <name> import <name>          # the model: importing builds nothing

THICKNESS_MM = 6.0                 # TODO: the profile face's height
KERF = 0.0


@model
def drawing():
    return flatten.flat_pattern(
        <name>(),
        coordinate=THICKNESS_MM,   # TODO: which face plane defines the profile
        kerf=KERF,
    )


if __name__ == "__main__":
    drawing()
```

`flat_pattern` is selection + flatten + union + optional kerf offset in one
call. Do the steps yourself when a part needs them apart: a bracket with flanges
on several planes selects each one, flattens each with its own transform, and
unions the result:

```python
@model
def drawing():
    part = bracket().shape
    faces = [
        *flatten.planar_faces(part, normal_axis="z", normal_sign=1.0,
                              coordinate_axis="z", coordinate=3.0),
        *flatten.planar_faces(part, normal_axis="y", normal_sign=-1.0,
                              coordinate_axis="y", coordinate=0.0),
    ]
    return flatten.union_faces(flatten.flatten_faces(faces))
```

## 3. Flat pattern of an imported STEP

For a vendor `.step` with no Python source. Read it with `read_step`, or convert
it once with `cadgen export vendor_panel.step vendor_panel.xbf` and read the xbf
with `read_xbf`, which is faster. Like every file a run reads, it is an input:
replacing it re-runs the drawing.

The face selection is a part-specific judgment call: pick the planar face(s)
that define the cut profile.

Never point a read at a file this project EXPORTS: compose the project's own
models by calling them. Keep vendor files in a `vendor/` directory beside the
drawing, and give the drawing its own stem:

```python
"""DXF profile of vendor_panel.step."""

from pathlib import Path

from cadgen import flatten, model, read_step

STEP_PATH = Path(__file__).resolve().parent / "vendor" / "vendor_panel.step"
KERF = 0.15


@model
def drawing():
    part = read_step(STEP_PATH)
    top_z = part.bounding_box().max.Z
    return flatten.flat_pattern(part, coordinate=top_z, kerf=KERF)


if __name__ == "__main__":
    drawing()
```

## Common additions

- **Bend / fold lines**: put them on a layer whose name says so (`BEND`, `FOLD`),
  a labelled child beside the profile. Open geometry is allowed there, and
  downstream tools classify it as bends rather than cuts.
- **Kerf / tool-radius compensation**: `flatten.offset_profile(shape, amount)`,
  or the `kerf=` argument of `flat_pattern`. Positive grows the profile (cut
  outside the line), negative shrinks it. Never hand-offset coordinates.
- **Curves stay curves.** The union and the offset are OCC operations on the real
  faces, so a filleted corner exports as an `ARC` and a hole as a `CIRCLE`, kerf
  included. If a drawing comes out as hundreds of short `LINE`s, something fell
  back to the sampled path: check the union inputs rather than accepting it.
- **Why did it (not) rebuild?** The run's report says how each body went (`run` or
  `replayed`); `cadgen inspect <id>`, the id the run printed, prints what the drawing
  was built from.
- **Kept current**: an `exports.py` beside the drawings calls `export(drawing, path)`
  for each, the model function itself, with paths anchored on `__file__`.
