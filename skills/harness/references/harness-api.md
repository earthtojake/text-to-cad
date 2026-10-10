# The harness API

`from cadgen import harness` gives the `@harness` decorator and the API:
`harness.Harness`, `harness.Connector`, `harness.Cable`, `harness.Wire`, `harness.Pin` and
`harness.HarnessError` (a `ValueError`; every refusal below is one, raised where the script
made the mistake). Keywords are WireViz's names for the same fields, and every keyword set is
closed: an unknown keyword fails, naming the closest known one.

## `@harness`

```python
@harness                                   # writes <file stem>.harness.yml beside the script
def cable(): ...


@harness(out="cables/main.harness.yml")    # out= is relative to the script; ends .harness.yml
def main(): ...


@harness(bom=True)                         # also <stem>.bom.csv beside it
                                           # (bom="parts/loom.csv" puts it there)
def loom(): ...
```

The function takes no parameters and returns a `harness.Harness`. A file may hold several
models; models sharing a file write `<function>.harness.yml`. Nothing else stacks on a
harness: `@step`, `@dxf`, `@pcb` and the mesh exports are refused, as are `gerber=` and
`pos=` (a board's manufacturing files).

Called inside another model's build, a `@harness` function returns its `Harness`. Inside a
harness's build a `@pcb` board returns its `pcb.Board`, 3D export or not; a `@step` part
called there is refused (it has no netlist).

## `harness.Harness(title=None)`

`title` is the document's `metadata.title`. `h.connectors`, `h.cables` and `h.connections`
list what it holds, in declaration order; `h.problems()` lists what would stop it being
written.

## Connectors

### From a board

```python
a = h.connector(board, "J3", type="JST PH 2.0 mm housing, 4 pin")   # board: a pcb.Board
a = h.connector(j3, type="JST PH 2.0 mm housing, 4 pin")            # j3: the board's part
```

- The pins are the part's, in its symbol's order. Each pin's label is the name of the net it
  carries on the board; a pin marked no-connect on the board is labelled `NC`.
- `type` is required: the housing that mates with the board's header. The document's `notes`
  also say what it mates with (`mates J3 of controller: JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical`,
  after any `notes=` given).
- The designator is the part's reference unless `name=` gives one; a designator is used once
  per harness, so the second board's `J1` needs a `name=`.
- `pins=`, `pinlabels=` and `pincount=` are refused: the board has the pins.
- The board must be a `pcb.Board` (a testbench's part is refused), and the reference one of
  its parts (the refusal lists them). 3D geometry is refused: call the board's `@pcb` model
  inside the harness, where it returns its `pcb.Board`.

### Free

```python
m = h.connector("M1", pinlabels=["A+", "A-", "B+", "B-"], type="JST XH 2.5 mm housing, 4 pin")
x = h.connector("X2", pins=["A1", "B1"])
f = h.connector("F1", pincount=1, style="simple", type="Ferrule 0.5 mm²")
```

- Pins come from `pins=`, `pinlabels=` or `pincount=`; given together, they agree on the count.
  Without `pins=`, pins are numbered from 1.
- A pin is a whole number, or text WireViz will not read as one: `"01"` (WireViz reads 1) and
  `"1-2"` (WireViz reads a range) are refused, as are a pin given twice and a label that is
  another pin's name.

### Keywords (both kinds)

| Keyword | Value |
| --- | --- |
| `type`, `subtype` | Text: the housing family and size; `"female"`, `"male"`, `"right angle"`... |
| `color` | The housing's colour code |
| `style` | `"simple"`: a one-pin connector (ferrule, ring lug), drawn without a pin table |
| `pincolors` | One colour code per pin |
| `hide_disconnected_pins` | `True` draws only wired pins |
| `notes` | Text, may span lines |
| `pn`, `manufacturer`, `mpn`, `supplier`, `spn` | Part numbers: the BOM's columns |
| `additional_components` | Parts bought with this one (below) |

### Pins

`x[1]` and `x["1"]` are pin 1; `x["VBUS"]` is the pin labelled `VBUS` when exactly one is
(otherwise the refusal lists the numbers); `x.pins` is every pin, in order. A pin knows
`id`, `label`, `net` (its board net's name, or `None`) and `connector`.

## Cables

```python
w = h.cable("W1", colors=["RD", "BK"], gauge="24 AWG", length=300)
w = h.cable("W2", color_code="DIN", wirecount=6, gauge=0.25, length=1200, shield=True, type="LiYCY")
w = h.cable("W3", colors=["RD", "BK"], gauge="20 AWG", length=150, category="bundle")
```

| Keyword | Value |
| --- | --- |
| `colors` | One colour per wire; it sets the wire count |
| `wirecount` | The wire count; with `color_code`, or alone for uncoloured wires |
| `color_code` | `"DIN"` (DIN 47100), `"IEC"` (IEC 60062 order), `"BW"`, `"TEL"`, `"TELALT"` (25-pair telephone), `"T568A"`, `"T568B"`; a cable longer than its code starts the code again |
| `gauge` | Required. `"24 AWG"` (a whole number, 0 to 40), or a cross-section in mm²: `0.25` or `"0.25 mm2"`. A bare number over 10 is refused: it is far more likely an AWG without its unit |
| `length` | Required. Millimetres, a number; the document has metres, WireViz's unit |
| `shield` | `True` adds a shield, wire `"s"` |
| `category` | `"bundle"`: loose wires rather than one jacketed cable; the BOM lists each wire by gauge and colour |
| `type` | Text: the cable's construction (`"LiYCY"`, `"silicone"`) |
| `color` | The jacket's colour code |
| `wirelabels` | One text label per wire |
| `notes`, `pn`, `manufacturer`, `mpn`, `supplier`, `spn` | As for connectors |
| `additional_components` | As for connectors, with a cable's multipliers |

`w[1]` is wire 1; `w["RD"]` the wire coloured `RD` when exactly one is; a wire label works
the same way; `w["s"]` is the shield; `w.wires` every wire but the shield.

### Colours

Two-letter codes, run together for a striped wire (`"WHGN"`: white, green stripe), in
capitals: `BK` black, `WH` white, `GY` grey, `PK` pink, `RD` red, `OG` orange, `YE` yellow,
`OL` olive green, `GN` green, `TQ` turquoise, `LB` light blue, `BU` blue, `VT` violet, `BN`
brown, `BG` beige, `IV` ivory, `SL` slate, `CU` copper, `SN` tin, `SR` silver, `GD` gold.

### Additional components

A list of dicts, each one BOM line bought with its connector or cable:

```python
additional_components=[
    {"type": "Crimp terminal", "mpn": "SPH-002T-P0.5S", "qty_multiplier": "populated"},
    {"type": "Heat shrink 6 mm", "qty": 0.05, "unit": "m"},
]
```

Keys: `type` (required), `subtype`, `manufacturer`, `mpn`, `supplier`, `spn`, `pn`, `qty` (a
number, default 1), `unit`, `qty_multiplier`. A connector's multipliers: `"pincount"`,
`"populated"` (one per wired pin), `"unpopulated"`. A cable's: `"wirecount"`,
`"terminations"`, `"length"`, `"total_length"`.

## Connections

```python
h.connect(a[1], w[1], b[2])                         # one wire's run: pin, wire, pin
h.connect(a.pins, w.wires, [b[2], b[1], b[4], b[3]]) # lists: one connection per item
h.connect(a[4], w["s"])                              # a free end: (pin, wire) or (wire, pin)
h.connect(a["TX"], w[3], b["RX"], joins=("TX", "RX"))
```

- The order is pin, wire, pin, or a pin and a wire either way round. Lists in one call have
  one item per connection; a list mixing pins and wires is refused, as is a connector or
  cable where pins or wires belong (`a.pins`, not `a`).
- A pin takes one wire. A wire is connected once: both of its ends in one call.
- **Nets.** A wire whose two ends are both board connectors joins two pins carrying the same
  net, and a net the boards name (`board.net("VBUS")`, not KiCad's made-up `Net-(J1-Pad1)`).
  A board pin on no net is refused. `joins=(from_net, to_net)` declares a wire that joins two
  different nets on purpose (a UART's TX to RX); it is checked: the ends carry exactly those
  nets, in that order, and a `joins=` where the nets already match is refused. It is for one
  wire's call between two board connectors.
- A refused call connects nothing.

## What a build checks before writing

Everything above, plus: the harness connects something; every connector and cable is
connected (WireViz leaves an unconnected one out of the drawing and the BOM); text has no
`<`, `>` or `&` (WireViz draws text as HTML labels) and no control characters (`notes` may
span lines). A failed build writes nothing; the message names the call and what to change.

## The document

`<name>.harness.yml` is WireViz YAML, its bytes a function of the harness: `metadata`
(the title), then `connectors`, `cables` and `connections`, each in the order the script
declared them, each field in a fixed order, every string double-quoted. One `connect` call is
one connection set (split where its rows run between different connectors or cables). It
carries no script, path or time.

WireViz has more than this API writes (mating arrows, loops, images, templates, `tweak`,
`options`, `additional_bom_items`). A hand-written WireViz document can use them, and the CAD
Viewer, `cadgen harness snapshot` and `cadgen harness bom` read any WireViz document; a document a
`@harness` model writes is rewritten by its next build, so do not edit one by hand.
