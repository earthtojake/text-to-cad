# The board API

Everything a `@pcb` function uses, from `from cadgen import pcb`. Unknown keyword
arguments are errors; every error says what to do instead.

## Coordinates

- Millimetres. **y up**, x right, as build123d draws. The board's (0, 0) is wherever its
  outline puts it; the KiCad files carry that point as their drill/place origin, so KiCad's
  placement file and STEP export come back in the same coordinates.
- `rotation` is degrees counter-clockwise, seen from the top. `side="bottom"` mirrors the
  part top-to-bottom in its own frame (KiCad's flip): a pad on the footprint's x axis stays
  on it, one above it ends up below it. `rotation` is still counter-clockwise seen from the
  top.
- Positions you read back (`pin.position`, `part.at`) are in the same frame, rounded to
  KiCad's nanometre.

## Board

```python
pcb.Board(
    outline=face_or_sketch,     # required; build123d 2D geometry in the XY plane, holes = cutouts
    layers=2,                   # copper layers: an even number 2..32 (F.Cu, In1.Cu.., B.Cu)
    thickness=1.6,              # mm
    fab=pcb.JLCPCB,             # where it is made: its limits are the board's design rules
    rules=None,                 # a pcb.Rules instead: pcb.PCBWAY.rules.replace(min_track_width=0.15)
    libraries=[],               # project folders holding <Lib>.kicad_sym / <Lib>.pretty, searched first
    title=None,                 # the title block; defaults to the model's name
)
```

Lines, arcs and circles of the outline become `Edge.Cuts` exactly; other curves are sampled.
Off-plane geometry is refused.

`pcb.Rules` fields (KiCad's names): `min_clearance`, `min_track_width`,
`min_via_diameter`, `min_via_annular_width`, `min_through_hole_diameter`,
`min_hole_to_hole`, `min_hole_clearance`, `min_copper_edge_clearance`,
`min_silk_clearance`, `min_text_height`, `min_text_thickness`, and the Default net class's
`track_width`, `clearance`, `via_diameter`, `via_drill`.

`fab=` is one of `pcb.JLCPCB` (the default), `pcb.PCBWAY`, `pcb.OSHPARK`, `pcb.AISLER`,
`pcb.EUROCIRCUITS`, `pcb.SEEED_FUSION`, `pcb.NEXTPCB` (all in `pcb.FABS`): each holds that fab's
standard-service limits (the price tier with no surcharge), for two copper layers
(`fab.rules`) and for four or more (`fab.multilayer`); the board takes the set for its
`layers=`. A board checked against them is one that fab makes at its base price. For a fab
not listed, pass `rules=pcb.Rules(...)` with the numbers from its capability page. Each
preset's default net class (0.25 mm tracks, 0.2 mm clearance, a 0.6/0.3 mm via, or the
larger via a fab needs) is well inside its limits; the minimums only matter where you ask
for less. [Manufacturing](manufacturing.md) has each fab's numbers and how to order.

## Parts and pins

```python
part = board.part(
    "Device:R",                         # the symbol, Library:Name
    footprint="Resistor_SMD:R_0603_1608Metric",  # default: the symbol's own Footprint field
    value="10k",                        # default: the symbol's Value
    ref=None,                           # default: prefix + next free number (R1, U2, J3)
    properties={"LCSC": "C25804", "MPN": "0603WAF1002T5E"},
    dnp=False,                          # on the board, not assembled
)
part[1]; part["2"]; part["VIN"]         # pins by number, or by a unique name
part.pins(); part.unconnected()          # all pins; pins on no net and not no-connect
pin.number, pin.name, pin.electrical_type, pin.net, pin.position, pin.pads, pin.stack
```

- A symbol pin needs a footprint pad with the same number; the part is refused otherwise.
- Pins a symbol draws at one point (a connector's repeated GND pins, a Pi header's two 3V3
  pins) are `pin.stack`: one connection in the schematic, so connecting or no-connecting one
  does the whole stack, and two nets on one stack are refused.
- Multi-unit symbols (an LM358's A, B and power units) are one part: pins of every unit
  are on it, and the schematic draws each unit.
- A power symbol (`power:GND`) is a net, not a part: use `board.net("GND")`.
- `pcb.find_symbols("ldo 3.3")` and `pcb.find_footprints("sot-223")` search KiCad's
  libraries and the project's.

## Nets

```python
net = board.net("VBUS", netclass="Power", power_flag=True, current=2.0)
anonymous = board.net()                  # named like KiCad: Net-(R1-Pad2)
board.connect(net, j1[1], u1["VIN"], c1[1])
board.no_connect(u1["NC"], *u1.unconnected())
```

- A pin joins one net; connecting it to a second is refused.
- `power_flag=True`: the net is powered from off the board (a connector, a battery, a test
  pad). KiCad's ERC otherwise reports its power inputs as undriven.
- `current=2.0`: the net's current in amperes, positive, one value per net. KiCad keeps no
  current per net, so it is kept in the `.kicad_pro` under `"cadgen": {"net_currents": ...}`
  for the review, which warns where the net's narrowest track is thinner than IPC-2221 asks
  (1 oz outer copper, 10 °C rise). It sets no width: size the track or net class yourself.
- Every pin must be connected or marked no-connect: KiCad's ERC fails a floating pin.

## Placement

```python
board.place(part, at=(x, y), rotation=0, side="top")
```

Every part must be placed before the board is written.

## Copper

```python
board.track(net, [(x, y), pin, (x, y)], width=None, layer="F.Cu")   # segments; a pin = its pad centre
board.arc(net, start=(x, y), mid=(x, y), end=(x, y), width=None, layer="F.Cu")
board.via(net, at=(x, y), diameter=None, drill=None)                 # through vias
board.zone(net, layers=["B.Cu"], shape=None, clearance=None, min_thickness=None,
           priority=0, thermal_gap=None, thermal_width=None, pads="thermal")  # pads: thermal|solid|none
board.keepout(shape=face, layers=None, tracks=True, vias=True, pads=False, pours=True, footprints=False)
board.netclass("Power", track_width=0.5, clearance=0.2, via_diameter=0.8, via_drill=0.4)
board.autoroute(skip=(), layers=None, passes=100, timeout=600)      # Freerouting, at build: routing.md
```

Width and via size default to the net's class (the Default class is `rules=`). KiCad fills
zones when the board is written. A zone `shape` may not have holes (cover them with a
keepout). Blind and buried vias are not typed: write them with `board.raw`.

## Other items

```python
board.hole(at=(x, y), diameter=3.2)      # unplated mounting hole
board.text("REV A", at=(x, y), layer="F.SilkS", size=1.0, thickness=None, rotation=0)
board.raw('(gr_text "X" (at 100 100) (layer "F.SilkS") (effects (font (size 1 1))))')
```

`board.raw` takes any one item of KiCad's board format, in KiCad's own coordinates (y down,
page origin, which is NOT the script's origin); KiCad checks it when the board is written.

## Custom design rules

`pcb.Rules` apply to the whole board. For a constraint on one part, net, net class or area,
write a rule in KiCad's own custom-rule language (KiCad's Board Setup > Custom Rules):

```python
# A USB-C receptacle's GND pads sit 0.19 mm from its locating pegs, as the maker drew them.
board.rule('''(rule "J1 land pattern"
    (constraint hole_clearance (min 0.15mm))
    (condition "A.memberOfFootprint('J1') && B.memberOfFootprint('J1')"))''')
board.rule('''(rule "HV clearance" (constraint clearance (min 1.5mm)) (condition "A.NetClass == 'HV'"))''')
```

The rules are written to the project's `.kicad_dru`, so KiCad's own editor applies them
too. KiCad ignores a rules file it cannot parse, every rule in it, without saying so;
cadgen checks that KiCad read the file and fails the build when it did not. Relax a rule
only where a part's maker specifies the geometry and the fab can make it, never to make a
layout mistake pass.

## Errors you will meet

| Message | Fix |
| --- | --- |
| `symbol library 'Device' has no 'Resistor'; did you mean ...` | Use a real name; search with `pcb.find_symbols` |
| `... has pin(s) 3 that footprint ... has no pad for` | The footprint is not the one this symbol's numbering was drawn for |
| `R4 is not placed` | `board.place(r4, at=...)` |
| ERC `pin_not_connected` | Connect it or `board.no_connect(pin)` |
| ERC `power_pin_not_driven` | `power_flag=True` on a net fed from off the board or through a passive part (a fuse, a diode), or connect the output that drives it |
| DRC `clearance` / `shorting_items` | Move the track or part; the finding gives both items and their positions |
| DRC `courtyards_overlap` | Parts too close: move one |
| DRC `copper_edge_clearance` | Copper too near the outline: move it in |
| DRC `hole_clearance` between one connector's own pads and pegs | The maker's land pattern is tighter than the board rules: a `board.rule` scoped to that part |
| DRC `starved_thermal` | A pad reaches the pour through too few spokes: a track into the pour, or `pads="solid"` |
| `KiCad could not read the board's custom rules` | A `board.rule` has a mistake KiCad rejects (an unknown property or function); fix its syntax |
| `(draft: N unrouted connections)` | Route the listed connections, or `board.autoroute()` |
