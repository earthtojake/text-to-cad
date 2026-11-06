# Read and check the schematic

A board's schematic (`.kicad_sch`) says what connects to what; the board carries it out. Read it,
look at it and check it before laying out, and hold the board to it after.

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

Run it with `cad run inspect_schematic.py`. The reader is the standard library alone (no KiCad):
sheets, symbols (reference, value, footprint, library id, fields, unit, the sheet it is on, its pins
with number, name and electrical type), wires and buses, junctions, labels (local, global,
hierarchical, and each power symbol's net), no-connects, and the nets they make, named as KiCad
names them -- the names `kicad-cli sch export netlist` gives, and the board's. A local net carries its
sheet's path (`/Power/VBUS`); `sch.net("VBUS")` finds it by its bare name when one sheet alone has
it. Positions are millimetres on each sheet's page, y down, as the file holds them. Each call reads
the current files.

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

Each picture is one sheet, drawn from the file's own symbols, wires and labels in KiCad's
colours, framed on what the sheet draws (`--border` draws the page's edge and frames the page).
Look after every edit. The text is a stroke font of its own, not KiCad's: same places, other glyphs.
A number is never read off a picture: read it from `kicad_sch.read`.

## Check it

```bash
cad kicad_sch erc board.kicad_sch --json
```

KiCad's electrical rules check (ERC) on the whole hierarchy, every finding with its sheet and where
it is on that sheet's page. Errors fail it; warnings are said. Fix the cause, never the rule:

- `pin_not_connected`: wire the pin, or place a no-connect on it when it is meant to float.
- `power_pin_not_driven`: a power net with no source on it (a regulator's output, a connector's
  supply pin). Where the supply comes from off the board, put a `PWR_FLAG` on the net.
- `label_dangling`, `wire_dangling`, `unconnected_wire_endpoint`: a label or wire that touches nothing;
  a wire's end must land exactly on a pin's end, a junction or another wire's end.
- `bus_to_bus_conflict`: two buses joined graphically whose names share no member. KiCad still joins
  vector members by index (`D3` meets `Q3`), so rename one to say what it is.
- `different_unit_net`, `multiple_net_names`: two names on one net; keep one.

`libraries_not_checked` is a note, not a finding: the check runs KiCad with private settings, so it
cannot see your global symbol and footprint library tables (a project's own `sym-lib-table` and
`fp-lib-table` it reads).

## Edit it

Edit a schematic in a `with kicad_sch.edit(...) as s:` block: it hands the block the open schematic
through KiCad's IPC API (KiPy's `Schematic`, kicode's: `kicode.schematic.Schematic`), the project's symbol
libraries already loaded, as `kicad_pcb.edit` does a board ([SKILL.md](../SKILL.md#native-files-are-the-source)):
saved at the block's end when it changed it, left byte for byte when it changed nothing, nothing saved
when it raises; a schematic not there yet is made, with its project. State the schematic you want, so a
second run changes nothing: place a symbol only when its reference is not there yet. Run the script with
`cad run schematic.py`.

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

Then read it back (`kicad_sch.read`: the pins and their nets), draw it and check it with ERC.

**The safe calls.**

- Place a symbol with `s.place_symbol_from_library("<library>:<symbol>", position, reference="R1")`
  (`orientation=`, `unit=` for the rest): KiCad copies the library's symbol, its pins and drawing, into the
  file and keeps its library link. Never make a `SchematicSymbolInstance` from a library id alone and
  create it: it comes out hollow, with no pins or drawing.
- Change an item only as it was read back: `s.get_symbols()`, `s.get_lines()`, `s.get_labels()` (and
  `s.for_sheet(sheet)` for a sheet of the hierarchy, `s.get_hierarchy()` for its sheets), changed and sent
  with `s.update_items(...)`. Make wires, labels, junctions and no-connects with `s.create_items(...)`, a
  group of edits in one commit (`s.begin_commit()`, `s.push_commit(commit)`). `s.get_netlist()` says what
  connects while the script runs.
- A wire's ends must land on a pin's end (`pin_at` above; turn the pin's offset with the symbol's
  orientation for a turned or mirrored one), a junction or another wire's end.

**Libraries.** A symbol is placed from the project's own symbol libraries: the rows of its `sym-lib-table`,
beside the `.kicad_pro` (`${KIPRJMOD}` is that folder). The script runs KiCad with private settings, so no
global library table, and none of KiCad's stock libraries, is there: copy each library a design needs (its
`.kicad_sym`) into the project and list it:

```
(sym_lib_table
  (version 7)
  (lib (name "parts")(type "KiCad")(uri "${KIPRJMOD}/parts.kicad_sym")(options "")(descr ""))
)
```

A placement from a library the table does not list fails in one line naming it and the row to add; a
listed library that did not load is said when the block starts. (`KICAD10_SYMBOL_DIR`, set to a copy of
KiCad's libraries, is what a row of `${KICAD10_SYMBOL_DIR}/Device.kicad_sym` reads.)

**Fragile on this nightly** (KiCad 10.99 over IPC; check the saved file after each):

- A sheet symbol made over IPC (`create_items(SheetSymbol())`) cannot be saved, whether its file is there
  or not: KiCad looks for the new sheet's file inside a folder named after the root's file, and its save
  fails ("failed to save schematic"). The edit then raises with KiCad's words, and every file is as it
  was. Write a hierarchy as text, as below, then fill its sheets over IPC.
- Updating a placed symbol (`update_items`) can detach it from its library: read the file back and check
  its `lib_id` after moving or changing one.
- A line ending (an arrow) set over IPC is lost on save.
- A bus entry gets a new uuid on save: never keep a `#bus_entry:<uuid>` across one.

Editing the `.kicad_sch` as text (KiCad's
[file format](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/)) is the fallback, for what the
API cannot do: keep every `uuid` (references and the board's links to its symbols are made of them), give
a new symbol its `lib_symbols` entry and its reference in the `instances` entry for its sheet's path.
After each edit, read it back, draw it and check it.

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
`s.for_sheet(sheet)` places its symbols, wires and its `VIN` hierarchical label, and saves. A sheet used
twice is two blocks naming one file, each of its symbols then holding a reference for each block's path
in its `instances`. A symbol written as text whose library symbol `extends` another is embedded in
`lib_symbols` flattened, as KiCad saves it: the parent's units and pins under the child's name, with
every property of the parent's that the child does not set (a lost one is ERC's `lib_symbol_mismatch`).

## Draw it cleanly

The netlist proves the connections; the picture proves a person can read them. Check both after each
edit: `kicad_sch.read` or `cad kicad_sch inspect` for what connects, and a `cad kicad_sch snapshot` of
each sheet changed for how it reads, iterating on the picture until nothing overlaps or runs long.

- Join buses and long runs with labels; wire local passives (pull-ups, decoupling, a filter) to their
  pins with real wires.
- Draw supplies as power symbols, ground pointing down and positive supplies up, with a `PWR_FLAG`
  where the supply enters (its connector or regulator), not anywhere on the net.
- Group an IC's decoupling capacitors on one supply symbol and one ground symbol, not one each.
- Box each subcircuit (the power input, an MCU and its passives) in a rectangle with a short title.
- Give every value its unit: `10k`, `100nF`, `4.7uH`.
- Name a differential pair's two nets with matching suffixes, `+`/`-` or `P`/`N` (`USB_D+`,
  `USB_D-`): that is how KiCad finds the pair.
- After redrawing a symbol, prove every pin kept its number, name and type: compare
  `{(pin.ref, pin.number): (pin.name, pin.type) for pin in sch.pins}` before and after.
- Lay out a new symbol's pins as KiCad's library conventions do
  ([KLC S4.2](https://klc.kicad.org/symbol/s4/s4.2/)): inputs left, outputs right, power at the top,
  ground at the bottom; a converter's power input left and its output right.

Report the liberties taken: a symbol redrawn, a sheet split or merged, a choice the documents left open.

## Into the board, and back

The board takes its parts and nets from the schematic's netlist:

```bash
cad kicad_sch export board.kicad_sch --to netlist -o tmp
```

writes `tmp/board.net`, the netlist [layout](layout.md)'s first step imports in a board's edit
(`b.import_netlist(...)`). There is no "Update PCB": a schematic edit reaches the board through that
netlist, exported from the saved schematic. One script does both, the schematic's block first:

```python
from cad import kicad_pcb, kicad_sch

with kicad_sch.edit("board.kicad_sch") as s:
    ...                                       # saved at this block's end
(netlist,) = kicad_sch.export("board.kicad_sch", "netlist", "tmp").written
with kicad_pcb.edit("board.kicad_pcb") as b:
    print(b.import_netlist(str(netlist)).report)  # dry_run=True first, to see what it would change
```

`report` is a property, KiCad's account of what the import changed. An import replaces a footprint only
when the netlist names another library footprint for it, so a project footprint changed in its library
keeps its old copy on the board, `update_footprints=True` or not. To refresh such parts in place (their
place, side and nets kept), list the library a second time in the project's `fp-lib-table` under another
name (`lib_refresh`, the same `uri`), import a copy of the netlist that names them through it
(`(footprint "lib_refresh:NAME")`), then import the schematic's own netlist again.

A board's and a schematic's edits of one project can also share one block, and one KiCad:
`with kicad_sch.edit("board.kicad_sch") as s, kicad_pcb.edit("board.kicad_pcb") as b:`, each saved at its
own end (the board's first). The netlist is read from the saved schematic, so import it after the
schematic's block, as above.

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
carried, or one made on the board alone. The other exports: `--to pdf` (every sheet), `--to svg` (a
file per sheet), `--to bom` (a CSV a line per value, footprint and `MPN`, for
[review-assembly](review-assembly.md)).
