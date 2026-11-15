# KiCad's API, by example

These are KiPy's own calls as kicode ships them on this nightly (KiCad 10.99), each run against it; nothing
here is text-to-cad's. Anything else is found on the object: `help(item)`, `dir(item)`,
`dir(kicode.board_types)`. Names come from `kicode`, never `kipy`
([SKILL.md](../SKILL.md#native-files-are-the-source)). A length is nanometres (`from_mm`), a position
`Vector2.from_xy_mm(x, y)`, y down. Each snippet makes an item only when the file does not hold it yet, so
a second run saves nothing. A section's later snippets go in the edit block its first one opens.

## A schematic

A symbol placed turned, a power symbol, and a symbol's value and footprint:

```python
from cad import kicad_sch
from kicode.geometry import Vector2
from kicode.schematic_types import (GlobalLabel, Junction, LocalLabel, NoConnectMarker,
                                    SchematicSymbolOrientation)

V = Vector2.from_xy_mm
with kicad_sch.edit("board.kicad_sch") as s:
    placed = {symbol.reference: symbol for symbol in s.get_symbols()}
    if "D1" not in placed:                    # SSO_0 (the default), SSO_90, SSO_180, SSO_270
        placed["D1"] = s.place_symbol_from_library(
            "parts:LED", V(101.6, 76.2), reference="D1", orientation=SchematicSymbolOrientation.SSO_90)
    if "#PWR01" not in placed:                # a power symbol is placed as any library symbol
        placed["#PWR01"] = s.place_symbol_from_library("parts:GND", V(101.6, 83.82), reference="#PWR01")
    d1 = placed["D1"]
    if (d1.value, d1.footprint_field.text.value) != ("green", "parts:LED_0603_1608Metric"):
        d1.value = "green"
        d1.footprint_field.text.value = "parts:LED_0603_1608Metric"
        s.update_items([d1])
```

A placed symbol is turned with `d1.transform.orientation = SchematicSymbolOrientation.SSO_270` and
`s.update_items([d1])`, set only when it differs.

A label, a junction and a no-connect marker, each at a point:

```python
new = []
if "LED" not in {label.text.value for label in s.get_labels()}:
    label = LocalLabel()                      # GlobalLabel() is made the same way
    label.text.value, label.position = "LED", V(101.6, 72.39)    # a pin's end or a wire's end
    new.append(label)
if V(101.6, 81.28) not in [junction.position for junction in s.get_junctions()]:
    junction = Junction()
    junction.position = V(101.6, 81.28)       # where wires meet; one that joins nothing is not saved
    new.append(junction)
if V(127.0, 72.39) not in [mark.position for mark in s.get_no_connects()]:
    mark = NoConnectMarker()
    mark.position = V(127.0, 72.39)           # the end of a pin meant to float
    new.append(mark)
if new:
    s.create_items(new)
```

## A board

The outline, a rectangle with rounded corners on Edge.Cuts:

```python
from cad import kicad_pcb
from kicode.board_types import (BoardArc, BoardLayer, BoardSegment, BoardText, Track, Via, Zone,
                                ZoneConnectionStyle, ZoneType, is_copper_layer)
from kicode.geometry import PolygonWithHoles, PolyLine, PolyLineNode, Vector2
from kicode.util.units import from_mm

V = Vector2.from_xy_mm
X0, Y0, X1, Y1, R = 100.0, 100.0, 130.0, 120.0, 1.0      # 30 x 20 mm, 1 mm corners
K = R * (1 - 0.5 ** 0.5)                                   # an arc's middle point, in from its corner
OUTLINE = [  # round the board: a side (no middle point), then the arc of the corner it ends at
    ((X0 + R, Y0), None, (X1 - R, Y0)), ((X1 - R, Y0), (X1 - K, Y0 + K), (X1, Y0 + R)),
    ((X1, Y0 + R), None, (X1, Y1 - R)), ((X1, Y1 - R), (X1 - K, Y1 - K), (X1 - R, Y1)),
    ((X1 - R, Y1), None, (X0 + R, Y1)), ((X0 + R, Y1), (X0 + K, Y1 - K), (X0, Y1 - R)),
    ((X0, Y1 - R), None, (X0, Y0 + R)), ((X0, Y0 + R), (X0 + K, Y0 + K), (X0 + R, Y0)),
]
with kicad_pcb.edit("board.kicad_pcb") as b:
    if not [shape for shape in b.get_shapes() if shape.layer == BoardLayer.BL_Edge_Cuts]:
        edge = []
        for start, mid, end in OUTLINE:
            shape = BoardArc() if mid else BoardSegment()  # an arc is its start, a point on it, its end
            shape.layer, shape.start, shape.end = BoardLayer.BL_Edge_Cuts, V(*start), V(*end)
            if mid:
                shape.mid = V(*mid)
            shape.attributes.stroke.width = from_mm(0.1)
            edge.append(shape)
        b.create_items(edge)
```

A track segment, a via and a text on silkscreen:

```python
nets = {net.name: net for net in b.get_nets()}             # the netlist import made them
new = []
if not [track for track in b.get_tracks() if track.net.name == "+5V"]:
    track = Track()                                        # one straight segment; a path is one a leg
    track.net, track.layer, track.width = nets["+5V"], BoardLayer.BL_F_Cu, from_mm(0.5)
    track.start, track.end = V(106.18, 108.48), V(107.9, 108.48)
    new.append(track)
if V(107.9, 108.48) not in [via.position for via in b.get_vias()]:
    via = Via()                                            # through the board, F.Cu to B.Cu
    via.net, via.position = nets["+5V"], V(107.9, 108.48)
    via.diameter, via.drill_diameter = from_mm(0.8), from_mm(0.4)
    new.append(via)
if "GND" not in {text.value for text in b.get_text()}:
    text = BoardText()
    text.value, text.layer = "GND", BoardLayer.BL_F_SilkS
    text.position = V(118.16, 104.3)                       # its centre
    text.attributes.size = V(1.0, 1.0)                     # x a glyph's width, y its height
    text.attributes.stroke_width = from_mm(0.15)
    new.append(text)
if new:
    b.create_items(new)
```

A copper zone: its outline, net, layers, priority and pad connection (a new zone left without one joins
every pad solid: [native files](board-api.md#edits)):

```python
if not [zone for zone in b.get_zones() if zone.name == "GND"]:
    line = PolyLine()
    for x, y in ((99.5, 99.5), (130.5, 99.5), (130.5, 120.5), (99.5, 120.5)):
        line.append(PolyLineNode.from_point(V(x, y)))
    line.closed = True
    outline = PolygonWithHoles()
    outline.outline = line
    zone = Zone()
    zone.type, zone.name, zone.net = ZoneType.ZT_COPPER, "GND", nets["GND"]
    zone.layers = [BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu]
    zone.priority = 0                                      # of two that overlap, the higher fills first
    zone.outline = outline
    zone.connection.zone_connection = ZoneConnectionStyle.ZCS_PTH_THERMAL   # or ZCS_THERMAL, ZCS_FULL
    zone.connection.thermal_spokes.gap = from_mm(0.3)
    zone.connection.thermal_spokes.width = from_mm(0.4)
    b.create_items([zone])
b.refill_zones()
```

The board's minimums, saved to the `.kicad_pro` at the block's end, and the copper layer count (a layer
taken away is deleted with what is on it):

```python
MINIMUMS = {"min_clearance": 0.15, "min_track_width": 0.15, "hole_clearance": 0.28,
            "copper_edge_clearance": 0.3}                  # mm; dir(rules.constraints) names the rest
rules = b.get_design_rules().rules
stale = {name: mm for name, mm in MINIMUMS.items() if getattr(rules.constraints, name) != from_mm(mm)}
for name, mm in stale.items():
    setattr(rules.constraints, name, from_mm(mm))
if stale:
    b.set_design_rules(rules)
if b.get_copper_layer_count() != 4:                        # even, 2 or more; then the non-copper layers kept
    b.set_enabled_layers(4, [layer for layer in b.get_enabled_layers() if not is_copper_layer(layer)])
```

## The project file

Netclasses, and which nets are in each, are JSON in the `.kicad_pro`: `net_settings.classes` and
`net_settings.netclass_patterns`. An edit's save leaves them as they are, so write them outside an edit block
([layout](layout.md#the-method)):

```python
import json
from pathlib import Path

PROJECT = Path("board.kicad_pro")
project = json.loads(PROJECT.read_text())
settings = project["net_settings"]
default = next(netclass for netclass in settings["classes"] if netclass["name"] == "Default")
default.update(clearance=0.2, track_width=0.25, via_diameter=0.7, via_drill=0.3)        # mm
power = dict(default, name="Power", track_width=0.5, via_diameter=0.8, via_drill=0.4, priority=0)
settings["classes"] = [default, power]                     # a class holds every key Default does
settings["netclass_patterns"] = [{"netclass": "Power", "pattern": net} for net in ("+5V", "+3V3", "GND")]
text = json.dumps(project, indent=2) + "\n"
if text != PROJECT.read_text():
    PROJECT.write_text(text)
```

The next edit reads them: `b.get_netclass_for_nets(list(nets.values()))` answers each net's class by the
net's name (`.name`, `.track_width`, `.clearance`, nanometres), where DRC's report names no netclass. The
minimums above are the same file's `board.design_settings.rules` (`min_clearance`, `min_hole_clearance`,
`min_copper_edge_clearance`, ...), and can be written the same way.
