# /// script
# dependencies = ["shapely"]
# ///
"""Step 4: GND pours on both copper layers over the whole board (0.25 mm clearance, thermal reliefs), stitching
vias on a 4 mm grid wherever a via fits clear of every other net, then KiCad's zone refill.
Run: cad run scripts/board_04_pour.py"""

import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD, H, W, X0, Y0  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from kicode.board_types import Via, Zone  # noqa: E402
from kicode.geometry import PolygonWithHoles, PolyLine, PolyLineNode, Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer, IslandRemovalMode, ZoneConnectionStyle  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

STITCH = 4.0
INSET = 0.3
# The stitching via (0.8/0.4) and the board's rules (twin_orbit.kicad_pro): 0.2 mm from other nets' copper, 0.5 mm
# hole to hole, 0.3 mm copper to edge; SLACK covers the board index's pad chords (within 0.008 mm of KiCad's).
VIA_R, DRILL_R, CLEARANCE, HOLE_TO_HOLE, EDGE, SLACK = 0.4, 0.2, 0.2, 0.5, 0.3, 0.02


def stitch_points(board):
    """The stitching sites: on a 4 mm grid, the first spot within 1.5 mm of each grid point where a GND via is in
    no pad, on no GND track, clear of every other net's copper and every hole, in no keepout, inside the edge.
    A GND via that a GND track ends at is a tie's (board_03_route.py) and blocks like any hole; the others are
    this step's own stitching, made again here, so they block nothing."""
    ends = {end for track in board.tracks if track.net == "GND" for end in (track.points[0], track.points[-1])}
    blocked = []
    for pad in board.pads:
        blocked.append(Polygon(pad.polygon).buffer(VIA_R + (CLEARANCE if pad.net != "GND" else 0.0) + SLACK))
        if pad.drill:
            blocked.append(Point(pad.at).buffer(pad.drill / 2 + HOLE_TO_HOLE + DRILL_R + SLACK))
    for track in board.tracks:
        keep = CLEARANCE if track.net != "GND" else 0.0
        blocked.append(LineString(track.points).buffer(track.width / 2 + keep + VIA_R + SLACK))
    for via in board.vias:
        if via.net != "GND":
            blocked.append(Point(via.at).buffer(max(via.diameter / 2 + CLEARANCE + VIA_R,
                                                    via.drill / 2 + HOLE_TO_HOLE + DRILL_R) + SLACK))
        elif via.at in ends:
            blocked.append(Point(via.at).buffer(via.drill / 2 + HOLE_TO_HOLE + DRILL_R + SLACK))
    for hole in board.holes:
        blocked.append(Point(hole.at).buffer(hole.diameter / 2 + HOLE_TO_HOLE + DRILL_R + SLACK))
    for area in board.rule_areas:
        blocked.append(Polygon(area.outline).buffer(VIA_R + SLACK))
    taken = unary_union(blocked)
    room = Polygon(board.outline[0]).buffer(-(EDGE + VIA_R + SLACK))
    offsets = (0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5)
    pts = []
    for k in range(int((H - 3.5) // STITCH) + 1):
        for i in range(int((W - 3.5) // STITCH) + 1):
            x, y = 2.0 + i * STITCH, 2.0 + k * STITCH
            for dy in offsets:
                site = next(((round(x + dx, 2), round(y + dy, 2)) for dx in offsets
                             if room.contains(p := Point(X0 + x + dx, Y0 + y + dy)) and not taken.intersects(p)), None)
                if site:
                    pts.append(site)
                    break
    return pts


def zone(layer, net):
    z = Zone()
    z.layers = [layer]
    poly = PolygonWithHoles()
    line = PolyLine()
    for x, y in ((INSET, INSET), (W - INSET, INSET), (W - INSET, H - INSET), (INSET, H - INSET)):
        line.append(PolyLineNode.from_point(Vector2.from_xy_mm(X0 + x, Y0 + y)))
    line.closed = True
    poly.outline = line
    z.outline = poly
    z.net = net
    z.name = f"GND_{'F' if layer == BoardLayer.BL_F_Cu else 'B'}"
    settings(z)
    return z


def settings(z):
    """Thermal reliefs on through-hole pads (hand soldering), solid on SMD pads; islands removed."""
    z.clearance = from_mm(0.25)
    z.min_thickness = from_mm(0.25)
    z.connection.zone_connection = ZoneConnectionStyle.ZCS_PTH_THERMAL
    z.island_mode = IslandRemovalMode.IRM_ALWAYS


pts = stitch_points(kicad_pcb.read(BOARD))
with kicad_pcb.edit(BOARD) as b:
    gnd = next(n for n in b.get_nets() if n.name == "GND")
    have = {z.name for z in b.get_zones()}
    new = [zone(L, gnd) for L in (BoardLayer.BL_F_Cu, BoardLayer.BL_B_Cu) if f"GND_{'F' if L == BoardLayer.BL_F_Cu else 'B'}" not in have]
    if new:
        b.create_items(new)
    olds = [z for z in b.get_zones() if z.name in ("GND_F", "GND_B")]
    for z in olds:
        settings(z)
    b.update_items(olds)
    ends = {(round(p.x / 1e6, 4), round(p.y / 1e6, 4)) for t in b.get_tracks() if t.net.name == "GND"
            for p in (t.start, t.end)}
    old_v = [v for v in b.get_vias() if v.net.name == "GND"
             and (round(v.position.x / 1e6, 4), round(v.position.y / 1e6, 4)) not in ends]  # the ties' vias stay
    if old_v:
        b.remove_items(old_v)
    have_v = set()
    vias = []
    for p in pts:
        if p in have_v:
            continue
        v = Via()
        v.position = Vector2.from_xy_mm(X0 + p[0], Y0 + p[1])
        v.diameter, v.drill_diameter = from_mm(0.8), from_mm(0.4)
        v.net = gnd
        vias.append(v)
    if vias:
        b.create_items(vias)
    b.refill_zones()
    print(f"zones added {len(new)}, stitching vias {len(vias)} (of {len(pts)} sites)")
