"""Ground pours on both copper layers, over the whole board (made once)."""
from board_common import X0, X1, Y0, Y1
from kicode.board_types import Net, Zone
from kicode.geometry import PolygonWithHoles, PolyLine, PolyLineNode, Vector2
from kicode.proto.board.board_types_pb2 import BoardLayer
from kicode.util.units import from_mm


def ensure(b):
    """Each pour covers the outline as board_common states it: one drawn for an older outline goes."""
    stale = []
    for z in b.get_zones():
        ys = [n.point.y / 1e6 for n in z.outline.outline.nodes]
        if z.name in ("GND_top", "GND_bottom") and (round(min(ys), 3), round(max(ys), 3)) != (Y0, Y1):
            stale.append(z)
    if stale:
        b.remove_items(stale)
    have = {z.name for z in b.get_zones()}
    new = []
    for name, layer, prio in (("GND_top", BoardLayer.BL_F_Cu, 0), ("GND_bottom", BoardLayer.BL_B_Cu, 0)):
        if name in have:
            continue
        z = Zone()
        z.name, z.layers, z.priority, z.net = name, [layer], prio, Net(name="GND")
        poly = PolyLine()
        for x, y in ((X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)):
            poly.append(PolyLineNode.from_point(Vector2.from_xy_mm(x, y)))
        poly.closed = True
        outline = PolygonWithHoles()
        outline.outline = poly
        z.outline = outline
        z.clearance = from_mm(0.25)
        z.min_thickness = from_mm(0.2)
        new.append(z)
    if new:
        b.create_items(new)
