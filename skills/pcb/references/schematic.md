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

Edit the `.kicad_sch` as text (the schematic's S-expressions: KiCad's
[file format](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/)), or in KiCad, and keep
every `uuid`: references and the board's links to its symbols are made of them. A placed symbol's
drawing lives in the file's `lib_symbols`; a new symbol needs its entry there. Its reference is the
`instances` entry for its sheet's path. After each edit, read it back, draw it and check it.

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

writes `tmp/board.net`, the netlist [layout](layout.md)'s first step imports in a board script
(`b.import_netlist(...)`). After a layout or a schematic edit, hold the board to the schematic pin by
pin:

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
