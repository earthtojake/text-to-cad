# `cadgen.drawing` reference

```python
from cadgen.drawing import drawing, Sheet, source_step
```

## Template

```python
from cadgen.drawing import drawing, Sheet, source_step

# Model facts the dimensions reference (model coordinates, mm).
L, W, H = 100.0, 70.0, 30.0
HOLES = [(-35.0, -25.0), (-35.0, 25.0), (35.0, -25.0), (35.0, 25.0)]


@drawing(out="../DXF/enclosure_drawing.dxf")
def enclosure_drawing():
    part = source_step("../STEP/enclosure.step")
    sheet = Sheet("A3", title="ENCLOSURE", part_number="ENC-001", material="ABS",
                  revision="A", notes=["BREAK SHARP EDGES."])
    top, front, right = sheet.three_views(part)      # third-angle, placed from the part's size
    top.overall()
    top.dim((HOLES[0][0], W / 2, 0), (HOLES[2][0], W / 2, 0), offset=24)
    top.diameter((HOLES[3][0], HOLES[3][1], H / 2), 1.5, text="%%c3 x 8 DEEP, 4 PLACES")
    front.dim((L / 2, -W / 2, 0), (L / 2, -W / 2, H), offset=12)
    return sheet          # or [sheet_one, sheet_two] for a multi-sheet drawing


if __name__ == "__main__":
    enclosure_drawing()
```

## `@drawing(out=..., pdf=True)`

Declares the drawing. The function returns a `Sheet` or a list of them. Calling
it writes the first sheet at `out` (relative to the script), further sheets as
`<stem>-sheet2.dxf`, and a PDF with one page per sheet at `../PDF/<stem>.pdf`
next to the DXF folder. `pdf="path.pdf"` places it; `pdf=False` skips it.

## `source_step(path)`

Reads the STEP the drawing documents, relative to the script. Missing file →
`FileNotFoundError` telling you to run the model first.

## `Sheet(size="A3", scale=1.0, title=..., part_number="", material="", revision="A", author="", units="mm", projection="THIRD ANGLE", notes=(), ink="mono", text_height=3.5, general_tolerance="", revisions=())`

- `size`: `A4`, `A3`, `A2`, `A1`, `A0`, landscape. `width`/`height` in mm.
- `scale`: drawing scale, 1 = 1:1, 0.5 = 1:2. Dimension values stay true size.
- `ink`: `"mono"` (default) is black ink with grey hidden lines, the printed look;
  `"color"` keeps per-layer colours (red dimensions, green notes) for review.
- `general_tolerance="ISO 2768-m"`: written as note 1, "TOLERANCES PER ISO 2768-m
  UNLESS OTHERWISE SPECIFIED." Give one on any drawing a shop will quote from.
- `revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ...]`: a revision table
  (REV, DATE, DESCRIPTION) top-right inside the frame.
- `sheet.three_views(shape, gap=None, iso=False)` → `(top, front, right)` placed
  in third-angle arrangement from the part's extents, with the gap sized for two
  rows of dimensions unless you pass one. `iso=True` adds an isometric view in the
  free top-right slot and returns it fourth. Use `view()` with `at=` only for a
  custom layout.
- `sheet.view(shape, name, at=(x, y), label=None, hidden=True, centre_marks=True, scale=None)`
  → `View`. `scale` overrides the sheet's for this view (a pictorial drawn smaller); say so in its label. `name` is one of `top`, `bottom`, `front`, `back`, `left`,
  `right`, `iso`. The projected geometry is centred on `at`.

## `View`

All points are MODEL coordinates (3-tuples; a 2-tuple means z = 0). Offsets
are sheet millimetres.

- `view.overall()`: overall width above and height left of the view.
- `view.dim(p1, p2, offset=12, text=None, orientation=None, tol=None, fit=None)`:
  linear dimension. `orientation` `"h"`/`"v"` or None (whichever the pair spans
  more). The sign of `offset` picks the side. `tol=0.1` states ±0.1 as a
  proper tolerance (stacked, smaller text); `tol=(0.05, 0.02)` states +0.05/-0.02
  deviations; `fit="H7"` appends an ISO fit class. `text` overrides the value;
  `"<>"` inside it inserts the measurement.
- `view.hole(center, diameter, depth=None, thru=False, cbore=(dia, depth), csk=(dia, angle), thread=None, count=None, angle=45, tol=None, fit=None)`:
  a hole callout in the standard symbols, e.g. `4× ⌀6.6 ↧12`, `⌀6 THRU`,
  `⌴ ⌀11 ↧6.5` (counterbore), `⌵ ⌀12 × 90°` (countersink), or `M6x1 - 6H THRU`
  when `thread` is given. Prefer it to `diameter()` for any hole a shop drills.
- `view.diameter(center, radius, angle=45, text=None)` and
  `view.radius(...)`: on a circular feature at `center`, plain value only.
- `view.note(text, at, offset=(10, 10))`: a leader from a model point to text.

## Layers written

| Layer | Linetype | Weight | Holds |
| --- | --- | --- | --- |
| SHEET | continuous | 0.35 | frame |
| TITLE | continuous | 0.25 | title block lines and text |
| VISIBLE | continuous | 0.50 | visible edges |
| HIDDEN | HIDDEN | 0.25 | hidden edges |
| CENTER | CENTER | 0.18 | centre marks |
| DIM | continuous | 0.18 | dimensions |
| NOTES | continuous | 0.25 | notes, view labels, leaders |

## Tags the viewer reads

Every entity a view writes carries XDATA (`CADGEN`: `view=<name>`, and for a
dimension `dim=<index>` into that view's authoring order, `overall-w`/`overall-h`
for `overall()`). The CAD Viewer uses them to list views and dimensions, to
preview a moved view or a new dimension, and to hand the matching line of this
script back to the agent. Nothing in the tags points outside the file.
