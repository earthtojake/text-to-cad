# `cadgen.eng_drawing` reference

```python
from cadgen.eng_drawing import eng_drawing, Sheet, Frame, geometry_notes
```

## Template

```python
from cadgen.eng_drawing import Sheet, eng_drawing
# The part, and the facts the dimensions reference, come from the model, not from this file.
from enclosure import FLOOR, HOLES, L, H, W, enclosure


@eng_drawing(out="../PDF/enclosure_drawing.pdf")
def enclosure_drawing():
    part = enclosure().shape    # the model, built by the engine (a replay when it holds it)
    sheet = Sheet("A3", title="ENCLOSURE", part_number="ENC-001", material="ABS",
                  revision="A", general_tolerance="ISO 2768-m",
                  notes=["BREAK SHARP EDGES."])
    top, front, right, iso = sheet.three_views(part, iso=True)
    front.section("A", through=(0, HOLES[0][1], 0))   # walls, floor and bores in section
    top.overall()
    top.dim((HOLES[0][0], HOLES[0][1], H), (HOLES[1][0], HOLES[0][1], H))   # hole pitch
    top.holes()                                       # every hole, sizes read off the part
    front.overall(width=False)                        # the width is the top view's
    front.dim((L / 2, HOLES[0][1], 0), (L / 2, HOLES[0][1], FLOOR))
    return sheet          # or [sheet_one, sheet_two] for a multi-sheet drawing


if __name__ == "__main__":
    enclosure_drawing()
```

