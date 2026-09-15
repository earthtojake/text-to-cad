# DXF drawing templates

Read this file when creating a new `<name>.py` drawing script. Copy the
template for the workflow that applies and replace the TODO markers.

Every template follows one contract: **the parameterless `@dxf` function
returns build123d 2D geometry and the engine writes the DXF.** You never
construct a document, name a file, or think about entities.

- Return a **bare shape** for a single-operation drawing — it lands on the `CUT`
  layer.
- Return **`{layer: shape}`** when the drawing genuinely has more than one CAM
  operation (`CUT` / `ENGRAVE` / `SCORE`).
- Geometry must lie in the **XY plane**. A face derived from a solid is at that
  solid's height, so relocate it (`flatten.flatten_face`, or
  `bd.Location((0, 0, -z)) * face`). The engine refuses off-plane geometry
  rather than silently writing its XY shadow.
- Validation runs during generation: cut layers must hold closed profiles, and
  open geometry belongs on a bend/engrave/reference-named layer.
- Every script ends with `if __name__ == "__main__": <drawing>()` — the call
  is what builds it.

## 1. Standalone drafting (DXF from scratch)

For pure 2D outputs — gaskets, panels, templates, cut layouts — with no 3D model
behind them. Keep meaningful dimensions as named constants.

```python
"""Standalone 2D drawing: <description>."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

# TODO: named dimension constants
WIDTH_MM = 40.0
HEIGHT_MM = 20.0
HOLE_D_MM = 4.5


@dxf
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

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

WIDTH_MM = 40.0
HEIGHT_MM = 20.0


@dxf
def drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(WIDTH_MM, HEIGHT_MM)
    with bd.BuildSketch() as mark:
        bd.Text("REV B", font_size=6)
    return {"CUT": cut.sketch, "ENGRAVE": mark.sketch}


if __name__ == "__main__":
    drawing()
```

Text is engraved **outlines**, not DXF `TEXT` entities: cut and marking
toolchains consume geometry, and font rendering inside CAM is unreliable.

## 2. Flat pattern of a generated STEP part

For a profile of a `$cad` model. The drawing imports the model and calls it,
exactly as an assembly composes a child: importing a model never builds it,
and the call inside the drawing's build returns the part's geometry (building
the part first if it is stale). The drawing's record pins the part's RESULT,
so a geometry change in the part makes the drawing stale and a comment or
refactor does not; a constant imported from the part is tracked by value.

```python
"""Flat-pattern DXF drawing for <name>; geometry reused from <name>.py."""

from __future__ import annotations

from cadgen import dxf, flatten

from <name> import <name>          # a child: tracked by its result; importing never builds

THICKNESS_MM = 6.0                 # TODO: the profile face's height


KERF = 0.0


@dxf
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
call. Do the steps yourself when a part needs them apart — a bracket with
flanges on several planes selects each one, flattens each with its own
transform, and unions the result:

```python
@dxf
def drawing():
    part = bracket()
    faces = [
        *flatten.planar_faces(part, normal_axis="z", normal_sign=1.0,
                              coordinate_axis="z", coordinate=3.0),
        *flatten.planar_faces(part, normal_axis="y", normal_sign=-1.0,
                              coordinate_axis="y", coordinate=0.0),
    ]
    return flatten.union_faces(flatten.flatten_faces(faces))
```

## 3. Flat pattern of an imported STEP

For a vendor `.step` with no Python source. Read it with `cadgen.read_step`,
which records the file's content hash as a build input — replacing the STEP
makes the drawing stale on its own, with no `--force`.

The face selection is a part-specific judgment call: pick the planar face(s)
that define the cut profile.

Never point `read_step` at a STEP this project GENERATES — that is a model
whose input changes every time its sibling builds. Keep vendor files in an
`imported/` directory beside the drawing (see the CAD skill's
`step-generation.md`), and give the drawing its own stem:

```python
"""DXF profile of vendor_panel.step."""

from __future__ import annotations

from pathlib import Path

from cadgen import dxf, flatten, read_step

_STEP_PATH = Path(__file__).parent / "imported" / "vendor_panel.step"


KERF = 0.15


@dxf
def drawing():
    part = read_step(_STEP_PATH)
    top_z = part.bounding_box().max.Z
    return flatten.flat_pattern(part, coordinate=top_z, kerf=KERF)


if __name__ == "__main__":
    drawing()
```

## Common additions

- **Bend / fold lines**: put them on a layer whose name contains `bend`
  (`{"CUT": profile, "BEND": fold_lines}`). Open geometry is allowed there, and
  downstream tools classify it as bends rather than cuts.
- **Kerf / tool-radius compensation**: `flatten.offset_profile(shape, amount)`,
  or the `kerf=` argument of `flat_pattern`. Positive grows the profile (cut
  outside the line), negative shrinks it. Never hand-offset coordinates.
- **Curves stay curves.** The union and the offset are OCC operations on the real
  faces, so a filleted corner exports as an `ARC` and a hole as a `CIRCLE`, kerf
  included. If a drawing comes out as hundreds of short `LINE`s, something fell
  back to the sampled path — check the union inputs rather than accepting it.
- **Why did it (not) rebuild?** `cadgen store why <drawing>.py` prints the
  drawing's gate: its closure files, each part it called with the pinned and
  current tree, and whether the `.dxf` on disk is the one it wrote.
