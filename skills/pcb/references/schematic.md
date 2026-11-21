# Read and check the schematic

Read this to read, look at, check or edit a schematic (`.kicad_sch`), to carry it into the board, and to hold
the board to it.

## Contents

- [Read it](#read-it)
- [References](#references)
- [Look at it](#look-at-it)
- [Check it](#check-it)
- [Edit it](#edit-it)
- [Into the board, and back](#into-the-board-and-back)

## Read it

```python
from cad import kicad_sch

sch = kicad_sch.read("board.kicad_sch")     # any sheet: the hierarchy is read from the project's root
print(sch.sheets)                           # each sheet: its path ("/", "/Power/"), page, file
print(sch.net("/Power/VBUS").pins)          # a net, by KiCad's name: the pins on it
pin = sch.resolve("#U3.7")                  # a pin: its name, electrical type, sheet, where, its net
print(pin.name, pin.type, pin.net)
for unit in sch.part("U3"):                 # every unit placed of a part
    print(unit.value, unit.footprint, unit.mpn, unit.sheet)
```

Run it with `cad run inspect_schematic.py`. Each call reads the whole hierarchy as the files are now:
`sheets`, `symbols` (each unit placed: `ref`, `value`, `footprint`, `lib_id`, `fields`, `sheet`, its `pins`
with number, name and electrical type), `pins`, `wires` (and buses), `junctions`, `labels`, `no_connects`,
`bus_entries`, and the `nets` they make, named as KiCad names them: the netlist's names, and the board's. A
local net carries its sheet's path (`/Power/VBUS`); `sch.net("VBUS")` finds it by its bare name when one
sheet alone has it. Positions are millimetres on each sheet's page, y down.

`cad kicad_sch inspect board.kicad_sch [REF] --json` says the same in one look: sheets, parts, nets,
and what a reference names.

## References

A schematic reference names what a board reference names where both hold it, so one cross-probes
the other:

| Reference | Names | `resolve` answers |
| --- | --- | --- |
| `#U3` | a part, every unit of it | the units, each a `Symbol` |
| `#U3.7` | its pin 7: the board's pad 7 | `Pin`: name, type, sheet, `at`, net |
| `#net:/Power/VBUS` | a net, by KiCad's name (the board's) | `Net`: pins, labels, sheets |
| `#sheet:/Power/` | a sheet, by its path | `Sheet`: file, page, parent, its pins |
| `#wire:<uuid>` | a wire, by the uuid KiCad saved it with; so `#bus:`, `#label:`, `#junction:`, `#no_connect:`, `#bus_entry:`, `#symbol:` (one unit) | the item, with its net |

## Look at it

```bash
cad kicad_sch snapshot board.kicad_sch tmp/root.png
cad kicad_sch snapshot board.kicad_sch tmp/power.png --sheet /Power/
```

Each picture is one sheet, framed on what it draws, its title block included (`--border`: the whole page
and its frame; [views](views.md#the-schematic-view) has the display's keys). The lettering is a stroke font
of cad's own: same places, other glyphs. The netlist proves the connections, the picture that a person can
read them: after an edit, look at each sheet changed and redraw until nothing overlaps or runs long.

## Check it

```bash
cad kicad_sch erc board.kicad_sch --json
```

KiCad's electrical rules check on the whole hierarchy, every finding with its sheet and where it is on that
sheet's page. It exits 1 on errors; warnings are said. Beside KiCad's own findings:

- `pin_on_wire_span`, `wire_end_on_wire_span` (warnings, the check's own): a pin's end that is joined some
  other way too (a wire ending on it, a label, another pin), or a wire's end, lying on another wire's span
  with no junction there. KiCad joins them, and its ERC and the board comparison both pass, so a wire drawn
  past a pin on its way elsewhere shorts the pin into that wire's net (a transistor's drain onto its
  supply). Each names the pin (`#Q1.3`) or the wire's end, and the wire it lies on (`#wire:<uuid>`), in
  `items`. Route the wire clear of the pin's end; where the join is meant, place a junction on it. A pin
  whose one connection is a straight wire across it is no finding: KiCad saves a rail drawn to each of a
  row of pins that way.
- `bus_to_bus_conflict`: two buses joined whose names share no member. KiCad still joins their members by
  index (`D3` meets `Q3`), so rename one to say what it is.
- `libraries_not_checked` is a note, not a finding: the check runs KiCad with private settings, so it sees a
  project's own `sym-lib-table` and `fp-lib-table` and no global table ([SKILL.md](../SKILL.md#setup)).
  `lib_symbol_issues` saying a library "was not found" at a stock path is a row naming a stock library
  with no KiCad installed: copy the library into the project.

A clean ERC says no rule broke, not that each pin is on the net the circuit means. Read the pins of each
driver, regulator and connector back (`sch.resolve("#Q1.3").net`, `sch.net("/Power/VBUS").pins`) against
the circuit you meant.

## Edit it

`with kicad_sch.edit(...) as s:` works as `kicad_pcb.edit` does for a board
([SKILL.md](../SKILL.md#native-files-are-the-source)): `s` is KiPy's open `Schematic` (kicode's
`kicode.schematic.Schematic`), the project's symbol libraries already loaded. A schematic not there yet is
made, with its project. Place a symbol only when its reference is not there yet, so a second run changes
nothing. Run the script with `cad run schematic.py`.

```python
from cad import kicad_sch
from kicode.geometry import Vector2
from kicode.schematic_types import SchematicLine, SchematicLineType

def pin_at(symbol, number):                  # a pin's end on the sheet, for a symbol placed at 0 degrees
    pin = next(pin for pin in symbol.definition.pins if pin.number == number)
    return symbol.position + pin.position    # its definition's frame, y down, unrotated and unmirrored

with kicad_sch.edit("board.kicad_sch") as s:  # any sheet of the project
    placed = {symbol.reference: symbol for symbol in s.get_symbols()}
    for ref, y in (("R1", 50.8), ("R2", 63.5)):
        if ref not in placed:
            placed[ref] = s.place_symbol_from_library("parts:R", Vector2.from_xy_mm(50.8, y), reference=ref)
    if not s.get_lines():
        wire = SchematicLine()
        wire.type = SchematicLineType.SLT_WIRE  # a new line is a graphic, joining nothing, until it is a wire
        wire.start, wire.end = pin_at(placed["R1"], "2"), pin_at(placed["R2"], "1")
        s.create_items(wire)
```

- **Place a symbol with `s.place_symbol_from_library("<library>:<symbol>", position, reference="R1")`**
  (`orientation=`, `unit=` for the rest): KiCad copies the library's symbol, its pins and drawing, into the
  file and keeps its library link. A `SchematicSymbolInstance` made from a library id alone and created
  comes out hollow, with no pins or drawing.
- **Change an item as it was read back**: `s.get_symbols()`, `s.get_lines()`, `s.get_labels()` (and
  `s.for_sheet(sheet)` for a sheet of `s.get_hierarchy()`), sent with `s.update_items(...)`. Make wires,
  labels, junctions and no-connects with `s.create_items(...)`, a group of edits in one commit
  (`commit = s.begin_commit()`, `s.push_commit(commit)`). `s.get_netlist()` says what connects while the
  script runs.
- **A wire's ends must land exactly on a pin's end** (`pin_at` above; turn the pin's offset with the
  symbol's orientation for a turned or mirrored one), a junction or another wire's end.
- **KiCad finds a differential pair by its two nets' names**: matching suffixes, `+`/`-` or `P`/`N`
  (`USB_D+`, `USB_D-`).
- **After redrawing a symbol, prove every pin kept its number, name and type**: compare
  `{(pin.ref, pin.number): (pin.name, pin.type) for pin in sch.pins}` before and after. A new symbol's pins
  follow [KLC S4.2](https://klc.kicad.org/symbol/s4/s4.2/): inputs left, outputs right, power at the top,
  ground at the bottom.

Report the liberties taken: a symbol redrawn, a sheet split or merged, a choice the documents left open.

**Libraries.** A symbol is placed from the project's own symbol libraries: the rows of its `sym-lib-table`,
beside the `.kicad_pro` (`${KIPRJMOD}` is that folder). No global library table is there, and a placement
from a library the table does not list fails in one line naming the row to add. A row may name a stock
library (`${KICAD10_SYMBOL_DIR}/Device.kicad_sym`), read in the KiCad the person installed; for a project
that opens anywhere, copy each library a design needs (its `.kicad_sym`) into the project and list it:

```
(sym_lib_table
  (version 7)
  (lib (name "parts")(type "KiCad")(uri "${KIPRJMOD}/parts.kicad_sym")(options "")(descr ""))
)
```

**Fragile on this nightly** (KiCad 10.99 over IPC; check the saved file after each):

- A sheet symbol made over IPC (`create_items(SheetSymbol())`) cannot be saved, whether its file is there
  or not: KiCad looks for the new sheet's file inside a folder named after the root's file, and the edit
  raises with KiCad's words ("failed to save schematic"), every file as it was. Write a hierarchy as text,
  as below, then fill its sheets over IPC.
- Changing a placed symbol's field (`update_items`) can save it on a private copy of its library symbol: a
  `(lib_name "C_1")` beside its `lib_id`, and a `C_1` among the file's `lib_symbols`. Look for `lib_name` in
  the saved file after changing one.

Editing the `.kicad_sch` as text (KiCad's
[file format](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/)) is the fallback, for what the
API cannot do: keep every `uuid` (references and the board's links to its symbols are made of them), and
give a new symbol its `lib_symbols` entry and its reference in the `instances` entry for its sheet's path.

**A hierarchy.** Each sheet is a block in its parent, written as text with a new uuid, a pin for each
hierarchical label inside, and its page under the root's uuid:

```
(sheet (at 101.6 50.8) (size 25.4 15.24) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
  (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "<new uuid>")
  (property "Sheetname" "Power" (at 101.6 50.1 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
  (property "Sheetfile" "power.kicad_sch" (at 101.6 66.68 0) (effects (font (size 1.27 1.27)) (justify left top)))
  (pin "VIN" input (at 101.6 55.88 180) (uuid "<new uuid>") (effects (font (size 1.27 1.27)) (justify left)))
  (instances (project "<project>" (path "/<root's uuid>" (page "2")))))
```

and the sheet's own file beside the root, `(kicad_sch (version 20250114) (generator "eeschema") (uuid
"<new uuid>") (paper "A4") (lib_symbols) (embedded_fonts no))`. Then fill each sheet in an edit of the
root: `sheet = next(item for item in s.get_hierarchy() if item.name == "Power")`, and
`s.for_sheet(sheet)` places its symbols, wires and its `VIN` hierarchical label. A sheet used twice is two
blocks naming one file, each of its symbols then holding a reference for each block's path in its
`instances`. A symbol written as text whose library symbol `extends` another is embedded in `lib_symbols`
flattened, as KiCad saves it: the parent's units and pins under the child's name, with every property of
the parent's that the child does not set (a lost one is ERC's `lib_symbol_mismatch`).

## Into the board, and back

The board takes its parts and nets from the schematic's netlist. There is no "Update PCB": a schematic
edit reaches the board through the netlist exported from the saved schematic (`cad kicad_sch export
board.kicad_sch --to netlist -o tmp` writes `tmp/board.net`) and imported in a board's edit. One script does
both, the schematic's block first:

```python
from cad import kicad_pcb, kicad_sch

with kicad_sch.edit("board.kicad_sch") as s:
    ...                                       # saved at this block's end
(netlist,) = kicad_sch.export("board.kicad_sch", "netlist", "tmp").written
with kicad_pcb.edit("board.kicad_pcb") as b:
    print(b.import_netlist(str(netlist)).report)  # dry_run=True first, to see what it would change
```

`report` is a property, KiCad's account of what the import changed. The two edits of one project can also
share one `with` line and one KiCad (`with kicad_sch.edit(...) as s, kicad_pcb.edit(...) as b:`), each saved
at its own end, the board's first: the netlist is read from the saved schematic, so import it after the
schematic's block all the same.

An import replaces a footprint only when the netlist names another library footprint for it, so a project
footprint changed in its library keeps its old copy on the board, `update_footprints=True` or not. To
refresh such parts in place (their place, side and nets kept), list the library a second time in the
project's `fp-lib-table` under another name (`lib_refresh`, the same `uri`), import a copy of the netlist
that names them through it (`(footprint "lib_refresh:NAME")`), then import the schematic's own netlist again.

After a layout or a schematic edit, hold the board to the schematic pin by pin:

```python
from cad import kicad_pcb, kicad_sch

sch, board = kicad_sch.read("board.kicad_sch"), kicad_pcb.read("board.kicad_pcb")
want = {(pin.ref, pin.number): pin.net for pin in sch.pins if not pin.ref.startswith("#")}
have = {(pad.part, pad.number): pad.net for pad in board.pads}
for key in sorted(set(want) | set(have)):
    if want.get(key) != have.get(key):
        print(key, "schematic:", want.get(key), "board:", have.get(key))
```

A part on one and not the other, or a pin on another net, is a change the netlist import has not
carried, or one made on the board alone.

The schematic's other exports: `--to pdf` (every sheet), `--to svg` (a file per sheet), `--to bom` (a CSV, a
line per value, footprint and `MPN`: `Refs` in ranges such as `C103-C106`, `Value`, `Footprint`, `MPN`,
`Qty`, `DNP`). An assembler's BOM is the board's ([manufacturing](manufacturing.md#exports)).
