# Assembly drawings

```python
from cadgen.eng_drawing import eng_drawing, parts_list, assembly_sheets, JOINTS
```

An assembly is a drawing set: a general arrangement keyed to a parts list,
then a sheet per part, each one refined like any sheet:

```python
@eng_drawing(out="../PDF/rig_drawing.pdf")
def rig_drawing():
    parts = parts_list(rig().shape)          # the assembly model, built by the engine
    parts.merge("eye:upper", "eye:lower")                                # one part, named twice
    parts.set("base_plate", material="AL 6061-T6", spec="AMS 4027", part_number="RIG-101")   # stated, never guessed
    parts.add("LOCTITE 243", spec="MIL-S-46163 TYPE II")                 # in no model: QTY AR
    sheets = assembly_sheets(parts, title="RIG", part_number="RIG-100", general_tolerance="ISO 2768-m",
                             stage="prototype")
    ga_front = next(v for v in sheets[0].views if v.name == "front")
    ga_front.flag("TORQUE TO 9 NM WITH LOCTITE 243", item="cap_screw")   # the finished state
    ga_front.flag("FLUSH WITHIN 0.1", item="bushing", joint="press_fit")
    top, front, right, iso = sheets.part("base_plate").views
    front.section("A")
    return sheets
```

## `parts_list(source)`

`source` is an assembly: a build123d `Compound` made with `children=`, as an
assembly model's `.shape`, `cadgen.read_xbf(path)` and `cadgen.read_step(path)`
hand one back. Returns a `PartsList`: one `Item` per
distinct part, numbered in the order the assembly first holds them.
Occurrences are one part when they have the same name, the same colour, the
same material (`shape.material`) and the same geometry (one prototype placed several times, or an exact translated
copy). Anything less stays apart: two parts of identical geometry can be
different parts (a steel spacer and a brass one), a
label's detail often names a finish (`piston_rod:chrome`), and mirror images
have identical volumes. `parts.twins` lists the item pairs that share a shape
under different names, and the script prints them.

- `parts[3]`, `parts["coil_spring"]`: an item by number, label or the label's
  name before the colon; an unknown or ambiguous key is refused with the list.
- `parts.set(key, description=..., part_number=..., material=..., spec=..., supplier=..., family=...)`:
  what the model cannot carry; chains. `spec` is the material's specification
  ("AMS 4027"), `supplier` who it is bought from, `family` the material family
  a section hatches it as: `steel`, `iron`, `aluminium`, `copper_alloy`,
  `plastic`, `elastomer`, `composite`, `fabric`, `glass` or `general`. Nothing
  else is accepted. It may follow `assembly_sheets`: each part's sheet reads
  its item when it renders, its MATERIAL cell `AL 6061-T6 PER AMS 4027`.
- `parts.add(description, quantity="AR", part_number="", material="", spec="", supplier="")`:
  an item the model does not hold (an adhesive, a sealant, a grease, a shim
  set at assembly), numbered last. It has no sheet and needs no balloon;
  `quantity` is a count or `"AR"` (as required). Add before drawing.
- `parts.merge(*keys, description=None)`: list items as one part, after
  checking their geometry and material are the same; a different shape or
  material is refused. What `set()` stated for any of them is kept, and two
  different values of one field (two part numbers) are refused. The first
  keeps its place, later items are numbered again, and the description is the
  label segments they share unless given. Merge before drawing from the list.
