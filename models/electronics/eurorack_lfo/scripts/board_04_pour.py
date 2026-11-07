# /// script
# dependencies = ["numpy", "scipy", "shapely"]
# ///
"""Step 4: GND pours on both copper layers over the whole board (0.25 mm clearance, thermal reliefs), stitching
vias on a 4 mm grid wherever a via fits clear of every other net, then KiCad's zone refill.
Run: cad run scripts/board_04_pour.py"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assist_route import G, NX, NY, Board  # noqa: E402
from boardlib import BOARD, H, W, X0, Y0  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from kicode.board_types import Via, Zone  # noqa: E402
from kicode.geometry import PolygonWithHoles, PolyLine, PolyLineNode, Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer, IslandRemovalMode, ZoneConnectionStyle  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

STITCH = 4.0
INSET = 0.3


def stitch_points(board_read):
    B = Board(board_read)
    for t in board_read.tracks:
        for a, b in zip(t.points, t.points[1:]):
            B.add_track(t.layer, (a[0] - X0, a[1] - Y0), (b[0] - X0, b[1] - Y0), t.width, B.nid(t.net))
    for v in board_read.vias:
        if v.net != "GND":
            B.add_via((v.at[0] - X0, v.at[1] - Y0), B.nid(v.net))
    ok = B.free(B.nid("GND"), 0.25)["via"].copy()
    from shapely.geometry import Point as _P
    from assist_route import raster
    for part in board_read.parts:
        for pad in part.pads:
            if pad.drill:
                ok &= ~raster(_P(pad.at[0] - X0, pad.at[1] - Y0).buffer(pad.drill / 2 + 0.2 + 0.5 + 0.2))
    for v in [v for v in board_read.vias if v.net != "GND"]:
        ok &= ~raster(_P(v.at[0] - X0, v.at[1] - Y0).buffer(0.2 + 0.5 + 0.2 + 0.1))
    # keep stitching clear of GND pads too (no via in a pad) and of each other
    pts = []
    for y in np.arange(2.0, H - 1.5, STITCH):
        for x in np.arange(2.0, W - 1.5, STITCH):
            best = None
            for dy in (0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5):
                for dx in (0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5):
                    i, j = int(round((x + dx) / G)), int(round((y + dy) / G))
                    if 0 <= i < NX and 0 <= j < NY and ok[j, i] and all(B.cu[L][j, i] == 0 for L in B.cu):
                        best = (round((x + dx), 2), round((y + dy), 2))
                        break
                if best:
                    break
            if best:
                pts.append(best)
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
    old_v = [v for v in b.get_vias() if v.net.name == "GND"]
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
