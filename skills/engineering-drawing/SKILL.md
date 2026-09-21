---
name: engineering-drawing
description: Make an engineering drawing of a part as a PDF - orthographic views with hidden lines and centre marks, real dimensions, hole callouts, notes and a title block on ISO sheets, all projected from the part's geometry so the drawing follows the model. Use when the user asks for a drawing, a dimensioned sheet, shop or manufacturing drawings, a print, or "2D views of this part".
---

# Engineering drawing

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

An engineering drawing is a DOCUMENT derived from a part. `cadgen.eng_drawing`
projects views from the part's geometry, places dimensions between points ON
that geometry, finds centre marks on it, and lays the result out on an ISO
sheet with a frame and a title block. Change the model, rerun the drawing
script, and the views, hidden lines and measured values move with it. Nothing
on the sheet is drawn by hand, and nothing on it is a number you typed unless
you chose to override a value.

**The output is one PDF.** That is what a shop receives and what every
operating system opens. No DXF is written, nothing is paired or linked, and
there is no CLI: the script is the interface. `$dxf` makes cut layouts and flat
patterns, which are toolpaths, not documents; the two are different jobs.

## Workflow

1. Get the part. `cadgen.read_step(Path(__file__).parent / "../STEP/part.step")`
   reads the artifact a `@step` model wrote (run `python <model>.py` first); a
   live build123d shape works just as well. The drawing documents geometry, it
   does not build it.
2. Write `<name>_drawing.py` beside the model, from
   [the template](references/sheet-api.md#template). Import the model facts the
   dimensions reference (hole pitch, overall size, wall) from the model module
   rather than retyping them, so moving a feature moves its dimension.
3. Place views with `sheet.three_views(part, iso=True)`, which returns FOUR
   views: top, front and right in third angle with room for two rows of
   dimensions, plus an isometric in the free corner. `sheet.three_views(part)`
   returns three. Use `sheet.view(part, name, at=(x, y))` (sheet millimetres
   from the bottom-left corner; A3 is 420 × 297, A4 is 297 × 210) only for a
   custom layout.
4. Dimension what a maker needs, in MODEL coordinates: overall size per view
   (`view.overall()`), feature positions and sizes (`view.dim`, with `tol=`
   or `fit=` where the design requires one), holes as callouts (`view.hole`:
   thru, depth, counterbore, countersink, thread), and notes with leaders
   (`view.note`). Leave `text` unset so the dimension is measured; give a
   value only where the model does not define it. Leave `offset` unset too and
   the dimension takes the next free row outside the view; pass one only to
   place a dimension deliberately, and remember it is measured from the
   dimension's own points, not the view's edge. Keep notes few and short; one
   wider than the sheet's note column is refused, and `notes=` takes a LIST
   (`notes="BREAK EDGES"` is a sequence of eleven characters, so it is refused
   too).
5. Run `python <name>_drawing.py`. It prints the PDF it wrote, and **anything
   it noticed while drawing** — read those first:
   - *"measures blank paper"*: the dimension's model points do not land on the
     view's geometry. Almost always the part was built from a corner and the
     script assumed it was centred. Check the part's bounding box.
   - *"annotation overlaps"*: two callouts print on top of each other, usually
     one view's outermost dimension against the label of the view above it.
     Pass a bigger `three_views(gap=...)` or place one with `offset=`. The text
     is measured as the renderer draws it, glyph by glyph, so this fires on ink
     and not on markup: a chain of toleranced dimensions is silent when the
     values clear each other.

   Steps 3 and 5 stand on their own: a sheet of views with no dimensions on it
   yet is a drawing, and writes its PDF.

   When running unattended, set `MPLCONFIGDIR` to a writable directory so
   matplotlib's font cache does not warn.
6. **Read the PDF** and fix what collides. Check that no dimension text sits on
   a view, that hidden lines appear where features are behind faces, that every
   hole has a centre mark, and that no leader crosses the part. Very small
   dimensions (a few mm) put their value on their own extension line; dimension
   the larger feature instead. Move `at=` or `offset=` and rerun.

## What the sheet contains

- Layers with meaning: `VISIBLE` (heavy outline), `HIDDEN` (dashed), `CENTER`
  (centre marks), `DIM`, `NOTES`, `TITLE`, `SHEET` (frame), each printed at its
  own weight — 0.5 mm down to 0.18 mm, so thick reads against thin on paper.
  An edge is drawn once: a silhouette that the kernel returns as both visible
  and hidden stays on `VISIBLE`. Hidden TANGENT transitions are not drawn at
  all — a fillet running into a face, or the seam where a cylinder closes on
  itself, marks nothing a shop can see, and drawn dashed it reads as a hidden
  edge that is not there (on a bore, as a line down the hole's own axis).
- Dimensions measured from the geometry, with filled arrowheads and witness
  lines, and true-size values at any drawing scale.
- A title block with title, part number, material, author, scale, units,
  projection, revision, `SHEET n OF m` and the drawing function's name;
  numbered notes above it (the general tolerance, when given, is note 1);
  a revision table top-right when `revisions=` is given. Text longer than
  its cell is set smaller, and cut with an ellipsis rather than overrun.
- PDF bytes that are a function of the content: no creation date is stamped, so
  an unchanged drawing rebuilds to an identical file.

## What fails loudly

The script raises rather than writing a wrong or missing document:

- Views that run off the frame, naming a scale that has been laid out and
  verified to fit, or saying that no standard scale does.
- A part argument the vocabulary does not define: an unknown view name, sheet
  size or projection, `orientation=` other than `"h"`/`"v"`, a negative or zero
  diameter, a counterbore that is not a `(diameter, depth)` pair, a `tol` that
  is not a number or a pair, a hole that is both `thru` and given a depth,
  `notes=` or `revisions=` given a bare string, a note wider than the sheet,
  `angle()` legs that are collinear or zero-length, a non-finite `at=` or
  `offset=`.
- A missing renderer. The PDF is the drawing, so no matplotlib is a failure,
  not a skipped half. A failed render leaves no file behind.
- `out=` missing or not naming a `.pdf`, at import time.

## Limits to state in the handoff

- Tolerances come only from `tol=`, `fit=` and `general_tolerance=` that you
  write; get the values from the design requirements or the user, never
  invented. A dimension without one is nominal.
- Views are orthographic projections with hidden lines from the kernel; no
  sections, details, or auxiliary views yet. Say what a view does not show.
- The sheet keeps callouts clear of the views it knows about, and reports
  annotation that still prints over other annotation, but it does not check
  annotation against line work. Read the PDF.
