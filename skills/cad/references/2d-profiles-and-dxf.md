# 2D profiles and DXF

Read this file when the person asks for a 2D profile, outline, template, gasket, panel, flat
pattern or a laser, plasma, waterjet or routing cut layout, for a DXF file, or to open or review an
existing `.dxf`. Whether a cut file is ready for a shop is the sheet-metal review's
[Cut files (DXF)](manufacturing-sheet-metal.md#cut-files-dxf).

## Contents

- [A drawing is a model](#a-drawing-is-a-model)
- [Flat patterns, kerf and curves](#flat-patterns-kerf-and-curves)
- [Check a drawing](#check-a-drawing)
- [See a drawing](#see-a-drawing)

## A drawing is a model

A drawing is a `@model` that returns build123d 2D geometry on z=0 (a sketch, a face, wires or
edges). Exporting its document to a `.dxf` runs the drawing checks and writes the file, which is
the one the viewer and `cad dxf snapshot` draw and a cutting service gets.

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
    gasket()
```

```bash
cad run src/gasket.py                     # prints id: and view:
cad model export "$ID" DXF/gasket.dxf     # runs the drawing checks, then writes
```

- **One shape is one layer, `CUT`.** For more than one CAM operation, return a `Compound` of
  labelled children, each label its layer. Children sharing a label share a layer, and several
  shapes make one part of a layer as `bd.Compound([a, b], label="ENGRAVE")`:

  ```python
  profile, text = cut.sketch, mark.sketch        # mark: a sketch of bd.Text("REV B", font_size=6)
  profile.label, text.label = "CUT", "ENGRAVE"
  return bd.Compound(children=[profile, text], label="drawing")
  ```

- **A layer's name says what it is for**, by its whole words: `bend` or `fold` is a bend layer,
  `engrave` or `etch` a marking layer, `ref`, `note`, `construction`, `dim`, `center`, `hidden`
  and the like a reference layer, and any other name a cut layer, whose profiles must close. A
  name may not hold any of `<>/\":;?*|=` or a backtick, and an unlabelled child is a cut layer
  of its own (`part2`).
- **Planar means 2D, on z=0, at 1:1, in millimetres** (`$INSUNITS` is set for you). The export
  refuses a document holding a solid (`bracket is 3D: a DXF is drawn from 2D geometry a model
  returns`) and an edge with any point off z=0, by its element name. A face taken from a solid
  sits at that solid's height: relocate it (`flatten_face(face)`, or `bd.Pos(0, 0, -z) * face`).
- **Text** is `bd.Text(...)`, written as outlines on a marking layer, never a DXF `TEXT` entity:
  cut and marking toolchains consume geometry.
- **A refused drawing writes nothing** (exit 2, naming what it refused), and neither does any
  other file of the same export. An unchanged drawing exports the same bytes, and the file is
  left as it was.

A drawing gets a script of its own beside the geometry it derives from, with its own stem
(`bracket_drawing.py` beside `bracket.py`), and composes models, never the reverse. `exports.py`
and the `@dxf("../DXF/gasket.dxf")` decorator write a drawing's file as they write any other
([exports](exports.md#standing-deliverables-exportspy)). An existing `.dxf` needs no model: hand
it straight to a snapshot or the viewer.

## Flat patterns, kerf and curves

Derive contours from the part's real topology with the helpers in `cad.build123d` rather than
redrawing them; draw an outline by hand only when there is no reliable 3D topology.

| Helper | Does |
| --- | --- |
| `flat_pattern(shape, coordinate=, kerf=)` | A flat plate's profile: its planar faces facing +Z at one height, laid into XY, fused and offset (`normal_axis=`, `normal_sign=` and `coordinate_axis=` pick another side) |
| `unfold(shape, k_factor=, bend_lines=False)` | A bent sheet part's flat pattern, each bend unrolled by its bend allowance |
| `planar_faces(shape, normal_axis=, normal_sign=, coordinate_axis=, coordinate=)` | The planar faces facing one way at one height; raises on an empty selection |
| `flatten_face(face)`, `flatten_faces(faces)` | Lays each face into XY by its own plane |
| `union_faces(faces)` | Fuses coplanar faces into one profile |
| `offset_profile(shape, amount)` | Kerf or tool-radius compensation: positive grows the profile (cut outside the line), negative shrinks it |

```python
"""Flat patterns of plate.py and bracket.py: their geometry reused, not redrawn."""

import build123d as bd
from cad import model
from cad.build123d import flat_pattern, unfold

from bracket import bracket        # the models: importing builds nothing
from plate import plate

KERF = 0.1                         # how far each edge moves: half the cut's width


@model
def plate_drawing():               # a flat plate: its top faces
    part = plate().shape
    return flat_pattern(part, coordinate=part.bounding_box().max.Z, kerf=KERF)


@model
def bracket_drawing():             # a bent part, unrolled, its bend lines on a layer of their own
    cut, bends = unfold(bracket().shape, k_factor=0.4, bend_lines=True).children
    return bd.Compound(children=[cut, bd.Compound(bends.edges(), label="BEND")], label="bracket_drawing")


if __name__ == "__main__":
    plate_drawing()
    bracket_drawing()
```

- **A flat plate** is `flat_pattern`, which selects the faces at one coordinate. A vendor STEP
  with no source is flattened the same way from `step.read(path)`
  ([inputs](model-contract.md#inputs)).
- **A bent part** is `unfold`: faces flattened plane by plane land on top of each other and are no
  blank. Without `bend_lines` it returns the outline alone, one shape. With it, it returns the
  outline labelled `CUT` and a group of the bends' centre lines labelled `BEND`: make the lines one
  part of their layer, as above, since a layer is named by a part's label. Take `k_factor` from the
  shop ([sheet metal](manufacturing-sheet-metal.md#review-the-part)).
- **Kerf** is `offset_profile` or `flat_pattern(..., kerf=...)`, never hand-offset coordinates, and
  the amount is how far each edge moves. A negative offset at or beyond half the narrowest
  feature consumes the profile, and the offset raises saying so.
- **Curves stay curves.** The union and the offset are exact, and each edge is written as one
  entity, so a filleted corner exports as an `ARC` and a hole as a `CIRCLE`, kerf included. A
  profile that comes out as hundreds of short `LINE`s fell back to a sampled union: check the
  union's inputs rather than accept it.

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
something is drawn.

`cad dxf` has no `inspect`: read a `.dxf` with `ezdxf`, which comes with the build123d
integration, in a script run by `cad run`. Such a script gets that integration by importing
build123d or, as here, by naming it in its header; one that imports `ezdxf` alone runs without
it (`No module named 'ezdxf'`):

```python
# /// script
# dependencies = ["cad[build123d]"]
# ///
import ezdxf
from ezdxf import bbox
from cad.engine.export.dxf import validate_dxf_file

for finding in validate_dxf_file("DXF/gasket.dxf"):     # the drawing checks, on any .dxf
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
[cut-file review](manufacturing-sheet-metal.md#cut-files-dxf).

## See a drawing

```bash
cad dxf snapshot DXF/gasket.dxf tmp/gasket.png
```

`cad dxf snapshot` draws a drawing the way the CAD Viewer's drawing pane does: whole, from above,
fitted with a margin, in the pens the file declares (an entity with no pen of its own takes the
paper's ink), on white paper. `--size-profile`, `--width` and `--height` size it; `--camera`
takes a plan view (`{"position": [x, y, d], "target": [x, y, 0], "up": [0, 1, 0],
"orthographicHalfHeight": h}`, looking straight down), `--annotation` ink on the sheet and
`--measurements` dimensions; every other flag is refused by name, and what it does not draw
(points, hatch patterns, images) is named in a warning.

A drawing's model has a page, but it shows a flat face in the 3D viewer, with no pens or layers.
The drawing a person wants is the exported `.dxf`, which the viewer opens as a read-only 2D
drawing with its layers: show the `.dxf` when they ask to see the drawing, and give its path
otherwise.

A Quick Edit prompt from a drawing names what the person picked by entity handle
(`panel.dxf#h2F` is `doc.entitydb["2F"]` in ezdxf; anything a block reference draws is named by
its INSERT). Its packet's views are plan-view cameras and its ink is in drawing coordinates, on
the sheet. Draw what the person saw, each view with their ink on it, before editing:

```bash
cad dxf snapshot --job tmp/panel.snapshot.json            # every view, into the paths its jobs name
cad dxf snapshot DXF/panel.dxf tmp/view.png --annotation tmp/panel.snapshot.json --camera authored
```
