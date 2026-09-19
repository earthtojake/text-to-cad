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
3. Place views with `sheet.three_views(part, iso=True)`: top, front and right
   in third angle with room for two rows of dimensions, and the isometric in
   the free corner. Use `sheet.view(part, name, at=(x, y))` (sheet millimetres
   from the bottom-left corner; A3 is 420 × 297, A4 is 297 × 210) only for a
   custom layout.
4. Dimension what a maker needs, in MODEL coordinates: overall size per view
   (`view.overall()`), feature positions and sizes (`view.dim`, with `tol=`
   or `fit=` where the design requires one), holes as callouts (`view.hole`:
   thru, depth, counterbore, countersink, thread), and notes with leaders
   (`view.note`). Leave `text` unset so the dimension is measured; give a
   value only where the model does not define it. `offset` is measured from
   the dimension's own points, not the view's edge: a dimension between
   interior points needs an offset that clears the geometry. Keep notes few
   and under about 45 characters; the layout reserves room for them.
5. Run `python <name>_drawing.py`. It prints every file written: one `.dxf`
   per sheet under `DXF/` and one `.pdf` with a page per sheet under `PDF/`.
   When running unattended, set `MPLCONFIGDIR` to a writable directory so
   matplotlib's font cache does not warn.
6. Open the `.dxf` with `cadgen viewer` (run in the project directory; the
   Sheet panel shows the drawing as it prints) to check the layout; send the
   `.pdf`. Check that no dimension text collides with a view, that hidden
   lines appear where features are behind faces, and that every hole has a
   centre mark. Very small dimensions (a few mm) put their value on their
   own extension line; dimension the larger feature instead. Move `at=` or
   `offset=` and rerun; never edit the DXF by hand.

## What the sheet contains

- Layers with meaning: `VISIBLE` (heavy outline), `HIDDEN` (dashed), `CENTER`
  (centre marks, dashed), `DIM`, `NOTES`, `TITLE`, `SHEET` (frame). Any CAD
  package and the CAD Viewer draw them with those weights and linetypes.
- Dimensions as `DIMENSION` entities with filled arrowheads and measured
  values, so a shop's CAD reads them as dimensions, not as lines and text.
- A title block with title, part number, material, author, scale, units,
  projection, revision, `SHEET n OF m` and the drawing function's name;
  numbered notes above it (the general tolerance, when given, is note 1);
  a revision table top-right when `revisions=` is given. Text longer than
  its cell is set smaller, not clipped.
- DXF bytes that are a function of the content: an unchanged drawing rebuilds
  to an identical DXF, like `@dxf`. The PDF carries a creation date and
  differs each run.

## Limits to state in the handoff

- Tolerances come only from `tol=`, `fit=` and `general_tolerance=` that you
  write; get the values from the design requirements or the user, never
  invented. A dimension without one is nominal.
- Views are orthographic projections with hidden lines from the kernel; no
  sections, details, or auxiliary views yet. Say what a view does not show.
- The sheet does not check for overlapping annotation. Look at the PDF.
