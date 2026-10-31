---
name: engineering-drawing
description: Make an engineering drawing of a part or an assembly as a PDF - views, sections and details, measured dimensions with the tolerances, GD&T and datums the person confirms, hole callouts, notes and a title block, and for an assembly balloons, a parts list, flag notes and a sheet per part, all projected from the geometry. Use when the user asks for a drawing, a dimensioned sheet, shop or assembly drawings, a parts list, a print, or "2D views of this part".
license: MIT
---

# Engineering drawing

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

An engineering drawing is a DOCUMENT derived from a part. `cadgen.eng_drawing`
projects views from the part's geometry, measures dimensions between points ON
it, reads hole sizes, depths and counts off its faces, draws centre lines on its
turned features, and lays the result out on an ISO sheet: a zoned border, a
title block with the projection symbol, numbered notes. Change the model, rerun
the drawing script, and every view and value moves with it.

**The output is one PDF**, a page per sheet. No DXF is written and there is no
CLI: the script is the interface. `$dxf` makes cut layouts and flat patterns,
which are toolpaths, not documents.

## Setup

Run cadgen through the `cadgen` command its installation writes, so this skill's commands
share one installation, and its engine server, with the CAD app's:

- `cadgen` below means `cadgen +0.8.3` (`~/.local/bin/cadgen +0.8.3` where `~/.local/bin` is not on your PATH)
- `python` below means `cadgen +0.8.3 run`

