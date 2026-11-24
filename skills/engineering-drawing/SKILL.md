---
name: engineering-drawing
description: Makes an engineering drawing of a part as a PDF, projected from its 3D geometry so the drawing follows the model, with dimensioned orthographic views, hole callouts, notes and a title block. Use when the person asks for a drawing, a dimensioned sheet, shop or manufacturing drawings, a blueprint, or "2D views of this part". Not for DXF cut layouts or flat patterns, which the cad skill makes.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# Engineering drawing

An engineering drawing is a document derived from a part. `cad.eng_drawing` projects views from the
part's geometry, places dimensions between points on that geometry, finds centre marks, and lays the
result out on an ISO sheet with a frame and a title block. Change the model and rerun the drawing
script, and the views, hidden lines and measured values follow.

The output is one PDF, written by a Python script: there is no command and no DXF. A cut layout or a
flat pattern is a toolpath, not a document: that is the cad skill's.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| Draw a part | `<name>_drawing.py` beside the model, from the script under [Workflow](#workflow) | [The calls](references/sheet-api.md) |
| Place views, dimensions, hole callouts, notes | `Sheet` and `View` | [Sheet API](references/sheet-api.md) |
| Check the drawing | What the run prints, then the PDF itself | [Check each change](#check-each-change) |

## Setup

Written for `cad==0.11.17`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

## Workflow

```python
from cad.eng_drawing import Sheet, eng_drawing
from enclosure import HOLES, L, H, W, enclosure   # the part and its facts come from the model


@eng_drawing(out="../PDF/enclosure_drawing.pdf")
def enclosure_drawing():
    part = enclosure().shape
    sheet = Sheet("A3", title="ENCLOSURE", part_number="ENC-001", material="ABS",
                  revision="A", general_tolerance="ISO 2768-m", notes=["BREAK SHARP EDGES."])
    top, front, right, iso = sheet.three_views(part, iso=True)
    top.overall()
    top.dim((HOLES[0][0], W / 2, 0), (HOLES[2][0], W / 2, 0))
    top.hole((HOLES[3][0], HOLES[3][1], H / 2), 3, depth=8, count=len(HOLES))
    front.dim((L / 2, -W / 2, 0), (L / 2, -W / 2, H))
    return sheet


if __name__ == "__main__":
    enclosure_drawing()
```

```bash
cad run enclosure_drawing.py
```

1. **Get the part.** Call the model and take its `.shape`; for a part with no model, read its file
   (`step.read`, `xbf.read`, the path anchored on `Path(__file__).parent`). Any build123d shape works.
2. **Import the model's facts** (hole pitch, overall size, wall) instead of retyping them, so moving a
   feature moves its dimension.
3. **Place views.** `sheet.three_views(part, iso=True)` returns four views: top, front and right in
   third angle with room for two rows of dimensions, and an isometric in the free corner (three
   without `iso`). `sheet.view(part, name, at=(x, y))` is for a custom layout, in sheet millimetres
   from the bottom-left corner.
4. **Dimension what a maker needs**, in model coordinates: overall size (`view.overall()`), feature
   positions and sizes (`view.dim`, with `tol=` or `fit=` where the design requires one), holes as
   callouts (`view.hole`: thru, depth, counterbore, countersink, thread) and notes with leaders
   (`view.note`). Leave `text` unset so the value is measured, and `offset` unset so the dimension
   takes the next free row outside the view.
5. **Run it and read the PDF.**

## Check each change

The run prints the PDF it wrote and anything it noticed while drawing. Read those first:

- **"measures blank paper"**: a dimension's model points do not land on the view's geometry. Usually
  the part was built from a corner and the script assumed it was centred: check its bounding box.
- **"annotation overlaps"**: two callouts print over each other, usually one view's outermost
  dimension against the label of the view above. Pass a larger `three_views(gap=...)` or place one
  with `offset=`.

Then open the PDF. The sheet keeps callouts clear of the views and reports annotation over
annotation, but it does not check annotation against line work: confirm no dimension text sits on a
view, hidden lines appear where features are behind faces, every hole has a centre mark, and no
leader crosses the part. A dimension of a few millimetres puts its value on its own extension line:
dimension the larger feature instead.

The script raises instead of writing a wrong or partial document: views that run off the frame (the
error names a scale that fits, or says that none does), an argument outside the vocabulary (an
unknown view, sheet size or projection; a hole both `thru` and given a depth; `notes=` given a bare
string instead of a list; a note wider than the sheet's note column), or a missing renderer. A failed
run leaves any earlier PDF untouched.

## What the drawing holds, and what it does not

- Visible edges heavy, hidden edges dashed, centre marks, dimensions with witness lines and
  arrowheads at true size at any drawing scale, and a title block (title, part number, material,
  scale, projection, revision, `SHEET n OF m`) with numbered notes above it. Text longer than its
  title-block cell is set smaller, then cut with an ellipsis, and nothing says so: read the title
  block in the PDF. Hidden tangent edges (a fillet running into a face) are not drawn.
- The PDF's bytes are a function of its content, with no creation date: an unchanged drawing rebuilds
  to an identical file.
- **Tolerances are only the ones written** (`tol=`, `fit=`, `general_tolerance=`), from the design's
  requirements or the person, never invented. A dimension without one is nominal.
- **Views are orthographic projections**: no sections, details or auxiliary views. Say in the hand-off
  what a view does not show.
