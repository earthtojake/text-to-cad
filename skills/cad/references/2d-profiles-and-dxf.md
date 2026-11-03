# 2D profiles and DXF

Read this file when the person asks for a 2D profile, outline, template, gasket, panel, flat
pattern or a laser, plasma, waterjet or routing cut layout, for a DXF file, or to open or review an
existing `.dxf`. Whether a cut file is ready for a shop is the sheet-metal review's
[Cut files (DXF)](manufacturing-sheet-metal.md#cut-files-dxf).

## Contents

- [A drawing is a model](#a-drawing-is-a-model)
- [Build it and export the DXF](#build-it-and-export-the-dxf)
- [Three workflows](#three-workflows)
- [Flat patterns, kerf and curves](#flat-patterns-kerf-and-curves)
- [Check a drawing](#check-a-drawing)
- [See a drawing](#see-a-drawing)

## A drawing is a model

**A drawing is a `@model` function that takes no parameters and returns build123d 2D geometry on
z=0: a sketch, a face, wires or edges. `cad model export <id> drawing.dxf` writes the DXF.** You never
construct a document, name an entity, or write a file from the model. It builds in the server's warm
worker like any model, and the DXF is written from its document by build123d's own exporter, once the
drawing checks pass. The CAD Viewer and `cad dxf snapshot` read the `.dxf` itself, so the file a
cutting service gets, the file the viewer draws and the file a snapshot renders are one file.

```python
import build123d as bd
from cad import model

HOLE_D = 4.5


@model
def gasket():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(HOLE_D / 2, mode=bd.Mode.SUBTRACT)
    return cut.sketch          # one shape: the CUT layer


if __name__ == "__main__":
    gasket()                   # decoration only declares: this call builds it
```

- **One shape** is one layer, `CUT`. That is the whole contract for most drawings.
- **A layer per part** when the drawing genuinely has more than one CAM operation: return a
  `Compound` of labelled children, each label its layer (`profile.label, marks.label = "CUT",
  "ENGRAVE"`). Children sharing a label share a layer, and several shapes make one part of a layer
  as `bd.Compound([a, b], label="ENGRAVE")`. A layer name may not be empty or hold any of
  `<>/\":;?*|=` and a backtick.
- **Layers carry intent.** Keep cut geometry and bend or fold lines on separate layers, and name a
  bend layer with `bend` or `fold` so downstream tools classify it as bends rather than cuts. DXF
  layers are drawing structure, not the STEP's part and assembly structure.
- **Planar means 2D, on z=0, at 1:1.** The export refuses a document holding a solid (`bracket is
  3D: a DXF is drawn from 2D geometry a model returns`) and an edge with any point more than 1e-6 mm
  off z=0, by its element name. A face taken from a solid sits at that solid's height; relocate it
  (`flatten_face(face)`, or `bd.Location((0, 0, -z)) * face`).
- **Units are millimetres.** The server sets `$INSUNITS`; a drawing never declares units.
- **No parameters.** Dimensions are module constants (`HOLE_D = 4.5`) or constants imported from the
  part the drawing derives from; a different drawing is a different `@model` function.
- **Text** is `bd.Text(...)` engraved OUTLINES on a marking layer, never a DXF `TEXT` entity: cut and
  marking toolchains consume geometry, and font rendering inside CAM is unreliable.
- **Output bytes are a function of the geometry.** Layers are written in name order and entities in
  an order of their content, so an unchanged drawing exports an identical file on any machine, and
  the file is replaced only when its bytes change.

## Build it and export the DXF

```bash
cad run src/gasket.py                   # prints id: and view:
cad model export "$ID" DXF/gasket.dxf     # ID: the id: line it printed; runs the drawing checks
```

Running the script is the only way to build a drawing, and exporting it the only way to write its
DXF. `cad run <drawing>.py` writes nothing; it prints each model's report (`built
src/gasket.py::gasket cold in 2.29s: ...`), its `id:` and its page, and exits 1 when a body raises.
Run each drawing script directly; do not sweep directories. `cad model export` exits 2 when it refuses
the drawing (3D, off the plane, a failed drawing check), naming which. An existing `.dxf` needs
neither: hand it straight to a snapshot or the viewer.

Drawings delivered after every change go in an `exports.py` beside them that imports each drawing
and calls `export(drawing, path)` (the model function itself, or the handle its call returns), with
paths anchored on `__file__`:

```python
# src/exports.py
from pathlib import Path

from cad import export

from gasket import gasket

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    export(gasket, ROOT / "DXF/gasket.dxf")
```

In a project built around its exported files, `@dxf("../DXF/gasket.dxf")` (from `cad`, relative to
the script) in place of `@model` writes the file on each run, through the same drawing checks.

Start a drawing from a short brief: outline dimensions, holes and slots, layers, units, output path
and the checks that will show it is right. Give meaningful dimensions named constants, and reuse the
part's geometry helpers rather than duplicating its formulas.

## Three workflows

One model per file is the recommendation, and a drawing gets its own script, in the same directory
as the geometry it derives from. A file MAY declare several models (two drawings, or a drawing
beside a part's `@model`): `cad run <file>.py` builds every one its `__main__` block calls, each with
its own id. A drawing composes models, never the reverse.

### 1. Drafted from scratch

Gaskets, panels, templates and cut layouts with no 3D model behind them:

```python
"""Standalone 2D drawing: <description>."""

import build123d as bd
from cad import model

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
@model
def drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(WIDTH_MM, HEIGHT_MM)
    with bd.BuildSketch() as mark:
        bd.Text("REV B", font_size=6)
    profile, text = cut.sketch, mark.sketch
    profile.label, text.label = "CUT", "ENGRAVE"
    return bd.Compound(children=[profile, text], label="drawing")
```

### 2. Flat pattern of a part this project models

Create and check the 3D model first. The drawing script sits beside the model it derives from, with
its OWN stem (`bracket_drawing.py` beside `bracket.py`), imports the model and calls it, exactly as
an assembly composes a child: importing never builds, and inside the drawing's run the call builds
the part in the same run and returns its geometry.

```python
"""Flat-pattern DXF drawing for bracket; geometry reused from bracket.py."""

from cad import model
from cad.build123d import flat_pattern

from bracket import bracket        # the model: importing builds nothing

THICKNESS_MM = 3.0                 # the profile face's height
KERF = 0.15


@model
def bracket_drawing():
    return flat_pattern(bracket().shape, coordinate=THICKNESS_MM, kerf=KERF)


if __name__ == "__main__":
    bracket_drawing()
```

An edit to the part re-runs the drawing's body on its next run, and a constant imported from the part
counts by its value; an edit the part's body does not reach (a comment, another model) re-runs
nothing.

### 3. Flat pattern of an imported STEP

For a vendor `.step`/`.stp` with no Python source. Read it with `step.read` (`read_step`), or convert
it once (`cad step export vendor_panel.step vendor_panel.xbf`) and read the xbf with `read_xbf`, which
is faster. Like every file a run reads, it is an input: replacing it re-runs the drawing. Which planar
faces define the cut profile is a judgment about the part.

```python
"""DXF profile of vendor_panel.step."""

from pathlib import Path

from cad import model, step
from cad.build123d import flat_pattern

STEP_PATH = Path(__file__).resolve().parent / "vendor" / "vendor_panel.step"
KERF = 0.15


@model
def panel_flat():
    part = step.read(STEP_PATH)                     # an input, by its bytes
    top_z = part.bounding_box().max.Z
    return flat_pattern(part, coordinate=top_z, kerf=KERF)


if __name__ == "__main__":
    panel_flat()
```

**Never read a file this project exports.** Keep source STEPs in a `vendor/` directory beside the
drawing, committed like any other input; for a part this project models, use workflow 2.

## Flat patterns, kerf and curves

Derive contours from the real topology with the helpers in `cad.build123d` rather than redrawing
them; draw a parametric outline by hand only when there is no reliable 3D topology.

| Helper | Does |
| --- | --- |
| `planar_faces(shape, normal_axis=, normal_sign=, coordinate_axis=, coordinate=)` | The planar faces facing one way at one height; raises on an empty selection |
| `flatten_face(face)`, `flatten_faces(faces)` | Lays a face into XY exactly |
| `union_faces(faces)` | Fuses them into one profile |
| `offset_profile(shape, amount)` | Kerf or tool-radius compensation: positive grows the profile (cut outside the line), negative shrinks it |
| `flat_pattern(shape, coordinate=, kerf=)` | Selection, flatten, union and kerf in one call |

`flat_pattern` selects the faces at ONE coordinate, so it lays out a flat plate but not a folded
part. For a bracket with flanges on several planes, select each plane's faces, flatten them and
union the result:

```python
from cad.build123d import flatten_faces, planar_faces, union_faces


@model
def bracket_drawing():
    part = bracket().shape
    faces = [
        *planar_faces(part, normal_axis="z", normal_sign=1.0, coordinate_axis="z", coordinate=3.0),
        *planar_faces(part, normal_axis="y", normal_sign=-1.0, coordinate_axis="y", coordinate=0.0),
    ]
    return union_faces(flatten_faces(faces))
```

Faces laid side by side are not an unfolded blank: a blank for bending needs the bend allowance
([sheet metal](manufacturing-sheet-metal.md#review-the-part)).

- **Kerf** is `offset_profile` or `flat_pattern(..., kerf=...)`; never hand-offset coordinates. A
  negative offset at or beyond half the narrowest feature consumes the profile, and the offset
  raises saying so.
- **Curves stay curves.** The union and the offset are exact OCC operations on the real faces, and
  each edge is written as one entity, so a filleted corner exports as an `ARC` and a hole as a
  `CIRCLE`, kerf included. A profile that comes out as hundreds of short `LINE`s fell back to the
  sampled path: check the union's inputs rather than accept it.
- **Why did it (not) rebuild?** The run's report says how each body went (`run` or `replayed`);
  `cad model inspect <id>` prints what the drawing was built from.

## Check a drawing

| The change | Check it with |
| --- | --- |
| Any drawing | `cad model export`: the drawing checks run on the document it is about to write |
| A dimension the person gave | A targeted `ezdxf` read of the exported `.dxf` (below): extents, a circle's radius, counts by layer |
| Layout, layers, marking | `cad dxf snapshot` of the exported file ([below](#see-a-drawing)) |
| A file from elsewhere | `validate_dxf_file` (below), then the same reads |

Every DXF export runs the drawing checks, and an error refuses the file, naming the check
(`[error] open_cut_profile: cut layer 'CUT' has segment endpoints that do not close a loop ...`):
units are set, nothing is drawn twice (an exact duplicate is a double cut), no entity has zero
length, every cut profile closes (polylines, circles, and chains of lines, arcs and splines), and
something is drawn. Open geometry is allowed only on a layer whose name's words make it a bend
(`bend`, `fold`), engraving (`engrave`, `etch`) or reference layer (`ref`, `note`, `construction`,
`dim`, `center`, `hidden` and the like).

The same checks run on any `.dxf`, one no model wrote too. No `cad` command inspects an existing
`.dxf`: read it with `ezdxf`, which arrives with build123d, in a script run by `cad run`:

```python
import ezdxf
from ezdxf import bbox
from cad.engine.export.dxf import validate_dxf_file

for finding in validate_dxf_file("DXF/gasket.dxf"):
    print(finding.render())

doc = ezdxf.readfile("DXF/gasket.dxf")
msp = doc.modelspace()
print(doc.header.get("$INSUNITS"), bbox.extents(msp).size)   # 4 is millimetres
cut = msp.query('*[layer=="CUT"]')
holes = msp.query('CIRCLE[layer=="CUT"]')
print(len(cut), sorted(round(c.dxf.radius * 2, 3) for c in holes))
```

The checks establish that the file is well formed as a cut layout, not that a shop can cut it:
overlapping or partly coincident curves, small features, kerf and the shop's rules are the
[cut-file review](manufacturing-sheet-metal.md#cut-files-dxf). Report only checks that ran.

## See a drawing

```bash
cad dxf snapshot DXF/gasket.dxf tmp/gasket.png
cad dxf snapshot DXF/gasket.dxf tmp/gasket.png --display '{"appearance": "dark"}'
```

`cad dxf snapshot` draws a drawing the way the CAD Viewer's drawing pane does: whole, from above,
fitted with a margin, in the pens the file declares (an entity with no pen of its own takes the
paper's ink), on light paper or dark. `--size-profile`, `--width` and `--height` size it; `--camera`
takes a plan view, `--annotation` ink on the sheet and `--measurements` dimensions; every other flag
is refused by name, and what it does not draw (points, hatch patterns, images) is named in a warning.

A Quick Edit prompt from a drawing carries a packet (inline JSON or a `.snapshot.json` path; save
inline JSON to a file first) whose views are plan-view `camera` windows (`{"position": [x, y, d],
"target": [x, y, 0], "up": [0, 1, 0], "orthographicHalfHeight": h}`, looking straight down) and whose
`annotation` marks are in drawing coordinates, on the sheet. Draw what the person saw, each window
with their ink and dimensions on it, before editing:

```bash
cad dxf snapshot --job tmp/panel.snapshot.json            # every view, into the paths its jobs name
cad dxf snapshot DXF/panel.dxf tmp/view.png --annotation tmp/panel.snapshot.json --camera authored
```

A drawing script's model has a page, but it shows a flat face in the 3D viewer, with no pens, layers
or entity refs. The drawing a person wants is the exported `.dxf`, which the viewer opens as a
read-only 2D drawing with its layers (it never runs drawing scripts): show the `.dxf` when they ask
to see the drawing, and give its path otherwise. Drag pans, the wheel or a pinch zooms, and a
double-click fits. Its Select, Pencil, Shapes and Measure feed Quick Edit, whose prompt names what
the person picked by entity HANDLE: `panel.dxf#h2F` is the modelspace entity whose handle is `2F`
(`doc.entitydb["2F"]` in ezdxf); anything a block reference draws is named by its INSERT, and a
dimension is one entity. The prompt's chip reads it as the entity's type and layer ("Circle on
CUT"). Measurements are in the unit `$INSUNITS` declares ("units" when it declares none).

Hand off the path of every `.dxf` you created or changed, the checks that ran, and every assumption
(units, kerf, which faces made the profile).
