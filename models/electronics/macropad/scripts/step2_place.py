"""Layout step 2: the outline and the fixed parts (keys, LEDs, holes, encoder, USB), then the strip's
parts from STRIP. Run: cad run scripts/step2_place.py   (from anywhere)

States the board it wants: each part at its place, side and angle; the outline drawn once."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from board_common import CORNER, X0, X1, Y0, Y1, placements  # noqa: E402
from strip import STRIP  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from kicode.board_types import BoardArc, BoardSegment  # noqa: E402
from kicode.geometry import Angle, Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

os.chdir(HERE.parent)
BOARD = "macropad.kicad_pcb"
WANT = {**placements(), **STRIP}


def v(x, y):
    return Vector2.from_xy_mm(x, y)


with kicad_pcb.edit(BOARD) as b:
    # outline: a rounded rectangle on Edge.Cuts, made when the board has none
    edges = [s for s in b.get_shapes() if s.layer == BoardLayer.BL_Edge_Cuts]
    ys = sorted({round(p.y / 1e6, 3) for s in edges for p in (s.start, s.end)})
    if edges and (min(ys), max(ys)) != (Y0, Y1):      # the outline changed size: draw it again
        b.remove_items(edges)
        edges = []
    if not edges:
        r = CORNER
        items = []
        for (sx, sy), (ex, ey) in (((X0 + r, Y0), (X1 - r, Y0)), ((X1, Y0 + r), (X1, Y1 - r)),
                                   ((X1 - r, Y1), (X0 + r, Y1)), ((X0, Y1 - r), (X0, Y0 + r))):
            s = BoardSegment()
            s.start, s.end, s.layer = v(sx, sy), v(ex, ey), BoardLayer.BL_Edge_Cuts
            s.attributes.stroke.width = from_mm(0.1)
            items.append(s)
        k = r * (1 - 2 ** -0.5)
        for (sx, sy), (mx, my), (ex, ey) in (((X0, Y0 + r), (X0 + k, Y0 + k), (X0 + r, Y0)),
                                             ((X1 - r, Y0), (X1 - k, Y0 + k), (X1, Y0 + r)),
                                             ((X1, Y1 - r), (X1 - k, Y1 - k), (X1 - r, Y1)),
                                             ((X0 + r, Y1), (X0 + k, Y1 - k), (X0, Y1 - r))):
            a = BoardArc()
            a.start, a.mid, a.end, a.layer = v(sx, sy), v(mx, my), v(ex, ey), BoardLayer.BL_Edge_Cuts
            a.attributes.stroke.width = from_mm(0.1)
            items.append(a)
        b.create_items(items)
    fps = {f.reference_field.text.value: f for f in b.get_footprints()}
    missing = sorted(set(WANT) - set(fps))
    if missing:
        raise SystemExit(f"not on the board: {missing}")
    to_flip = [fps[r] for r, (_, _, _, side) in WANT.items()
               if (side == "B") != (fps[r].layer == BoardLayer.BL_B_Cu)]
    if to_flip:
        b.flip_items(to_flip)
        fps = {f.reference_field.text.value: f for f in b.get_footprints()}
    changed = []
    for ref, (x, y, deg, side) in WANT.items():
        f = fps[ref]
        # KiCad turns a part it flips left-right by 180 degrees: a bottom part's angle as the table
        # means it (mirrored, then turned) is KiCad's plus 180
        deg = (deg + 180) % 360 if side == "B" else deg
        pos, ang = v(x, y), Angle.from_degrees(deg)
        if (f.position.x, f.position.y) != (pos.x, pos.y) or abs(f.orientation.degrees - deg) % 360 > 1e-6:
            f.position, f.orientation = pos, ang
            changed.append(f)
    if changed:
        b.update_items(changed)
    print(f"flipped {len(to_flip)}, moved {len(changed)}")
