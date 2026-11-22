# `cad.eng_drawing` reference

Read this for the calls a drawing script makes and what each argument does: `@eng_drawing`, `Sheet`
and `View`. A whole script is SKILL.md's [Workflow](../SKILL.md#workflow).

## `@eng_drawing(out="<path>.pdf")`

The function returns a `Sheet` or a list of them. Calling it writes one PDF at `out`, a page per
sheet, and returns `[path]`. `out` is required and must name a `.pdf`, both checked when the script
is imported; a relative path resolves against the script.

## `Sheet(size="A3", scale=1.0, title="UNTITLED", part_number="", material="", revision="A", author="", units="mm", projection="THIRD ANGLE", notes=(), ink="mono", text_height=3.5, general_tolerance="", revisions=())`

- `size`: `A4`, `A3`, `A2`, `A1`, `A0`, landscape. `width`/`height` in mm.
- `scale`: drawing scale, 1 = 1:1, 0.5 = 1:2. Dimension values stay true size at any scale.
- `projection`: `"THIRD ANGLE"` (default) or `"FIRST ANGLE"`: the title block's label and the
  arrangement `three_views` lays out. Anything else is refused.
- `ink`: `"mono"` (default) is black ink with grey hidden lines, the printed look;
  `"color"` colours each kind of line (red dimensions, green notes) for review.
- `general_tolerance="ISO 2768-m"`: written as note 1, "TOLERANCES PER ISO 2768-m
  UNLESS OTHERWISE SPECIFIED."
- `revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ...]`: a revision table
  (REV, DATE, DESCRIPTION) top-right inside the frame.
- `sheet.three_views(shape, *, gap=None, hidden=True, centre_marks=True, iso=False)` →
  `(top, front, right)` placed from the part's extents in the arrangement `projection` names, with
  the gap sized for two rows of dimensions unless you pass one. `iso=True` adds an isometric view
  in the free corner and returns it fourth: unpack four names.
- `sheet.view(shape, name, *, at, label=None, hidden=True, centre_marks=True, scale=None)`
  → `View`. `name` is one of `top`, `bottom`, `front`, `back`, `left`, `right`, `iso`, and the
  projected geometry is centred on `at`. `scale` overrides the sheet's for this view (a pictorial
  drawn smaller); say so in its label.

## `View`

Points are model coordinates (3-tuples; a 2-tuple means z = 0) and offsets are sheet millimetres.
Arguments after the points are keyword-only.

- `view.overall()`: overall width above and height left of the view, on the outermost row of each
  side, so the feature dimensions sit inside it.
- `view.dim(p1, p2, *, offset=None, text=None, orientation=None, tol=None, fit=None)`:
  linear dimension. `orientation` is `"h"`, `"v"` or None (whichever the pair
  spans more). `offset` left unset takes the next free row outside the view, so unplaced
  dimensions never stack on each other or on `overall()`. A number places the line that far from
  the farther of the two points (not from the view's edge), and its sign picks the side; a
  dimension between interior points then needs an offset that clears the geometry.
  `tol=0.1` states ±0.1 (stacked, smaller text); `tol=(0.05, 0.02)` states +0.05/-0.02
  deviations; `fit="H7"` appends an ISO fit class. `text` overrides the value; `"<>"` inside it
  inserts the measurement.
- `view.hole(center, diameter, *, depth=None, thru=False, cbore=(dia, depth), csk=(dia, angle), thread=None, count=None, angle=45, tol=None, fit=None, label=None)`:
  a hole callout in the standard symbols, e.g. `4× ⌀6.6 ↧12`, `⌀6 THRU`,
  `⌴ ⌀11 ↧6.5` (counterbore), `⌵ ⌀12 × 90°` (countersink), or `M6x1 - 6H THRU`
  when `thread` is given; `label="WHEEL"` is appended; `angle` is where the
  leader leaves the circle, in degrees from horizontal. Prefer it to
  `diameter()` for any hole a shop drills. Every size must be a positive
  number, and a hole is either `thru` or has a `depth`.
- `view.diameter(center, radius, *, angle=45, text=None)` and `view.radius(...)`: on a circular
  feature at `center`, plain value only. Both take the radius.
- `view.angle(vertex, p1, p2, *, offset=14)`: the angle at `vertex` between the legs
  toward `p1` and `p2`; `offset` is the arc's distance from the vertex.
- `view.note(text, at, *, offset=(10, 10))`: a leader from a model point to text.

`hole`, `diameter` and `radius` print the sizes they are given, not the part's:
`diameter(center, 10)` on a bore of radius 6 prints ⌀20, with nothing said. Pass the model's own
numbers.
