# Inspection: what the user points at

The CAD Viewer shows a `.kicad_pcb` as KiCad plots it, and lets a person point at what is on
it: a part, a pad, a net, a stretch of copper, a spot on the board. What they point at reaches
you as a **board reference** in their prompt, and resolves back to the board and to the line of
your script that made it. The viewer never edits; you do, in the script.

## Board references

A reference is a token, `<file>#<selector>`, exactly as a STEP reference is: the file is the
file's absolute path (JSON-quoted when it holds a space, `#`, a quote or a backslash), and
several selectors share one `#`, comma-joined: `/work/PCB/servo.kicad_pcb#U3,C14.2`.
`resolve()` reads the file as a path (`~` expanded, links followed, a relative one read from the
working directory) and refuses a reference that names another document.

| Selector | Names |
| --- | --- |
| `#U3`, `#J2-J4`, `#_U1` | a part, by its reference designator (a letter or `_`, then letters, digits, `_`, `+` or `-`) |
| `#U3.9`, `#J4.A4`, `#U2.EP` | a pad of a part, numbered as KiCad numbers it |
| `#net:VIN`, `#net:TX/RX`, `#net:"/Power Stage/VLOC"` | a net, by the name KiCad shows; quoted when it holds whitespace (a hierarchical sheet's name puts one in its nets), a quote, a comma, `@` or `#` |
| `#net:VIN@x57.6y21.6` | that net's copper (a track, via, pour or pad) at a point |
| `#@x3.5y3.5` | a point on the board |

Points are millimetres in the script's frame: y up, from the board's drill/place origin, which
is where cadgen puts the script's own origin. They are the numbers `board.place`,
`pin.position` and the build's DRC findings use, written with at most three decimals
(`x-3y0.5`).

## Resolving one

```python
from cadgen import pcb

board = pcb.read_board("PCB/servo.kicad_pcb")      # any KiCad 10 board; runs nothing
part = board.resolve("PCB/servo.kicad_pcb#U3")      # a Part
part.script                                         # "servo.py:183": the board.part(...) line
part.at, part.rotation, part.side, part.value, part.footprint, part.fields
pad = board.resolve("#J4.A4")                       # a Pad: .net, .at, .name, .type, .side, .polygon
net = board.resolve("#net:VIN")                     # a Net: .netclass, .pads, .tracks, .vias, .zones
copper = board.resolve("#net:VIN@x57.6y21.6")       # Copper: .items, that net's copper there
point = board.resolve("#@x3.5y3.5")                 # a Point: .on_board, .parts, .pads, .copper, .holes
board.resolve_all("PCB/servo.kicad_pcb#U3,C14.2")   # a token of several, each resolved
board.at(12, 8)                                     # what is at a point
```

A file before the `#` must name the board you read; a reference to another file is refused,
as are a part, pad or net the board does not have (the message lists what it does have) and
copper nowhere near the point (it names the nearest). A number several pads share (a USB
connector's four `SH` shield pads, a regulator's tab and pin both `2`) names them all: it
resolves to the first, whose repr says how many share it, and `part.pads_numbered("SH")` lists
every one; the person's point, when they gave one, says which. A reference names the board as it was
when the person picked: if you have rebuilt since, resolve against the new board and check it
still names what they meant.

## The script line

A board cadgen builds remembers, for every `board.part(...)` and `board.hole(...)`, the first
line outside cadgen that called it, and writes it into the KiCad files as a hidden field,
`Script` = `<path>:<line>`, on the part's symbol and its footprint. The path is relative to
the model script's folder (`lib/power.py:41` for a part a helper in `lib/` made). `part.script`
reads it back. A board drawn in KiCad has none: find the part in its project instead.

## The loop

1. The person picks in the viewer (Select, then copy) and writes what they want: "move
   `PCB/servo.kicad_pcb#C14` next to `#U3.9`", "this VIN track `#net:VIN@x57.6y21.6` is too
   thin".
2. Resolve each reference with `pcb.read_board(...)` (a schematic's with
   `pcb.read_schematic(...)`).
3. Edit the line `part.script` names, or the copper call near the resolved points.
4. Run the script. The viewer shows the new board; KiCad's checks run on every build, and
   the viewer lists the board's DRC findings, each with references to the pads and parts in it.

## Schematics

A `.kicad_sch` speaks the same selectors for its symbols, pins and nets: `#U3` a part,
`#U3.9` pin 9 of U3, `#net:VIN` a net. Copper and points are a board's alone; a schematic
refuses them.

```python
schematic = pcb.read_schematic("PCB/servo.kicad_sch")   # the root sheet; runs KiCad's netlist once
part = schematic.resolve("PCB/servo.kicad_sch#U3")       # a Part: .script, .value, .lib, .footprint, .fields
part.units                                               # each unit drawn: .unit, .sheet, .at, .rotation, .mirror
pin = schematic.resolve("#U3.9")                         # a Pin: .net, .name, .type, .unit, .sheet
net = schematic.resolve("#net:/Power/EN")                # a Net: .netclass, .nodes ("U3.9", ...), .pins, .parts, .labels
schematic.sheets[pin.sheet].path                         # "/Power/": the sheet it is drawn on
```

Net names are KiCad's own. A cadgen schematic labels every net with the script's name
(`VIN`, `TX/RX`); in one drawn in KiCad, a global label or power symbol names its net as
written, a local or hierarchical label with its sheet's path (`/Power/EN`), and a net no
label names is called after a pin on it (`Net-(D1-A)`); a pin left open is alone on a net of
its own, `unconnected-(…)`. A sheet used twice in a hierarchy is two sheets, each with its
own references. A part's `script` is the same line its footprint names on the board.
Positions are the sheet's millimetres (y down, from the page's corner), for finding things
on the sheet; the script never uses them.
