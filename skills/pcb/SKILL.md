---
name: pcb
description: Design printed circuit boards in Python and get a checked KiCad 10 project. Use for PCBs, circuit boards, schematics, KiCad files (.kicad_pcb, .kicad_sch, .kicad_pro, .kicad_dru), parts and footprints, placement, routing by hand or autorouting with Freerouting, ground pours, design rule and electrical rule checks (DRC, ERC), Gerbers, BOMs, pick-and-place files, JLCPCB orders, a board's 3D STEP/GLB for an enclosure, and SPICE simulation of a board's circuits. Open and visually review existing KiCad boards and schematics in CAD Viewer.
license: MIT
---

# PCB design

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Setup

This skill's commands are thin entrypoints over the `cadgen` distribution. Install it once:

```bash
python -m pip install -r requirements.txt
```

Boards are checked and drawn by KiCad 10 itself, through its command line, `kicad-cli`.
Install KiCad 10 (it brings `kicad-cli`, its symbol and footprint libraries, its 3D models
and the ngspice simulator):

- macOS: `brew install --cask kicad` (or the disk image from https://www.kicad.org/download/macos/).
- Windows: the installer from https://www.kicad.org/download/windows/.
- Ubuntu: `sudo add-apt-repository ppa:kicad/kicad-10.0-releases && sudo apt install kicad`.

cadgen finds `kicad-cli` on `PATH` or in the usual install folders; `CADGEN_KICAD_CLI`
names one explicitly. Snapshots also need `python -m playwright install chromium`.
Autorouting runs Freerouting, a separate program ([routing](references/routing.md) says how to install it).

## The contract

**A `@pcb` function takes no parameters and returns a `pcb.Board`. cadgen writes the KiCad
project and KiCad checks it.** The script is the source; the KiCad files are outputs, as a
STEP is for a part: never edit them by hand, edit the script and run it.

```python
from cadgen import build123d as bd
from cadgen import pcb

WIDTH, HEIGHT = 40.0, 30.0


@pcb
def blinky():
    with bd.BuildSketch() as outline:
        bd.RectangleRounded(WIDTH, HEIGHT, 2)
    board = pcb.Board(outline=outline.sketch)        # 2 layers, JLCPCB's limits by default

    vbus = board.net("VBUS", power_flag=True)          # powered from the connector
    gnd = board.net("GND", power_flag=True)
    led = board.net()                                  # unnamed: KiCad-style name from its first pin

    j1 = board.part("Connector_Generic:Conn_01x02",
                    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
    r1 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="1k",
                    properties={"LCSC": "C21190"})
    d1 = board.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value="red")

    board.connect(vbus, j1[1], r1[1])
    board.connect(led, r1[2], d1["A"])
    board.connect(gnd, j1[2], d1["K"])

    board.place(j1, at=(-15, 0))
    board.place(r1, at=(0, 5), rotation=90)
    board.place(d1, at=(8, -5))

    board.track(vbus, [j1[1], (0, 0), r1[1]])          # a point may be a pin: the track ends on its pad
    board.track(led, [r1[2], (0, 8), (12, 8), (12, -5), d1["A"]])
    board.track(gnd, [d1["K"], (7.2125, -8)])
    board.via(gnd, at=(7.2125, -8))
    board.zone(gnd, layers=["B.Cu"])                    # ground pour on the bottom
    return board


if __name__ == "__main__":
    blinky()
```

```bash
python blinky.py      # built blinky.kicad_pcb
```

The run writes `blinky.kicad_pro`, `blinky.kicad_sch`, `blinky.kicad_pcb` and
`blinky.kicad_dru` (the board's custom design rules, empty without `board.rule`) beside the
script (`@pcb(out="../PCB/blinky.kicad_pcb")` moves them; the four always share a stem and a
folder). The schematic is generated from the netlist: every connected pin gets a short
stub and a global label with its net's name, unused pins marked no-connect get KiCad's X,
and nets with `power_flag=True` get a `PWR_FLAG`. It is correct by construction; you never
draw it.

Before a byte is written, KiCad fills the zones and runs its ERC (on the schematic) and its
DRC with the schematic-to-board parity check (on the board), on a staged copy:

- **Any error fails the build and writes nothing** — clearance, a short, a floating pin
  (`pin_not_connected`), a power input nothing drives (`power_pin_not_driven`: mark the net
  `power_flag=True` when a connector or battery feeds it), a courtyard overlap. Each finding
  names the items and their positions in the script's coordinates.
- **Unrouted connections make a draft**: the board is written and the run says so,
  `built blinky.kicad_pcb (draft: 3 unrouted connections)`, listing each missing connection.
  The viewer draws a draft's ratsnest. A draft is a stage, not a result: route it.
- Warnings (silkscreen over copper, a dangling track end) are printed and do not block.

An unchanged script is a no-op (`current blinky.kicad_pcb`); `--force` rebuilds;
`cadgen store why blinky.py` says why a board is stale. The library files a board read are
its inputs: a KiCad update that changes a part's footprint makes the board stale.

## The board API

The words are KiCad's: libraries by `Library:Name`, layers `F.Cu`/`B.Cu`/`In1.Cu`/
`Edge.Cuts`, rule names as KiCad's Board Setup has them. Shapes are build123d 2D geometry,
as `@dxf` takes. Lengths are millimetres; **y is up** and the outline's coordinates are the
board's: (0, 0) is wherever you draw it, and KiCad's drill/place origin is put there.
Rotation is degrees counter-clockwise seen from the top. The full reference is
[the board API](references/board-api.md); the core:

| Call | What it does |
| --- | --- |
| `pcb.Board(outline=, layers=2, thickness=1.6, fab=pcb.JLCPCB, rules=None, libraries=[folder], title=)` | A board: outline (holes in the face are cutouts), copper layer count, the fab whose limits it is checked against (`pcb.PCBWAY`, `pcb.OSHPARK`, `pcb.AISLER`, ...) or your own `rules=`, project-local libraries searched before KiCad's |
| `board.part(symbol, footprint=, value=, ref=, properties={}, dnp=False)` | A part: KiCad symbol and footprint (the symbol's own default footprint when it has one); `ref` defaults to the next free `R1`, `U3`...; `properties` are BOM fields (`LCSC`, `MPN`, `Manufacturer`) |
| `part[1]`, `part["VIN"]` | A pin by number, or by name when unique (an ambiguous name is refused, listing the numbers) |
| `board.net(name=None, netclass=, power_flag=False)` | A net; one name is one net |
| `board.connect(net, *pins)` / `board.no_connect(*pins)` / `part.unconnected()` | The netlist. Every pin must be connected or marked no-connect, or ERC fails the build |
| `board.place(part, at=(x, y), rotation=0, side="top")` | Placement, a separate step so subcircuits stay reusable |
| `board.track(net, points, width=, layer="F.Cu")`, `board.arc(net, start=, mid=, end=)`, `board.via(net, at=)` | Copper. Widths and via sizes default to the net's class |
| `board.zone(net, layers=["B.Cu"], shape=None, clearance=, priority=0, pads="thermal")` | A pour, KiCad-filled; the whole board when `shape` is omitted |
| `board.keepout(shape=, tracks=True, vias=True, pours=True, pads=False, footprints=False)` | An area copper may not enter |
| `board.netclass(name, track_width=, clearance=, via_diameter=, via_drill=)` | A net class; nets join it with `board.net(name, netclass=...)` |
| `board.hole(at=, diameter=)`, `board.text(text, at=, layer="F.SilkS", size=1.0)` | Unplated holes, board text |
| `board.rule('''(rule "J1 pads" (constraint hole_clearance (min 0.15mm)) (condition "A.memberOfFootprint('J1')"))''')` | A KiCad custom design rule, for what the board-wide rules cannot scope; one KiCad cannot read fails the build |
| `board.raw("(gr_text ...)")` | Any board item KiCad's format has, in KiCad's coordinates (y down, page origin) |
| `board.autoroute(skip=(), layers=None, passes=100)` | Route everything not drawn, with Freerouting, when the board is built; the same board always routes the same way ([routing](references/routing.md)) |
| `pin.position`, `part.at`, `net.pins` | Where things are: a pad's centre in board coordinates, for routing helpers |

Find real names before you write them; never guess a footprint:

```python
from cadgen import pcb

pcb.find_symbols("ldo 3.3")        # [("Regulator_Linear:AMS1117-3.3", "1A Low Dropout regulator..."), ...]
pcb.find_footprints("sot-223")     # ["Package_TO_SOT_SMD:SOT-223", ...]
```

A wrong name fails with the closest real ones (`did you mean Resistor_SMD, ...`). A symbol's
pins must have pads on its footprint (checked when the part is made). For a part KiCad's
libraries lack, keep a project library (`parts.kicad_sym`, `parts.pretty/`) and pass its
folder as `libraries=`; parts on step.parts or LCSC usually come with KiCad files.

Write subcircuits as plain functions of a circuit, so the board and a simulation testbench
share them:

```python
def led_driver(c, supply, gnd, colour="red"):
    r = c.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="1k")
    d = c.part("Device:LED", footprint="LED_SMD:LED_0603_1608Metric", value=colour)
    node = c.net()
    c.connect(supply, r[1]); c.connect(node, r[2], d["A"]); c.connect(gnd, d["K"])
    return r, d
```

## Workflow

1. Turn the request into a brief: what the board does, its connectors and power, the
   outline and mounting holes (from the enclosure when there is one), layer count, fab.
2. Choose parts with `find_symbols`/`find_footprints`; prefer parts the fab stocks (LCSC
   numbers in `properties` for JLCPCB assembly).
3. Write the netlist, then place: connectors at the edges, decoupling capacitors at their
   pins, the parts of one subcircuit together, nothing in a courtyard of another
   ([layout](references/layout.md)). Run it; ERC findings come back before any routing.
4. Route: power and sensitive nets by hand, ground as a pour, the rest by hand or with
   `board.autoroute()`. Run until the board is no longer a draft and has no DRC errors.
5. Check behaviour where it matters with a simulation ([simulation](references/simulation.md)).
6. Add the outputs the job needs (below), look at the board and its snapshot, hand off.

## Outputs beyond the KiCad project

The manufacturing files are arguments of `@pcb` (`True` writes the file beside the board, a
path moves it); the 3D exports are the part decorators, stacked either side of `@pcb`. Each
is written on every build from the board KiCad just checked, and each has a door for any
saved board:

| Declaration | Writes | Door |
| --- | --- | --- |
| `@pcb(gerber=True)` | `blinky.gerbers.zip`: every copper, mask, paste and silkscreen layer, the outline, Excellon drills: what every fab makes boards from | `cadgen pcb gerber BOARD [OUT]` |
| `@pcb(bom=True)` | `blinky.bom.csv`: the parts to buy and place, one row per distinct part | `cadgen pcb bom BOARD [OUT]` |
| `@pcb(pos=True)` | `blinky.pos.csv`: pick-and-place, each part's position (mm from the script's origin), rotation and side | `cadgen pcb pos BOARD [OUT]` |
| `@step`, `@glb`, `@stl`, `@threemf` | the populated board in 3D (KiCad's own model of it) | `cadgen step build`/`glb build` of the STEP |

`gerber=` and `pos=` refuse a draft: a board that declares either fails its build, naming
what is left to route. `bom=` is allowed early, for pricing and ordering parts. All are
byte-for-byte the same for the same board. See [manufacturing](references/manufacturing.md)
for ordering.

**A board with a 3D export is a part.** Its geometry is the populated board, in the script's
own coordinates (the outline as drawn, z = 0 on the board's bottom face), each part labelled
by its reference. An enclosure composes it like any child, so the board's outline, holes
and connectors line up with the case they were drawn against:

```python
@step
@pcb
def controller():
    ...                                 # the board, as above

@step
def case():
    ...
    return bd.Compound(children=[shell, bd.Pos(0, 0, FLOOR) * controller()])
```

Called inside a `@harness`, any board returns its `pcb.Board` (the netlist and placement);
inside any other model's body, a board WITHOUT a 3D export does too, which is how a test
reads it. The enclosure itself is
`$cad`'s work; the cables between boards are `$harness`'s, checked against these netlists.

## Checking an existing project

```bash
cadgen pcb validate path/to/board.kicad_pcb            # ERC + DRC with parity, never writes into the project
cadgen pcb validate path/to/board.kicad_pcb --json     # {"ok", "path", "issues": [...], "summary"}
cadgen pcb snapshot path/to/board.kicad_pcb tmp/board.png
cadgen pcb snapshot path/to/board.kicad_sch tmp/schematic.png
```

`validate` takes any KiCad 10 project, one drawn in KiCad included; positions are
millimetres from the board's drill/place origin, y up. A snapshot is the CAD Viewer's
picture: KiCad's own plot of the board (all layers, back to front, ratsnest on a draft) or
of every schematic sheet.

## Show the model

Show the user each file you create or change, and any they ask to see. Snapshots and
validation don't replace this.

- If your tools include `cad_show` (your host may prefix it), use it, and follow its
  description for when to call it again. `cad_view` reads what the user selected;
  `cad_screenshot` shows you what they see. Neither is a review of your own work.
- Otherwise run the CAD Viewer from the models directory (usually `models/`, not an
  artifact's output folder):

  ```bash
  cd /absolute/path/to/model-workspace && cadgen viewer --host 127.0.0.1 --json --detach
  ```

  `--detach` returns once the viewer answers requests and leaves it running in the
  background: always pass it, since a foreground viewer never exits (and piping its
  output through `tail` can hide the URL for good). It starts or reuses the viewer.
  Read `url` from its one JSON line (never guess the port); for each file under that
  directory return `url?file=<URL-encoded relative path>`, or `url` alone to review the
  directory. If it fails to launch, say so.

The viewer draws `.kicad_pcb` and `.kicad_sch` files read-only, as KiCad plots them: drag to
pan, wheel or pinch to zoom, double-click to fit. Show the board and its schematic; a board
with a 3D export also has its `.step`/`.glb` to show.

## Handoff

Report the files written, the build's last line (built or draft, and what is unrouted), the
checks that ran (KiCad's ERC and DRC run on every build; simulations you ran), the parts
without an LCSC or MPN field, and assumptions (ratings, footprints chosen, rules). Show the
board and schematic ([Show the model](#show-the-model)).

## References

- [The board API](references/board-api.md): every call, argument and error.
- [Layout](references/layout.md): placement and routing rules that make boards that work.
- [Routing](references/routing.md): hand routing and Freerouting.
- [Simulation](references/simulation.md): SPICE testbenches over the board's own subcircuits.
- [Manufacturing](references/manufacturing.md): Gerbers, BOM, placement and ordering.
