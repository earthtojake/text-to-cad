# Native KiCad files

The saved `.kicad_pcb` is the editable source. cadgen's API reads it; it does not create a
second live document or write it back. For file syntax use KiCad's
[board format](https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/) and
[common syntax](https://dev-docs.kicad.org/en/file-formats/sexpr-intro/).

When editing, preserve the format version, generator, UUIDs, project netclasses, unknown
properties and footprint graphics. Parse S-expressions for structural changes; a global text
replacement can change unrelated pads, text or graphics. Write atomically after validating
balanced syntax, then read the new board and run KiCad's DRC. The read-only `read_board` API
is documented in [checks](checks.md); its index is not a lossless serializer.

KiCad 9/10 footprints use `(at x y angle)`. KiCad 11 development files can use
`(transform (translate x y) (rotate angle) (scale sx sy))`. The reader handles both. Net codes
and names also differ between formats; preserve the file's convention. Board coordinates are
millimetres, x right, y down. Footprint graphics and pads are local to the footprint, and
bottom-side placement includes mirroring. Never apply a translation or rotation twice.

For a new board, start with a valid native file from the KiCad version in use. Establish the
layer stack, closed Edge.Cuts outline and thickness, place verified library footprints, assign
nets from the circuit specification, route and refill zones, then save and run DRC. A schematic
and its pin/net mapping remain part of the project when present. A board without a schematic
requires an explicit, reviewable circuit specification; footprint numbers alone do not tell
which connections are electrically correct.

## Design rules

Board Setup writes project limits and netclasses to `.kicad_pro`; custom rules live in the
sibling `.kicad_dru`. Preserve them through edits. Consult the installed version's
[custom rules manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html#custom_design_rules)
before adding constraints. DRC checks only declared rules; compare them with the selected fab,
copper weight and electrical needs. Record the source of adopted limits.