If `cadgen` is not on your PATH, or it says 0.8.3 is not installed, run
`uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.3 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command and starts the engine. With the CAD app's server running, nothing else
needs the sandbox's permission: it starts the engine and holds it. Without it, a sandboxed
shell cannot start the engine; when a command says no engine is running, run `cadgen server`
outside the sandbox once.

## Workflow

0. **Ask before dimensioning.** Which dimensions matter, how tightly and from
   which faces depends on how the part is used and how far along it is, and
   only the person knows. Before any dimension:
   - **Name the critical interfaces**, read off the model: pins and the bores
     they run in, bores that take a bearing or bushing, sliding and sealing
     faces, and the faces the part mounts on. For an assembly, read them off
     where parts meet: a pin in a bushing in a bore is two fits.
   - **Ask** the stage (concept, prototype, production) and the use, then
     propose which interfaces need a requirement, one numbered item at a
     time, each with a picture of the part with that feature marked (`cadgen
     snapshot --annotation`).
   - **For an assembly, ask joint by joint what it does**: turns, slides,
     locates or stays fixed, which decides its fit; how it is held (a torque,
     a press, a bond, a pin's retention); the end play it needs along its
     axis; and for a moving one, its stroke and the mounting distances at each
     end of it (retracted and extended). A first run of the set, before
     anything is stated, lists the joints in its `interface:` lines.
   - **Ask how it is dimensioned**: baseline from a datum or chain, which
     sizes are reference, and the tolerances (linear ± on a simple part,
     which calipers check; GD&T only where the function needs it). These are
     design intent, never the model's to assume.
   - **Write only what the person confirms** into the script; dimension with
     it from the start, not as a pass afterwards.
   - **Say where the model is simplified**: a solid where a tube belongs, a
     plain bore where a thread goes, a coil drawn as segments. Fix the model,
     or put a note on that part's sheet naming what it leaves out. Never infer
     a bore or a thread from a part's name.

   How: [design intent, tolerances and GD&T](references/intent-and-gdt.md).
   A person who wants a quick sheet of views can skip the questions; the
   drawing then states nominal sizes only, and the handoff says so.

   **Refreshing an existing drawing** (the model changed, or the drawing is
   being regenerated or shown): read its script's stage and requirements
   first. A `concept` stage or a sheet of nominal sizes records where things
   stood, not that they are settled: name the interfaces still without a
   requirement and ask whether to settle them now. Never carry a nominal
   drawing forward as if it showed tolerancing ("The actuator has nominal
   dimensions only; to show tolerancing, let's set the pin and bushing fits and
   the mounting faces first").
1. **Get the part.** Call the model: `enclosure()`, imported from the model's
   script, is built by cadgen's engine (a replay when the engine already holds
   it), and its `.shape` is the part. For a part with no model, read its file:
   `read_step` for a STEP, `read_xbf` for an xbf, anchored on
   `Path(__file__).parent`. Any build123d shape works. The drawing documents
   geometry; it does not build it.
2. **Write `<name>_drawing.py`** beside the model. For a single part, start
   from its first pass: `part_sheet(part, title=..., part_number=...)` draws
   the views that earn their place (the one looking down most holes as the
   front), overall sizes, holes called out and located
   (a table past six), hexagons across their flats, boss diameters, slopes by
   their angle, every step placed and edges noted, from the part alone
   ([part_sheet](references/sheet-api.md#part_sheetpart-fields)); refine that
   sheet with the person's requirements. To lay it out yourself, start from
   [the template](references/sheet-api.md#template). Import the facts your
   dimensions reference (hole pitch, wall, step lengths) from the model module
   rather than retyping them, so moving a feature moves its dimension. If the
   model keeps them inside a function, read them from its source and say so in
   the handoff; `holes()` and `overall()` need none.
3. **Choose the sheet and the views.** `Sheet(size=None, scale=None)` lets the
   sheet choose: the smallest of A4 to A2 that draws the part at 1:1 or larger,
   else A3 reduced; give either to fix it. `sheet.three_views(part, iso=True)`
   returns top, front, right and an isometric, in the projection the sheet
   names. A turned or symmetric part shows the same picture from two sides:
   draw the ones that differ, `three_views(part, views=("front", "right"))`;
   the run says when two views drawn are alike. The sheet lays them out again
   when it renders, spacing each pair for the dimensions they end up carrying,
   so add annotation freely. Where hidden
   lines would be the only way to show something (walls, floors, a bore's
   depth, a keyway), cut that view: `front.section("A", through=(x, y, z))`
   draws SECTION A-A, hatched, with its cutting plane on the view that sees it
   edge-on. Where a
   feature is too small to dimension at the sheet's scale (a chamfer, a groove,
   a thin wall), `sheet.detail(front, (x, y, z), radius)` draws DETAIL B larger,
   in free paper near its parent, which gets the circle and the letter. Where a
   flat face is inclined in one view and seen as a line there (a bent tab, a
   sloped boss), `sheet.auxiliary(front, point_on_face)` draws VIEW C square
   onto it, from that view. Where a
   long part is the same section along most of its length (a shaft, a rail),
   `front.broken(start, end)` takes that stretch out of the views that show it;
   dimensions across the break still state the true length.
4. **Dimension what a maker needs**, in MODEL coordinates:
   - `view.overall()` for overall size; `overall(height=False)` where another
     dimension already states it (a turned part's height is its diameter).
   - `view.dim(p1, p2)` for feature sizes and positions. Leave `offset` unset:
     the dimension goes on the side of the view its points are on and the
     shortest sits nearest the view. Put the points at the END of the edges
     they measure, on the side the dimension will go: a point in the middle of
     an edge runs its extension line along that edge. Two points that differ
     in one direction measure that direction; pass `orientation=` otherwise.
     Diameters of turned features go on the profile with `text="%%c<>"`. An
     inclined edge the view sees edge-on (a tab's length or thickness) takes
     `orientation="aligned"`: its true length, along it.
   - **Locate every feature and face.** A hole, slot or step is drawn where it
     is only when a dimension ties it to an edge, a datum or a located
     feature. Where the design is symmetric, say so: `view.symmetric("v")` (or
     `"h"`) states the part symmetric about the view's vertical (horizontal)
     centre line and draws the symbol; a part that is not its own mirror image
     there is refused. A feature on that line is then located, a spacing across
     it places both ends, and one side's dimensions place the other side's
     mirror. A feature that only looks centred is not located.
   - **State each size once.** A size the other dimensions add up to (an
     overall length over a chain, a height that follows from an angle) is
     `reference=True`, or left out.
   - `view.holes()` calls out every hole and slot the view looks down;
     `view.hole(point)` and `view.slot(point)` call out one. Diameter, THRU or
     depth, counterbore, countersink, a slot's width and length, the `4×` count
     and a bolt circle's `EQ SP ON ⌀60` are **read off the part**: do not type
     them. Anything you do
     type is checked, and a value the part contradicts stops the script, as
     does a `hole()` where the part has no hole to read (a boss's circle is
     none). Only `thread=` (which the geometry cannot carry) and `label=` are yours;
     with `thread=`, say how many of the identical bores are tapped (`count=`)
     and, for a blind one, the thread's depth (`depth=`).
     A chamfered bore end is part of its hole: it is called out as `⌵`, with
     `BOTH ENDS` or `FAR SIDE` when the other end is opened out too. For a part
     with many holes, `view.hole_table()` tags each one (A1, B1 ...) and lists
     its position and size in a table instead.
   - `Sheet(notes=geometry_notes(part))` adds `FILLETS R2 UNLESS OTHERWISE
     SPECIFIED.` and the like only where the part makes it true (every inside
     corner filleted, or every outside edge rounded or chamfered). Other sizes
     need a `radius()` callout or a note giving the size.
   - `view.diameter(center)` / `view.radius(center)` measure the circle or arc
     there; pass `size=` only to pick one of several concentric ones.
   - Each dimension is one of three kinds: toleranced (`tol=`, `fit=`,
     `limits=`; inspect to this), basic (`basic=True`, boxed; a GD&T frame
     bounds the feature) or reference (`reference=True`, in parentheses;
     information only). `frame=Frame(...)` on a callout or dimension,
     `view.datum("A", point)`, `view.frame(point, Frame(...))` and
     `Sheet(general_profile=...)` give GD&T, on a sheet whose `profile=` names
     the standard that reads it (`GENERIC` is ISO GPS; with none, a frame is
     refused); `key=True` marks a key characteristic. `Sheet(stage=, profile=)`
     says how far along it is and whose conventions it follows. All of it:
     [intent and GD&T](references/intent-and-gdt.md).
   - Every tolerance, fit, datum, frame, material, spec, finish and note comes
     from the person or the requirements, confirmed in step 0. Never invent
     one, and never present a guess as a requirement: a field you leave blank
     prints as an empty, captioned cell, which says the drawing does not
     state it, and the run reports what the sheet's stage still needs.
5. **Run `python <name>_drawing.py` and read what it prints** before the PDF:
   - *"incomplete: …"*: a hole or slot not called out or not located, a flat
     face not placed, an inclined face with no angle, a taper's end or a
     groove's size or place, an overall size (or one given only as reference
     with nothing else fixing it), a turned diameter, a fillet, round or
     chamfer not stated, or what the sheet's stage asks for (a general
     tolerance, datums, the material and its spec, the finish). Each line
     names the call that states it. Take positions from the model's
     constants; ask the person for anything that is a requirement.
   - *"redundant: …"*: dimensions that state one size twice, every one in the
     loop named. Make one of them reference, or leave it out; which one is a
     design decision (the one that matters is toleranced).
   - *"would measure blank paper"* (it stops the script): a dimension's points
     miss the view. Usually the part was built from a corner and the script
     assumed it was centred.
   - *"annotation overlaps"* (it stops the script), *"views crowded"*,
     *"leader crosses the view"*, *"its leader crosses a dimension line"*:
     not enough paper where the annotation is. The message names the view and
     side asking most, and a larger sheet or smaller scale; moving that
     annotation to a view with room to spare often does instead.
   - *"separate solids"* (it stops the script): the part is in pieces, usually
     a cut that runs right through the model. Fix the model before drawing it,
     or, if it is an assembly, draw it as one (below).
   - *"requirements: …"*: one line per part sheet, apart from the `incomplete:`
     lines: its stage; how many sizes are toleranced, basic, reference or
     nominal (and under which general tolerance); its datums and frames; and
     each hole, slot or turned diameter with no fit, tolerance or position. A
     sheet can have no `incomplete:` line and still read "all nominal".
   - *"interface: …"*: for an assembly, where its parts meet: a turned surface
     of one part in a bore of another, with their clearance at nominal sizes
     (no clearance and interference say so), and faces that touch square to
     such a joint's axis (no end play). These are the joints to settle with
     the person (step 0); the line stays as the record of each joint, and the
     sheets' `requirements:` lines say which sizes still have no fit.
   - A refusal (an exception, no PDF): a typed size the part contradicts, a
     hole called out where no hole is, views that run off the frame on a sheet
     whose scale you fixed. The message says what the part has, or which scale
     fits. A sheet that chose its own scale takes a larger sheet or the next
     scale down instead. A failed render leaves no file it wrote; an earlier
     PDF stays byte for byte.

   Set `MPLCONFIGDIR` to a writable directory when running unattended.
6. **Read the PDF** (render a page to PNG if you cannot view PDFs). Check that
   every feature a maker needs is located and sized exactly once, that no text
   sits on line work, that hidden lines and centre lines appear where they
   should, and that the section shows what it was cut for. Fix the script, rerun,
   and read it again.
7. **Hand off two things, separately.** *Geometry*: what is located and sized,
   what the `incomplete:` and `redundant:` lines still name (none, at best),
   and which parts are simplified. *Requirements*: the `requirements:` line
   for each sheet (what is toleranced and what is nominal, the datums, the
   interfaces left without a fit, tolerance or position) and, for an
   assembly, each `interface:` joint and what the person decided about it.
   "All features dimensioned" and "no tolerances stated" can both be true;
   say both, and say which requirements came from the person.

Steps 3 and 5 stand on their own: a sheet of views with no dimensions is a
drawing too, and writes its PDF with a list of everything it leaves unstated.

## Assemblies

An assembly is drawn as a set: a general arrangement (GA) that shows it whole,
keys every part to a parts list with a balloon, and one sheet per distinct part.

```python
# in the @eng_drawing function; from cadgen.eng_drawing import assembly_sheets, parts_list
parts = parts_list(rig().shape)                    # the assembly model, called
parts.merge("eye:upper", "eye:lower")              # one part the model names twice
parts.set("base_plate", material="AL 6061-T6", spec="AMS 4027")   # only what the person states
parts.add("LOCTITE 243", spec="MIL-S-46163 TYPE II")             # not modelled: QTY AR
sheets = assembly_sheets(parts, title="RIG", part_number="RIG-100", stage="prototype")
front = next(v for v in sheets[0].views if v.name == "front")
front.flag("TORQUE TO 9 NM WITH LOCTITE 243", item="cap_screw")   # how the joint is held
sheets.part("base_plate").views[1].section("A")   # refine any part's sheet
return sheets
```

- `parts_list` reads one item per distinct part off the assembly, with its
  quantity; the description is the model's own name for it
  (`piston_rod:chrome` reads `PISTON ROD, CHROME`). Label the model's parts
  before drawing it. PART NO. and MATERIAL stay blank unless `parts.set(...)`
  states them. Two names on one shape stay two items and the report says so;
  `parts.merge(a, b)` lists them as one after checking the shapes match.
- `assembly_sheets` makes the GA (views, overall sizes as reference
  dimensions, balloons, the parts list with each item's SHEET) and a
  first-pass sheet per part, as `part_sheet` draws one: the views that earn
  their place and an isometric, overall sizes, the holes and slots its views
  look down called out and located, steps placed and edges noted, and for a
  part turned whole (a cross hole or a cotter hole
  allowed) its diameters, its tapers' end diameters, each groove's radius,
  and every shoulder, taper end and groove placed from one end. Each is an
  ordinary `Sheet`: refine `sheets.part(name)` like any other (past six steps
  along an axis, the rest are yours to place), then run and read the report.
- The GA states the finished state, each requirement a flag note where it
  applies: how each joint is held (torque, threadlocker, press fit, bond and
  its cure, weld, rivet), work done at assembly, gaps and orientation that
  matter, marking. The steps themselves belong to work instructions, not the
  drawing.
- A section through the assembly, `view.section("A", parts=parts)`, is drawn
  as drafters draw one: every part in one hatch, neighbours turned or spaced
  apart, solid shafts, rods and pins cut along their axis left uncut, and
  `balloons(parts)` on it saying which part is which. Keep material-coded
  hatching off a busy assembly: the parts list says what each part is made of.
- A layered part (a phone case's shell, tape and lining) is a small assembly:
  `view.section("A", parts=parts, materials=True)` hatches each layer as its material family
  (`parts.set(n, family="plastic")`), fills a layer too thin to hatch solid
  and names it, and draws a material key, a row per layer; each layer's thickness and coverage,
  as the person states them, go in a note.

Parts lists, balloons on a custom GA, and what the script prints about them:
[assemblies reference](references/assemblies.md).

## What the sheet contains

- Line work with meaning, each at its own weight: visible outline (0.5),
  hidden (dashed), centre lines (chain), section hatching (ANSI31), dimensions,
  notes. Centre marks on every hole seen end-on, a centre line down every
  turned feature seen from the side, down every slot and across its ends, and a
  bolt circle's pitch circle. A centre line stated symmetric carries the ISO
  129-1 symbol, two short strokes beyond each end.
- Dimensions measured from the geometry, true size at any scale; values wider
  than their extension lines set beside them. Hole callouts in the standard
  symbols (⌀ ↧ ⌴ ⌵), drawn as line work so they print the same everywhere.
- An ISO 5457 zoned border, an ISO 7200-style title block (TITLE, DWG NO., REV,
  SHEET, MATERIAL, FINISH, SCALE, SIZE, DRAWN, DATE, UNITS and the ISO 5456-2
  projection symbol; COMPANY, STAGE and a profile's own cells in a band above
  when a stage or profile is given), numbered notes (a general profile first,
  then the standard, the general tolerance, the author's notes and the flag
  notes, each numbered in its flag), and a revision table when `revisions=`
  is given.
- Feature control frames, datum feature symbols and key characteristic marks,
  drawn as line work, each kept on rows of its own clear of other annotation.
- Hole tables: each hole and slot tagged on the view, an X and Y origin, and a
  table of TAG, X, Y and SIZE. Auxiliary views labelled VIEW C with the viewing
  arrow on their parent; broken views with a zigzag break line across each cut.
- On an assembly's GA, balloons (item number in a circle, a leader ending in a
  dot on the part) in even columns whose leaders do not cross, and an ISO 7573
  parts list standing on the title block: ITEM, QTY, DESCRIPTION, PART NO.,
  MATERIAL, SPEC, SUPPLIER and, in a set with part sheets, the SHEET each item
  is detailed on, read upward from the header. A section through an
  assembly is hatched in one pattern and ballooned; one hatched by material
  (`materials=True`) carries a material key.
- Notes on the frame's foot beside the title block, each wrapped at its words
  to the room there.
- PDF bytes that are a function of the content: an unchanged drawing rebuilds
  to an identical file.

## Limits to state in the handoff

- Every dimension without `tol=`/`fit=`/`limits=` is nominal, governed by the
  general tolerance or general profile if one is given; the `requirements:`
  line counts them. Say which requirements came from the person, and which
  interfaces the stage asks about that they have not decided.
- GD&T: single-segment frames on callouts, dimensions and surfaces, datum
  feature symbols on faces and features of size; no composite frames, datum
  targets, projected zones or all-around symbols. Weld symbols are not drawn:
  a weld is a flag note.
- Full sections and circular details only: no half, offset or broken-out
  sections. Auxiliary views are projected from a view that sees the face
  edge-on (no secondary auxiliaries), drawn unrotated, and by default partial
  (the face and what lies within its outline); a view takes one break. Say what
  a view does not show.
- Checked for completeness: holes and slots (called out and located), flat
  faces square to a model axis (placed), inclined flat faces (an angle, or
  both ends placed), overall sizes, turned diameters, tapers and grooves,
  fillets, rounds and chamfers. A curved pocket or a freeform surface is
  not, and is stated with `dim`, a detail or a `note`. A bolt circle's
  clocking (where its first hole sits) is a `dim` or an `angle` you add.
- The location, redundancy and reference checks follow dimensions along the
  model axes. An aligned dimension at a stated angle (one leg along a model
  axis, or square to such a leg) counts for its run and its rise; an angle
  alone fixes no length. Features that share a coordinate share a place (two
  holes on one centre line are located together), but a dimension's end on a
  hole or on one face is that feature when the check looks for a size stated
  twice. A hole on an inclined axis is not location-checked: say how the
  auxiliary view locates it.
- `interface:` lines find coaxial full cylinders of different parts whose
  diameters are within 10 % of the bore or 2 mm, and flat faces of parts on
  such an axis that touch square to it, a repeated joint once with its number
  of places. Splines, keys, threads modelled as plain bores and faces that
  touch away from a turned joint are not found: ask about them.
- Millimetres only; one part per arrangement.
- Assembly sheets: balloons go on whole views and on sections cut part by
  part, not on details; parts are drawn in their model frame. Say which part
  sheets are still a first pass.

## References

- Sheets, views and every annotation call, with a template: `references/sheet-api.md`
- The interview, dimension kinds, frames and datums, stages and profiles: `references/intent-and-gdt.md`
- Assembly drawings, parts lists, balloons, flag notes and layered parts: `references/assemblies.md`