A turned part states its diameters on the profile, cuts the view that shows what
hidden lines cannot (here a keyway's depth) and draws a detail of what is too
small to dimension at 1:1:

```python
from shaft import CHAMFER, KEY_DEPTH, KEY_END, KEY_START, KEY_WIDTH, LENGTH, STEP_DIAMETER, STEP_LENGTH, shaft


@eng_drawing(out="../PDF/shaft_drawing.pdf")
def shaft_drawing():
    part = shaft().shape                                  # axis along X
    sheet = Sheet("A3", title="SHAFT", part_number="SH-001", general_tolerance="ISO 2768-m")
    top, front, right, iso = sheet.three_views(part, iso=True)
    middle, r = (KEY_START + KEY_END) / 2, STEP_DIAMETER / 2
    right.section("A", through=(middle, 0, 0))            # the end view, cut through the keyway
    front.overall(height=False)                           # the height is the diameter
    front.dim((STEP_LENGTH / 2, 0, -r), (STEP_LENGTH / 2, 0, r), text="%%c<>")
    front.dim((0, 0, -r), (STEP_LENGTH, 0, -r))
    top.dim((KEY_START, KEY_WIDTH / 2, r), (KEY_END, KEY_WIDTH / 2, r))
    right.dim((middle, 0, -r), (middle, 0, r - KEY_DEPTH))   # what is left under the keyway
    end = sheet.detail(front, (LENGTH, 0, r), 4)            # the end chamfer, drawn at 5:1
    end.dim((LENGTH - CHAMFER, 0, r), (LENGTH, 0, r))
    return sheet
```

## `@eng_drawing(out="<path>.pdf")`

Declares the drawing. The function returns a `Sheet` or a list of them. Calling
it renders one PDF at `out`, a page per sheet, prints what it noticed and what
the drawing leaves unstated, and returns `[path]`.

`out` is required and must name a `.pdf`; a relative path resolves against the
script. Both are checked when the module is imported. There is no CLI verb: a
`Sheet` is composed in Python and no argument list carries that.

## The part

Call the model: `enclosure()` is built by cadgen's engine, a replay when the engine
already holds it, and its `.shape` is the part as a build123d tree. A part with no model is
read from its file instead:

```python
from pathlib import Path

from cadgen import read_step

part = read_step(Path(__file__).parent / "../vendor/enclosure.step")
```

`read_xbf` reads an xbf the same way. Anchor the path on the
script, since it resolves against the process's working directory otherwise. Any
build123d shape works: a drawing takes geometry, not a file.

## `Sheet(size="A3", scale=1.0, title=..., part_number="", material="", spec="", finish="", revision="A", author="", date="", units="mm", projection="THIRD ANGLE", notes=(), ink="mono", text_height=3.5, general_tolerance="", general_profile=None, revisions=(), stage=None, profile=None, category="", company="", fields={})`

- `size`: `A4`, `A3`, `A2`, `A1`, `A0`, landscape, with an ISO 5457 zone grid.
  `None` lets `three_views` choose: the smallest of A4 to A2 that draws the
  part at 1:1 or larger, else A3 at a reduced scale; with `scale` fixed, the
  smallest sheet that holds the views at it.
- `scale`: 1 = 1:1, 0.5 = 1:2, 2 = 2:1. Values stay true size at any scale.
  `None` lets `three_views` choose the largest standard scale, up to 10:1, that
  fits. A chosen scale is chosen again when the sheet renders, from the
  annotation each view carries; should it still run out of paper, a chosen
  sheet tries the next size up, then the next scale down. A size or scale you
  set afterwards is yours.
- `title`, `part_number` (DWG NO.), `material`, `finish`, `revision`, `author`
  (DRAWN), `date`: title block cells. A long title is set smaller to end inside
  its cell; any other value too long for its cell at the smallest legible text
  is refused, never cut. `spec` is the material's specification:
  MATERIAL reads `AL 6061-T6 PER AMS 4027`; a spec without a material is
  refused. A field left empty prints as an empty,
  captioned cell. Nothing is stamped from the clock. The drawing function's
  name prints small under the title, so a print leads back to its script.
- `units`: `"mm"`, the unit every value is measured in; anything else is refused.
- `projection`: `"THIRD ANGLE"` or `"FIRST ANGLE"`. It sets the arrangement
  `three_views` makes and the projection symbol the title block draws.
- `general_tolerance="ISO 2768-m"`: a note, "TOLERANCES PER ISO 2768-m UNLESS
  OTHERWISE SPECIFIED." (under an ASME profile, "UNLESS OTHERWISE SPECIFIED,
  TOLERANCES ARE ±0.1." from `general_tolerance="±0.1"`). `notes=` takes a
  LIST; a bare string is refused.
- `general_profile=Frame("surface_profile", 0.2, ("A", "B", "C"))`: note 1,
  "UNLESS OTHERWISE SPECIFIED, ALL SURFACES" and the frame. Its datums must be
  defined on the sheet.
- `stage`: `"concept"`, `"prototype"` or `"production"`, printed in the title
  block's band and checked by the report. `profile` (`GENERIC` or
  a company's own `Profile`) sets the tolerancing standard, its notes, the band's extra cells
  and the key characteristic mark; `category` is one of the profile's names
  for a stage; `company` and `fields` fill the band's cells. With none of
  these the title block has no band. See [intent and GD&T](intent-and-gdt.md).
  `notes=geometry_notes(part)` adds the general notes the part's geometry
  states (below).
- `revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ...]`: a revision table.
- `subtitle`: a second line under the title; a part's sheet of an assembly
  carries `ITEM 4 (QTY 2) OF RIG` there.
- `ink`: `"mono"` (default) or `"color"` (per-layer colours, for review).

### `sheet.three_views(shape, gap=None, iso=False, views=("top", "front", "right"))`

Returns `(top, front, right)`, or four views with `iso=True`. `views` names the
principal views to draw, returned in that order: a turned or symmetric part
draws only the ones that differ, and the run says when two drawn views are the
same picture. When the sheet
renders, the views are laid out again with each gap sized to the dimensions and
callouts the facing views carry; `gap=` fixes it instead. The isometric takes
the larger free region at the sheet's scale or the largest standard scale that
fits; its label states its scale when that differs from the sheet's. A label or
scale you set on it yourself is kept.

### `sheet.detail(view, center, radius, letter="B", scale=None, at=None)`

A detail view: what `view` shows inside a circle of `radius` (model mm) round
`center` (a model point), drawn larger and labelled `DETAIL B (5:1)`; the parent
gets the circle and the letter. `scale` defaults to the largest standard scale,
at least twice the parent's, that keeps the circle within 60 mm, and steps down
when the paper has no room for it. Left without `at=`, it goes in the free paper
nearest its parent, clear of every view and its annotation; a scale you give
that finds no room is refused. A detail of a section keeps its hatching; to cut
a detail, cut its parent. Give
it dimensions, callouts and notes like any view; `holes()` on it calls out only
what its circle holds.

### `sheet.auxiliary(view, point, letter="C", scale=None, at=None, partial=True)`

An auxiliary view: the part seen square to the flat face through `point` (a
model point on it; the middle of a face with a hole in it will do), so an
inclined face shows its true shape and its holes as circles. `view` must see
that face edge-on, as a line; a face inclined in every principal view would need
a secondary auxiliary view, which is refused. Labelled `VIEW C`;
`view` gets an arrow pointing the way it looks, with the letter. Drawn with the
face's slope running up the sheet, at `view`'s scale unless `scale` is given,
in the free paper nearest `view` unless `at` places it. `partial` (the default)
draws the face and what lies within its outline; the rest of the part is
foreshortened there. A face square to a principal view is refused: draw that
view. Give it dimensions and callouts like any view; `holes()` on it calls out
the holes in that face.

### `sheet.view(shape, name, at=(x, y), label=None, hidden=True, centre_marks=True, scale=None)`

One view, centred on `at` (sheet mm from the bottom-left corner), for a custom
layout. `name` is `top`, `bottom`, `front`, `back`, `left`, `right` or `iso`.

A view whose geometry runs off the frame is refused, naming a scale that fits.

## `View`

Points are MODEL coordinates (3-tuples; a 2-tuple means z = 0); offsets are
sheet millimetres.

- `view.overall(width=True, height=True, reference=False)`: overall width above
  and height left of the view, each on the outermost row of its side;
  `reference=True` prints them in parentheses, stating no requirement.
- `view.dim(p1, p2, offset=None, text=None, orientation=None, tol=None, fit=None, limits=None, basic=False, reference=False, frame=None, datum=None, key=False)`:
  a linear dimension, measured. Unplaced, it goes on the side of the view its
  points are on, the shortest nearest the view. `offset` places the line that
  far from the farther point (its sign picks the side). `orientation` unset
  measures the direction the points differ more in, and the script says when
  that was close to a guess. A point on a hole's centre runs its extension line
  as a centre line. `text` overrides the
  value; `"<>"` inserts the measurement, `"%%c<>"` prefixes ⌀ (a diameter on a
  profile). `tol=0.1` prints ±0.1, `tol=(0.05, 0.02)` +0.05/-0.02, `fit="H7"`
  appends an ISO 286-1 tolerance class (a hole's in capitals, `"g6"` a
  shaft's, `"H7/g6"` a fit; anything else is refused) and is the size's whole
  tolerance, so it takes no `tol` or `limits`; `limits=(39.98, 40.02)` prints
  the two limits (checked against the part). `basic=True` boxes the value; `reference=True` puts it in
  parentheses; neither takes a tolerance. `frame=` draws a `Frame` beyond the
  value on a row of its own, `datum="B"` makes the feature a datum, `key=True`
  marks a key characteristic. `orientation` is `"h"`, `"v"`, None, or
  `"aligned"`: along the line between the points, the true length of an
  inclined edge the view sees edge-on (a tab's length, its thickness across
  its end). An aligned dimension stands off its own edge, on the side away
  from the view's middle unless `offset` (positive to the left going from
  `p1` to `p2`) says otherwise, and takes no frame, datum or key mark. With an
  `angle()` fixing its direction, the report counts it for its run and rise.
  On a broken view it states the true length; one inclined across the break
  is refused.
- `view.symmetric(direction)`: state the part symmetric about the view's
  vertical (`"v"`) or horizontal (`"h"`) centre line, drawn with the ISO
  129-1 symbol through the part's middle, two short strokes beyond each end.
  A part that is not its own mirror image about that line is refused. The
  completeness report then counts a feature on that line as located, a
  spacing centred on it as placing both its ends, and a place reached on one
  side as placing its mirror. A principal view only, not a detail; call it in
  each view where the symmetry is read.
- `view.holes(angle=45)`: one callout per kind of hole or slot the view looks
  down (`4× ⌀5.5 THRU`, `⌀28 THRU`, `8 × 30 SLOT THRU`), placed on the one
  nearest the view's edge. Identical holes equally spaced round a turned axis
  of the part read `6× ⌀6 THRU EQ SP ON ⌀60`, and their pitch circle is drawn.
  A blind or counterbored hole that opens on the far side belongs to the
  opposite view. A kind that a `hole()` or `slot()` call on the same view
  states is left to that call, so a first pass's `holes()` and the fit given
  one bore make one callout. An isometric looks down no hole, so callouts on
  one are refused.
- `view.hole_table(origin=None, at=None)`: tabulate the holes and slots the
  view looks down instead of calling them out: each tagged on the view (A1, A2
  for one kind, B1 for the next), an X and Y origin marked (the lower-left
  corner of the view's extent unless `origin`, a model point, is given), and a
  table of TAG, X, Y and SIZE in free paper beside the view (or with its
  top-left corner at `at`). Sizes are read off the part as a callout reads
  them. A view tabulates its holes or calls them out, not both, but for a
  `hole(point, thread=...)`, which gives tapped holes' rows their thread under
  a letter of their own (nothing in the part says a bore is tapped).
- `view.hole(point, diameter=None, depth=None, thru=None, cbore=None, csk=None, thread=None, count=None, angle=45, tol=None, fit=None, label=None, frame=None, datum=None, key=False)`:
  one callout on the hole whose axis passes through `point`, in a view looking
  down that axis. Every size and the count come from the part; a value given is
  checked and a contradiction is refused, naming what the part has. `label`
  is appended (`"WHEEL"`). `thread` states a tapped hole: a metric thread
  of ISO 261's sizes and pitches, with an optional ISO 965-1 class for a tapped
  hole (`"M6"`, `"M6x0.75 - 6H"`; with no pitch, the coarse one), or a unified
  inch thread of ASME B1.1's sizes and its UNC, UNF or UNEF count
  (`"1/4-20 UNC-2B"`, `"#10-32 UNF"`, `"1-8 UNC"`); any other thread, such as a
  pitch the size does not have (`"M6x5"`, `"1/4-28 UNC"`), is refused. The bore is its tap drill (basic minor diameter to about d - P: ⌀5 for
  M6x1, the #7 drill for 1/4-20) or the thread's own size (⌀6). It takes no `diameter`,
  `tol` or `fit`; a plain hole takes `tol` or a hole's `fit` (`"H7"`,
  `"H7/g6"`), not both. A tap drill is stated with the thread after it: `⌀5 ↧12
  M6x1 - 6H ↧10`. `count` is how many of the identical bores are tapped (all,
  or `count=1` for this one; left unset over several, it is refused), and
  `depth` the thread's depth, which a blind tap drill needs. One hole takes one
  callout: a second `hole()` on it is refused. A hole whose end opens out in
  steps (a chamfered counterbore, a counterbore in a counterbore) has no one
  callout, and `hole()`, `holes()` and `hole_table()` refuse it.
  A through hole opened out at both ends reads `BOTH ENDS` or `FAR SIDE ...`.
  Pieces of one bore separated by air (a clevis's arms, a cross hole) are one
  hole; a groove or a pocket with material inside is not a hole. `frame=`
  hangs a `Frame` (its position, say) under the callout; `datum=` and `key=`
  as `dim` takes them.
- `view.slot(point, width=None, length=None, thru=None, depth=None, count=None, angle=45, label=None, frame=None, datum=None, key=False)`:
  one slot callout, `point` being the slot's centre or either end's centre.
  Width, length end to end, THRU or depth and the count come from the part;
  values given are checked. A slot is two half-round ends with straight sides
  and air between; a half-round notch in an edge is not one.
- `view.diameter(center, size=None, angle=45, text=None, basic=False, reference=False, frame=None, datum=None, key=False)` and
  `view.radius(center, size=None, ...)`: the circle or arc centred there,
  measured; `size` (a diameter, or a radius) picks one of several.
- `view.section(letter="A", through=None, parts=None, materials=False)`: draw the view as a full section
  through `through` (default: the part's middle), square to the line of sight.
  Cut faces are hatched, hidden lines are left out, the view is labelled
  `SECTION A-A`, and the cutting plane is drawn on a view of the same part
  that sees it edge-on. Letters I, O and Q are refused. `parts=` on a view of
  an assembly cuts each item on its own, as an assembly section is drawn:
  every part in the one general-purpose hatch, parts that touch turned a right
  angle and then spaced wider so no two neighbours look alike, a part thinner
  than 1 mm on the sheet filled solid, solids the model overlaps hatched once,
  and a solid turned part the plane cuts along its axis (a shaft, a rod, a pin,
  a bolt) drawn uncut (ISO 128-50). `balloons(parts)` on it keys each part it
  cuts. What a part is made of is the parts list's to say. `materials=True`
  instead hatches each part as its material family (`parts.set(n,
  family=...)`), names a thin one with a leader and adds a material key: for a
  layered part, where the materials are the point. On a busy assembly it
  makes a section hard to read.
- `view.broken(start, end)`: take the stretch between two model points (along
  one model axis, in the view's plane) out of the view, the two ends drawn 10
  mm apart with a zigzag break line across each cut. The other views of the
  arrangement that show that length break alike; the isometric is drawn whole.
  A dimension across the break, and `overall()`, state the true length; one
  with a point inside the stretch is reported. Break only where the section is
  constant: the script says when the stretch holds a hole or a change of shape.
  One break per view; not on a section, detail or auxiliary view.
- `view.angle(vertex, p1, p2, offset=14)`: the angle at `vertex` between the
  legs toward `p1` and `p2`, the one under half a turn, whichever order the
  legs come in. A leg along an inclined face states its slope; so does a leg
  along its normal (the right angle a drawing implies).
- `view.note(text, at, offset=(10, 10))`: a leader from a model point to text.
- `view.datum(letter, at, offset=None)`: a datum feature symbol on the face
  through `at`, its stem out by the nearest side of the view unless `offset`
  points it. A letter names one feature per sheet.
- `view.frame(at, frame, offset=(10, 10))`: a feature control frame with a
  leader to the surface through `at`.
- `view.flag(text, at=None, item=None, joint=None, offset=None)`: a flag note,
  numbered as its note in the notes block; see [assemblies](assemblies.md).

## `Frame(characteristic, tolerance, datums=(), diameter=False, modifier=None)`

A feature control frame, `Frame("position", 0.1, ("A", "B"), diameter=True,
modifier="M")`. The characteristics and their rules (form names no datum,
orientation and runout need one, a diameter zone and a material condition only
where they apply) are in [intent and GD&T](intent-and-gdt.md#frames-and-datums).
A frame naming a datum no view of its sheet defines is refused.

## `part_sheet(part, **fields)`

A first pass of one part, from the part alone, as a `Sheet` the script refines
before returning it. `fields` are `Sheet`'s own; the sheet chooses its size and
scale unless they are given.

```python
@eng_drawing(out="../PDF/bracket_drawing.pdf")
def bracket_drawing():
    sheet = part_sheet(read_step(STEP), title="BRACKET", part_number="BR-100")
    top = next(v for v in sheet.views if v.name == "top")
    top.dim(...)            # what the first pass left, and the person's requirements
    return sheet
```

- **Views that earn their place**: the view looking down most of the holes
  and slots is drawn as the front, the part turned to face it as drafters
  choose a front (your points stay in the part's own frame), and spun about
  the front's line of sight so holes the front doesn't see open toward a view
  a first pass draws, not the bottom, back or left; then each further
  view that looks down a hole, sees a slope edge-on, or shows a model axis no
  view chosen shows, a tie going to the view beside the front before the one
  above it, with an isometric. A plate's two edge views show one thing, its
  thickness, and one is drawn, beside the front. A part turned whole is drawn as `assembly_sheets` draws one (its
  diameters, tapers and grooves, every step placed from one end, a long one
  lying down).
- **Holes**: up to six in a view called out once (`5× ⌀5.5 THRU`) and located
  from the part's edge faces; more in a hole table. A hole down a hexagon's
  axis (a nut's bore) is located by the hexagon.
- **Hexagons**: `HEX 19 A/F` across the flats in the view down its axis, which
  states all six sides and their angles; its centre located from the edges
  unless it spans the part.
- **Bosses and shanks**: a round one on a part not turned whole (a bolt's
  shank, a boss on a plate) is given its diameter across its profile
  (`⌀10`), its centre located from the edges.
- **Faces**: every flat face square to a model axis placed from the same
  edges, the largest faces first, at most six places along an axis across all
  the views, in the front first. A ladder
  past that shrinks the part more than it helps; the report names the rest.
- **Slopes**: one at a whole or half degree is stated by its angle (`30°`,
  measured from the view axis that gives the rounder number) and its rounder
  end placed; any other by both its ends, as a gusset is given by its legs.
- **Edges**: `geometry_notes(part)`, then a note for each fillet, round and
  chamfer size it leaves (`5× CHAMFER 0.5 × 45°.`).

It states geometry only: every size is nominal, and the run's `requirements:`
line says so. Dimensions it adds are ordinary ones: add, or replace any by
building the sheet by hand instead.

A hole callout wider than 60 mm on the sheet stacks a stage a line (the bore,
then its counterbore or countersink), as drafters write one, so one long callout
no longer pushes every view after it onto a larger sheet.

## `geometry_notes(part)`

The general notes the part's own geometry makes true, for `Sheet(notes=...)`.
A note such as `FILLETS R2 UNLESS OTHERWISE SPECIFIED.` tells the shop how to
treat every edge of its kind drawn without a callout, so it is written only
when the part leaves no such edge sharp: `FILLETS` when every inside corner is
filleted, and `ROUNDS` or `CHAMFERS 1 × 45°` (whichever is commoner) when every
outside edge is rounded or chamfered. Each gives the commonest size. A part
with sharp edges of both kinds gets no notes; an empty list is the right
answer for it.

A blend is a part-cylinder or torus face tangent to the two faces it joins; a
chamfer is a narrow flat strip bevelling a square edge, or a short cone
bevelling a turned end. The script reports every blend and chamfer size no
note states: `radius()` states a blend where a view shows it as an arc, and a
note giving the size (`CHAMFER 0.5 × 45°`, `4 FILLETS R1`) states either.

## What the script prints

| Line | Means |
| --- | --- |
| `incomplete: 4× ⌀5.5 THRU is not called out. top.hole(...) states it ...` | the part has holes the sheet does not call out |
| `incomplete: 8 × 30 SLOT THRU is not called out. top.slot(...) ...` | a slot is not called out |
| `incomplete: the overall size along Z (8) is not dimensioned. front.overall() ...` | an overall extent is not stated in any view |
| `incomplete: the turned diameter ⌀30 is not dimensioned ...` | a shaft step or boss has no diameter |
| `incomplete: 4 rounds R2 are not stated. Sheet(notes=geometry_notes(part)) ...` | a blend radius is not stated |
| `incomplete: 2 chamfers 1 × 45° are not stated ...` | a chamfer is not stated |
| `front.broken(): the break from X = 100 to 500 hides some of the part ...` (stops the script) | the part changes inside a break; move it |
| `front dim 2: ... would measure blank paper ...` (stops the script) | a dimension's points miss the view |
| `annotation overlaps: '120' would print over 'TOP' ...` (stops the script) | two pieces of text collide; give the view room, or place one with `offset=` |
| `views crowded: ... Sheet("A2") or Sheet(scale=0.5) gives them room` | the views' annotation needs more paper |
| `SECTION A-A has no view on this sheet that sees its cutting plane ...` (stops the script) | add the view that shows the plane |
| `front dim 0: ... so it could measure either ...` (stops the script) | pass `orientation=` |
| `the part in the top view is 2 separate solids ...` (stops the script) | the model is in pieces |
| `DETAIL B: no free paper on A3 for a 50 mm circle at 10:1 ...` | give `at=`, a smaller `scale=`, or a larger sheet |
| `VIEW C: no free paper on A3 for it at 1:1 ...` | the same, for an auxiliary view |
| `top.hole_table(): no free paper on A3 for a 70 x 48 mm table ...` | give the table `at=`, or a larger sheet or smaller scale |
| `top.hole_table(): the top view looks down no hole or slot` | tabulate the view that looks down the holes |
| `front dim 3: (250, 0, 0) is inside the break ...` (stops the script) | dimension to a point outside the broken stretch |
| `top.holes(): 1 hole(s) or slot(s) at ... are inside the break ...` (stops the script) | call them out in a view without the break, and the rest with `hole()` |
| `incomplete: sheet 3 (PIN): the turned diameter ⌀6 ...` | on a drawing of several parts, each line names its sheet |
| `incomplete: 4× ⌀5.5 THRU is not located along X and Y ...` | no dimension ties the feature to an edge, a datum or a located feature; dimension it, tabulate it, or state the symmetry it sits on |
| `incomplete: the face at Z = 8 (square to Z) is not located ...` | a step or shoulder is not placed; dimension it from an edge or a located face |
| `incomplete: an inclined face (its normal (...)) has no angle ...` | add `view.angle(...)` in a view that sees it edge-on, or place both its ends; more than three on one part are one line with the count |
| `incomplete: the taper from ⌀30 to ⌀20 leaves ⌀20, its end at Z = 60 unstated ...` | a cone needs both end diameters, each end placed along its axis |
| `incomplete: the groove R1.5 at Z = 12 leaves its radius R1.5 unstated ...` | a turned groove needs its radius and its middle placed |
| `incomplete: the overall size along X (100) is given only as a reference dimension ...` | nothing else fixes the size; dimension it, or the sizes that add up to it |
| `redundant: along X, the 20 (front dim 0), the 40 (front dim 1) and the 60 (front overall) state one size twice ...` | the loop's dimensions, each named; make one reference or leave it out |
| `interface: item 7 (PIN) ⌀12 in item 1 (CLEVIS) ⌀12 ...: no clearance at nominal sizes ...` | a joint to settle: whether it turns, slides, locates or is fixed decides the fit on both sizes |
| `interface: item 1 (CLEVIS) and item 6 (BUSHING) touch face to face ...: no end play ...` | a joint with no end play at nominal sizes; ask what it needs |
| `requirements: concept; 14 sizes, all nominal; no general tolerance; no datums or frames; no fit, tolerance or position on ⌀12 THRU, 4× ⌀6.6 THRU.` | one per part sheet: what it requires, apart from what it draws; report it at the handoff |
| `incomplete: a prototype drawing states a general tolerance ...` | what the sheet's stage asks for; ask the person |
| `incomplete: a production drawing locates its features from datums ...` | mark the datums the person gave with `view.datum` |
| `note: a production drawing marks its key characteristics ...` | ask whether any feature is one; `key=True` marks it |
| `top dim 2: a basic dimension, and no GD&T frame on the sheet bounds it ...` (stops the script) | add the frame, or make it toleranced |
| `sheet 2 (BRACKET), top hole 0: its frame names datum A, which no view of this sheet defines ...` | define the datum on that sheet with `view.datum` (a refusal) |
| `sheet 1 (BRACKET), top hole 0: a GD&T frame is read by ISO GPS or ASME Y14.5-2018 ... the sheet names neither ...` | give the sheet `profile=GENERIC` or the person's own `Profile` (a refusal) |
| `the title block's MATERIAL '...' does not fit its 60 mm cell ...` | shorten the value (a refusal) |
| `0.00001: a stated tolerance prints exactly as given, to at most 4 decimal places` | state it to four places or fewer (a refusal) |
| `front: the thin layer '...' has no clear place for its callout ...` | give the section more room, or draw a detail of it |
| `top hole 0: its leader crosses a dimension line ...` | no clear way out; move the callout or the dimension |
| `the top and right views draw the same picture ...` | `three_views(views=(...))` leaves one out |

## Layers

| Layer | Linetype | Weight | Holds |
| --- | --- | --- | --- |
| SHEET | continuous | 0.35 | frame, zone marks |
| TITLE | continuous | 0.25 | title block, projection symbol, parts list |
| VISIBLE | continuous | 0.50 | visible edges |
| HIDDEN | DASHED | 0.25 | hidden edges |
| CENTER | CENTER | 0.18 | centre marks and centre lines, cutting planes |
| DIM | continuous | 0.18 | dimensions, callouts, frames, datum symbols, key marks, flags |
| NOTES | continuous | 0.25 | notes, view labels, leaders, detail circles, balloons |
| HATCH | continuous | 0.18 | section hatching: one pattern, or one per material family with `materials=True` |

They exist inside the ezdxf document the page is rendered from; the PDF carries
their weights and dash patterns, not the layer names.
