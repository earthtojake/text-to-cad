# `cadgen.eng_drawing` reference

```python
from cadgen.eng_drawing import eng_drawing, Sheet
```

## Template

```python
from pathlib import Path

import cadgen
from cadgen.eng_drawing import Sheet, eng_drawing
# The facts the dimensions reference come from the model, not from this file.
from enclosure import HOLES, L, H, W


@eng_drawing(out="../PDF/enclosure_drawing.pdf")
def enclosure_drawing():
    part = cadgen.read_step(Path(__file__).parent / "../STEP/enclosure.step")
    sheet = Sheet("A3", title="ENCLOSURE", part_number="ENC-001", material="ABS",
                  revision="A", general_tolerance="ISO 2768-m",
                  notes=["BREAK SHARP EDGES."])
    # Third angle, placed from the part's size. iso=True returns FOUR views.
    top, front, right, iso = sheet.three_views(part, iso=True)
    top.overall()
    top.dim((HOLES[0][0], W / 2, 0), (HOLES[2][0], W / 2, 0))   # unplaced: next free row
    top.hole((HOLES[3][0], HOLES[3][1], H / 2), 3, depth=8, count=len(HOLES))
    front.dim((L / 2, -W / 2, 0), (L / 2, -W / 2, H))
    return sheet          # or [sheet_one, sheet_two] for a multi-sheet drawing


if __name__ == "__main__":
    enclosure_drawing()
```

## `@eng_drawing(out="<path>.pdf")`

Declares the drawing. The function returns a `Sheet` or a list of them. Calling
it renders one PDF at `out`, a page per sheet, and returns `[path]`.

`out` is required and must name a `.pdf`; a relative path resolves against the
script. cadgen has no default location — where a document belongs is the
caller's decision. Both are checked when the module is imported, not when the
drawing runs.

There is no `eng_drawing` CLI verb. A `Sheet` is composed in Python — views,
their placement, and dimensions between points on the part's geometry — and no
argument list carries that, so the decorator is the whole surface.

## The part

`cadgen.read_step(path)` returns build123d geometry, reads warm from the store,
and records the file as an input. Anchor the path on the script
(`Path(__file__).parent / "../STEP/part.step"`) — it resolves against the
process's working directory otherwise. A live build123d shape works too; a
drawing takes geometry, not a file.

## `Sheet(size="A3", scale=1.0, title=..., part_number="", material="", revision="A", author="", units="mm", projection="THIRD ANGLE", notes=(), ink="mono", text_height=3.5, general_tolerance="", revisions=())`

- `size`: `A4`, `A3`, `A2`, `A1`, `A0`, landscape. `width`/`height` in mm.
- `scale`: drawing scale, 1 = 1:1, 0.5 = 1:2. Dimension values stay true size at
  any scale — each view divides its measurement by its own scale.
- `projection`: `"THIRD ANGLE"` (default) or `"FIRST ANGLE"`. The label and the
  arrangement `three_views` produces are the same decision, so anything else is
  refused rather than printed over the wrong layout.
- `ink`: `"mono"` (default) is black ink with grey hidden lines, the printed look;
  `"color"` keeps per-layer colours (red dimensions, green notes) for review.
- `general_tolerance="ISO 2768-m"`: written as note 1, "TOLERANCES PER ISO 2768-m
  UNLESS OTHERWISE SPECIFIED." Give one on any drawing a shop will quote from.
- `revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ...]`: a revision table
  (REV, DATE, DESCRIPTION) top-right inside the frame.
- `sheet.three_views(shape, gap=None, iso=False)` → `(top, front, right)` placed
  from the part's extents in the arrangement `projection` names, with the gap
  sized for two rows of dimensions unless you pass one. `iso=True` adds an
  isometric view in the free corner and returns it FOURTH — unpack four names.
  Use `view()` with `at=` only for a custom layout.
- `sheet.view(shape, name, at=(x, y), label=None, hidden=True, centre_marks=True, scale=None)`
  → `View`. `scale` overrides the sheet's for this view (a pictorial drawn
  smaller); say so in its label. `name` is one of `top`, `bottom`, `front`,
  `back`, `left`, `right`, `iso`. The projected geometry is centred on `at`.

A view whose geometry runs off the frame raises, naming the scale that fits.

## `View`

All points are MODEL coordinates (3-tuples; a 2-tuple means z = 0). Offsets
are sheet millimetres.

- `view.overall()`: overall width above and height left of the view, on the
  OUTERMOST row of each side — the feature dimensions sit inside it.
- `view.dim(p1, p2, offset=None, text=None, orientation=None, tol=None, fit=None)`:
  linear dimension. `orientation` is `"h"`, `"v"` or None (whichever the pair
  spans more); anything else is refused. `offset` left unset takes the next free
  row outside the view, so unplaced dimensions never stack on each other or on
  `overall()`. A number places the line that far from the farther of the two
  points (not from the view's edge), and its sign picks the side; a dimension
  between interior points then needs an offset that clears the geometry.
  `tol=0.1` states ±0.1 as a proper tolerance (stacked, smaller text);
  `tol=(0.05, 0.02)` states +0.05/-0.02 deviations; `fit="H7"` appends an ISO
  fit class. `text` overrides the value; `"<>"` inside it inserts the
  measurement.
- `view.hole(center, diameter, depth=None, thru=False, cbore=(dia, depth), csk=(dia, angle), thread=None, count=None, angle=45, tol=None, fit=None, label=None)`:
  a hole callout in the standard symbols, e.g. `4× ⌀6.6 ↧12`, `⌀6 THRU`,
  `⌴ ⌀11 ↧6.5` (counterbore), `⌵ ⌀12 × 90°` (countersink), or `M6x1 - 6H THRU`
  when `thread` is given; `label="WHEEL"` is appended; `angle` is where the
  leader leaves the circle, in degrees from horizontal. Prefer it to
  `diameter()` for any hole a shop drills. Every size must be a positive
  number, and a hole is either `thru` or has a `depth`.
- `view.diameter(center, radius, angle=45, text=None)` and
  `view.radius(...)`: on a circular feature at `center`, plain value only.
- `view.angle(vertex, p1, p2, offset=14)`: the angle at `vertex` between the legs
  toward `p1` and `p2`; `offset` is the arc's distance from the vertex.
- `view.note(text, at, offset=(10, 10))`: a leader from a model point to text.

## Layers

| Layer | Linetype | Weight | Holds |
| --- | --- | --- | --- |
| SHEET | continuous | 0.35 | frame |
| TITLE | continuous | 0.25 | title block lines and text |
| VISIBLE | continuous | 0.50 | visible edges |
| HIDDEN | DASHED | 0.25 | hidden edges |
| CENTER | CENTER | 0.18 | centre marks |
| DIM | continuous | 0.18 | dimensions |
| NOTES | continuous | 0.25 | notes, view labels, leaders |

They exist inside the ezdxf document the page is rendered from; the PDF carries
their weights and dash patterns, not the layer names.
