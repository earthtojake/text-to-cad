# Native KiCad files

Read this to create a board, to set its rules, or when an edit needs more than
[SKILL.md](../SKILL.md#native-files-are-the-source) says of `kicad_pcb.edit`.

## The files

A board is its `.kicad_pcb`. The `.kicad_pro` beside it holds its rules and netclasses, the `.kicad_dru` its
custom rules. `kicad_pcb.edit("new.kicad_pcb")` makes a board that is not there yet (two copper layers,
1.6 mm), with its project when it has none. Give it a closed `Edge.Cuts` outline (DRC's `invalid_outline`
until then; rounded or chamfered corners, as the person confirms), then its parts and nets from the
schematic's netlist ([layout](layout.md)). A board with no schematic needs a circuit specification a person
can review: footprint pad numbers alone do not say which connections are right.

KiCad 9 and 10 place a footprint with `(at x y angle)`. The nightly that an edit saves with writes
`(transform (translate x y) (rotate angle) (scale sx sy))`, and names each net where older files number it.
`kicad_pcb.read` reads both ([checks](checks.md)); it is read-only, and nothing here writes a board from it.

What the API cannot change (a text's angle, below) is changed in the file's text
([board format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/),
[common syntax](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/)): the one node, in the file's own
convention, never a global replace, which reaches unrelated pads and texts. Then read the board back and
run DRC.

## Design rules

DRC checks the rules the project declares and nothing else:

- **The board's minimums** (clearance, track width, via and hole sizes, copper to edge) are the `.kicad_pro`'s
  `board.design_settings.rules`. In an edit, `rules = b.get_design_rules().rules`, set
  `rules.constraints.min_clearance = from_mm(0.15)` and its neighbours (nanometres), then
  `b.set_design_rules(rules)`: saved with the board.
- **Netclasses** (a net's clearance, track width, via, and differential pair width and gap), which DRC holds
  a net to over the minimums, are the `.kicad_pro`'s `net_settings.classes`, given to nets by its
  `netclass_patterns` (`{"netclass": "Power", "pattern": "/VIN"}`). Write them as JSON outside an edit block:
  an edit's save writes back the classes KiCad loaded. A board an edit makes has KiCad's `Default` alone
  (0.2 mm clearance and width). `kicad_pcb.read(path).net("/VIN").netclass` says which class a net took.
- **Custom rules** are the `.kicad_dru`
  ([KiCad's manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#custom_design_rules)).

## Edits

What the open board (KiPy's `Board`) does that its names do not say:

- **A new item needs every field KiCad keeps it by.** A track with no layer (`track.layer = BoardLayer.BL_F_Cu`,
  `from kicode.proto.board.board_types_pb2 import BoardLayer`) is dropped without a word, though
  `create_items` answers it. One with no width is saved 0 mm wide (DRC's `track_width`). Read a new item
  back (`b.get_tracks()`) to see it is there.
- **Updating a footprint replaces its whole definition** (pads, graphics, 3D models) and sets its layer and
  lock. Change only footprints read back from the board (`b.get_footprints()`), sent with
  `b.update_items(...)`. A new `FootprintInstance` built from an id and a position wipes that footprint's
  pads and graphics. Moving a footprint that owns a zone, and the back side's orientation, are
  [placement](placement.md#move-then-check)'s.
- **A field is hidden with `field.visible`** (`fp.reference_field.visible = False`);
  `text.attributes.visible` changes nothing.
- **`zone.is_rule_area()` is a method**, where its neighbours are properties: `not zone.is_rule_area` is
  always false.
- **A new `Zone()` has no outline to read** (`zone.outline` raises `IndexError`). Assign one:
  `outline = PolygonWithHoles(); outline.outline = line; zone.outline = outline`, `line` a `PolyLine` of
  `PolyLineNode.from_point(Vector2.from_xy_mm(x, y))` (all from `kicode.geometry`).
- **A text's angle set over the API** (a footprint field's `text.attributes.angle`, a board text's) reads
  back changed in the block and is saved as it was. A field turns with its footprint; any other angle is
  set in the saved file's text, after the block.
