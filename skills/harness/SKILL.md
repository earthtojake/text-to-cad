---
name: harness
description: Design wiring harnesses in Python and get a WireViz document checked against the boards it plugs into. Use for wiring harnesses, cables and cable assemblies between @pcb boards, motors, sensors and batteries, connector pinouts, housings and crimp terminals, wire colours, gauges and lengths, `.harness.yml` (WireViz YAML) files, harness diagrams and a harness's bill of materials. Open and visually review existing harness documents in CAD Viewer.
license: MIT
---

# Wiring harnesses

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/), so this skill's commands share
one installation, and its warm build daemon, with the CAD app's server:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.17 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.17 python`

The first run downloads that installation and the first snapshot its headless
browser; later runs reuse both.

`cadgen doctor <skill-dir>` reports the installation in use and checks that it is
the one this skill pins; use it for installation errors.

cadgen writes and checks a harness on its own. Drawing it (the CAD Viewer, `cadgen harness
snapshot`) and listing its parts (`bom=True`) are done by WireViz, a separate program (GPL-3.0) that cadgen runs and never
imports, which draws with Graphviz. Install both, WireViz in its own tool environment:

- macOS: `brew install graphviz`, then `uv tool install wireviz` (or `pipx install wireviz`).
- Windows: Graphviz from https://graphviz.org/download/ (let its installer add it to PATH),
  then `uv tool install wireviz`.
- Ubuntu: `sudo apt install graphviz`, then `uv tool install wireviz`.

cadgen finds `wireviz` on `PATH` or in `~/.local/bin` (where uv and pipx put it);
`CADGEN_WIREVIZ` names one explicitly. It finds `dot` on `PATH` or where Graphviz installs.
A harness that reads boards runs their `@pcb` functions, which look parts up in KiCad's
libraries: install KiCad 10 as `$pcb` says.

## The contract

**A `@harness` function takes no parameters and returns a `harness.Harness`. The build checks
it and writes one WireViz document, `<name>.harness.yml`.** The script is the source; the
document is the output: never edit it by hand. The words are WireViz's (connectors, pins,
pinlabels, cables, wirecount, colors, gauge, length, shield, connections), so the document is
the WireViz YAML a person would write, and opens in WireViz as it is.

A connector comes from a board or is free:

