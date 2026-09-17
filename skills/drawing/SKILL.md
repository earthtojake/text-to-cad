---
name: drawing
description: Make an engineering drawing of a part: orthographic views with hidden lines and centre marks, real dimensions, notes and a title block on ISO sheets, written as DXF plus a paged PDF, all derived from the part's STEP so the drawing follows the model. Use when the user asks for a drawing, a dimensioned sheet, shop or manufacturing drawings, a print, or "2D views of this part".
---

# Engineering drawing

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

A drawing here is a DOCUMENT derived from a part. `cadgen.drawing` projects
views from the part's geometry, places dimensions between points ON that
geometry, finds centre marks on it, and lays the result out on an ISO sheet
with a frame and a title block. Change the model, rerun the drawing script,
and the views, hidden lines and measured values move with it. Nothing on the
sheet is drawn by hand, and nothing on it is a number you typed unless you
chose to override a value.

This is the drawing skill; `$dxf` makes cut layouts and flat patterns, and the
two are different documents. A drawing writes real DXF `DIMENSION` entities
and a LAYER table with linetypes; a cut layout writes geometry only.

## Workflow

1. Get the part as a STEP the model wrote (run `python <model>.py` for a
   `@step` model, or take any imported STEP). The drawing reads that
   artifact: it documents what was built, it does not rebuild it.
2. Write `<name>_drawing.py` beside the model, from
   [the template](references/sheet-api.md#template). Name the model facts the
   dimensions reference as constants (hole pitch, overall size, wall) so the
   script reads as a drawing brief.
3. Choose views: `top`, `front`, `right` (third angle: right view to the right
   of front, top above front), plus `iso` when it helps. Place each with
   `at=(x, y)` in sheet millimetres from the bottom-left corner; A3 is
   420 × 297, A4 is 297 × 210.
4. Dimension what a maker needs, in MODEL coordinates: overall size per view
   (`view.overall()`), feature positions and sizes (`view.dim`,
   `view.diameter`, `view.radius`), and notes with leaders (`view.note`).
   Give the value only where the model does not define it (a callout such as
   `"%%c3 x 8 DEEP, 4 PLACES"`); everywhere else leave `text` unset so the
   dimension is measured.
5. Run `python <name>_drawing.py`. It prints every file written: one `.dxf`
   per sheet under `DXF/` and one `.pdf` with a page per sheet under `PDF/`.
6. Open the `.dxf` in `$cad-viewer` to check the layout; send the `.pdf`.
   Check that no dimension text collides with a view, that hidden lines
   appear where features are behind faces, and that every hole has a centre
   mark. Move `at=` or `offset=` and rerun; never edit the DXF by hand.

## What the sheet contains

- Layers with meaning: `VISIBLE` (heavy outline), `HIDDEN` (dashed), `CENTER`
  (centre marks, dashed), `DIM`, `NOTES`, `TITLE`, `SHEET` (frame). Any CAD
  package and the CAD Viewer draw them with those weights and linetypes.
- Dimensions as `DIMENSION` entities with filled arrowheads and measured
  values, so a shop's CAD reads them as dimensions, not as lines and text.
- A title block with title, part number, material, author, scale, units,
  projection, revision and `SHEET n OF m`; numbered notes above it.
- Bytes that are a function of the content: an unchanged drawing rebuilds to
  identical files, like `@dxf`.

## Limits to state in the handoff

- Tolerances are not generated. A dimension carries a tolerance only if you
  write it into `text`; say so in the notes, and get the values from the
  design requirements or the user, never invented.
- Views are orthographic projections with hidden lines from the kernel; no
  sections, details, or auxiliary views yet. Say what a view does not show.
- The sheet does not check for overlapping annotation. Look at the PDF.
