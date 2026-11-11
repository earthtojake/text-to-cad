---
title: Engineering drawings
description: Ask your agent for a dimensioned PDF drawing of a part, with views, hidden lines, hole callouts and a title block, all projected from the model.
---

An engineering drawing is the 2D sheet a shop works from: orthographic views of a part, its dimensions, hole callouts, notes and a title block. text-to-cad projects the views from the part's own geometry and measures every dimension on that geometry, so when you change the model and rerun the script, the drawing follows. You end up with one PDF.

## What to ask

- "Make a dimensioned drawing of the enclosure on an A3 sheet, third angle, with an isometric view."
- "I need a shop drawing of the bracket: overall size, hole positions, and a callout for each hole. Material 6061 aluminium."
- "Add a counterbore callout to the mounting holes on the base plate drawing and rerun it."
- "Draw the vendor STEP file in `vendor/flange.step` on an A4 sheet with a general tolerance of ISO 2768-m."
- "Add a revision table to the drawing, revision A dated today, initial release."

## What your agent does

1. Gets the part. For a part with a model, the agent calls the model function (for example `enclosure()`) and takes its `.shape`. For a part that only exists as a file, it reads the STEP with `step.read` or an `.xbf` with `xbf.read`. The drawing documents geometry; it does not build it.
2. Writes `<name>_drawing.py` beside the model. Dimension values such as hole pitch, overall size and wall thickness are imported from the model module, so moving a feature moves its dimension.
3. Places views with `sheet.three_views(part, iso=True)`, which returns the top, front and right views in third angle plus an isometric view. A custom layout uses `sheet.view(part, name, at=(x, y))`.
4. Adds dimensions in model coordinates: `view.overall()` for overall size, `view.dim` for feature positions, `view.hole` for hole callouts (through, depth, counterbore, countersink, thread) and `view.note` for notes with leaders. It leaves `text` and `offset` unset so the value is measured and the dimension takes the next free row. It adds `tol=` or `fit=` only where you give a tolerance or the design requires one.
5. Runs the script:

   ```bash
   cad run enclosure_drawing.py
   ```

   It prints the PDF it wrote and anything it noticed while drawing, such as a dimension that "measures blank paper" or an "annotation overlaps" warning. The agent reads those first.
6. Opens the PDF and checks it: no dimension text on a view, hidden lines where features sit behind faces, a centre mark on every hole, no leader crossing the part. It moves `at=` or `offset=` and reruns until the sheet is clean.

A short drawing script looks like this:

```python
from cad.eng_drawing import Sheet, eng_drawing
from enclosure import HOLES, L, H, W, enclosure


@eng_drawing(out="../PDF/enclosure_drawing.pdf")
def enclosure_drawing():
    part = enclosure().shape
    sheet = Sheet("A3", title="ENCLOSURE", part_number="ENC-001", material="ABS",
                  revision="A", general_tolerance="ISO 2768-m",
                  notes=["BREAK SHARP EDGES."])
    top, front, right, iso = sheet.three_views(part, iso=True)
    top.overall()
    top.hole((HOLES[3][0], HOLES[3][1], H / 2), 3, depth=8, count=len(HOLES))
    return sheet


if __name__ == "__main__":
    enclosure_drawing()
```

The `out` path is required, must end in `.pdf`, and is resolved against the script. text-to-cad has no default location for drawings, so you choose where they belong.

## What you get

- One PDF at the path in `out`, with a page per sheet. Sheet sizes are `A4`, `A3`, `A2`, `A1` and `A0`, landscape.
- Line weights by meaning: heavy visible outlines, dashed hidden lines, thin centre marks and dimensions.
- Dimensions with filled arrowheads and witness lines. Values are true size at any drawing scale.
- A title block with title, part number, material, author, scale, units, projection, revision and sheet count. The general tolerance, when given, is note 1. A revision table appears top-right when you pass `revisions=`.
- No creation date is stamped, so an unchanged drawing rebuilds to an identical file.

The drawing is a PDF written by a script, not a CAD Viewer document. Open it in any PDF reader.

If the script is asked for something it cannot draw correctly, it raises an error and writes no file. Examples are views that run off the frame (the error names a scale that fits), an unknown sheet size, or a note wider than the sheet. A failed run leaves any earlier PDF unchanged.

## Limits

- Tolerances come only from `tol=`, `fit=` and `general_tolerance=` that your agent writes from your requirements. A dimension without one is nominal. The agent does not invent values, so tell it what you need.
- Views are orthographic projections with hidden lines from the kernel. There are no section views, detail views or auxiliary views yet.
- The sheet keeps callouts clear of the views it knows about and reports annotation that prints over other annotation. It does not check annotation against line work, so the PDF has to be read by eye.
- It is not for DXF cut layouts or flat patterns. For those, see [DXF profiles](/docs/guides/dxf-profiles).
- There is no `eng_drawing` command. The Python script is the interface.

## Go deeper

- [The engineering-drawing skill](repo:skills/engineering-drawing/SKILL.md) and its [sheet API reference](repo:skills/engineering-drawing/references/sheet-api.md): every `Sheet` and `View` argument.
- [Parts and assemblies](/docs/guides/parts-and-assemblies): the models a drawing documents.
- [Manufacturing checks](/docs/guides/manufacturing-checks): checking a part before it goes to a shop.
- [SendCutSend](/docs/guides/sendcutsend): pre-upload checks for laser-cut and bent parts.
- [The `step` document type](/docs/document-types/step), for drawing a vendor STEP file.
- [The build123d integration](/docs/integrations/build123d).