- `h.connector(board, "J1", type=...)`: the board's part `J1`. Its pins are the part's, each
  labelled with the **net** it carries on that board; `type` names the **housing** that mates
  with the board's header (the board has the header, the harness has the housing), and the
  designator defaults to the reference (`name=` sets one; two boards' `J1`s need one).
- `h.connector("M1", pinlabels=["A+", "A-", "B+", "B-"], type=...)`: a motor's lead, a
  battery, a sensor's pigtail: pins by `pins=`, `pinlabels=` or `pincount=`.

A board is read by calling its `@pcb` model inside the harness: it returns its `pcb.Board`
there, 3D export or not (its netlist; the copper does not matter, a draft is fine).

### A worked example: two boards and a cable between them

The boards are `$pcb` models. Their headers are pinned out differently, which is what a
harness is for:

```python
# controller.py
from cadgen import build123d as bd
from cadgen import pcb


@pcb
def controller():
    with bd.BuildSketch() as outline:
        bd.RectangleRounded(40, 30, 2)
    board = pcb.Board(outline=outline.sketch, title="controller")
    vbus, gnd = board.net("VBUS", power_flag=True), board.net("GND", power_flag=True)
    sda, scl = board.net("SDA"), board.net("SCL")
    j1 = board.part("Connector_Generic:Conn_01x04", footprint="Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical")
    r1 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="4k7")
    r2 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="4k7")
    c1 = board.part("Device:C", footprint="Capacitor_SMD:C_0603_1608Metric", value="100n")
    board.connect(vbus, j1[1], r1[1], r2[1], c1[1])
    board.connect(gnd, j1[2], c1[2])
    board.connect(sda, j1[3], r1[2])
    board.connect(scl, j1[4], r2[2])
    board.place(j1, at=(-15, 0))
    board.place(r1, at=(0, 6), rotation=90)
    board.place(r2, at=(5, 6), rotation=90)
    board.place(c1, at=(5, -6))
    return board


if __name__ == "__main__":
    controller()
```

```python
# driver.py: the same nets on a JST PH header pinned GND, VBUS, SCL, SDA
from cadgen import build123d as bd
from cadgen import pcb


@pcb
def driver():
    with bd.BuildSketch() as outline:
        bd.RectangleRounded(30, 25, 2)
    board = pcb.Board(outline=outline.sketch, title="driver")
    vbus, gnd = board.net("VBUS", power_flag=True), board.net("GND", power_flag=True)
    sda, scl = board.net("SDA"), board.net("SCL")
    j1 = board.part("Connector_Generic:Conn_01x04", footprint="Connector_JST:JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical")
    r1 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="10k")
    r2 = board.part("Device:R", footprint="Resistor_SMD:R_0603_1608Metric", value="10k")
    c1 = board.part("Device:C", footprint="Capacitor_SMD:C_0603_1608Metric", value="1u")
    board.connect(gnd, j1[1], c1[2])
    board.connect(vbus, j1[2], c1[1], r1[1], r2[1])
    board.connect(scl, j1[3], r2[2])
    board.connect(sda, j1[4], r1[2])
    board.place(j1, at=(-9, 0), rotation=90)
    board.place(r1, at=(4, 5), rotation=90)
    board.place(r2, at=(8, 5), rotation=90)
    board.place(c1, at=(6, -6))
    return board


if __name__ == "__main__":
    driver()
```

```python
# cable.py
from cadgen import harness

from controller import controller
from driver import driver

NETS = ["VBUS", "GND", "SDA", "SCL"]


@harness(bom=True)                             # also write cable.bom.csv
def cable():
    h = harness.Harness(title="Controller to driver, I2C and power")
    a = h.connector(controller(), "J1", name="CTRL_J1", type="Dupont 2.54 mm housing, 1x4", subtype="female",
                    additional_components=[{"type": "Dupont crimp terminal", "qty_multiplier": "populated"}])
    b = h.connector(driver(), "J1", name="DRV_J1", type="JST PH 2.0 mm housing, 4 pin", subtype="female",
                    mpn="PHR-4",
                    additional_components=[{"type": "JST PH crimp terminal", "mpn": "SPH-002T-P0.5S",
                                            "qty_multiplier": "populated"}])
    w = h.cable("W1", colors=["RD", "BK", "YE", "GN"], gauge="24 AWG", length=300)   # length in mm
    h.connect([a[net] for net in NETS], w.wires, [b[net] for net in NETS])        # pins by net name
    return h


if __name__ == "__main__":
    cable()
```

```bash
python cable.py      # built cable.harness.yml (and wrote BOM: cable.bom.csv)
```

Connecting pins by their net names (`a["VBUS"]`) makes the cable follow each board's pinout:
the document crosses the wires (`CTRL_J1` pins 1-4 to `DRV_J1` pins 2, 1, 4, 3). Connect
pin 1 to pin 1 instead (`h.connect(a.pins, w.wires, b.pins)`) and the build fails, writing
nothing:

```text
[python cable.py] FAILED: HarnessError: W1 wire 1 (RD) runs from CTRL_J1 pin 1 (net VBUS on its
board) to DRV_J1 pin 1 (net GND on its board): the two ends carry different nets (DRV_J1 carries
VBUS on pin 2). Wire the pins that carry the same net, or, where the cable joins two different
nets on purpose (TX to RX), say so: h.connect(..., joins=("VBUS", "GND"))
```

An unchanged script is a no-op (`current cable.harness.yml`); `--force` rebuilds;
`cadgen store why cable.py` says why a harness is stale. The boards' scripts and the library
files they read are the harness's inputs: re-pin a board's header and the harness rebuilds.
The document's bytes are a function of the script: the same harness writes the same file.

## The harness API

| Call | What it does |
| --- | --- |
| `harness.Harness(title=None)` | A harness; `title` is the document's title |
| `h.connector(board, "J1", type=, name=, ...)` / `h.connector(part, type=, ...)` | A board's connector: pins and net labels from the board; `type` (the housing) required |
| `h.connector("M1", pins=, pinlabels=, pincount=, type=, ...)` | A free connector, named by its designator |
| connector keywords | `subtype`, `color`, `style="simple"` (one pin: a ferrule, a ring lug), `pincolors`, `hide_disconnected_pins`, `notes`, `pn`, `manufacturer`, `mpn`, `supplier`, `spn`, `additional_components` |
| `x[1]`, `x["VBUS"]`, `x.pins` | A pin by number, or by label when unique (a board pin's label is its net); every pin |
| `h.cable("W1", colors=["RD", "BK"], gauge="24 AWG", length=300)` | A cable: one colour per wire, a gauge (`"22 AWG"`, or mm²: `0.25`), a length in **millimetres** (written in metres, WireViz's unit) |
| cable keywords | `wirecount` (with `color_code="DIN"`, `"IEC"`, `"BW"`, `"TEL"`, `"TELALT"`, `"T568A"`, `"T568B"`), `shield=True` (wire `"s"`), `category="bundle"` (loose wires: the BOM lists each), `type`, `color` (the jacket), `wirelabels`, `notes`, part numbers, `additional_components` |
| `w[1]`, `w["RD"]`, `w["s"]`, `w.wires` | A wire by number, colour or label; the shield; every wire |
| `h.connect(pin, wire, pin)` | One wire's run; `(pin, wire)` or `(wire, pin)` leaves an end free; lists of each make several |
| `h.connect(a["TX"], w[3], b["RX"], joins=("TX", "RX"))` | A wire that joins two different board nets on purpose |

Colours are WireViz's two-letter codes, run together for a striped wire: BK black, WH white,
GY grey, PK pink, RD red, OG orange, YE yellow, OL olive, GN green, TQ turquoise, LB light
blue, BU blue, VT violet, BN brown, BG beige, IV ivory, SL slate, CU copper, SN tin, SR silver,
GD gold (`"WHGN"`: white with a green stripe). `additional_components` are WireViz's: dicts of
`type`, `subtype`, `manufacturer`, `mpn`, `supplier`, `spn`, `pn`, `qty`, `unit`, and
`qty_multiplier` (`"populated"` puts one crimp terminal on every wired pin). Every keyword set
is closed: a misspelt one fails, naming the closest. The full reference, every refusal
included, is [the harness API](references/harness-api.md).

## Checks

Every build checks the harness before a byte is written; a failure names what to change and
writes nothing:

- **Nets.** A wire whose two ends are on boards joins pins that carry the same named net.
  Crossing nets on purpose is `joins=(from_net, to_net)`, checked against both boards. A board
  pin on no net, and a net no board names (KiCad's `Net-(J1-Pad1)`), are refused.
- **Pins and wires.** A pin takes one wire; a wire is connected once (both ends in one call);
  lists in one `connect` have one item per connection.
- **Declarations.** Every connector and cable is connected to something (WireViz would leave it
  out of the drawing and the BOM); every colour, gauge and length is one WireViz reads; a
  cable has a gauge and a length; text has no `<`, `>` or `&` (WireViz draws it as HTML).

## A board with a 3D export

A `@pcb` board that also declares `@step` (or a mesh export) is a part to the enclosure that
calls it, and still a netlist to a harness: called in a `@harness` function it returns its
`pcb.Board`, so one board model serves both. A `@step` part has no netlist, and a harness
that calls one fails at the call.

## Bill of materials

`@harness(bom=True)` writes `<name>.bom.csv` beside the document on every build (a path
instead of `True` moves it): WireViz's list of the harness's parts, grouped, with designators and the part
numbers given: each housing by type and pin count, each additional component (a terminal per
populated pin), each jacketed cable by wire count, gauge and length, and for a bundle each wire
by gauge and colour with its length. It needs WireViz; a build that cannot list the parts
writes neither file. The same list of any saved document, a hand-written one included:

```bash
cadgen harness bom path/to/cable.harness.yml                # cable.bom.csv beside it
cadgen harness bom path/to/cable.harness.yml out/cable.csv
```

## Looking at a document

```bash
cadgen harness snapshot cable.harness.yml tmp/cable.png
cadgen harness snapshot cable.harness.yml tmp/cable.png --appearance dark --width 2400 --height 1200
```

A snapshot is the CAD Viewer's picture as a PNG: WireViz's own diagram of the document (every
connector with its pins and labels, every cable with its wires' colours, the runs between them),
fitted to the image. It takes any WireViz document, a hand-written one included, and is the
quickest check that WireViz reads it: a document WireViz refuses fails with WireViz's reason
(`X2:9 not found`). Look at it after a build, before handing off.

## Show the model

Show the user each file you create or change, and any they ask to see. Snapshots and
validation don't replace this.

- If your tools include `cad_show` (your host may prefix it), use it with the file's
  absolute path, and follow its description for when to call it again. `cad_view` reads
  what the user selected; `cad_screenshot` shows you what they see. Neither is a review
  of your own work.
- Otherwise run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --host 127.0.0.1 --json --detach
  ```

  `--detach` returns once the viewer answers requests and leaves it running in the
  background: always pass it, since a foreground viewer never exits (and piping its
  output through `tail` can hide the URL for good). It starts this machine's one viewer,
  or reuses it. Read `url` from its one JSON line (never guess the port), and for each
  file return `url?file=<its URL-encoded absolute path>`. If it fails to launch, say so.

The viewer draws a `.harness.yml` read-only, as WireViz draws it: every connector with its
pins and labels, every cable with its wires' colours, and the runs between them. Show the
harness and the boards it joins.

## Handoff

Report the files written, the build's last line, the checks that ran (every build checks nets,
pins and wires), each housing and terminal without a part number, the cable lengths and gauges
chosen and why (current, flex, reach), and the crossings declared with `joins=`. Show the
harness ([Show the model](#show-the-model)).

## References

- [The harness API](references/harness-api.md): every call, keyword, document field and refusal.