- `item.number`, `.description` (the label read out: `piston_rod:chrome` is
  `PISTON ROD, CHROME`), `.quantity`, `.part_number`, `.material`, `.labels`,
  `.refs` (each occurrence's ref, its path of names: `hand/finger.2`), `.shape`
  (one occurrence in its own frame), `.occurrences` (each placed in the
  assembly), `.prototypes` (the geometries, each placed one or more times, they
  are).
- `parts.assembly`: the whole assembly, placed, for the GA's views.

## `assembly_sheets(parts, title=..., part_number="", revision="A", size="A3", author="", date="", projection="THIRD ANGLE", ink="mono", notes=(), general_tolerance="", revisions=(), stage=None, profile=None, category="", company="", fields=None)`

Returns the set as a list of `Sheet`s: the general arrangement (front view, the
one of top and right showing more, an isometric; no hidden lines; overall
sizes as reference dimensions, an assembly's envelope being information nobody
inspects; balloons; the parts list, continued on further sheets past 16 items
on A3), then one sheet per modelled item. A GA that does not fit `size` beside its
parts list at 1:50 or larger is refused, naming a larger size. A part's sheet
draws `item.shape` as `part_sheet` draws a part, in the views that earn their place and an isometric on a
sheet that chooses its own size and scale (`Sheet(size=None, scale=None)`); a
long turned part lies down, and the points you give its views stay in the
part's own frame, as `item.shape` is. It states its overall sizes, calls out
the holes and slots each view looks down and locates them (a prismatic part's
from its edge faces, or in a hole table past six; a turned part's from its axis
and its end, a cross hole included), and is titled
with the item's description over `ITEM n (QTY q) OF <title>`. A part turned
whole states its profile: its diameters, each taper's end diameters, each
groove's radius, and every shoulder, taper end and groove placed along the
axis from its near end (the far end is the overall length's). A prismatic
part's steps and faces are placed from its edges, the largest six along an
axis, and its edges noted; the report names any step left. Every sheet carries the drawing number, revision, author
and date, and the stage, profile, category, company and fields; `notes` and
`revisions` go on the GA, `general_tolerance` on the part sheets.
`sheets.part(key)` is an item's sheet; `sheets.parts` the list. A detail of a
joint on the GA is `sheets[0].detail(ga_front, point, radius)`.

## What an assembly drawing states

The finished state, as ASME Y14.24 has it: what must be true once it is put
together, not the steps. Each requirement is a flag note on the view where it
applies:

- how each joint is held: a torque or torque spec, a threadlocker grade, a
  lubricant, safety wire, a cotter pin, staking
- bonding and sealing: the adhesive or sealant with its spec, the surface
  preparation and cure spec, masking
- work done at assembly ("PRESS WITH RETAINING COMPOUND", "REAM AFTER
  ASSEMBLY TO ⌀X"); those dimensions are toleranced, being inspected then
- the orientation, gaps and clearances that matter
- marking

Ask the person for every value, joint by joint; never supply a torque or an
adhesive. The order of work, fixtures and procedures belong to work
instructions, a separate document.

## Joints and interfaces

The run prints an `interface:` line for each place the parts meet on a turned
axis:

- a turned surface of one part in a bore of another, their diameters within
  10 % of the bore or 2 mm of each other (whichever is more: a fit, or a
  clearance a rod runs in), with the clearance at nominal sizes, or "no
  clearance", or the interference;
- two parts on such an axis whose flat faces touch square to it: no end play
  at nominal sizes. A clevis gap filled exactly by an eye and two bushing
  flanges prints one line per touching pair.

A joint the assembly repeats (four bolts in four holes) is one line, with its
number of places: each pair of parts that meet there (two bushings in one bore
are two places; two plates touching once are one, however many pins cross).

Nominal sizes that meet exactly are what a model says, not what a shop can
make: each line is a joint to settle with the person. For each joint, ask:

1. **What it does**: turns, slides, locates, or stays fixed. That decides the
   fit on both sizes (a clearance, transition or interference fit; a thread).
2. **How it is held**: a press, a thread and its torque, a retaining ring, a
   cotter pin, a bond. Each is a flag note.
3. **End play**: how much the joint may move along its axis, or that it is
   clamped. A stack of parts across a gap is a tolerance stack: state the gap
   and the parts' widths with tolerances that keep it.
4. **For a moving joint**: its stroke or travel, and the mounting distances at
   each end of it (retracted and extended, eye to eye), which the general
   arrangement states as reference dimensions or flag notes.

Write the answers as `fit=`/`tol=` on both parts' sizes, `thread=` on a
threaded bore, and flag notes on the GA. The lines stay in the run as the
record of each joint; each sheet's `requirements:` line says which sizes still
have no fit. Splines, keys and threads modelled as plain bores are not found;
ask about them too.

## `view.flag(text, at=None, item=None, joint=None, offset=None)`

A numbered flag where a requirement applies, the note under that number after
the sheet's other notes, its flag beside it. Exactly one of `at` (a model
point) or `item` (a part the view balloons, by number or name; the leader lands
where its balloon's does). `joint` says how the parts there are held, one of
`JOINTS`: `weld`, `braze`, `solder`, `rivet`, `crimp`, `press_fit`, `bond`,
`tape`, `overmold`, `snap`, `not_bonded`; its word begins the note (`BOND:
LOCTITE 401`). The same note flagged twice keeps one number. Left without
`offset`, the flag takes the nearest place off the view clear of its
annotation, its leader crossing no line. Weld symbols (AWS A2.4, ISO 2553) are
not drawn; a weld is a flag note.

## Layered parts

A part made of layers (a phone case's shell, tape and lining; a laminate) is
modelled as a small assembly, a layer per part, and drawn with a section
through it:

```python
parts = parts_list(case_back().shape)
parts.set("shell", material="PC/ABS", family="plastic")
parts.set("tape", material="3M VHB 4910")
sheet = Sheet("A3", 5.0, title="CASE BACK")
front = sheet.view(parts.assembly, "front", at=(180, 170), hidden=False).section("A", parts=parts, materials=True)
front.flag("15 PSI, 72 H DWELL", at=(10, 0, 1.6), joint="tape")   # a point on the tape
```

With `materials=True` each layer is hatched as its family, neighbours of one
family at different angles (layers that touch never alike); one thinner than 1 mm on the sheet is
filled solid and named with a leader (draw a detail at a larger scale to show
it hatched); where the model overlaps solids the earlier item takes the region.
A material key lists each part: its hatch, item number, family and material;
thin layers read THIN, SOLID. Every place two layers meet
gets a flag with its `joint`, including `not_bonded`. A liquid adhesive is
never modelled: its flag and the parts list carry it. Tapes and films are
modelled as thin layers when they are.

## `sheet.parts_list(parts, first=1, last=None)`

Draws `parts` as the parts list, standing on the title block and as wide as it
(ISO 7573, ASME Y14.34): ITEM, QTY, DESCRIPTION, PART NO., MATERIAL, SPEC,
SUPPLIER, the header against the block and item 1 above it. In a set with a
sheet per part (`assembly_sheets`, or any set whose sheets come from it), a
SHEET column gives the sheet each item is detailed on, counted in the set's
final order when it renders, so a sheet inserted after the GA moves them. `first`/`last` draw a run of a list too
long for one sheet; one that does not fit is refused, naming where to split it,
and each run of a split list says on which sheet it continues. The views and
any detail keep clear of it; a hand-placed view over it, or a note running
under it, is refused. Each column takes the room its widest entry needs; a
list whose entries cannot fit the title block's width even at the smallest
legible text is refused, naming the longest entry, never cut.

## `view.balloons(parts)`

Balloon every item of `parts` the view shows, on a view of `parts.assembly`.
Each leader ends in a dot on a point of the part the view sees. The balloons
stand in a column each side of a tall view (rows above and below a wide one),
may run the frame's height clear of other views, the title block and the parts
list, keep their leaders uncrossed and off dimension text, and stand outside
any hole callouts. An item already ballooned in an earlier view of the sheet is
skipped, so balloon the views in order of preference. A column the paper cannot
hold is refused, naming a larger sheet or scale. On a section cut part by part
(`section(..., parts=parts)`) each leader ends inside its part's cut; a section
cut whole, and a detail, are refused.

## What the script prints

| Line | Means |
| --- | --- |
| `incomplete: item 4 (CORE) has no balloon ...` | no ballooned view shows that part; balloon a view from a side where it shows |
| `incomplete: the parts list leaves out items 18, 19 ...` | draw the rest with `parts_list(parts, first=18)` on another sheet |
| `note ... runs under the parts list` / `view is drawn over the parts list` | shorten the note, move the view |
| `note: items 1 and 10 (... and ...) are the same shape under different names ...` | `parts.merge(1, 10)` lists them as one part, if they are one |
| `front.balloons(): 9 balloons do not fit on the right of the front view on A3 ...` | a larger `size=`, or balloon some items on another view (a refusal) |
| `the general arrangement does not fit A3 beside its parts list ...` | give `assembly_sheets()` a larger `size=` (a refusal) |
| `item 2's SPEC '...' does not fit the parts list's SPEC column ...` | shorten it: `parts.set(2, spec=...)` (a refusal) |
| `flag(item='pin') on the front view finds the item in the parts list the view balloons ...` | `front.balloons(parts)` first, or flag with `at=` (a refusal) |
| `front flag 3: no clear place near its point ...` | give `flag(..., offset=(x, y))` |
| `interface: item 7 (PIVOT PIN) ⌀12 in item 1 (CLEVIS) ⌀12, on the axis along Y through (0, -16, 36): no clearance at nominal sizes ...` | a fit nobody has chosen: ask what the joint does ([joints](#joints-and-interfaces)) |
| `interface: item 2 (EYE) and item 6 (BUSHING) touch face to face square to the axis along Y, at (0, 10, 36): no end play ...` | ask the end play the joint needs, or that it is clamped |
