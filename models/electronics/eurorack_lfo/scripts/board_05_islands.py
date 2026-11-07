# /// script
# dependencies = ["shapely"]
# ///
"""Step 5: every piece of the B.Cu GND pour that holds no stitching via gets one (inside it, clear of its edge),
and a stitching via that joins nothing is removed; then the pours refill. Run after board_04_pour.py."""
import sys
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.ops import polylabel, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD, X0, Y0  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from cad.kicad_pcb import inside  # noqa: E402
from kicode.board_types import Via  # noqa: E402
from kicode.geometry import Vector2  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

board = kicad_pcb.read(BOARD)
vias = [v.at for v in board.vias if v.net == "GND"]
f_fill = [Polygon(f) for z in board.zones if z.name == "GND_F" for f in z.fills]
adds = []
for z in board.zones:
    if z.name != "GND_B":
        continue
    for f in z.fills:
        if any(inside(v, f) for v in vias):
            continue
        # a via's 0.4 mm radius plus 0.05 inside both pours (each pour already keeps 0.25 from other copper)
        room = Polygon(f).buffer(-0.45).intersection(unary_union([g.buffer(-0.45) for g in f_fill]))
        if room.is_empty:
            continue
        piece = max(getattr(room, "geoms", [room]), key=lambda g: g.area)
        p = polylabel(piece, 0.01) if piece.geom_type == "Polygon" else piece.representative_point()
        adds.append((p.x, p.y))
dangling = []
for v in board.vias:
    if v.net == "GND" and not any(inside(v.at, f) for z in board.zones if z.name == "GND_B" for f in z.fills):
        dangling.append(v.at)
with kicad_pcb.edit(BOARD) as b:
    gnd = next(n for n in b.get_nets() if n.name == "GND")
    drop = [v for v in b.get_vias() if v.net.name == "GND" and (round(v.position.x / 1e6, 3), round(v.position.y / 1e6, 3)) in
            {(round(x, 3), round(y, 3)) for x, y in dangling}]
    if drop:
        b.remove_items(drop)
    new = []
    for x, y in adds:
        v = Via()
        v.position = Vector2.from_xy_mm(x, y)
        v.diameter, v.drill_diameter = from_mm(0.8), from_mm(0.4)
        v.net = gnd
        new.append(v)
    if new:
        b.create_items(new)
    b.refill_zones()
print(f"island vias added {len(adds)}, dangling vias removed {len(drop)}")
