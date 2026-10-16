"""An LED and its resistor on a 2-pin header: the smallest complete board."""
from cadgen import pcb
from cadgen.kipy.board_types import BoardLayer, BoardPolygon, Net, Track, Via, Zone
from cadgen.kipy.geometry import Angle, PolygonWithHoles, PolyLineNode, Vector2
from cadgen.kipy.util.units import from_mm

WIDTH, HEIGHT = 40.0, 30.0           # the outline, centred on KiCad's origin
PARTS = {                             # ref: footprint, (x, y) mm, rotation, pad -> net
    "J1": ("Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", (-15, 0), 0, {"1": "VBUS", "2": "GND"}),
    "R1": ("Resistor_SMD:R_0603_1608Metric", (0, 5), -90, {"1": "VBUS", "2": "LED"}),
    "D1": ("LED_SMD:LED_0603_1608Metric", (8, -5), 0, {"1": "GND", "2": "LED"}),
}


def rectangle(w, h, inset=0.0):
    poly = PolygonWithHoles()
    for x, y in ((-w / 2 + inset, -h / 2 + inset), (w / 2 - inset, -h / 2 + inset),
                 (w / 2 - inset, h / 2 - inset), (-w / 2 + inset, h / 2 - inset)):
        poly.outline.append(PolyLineNode.from_xy(from_mm(x), from_mm(y)))
    poly.outline.closed = True
    return poly


def track(net, width, *points, layer=BoardLayer.BL_F_Cu):
    """Straight segments through `points` (Vector2 or (x, y) mm), one Track each."""
    nodes = [p if isinstance(p, Vector2) else Vector2.from_xy_mm(*p) for p in points]
    for a, b in zip(nodes, nodes[1:]):
        t = Track()
        t.start, t.end, t.width, t.layer, t.net = a, b, from_mm(width), layer, Net(name=net)
        yield t


@pcb
def blinky(board):
    # Place: every footprint comes from a library the project table (fp-lib-table) declares.
    pads, placed = {}, []
    for ref, (footprint, at, rotation, nets) in PARTS.items():
        fp = board.place_footprint_from_library(footprint, Vector2.from_xy_mm(*at), Angle.from_degrees(rotation))
        fp.reference_field.text.value = ref
        for pad in fp.definition.pads:
            pad.net = Net(name=nets[pad.number])
            pads[f"{ref}.{pad.number}"] = pad.position         # absolute, in nm: route from these
        placed.append(fp)
    board.update_items(placed)

    # Outline and copper, created in one call.
    edge = BoardPolygon()
    edge.polygons.append(rectangle(WIDTH, HEIGHT))
    edge.layer = BoardLayer.BL_Edge_Cuts
    edge.attributes.stroke.width = from_mm(0.1)

    via = Via()
    via.position, via.net = Vector2.from_xy_mm(7.2125, -8), Net(name="GND")
    via.diameter, via.drill_diameter = from_mm(0.6), from_mm(0.3)

    pour = Zone()                                                # a copper zone by default
    pour.outline, pour.layers, pour.net, pour.name = rectangle(WIDTH, HEIGHT, inset=0.5), [BoardLayer.BL_B_Cu], Net(name="GND"), "GND"

    board.create_items([
        edge,
        *track("VBUS", 0.3, pads["J1.1"], (0, 0), pads["R1.1"]),
        *track("LED", 0.25, pads["R1.2"], (0, 8), (12, 8), (12, -5), pads["D1.2"]),
        *track("GND", 0.25, pads["D1.1"], via.position),
        via,
        pour,
    ])

    rules = board.get_design_rules().rules                       # the board's DRC limits
    rules.constraints.min_clearance = from_mm(0.15)
    rules.constraints.min_track_width = from_mm(0.15)
    board.set_design_rules(rules)


if __name__ == "__main__":
    blinky()
