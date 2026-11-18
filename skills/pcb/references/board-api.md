# Native KiCad files

The saved `.kicad_pcb` is the editable source. `cad.kicad_pcb` reads it; it does not create a
second live document or write it back. For file syntax use KiCad's
[board format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/) and
[common syntax](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/).

When editing, preserve the format version, generator, UUIDs, project netclasses, unknown
properties and footprint graphics. Parse S-expressions for structural changes; a global text
replacement can change unrelated pads, text or graphics. Write atomically after validating
balanced syntax, then read the new board and run KiCad's DRC. The read-only `kicad_pcb.read` API
is documented in [checks](checks.md); its index is not a lossless serializer.

KiCad 9/10 footprints use `(at x y angle)`. KiCad 11 development files can use
`(transform (translate x y) (rotate angle) (scale sx sy))`. The reader handles both. Net codes
and names also differ between formats; preserve the file's convention. Board coordinates are
millimetres, x right, y down. Footprint graphics and pads are local to the footprint, and
bottom-side placement includes mirroring. Never apply a translation or rotation twice.

For a new board, start with a valid native file from the KiCad version in use. Establish the
layer stack, closed Edge.Cuts outline and thickness, place verified library footprints, assign
nets from the circuit specification, route and refill zones, then save and run DRC; with a
schematic, follow [layout](layout.md), which imports its netlist. A schematic
and its pin/net mapping remain part of the project when present. A board without a schematic
requires an explicit, reviewable circuit specification; footprint numbers alone do not tell
which connections are electrically correct.

## Design rules

Board Setup writes project limits and netclasses to `.kicad_pro`; custom rules live in the
sibling `.kicad_dru`. Preserve them through edits. Consult the installed version's
[custom rules manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#custom_design_rules)
before adding constraints. DRC checks only declared rules; compare them with the selected fab,
copper weight and electrical needs. Record the source of adopted limits.

## Edits

Change a board in a `with kicad_pcb.edit("board.kicad_pcb") as b:` block ([SKILL.md](../SKILL.md#native-files-are-the-source)):
KiPy's open board, saved at the block's end only when the block changed it, and not at all when it
raises. Write the block to state the board it wants, so a second run changes nothing: set a footprint's
position, a track's width or a net to its value, and create an item only when the board does not hold
it yet. Read the board in the block (`b.get_footprints()`, `b.get_tracks()`, `b.get_nets()`), or with
`kicad_pcb.read` after it.

A new item needs every field KiCad needs to keep it: a track with no layer (`track.layer =
BoardLayer.BL_F_Cu`, `from kicode.proto.board.board_types_pb2 import BoardLayer`) or width is dropped
without a word, and the block saves nothing for it. Read it back (`b.get_tracks()`) to see it is there.

Updating a footprint through KiCad's IPC API replaces its whole definition (pads, graphics, 3D
models) and sets its layer and lock. Edit only footprints read back from the board
(`b.get_footprints()`), changed and sent with `b.update_items(...)`: KiPy sends their full body. Never
build a new `FootprintInstance` from an id and a position to update an existing one; it wipes that
footprint's pads and graphics. Moving a footprint that owns a zone, and the back side's orientation,
are [placement](placement.md#move-then-check)'s.

KiPy's traps on this nightly:

- A field is hidden with `field.visible` (`fp.reference_field.visible = False`); `text.attributes.visible`
  is deprecated and changes nothing.
- `zone.is_rule_area()` is a method, where its neighbours are properties: `not zone.is_rule_area` is
  always false.
- A new `Zone()` has no outline to read (`zone.outline` raises `IndexError`): build one and assign it,
  `outline = PolygonWithHoles(); outline.outline = line; zone.outline = outline`, `line` a `PolyLine` of
  `PolyLineNode.from_point(Vector2.from_xy_mm(x, y))` (from `kicode.geometry`).
- A text's angle set over the API (a footprint field's `text.attributes.angle`, a board text's) reads
  back changed in the block and is saved as it was. A field turns with its footprint; any other angle
  is set in the saved file, as text, after the block.

KiCad writes a STEP or GLB export through a temporary file of a fixed name in the output folder, so
two exports into one folder at once can collide. Give each export (`kicad_pcb.export`, after the block)
a folder of its own.
