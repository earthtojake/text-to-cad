"""Step 2: the outline and every part's place. States the board it wants (positions, rotations, sides), so a
second run changes nothing. Run: cad run scripts/board_02_place.py"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD, CORNER_R, H, LFO_PITCH, W, A, b_ref, ref_of  # noqa: E402
from place_table import PLACE, SHARED  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from kicode.board_types import BoardArc, BoardSegment  # noqa: E402
from kicode.geometry import Angle, Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402


def table():
    out = dict(SHARED)
    for ref, (x, y, rot, side) in PLACE.items():
        out[ref] = (x, y, rot, side)
        if ref[-3:-2] == "1" and ref[-3:].isdigit() and len(ref.rstrip("0123456789")) + 3 == len(ref):
            out[b_ref(ref)] = (x + LFO_PITCH, y, rot, side)
    return out


def outline_items():
    r = CORNER_R
    pts = []
    (x0, y0), (x1, y1) = A(0, 0), A(W, H)
    segs = [((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)), ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))]
    for s, e in segs:
        seg = BoardSegment()
        seg.start, seg.end = Vector2.from_xy_mm(*s), Vector2.from_xy_mm(*e)
        seg.layer = BoardLayer.BL_Edge_Cuts
        seg.attributes.stroke.width = from_mm(0.05)
        pts.append(seg)
    k = r * (1 - math.sqrt(0.5))
    arcs = [((x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0)), ((x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r)),
            ((x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1)), ((x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r))]
    for s, m, e in arcs:
        arc = BoardArc()
        arc.start, arc.mid, arc.end = Vector2.from_xy_mm(*s), Vector2.from_xy_mm(*m), Vector2.from_xy_mm(*e)
        arc.layer = BoardLayer.BL_Edge_Cuts
        arc.attributes.stroke.width = from_mm(0.05)
        pts.append(arc)
    return pts


want = table()
with kicad_pcb.edit(BOARD) as b:
    edges = [s for s in b.get_shapes() if s.layer == BoardLayer.BL_Edge_Cuts]
    xs = [v / 1e6 for s in edges for v in (s.start.x, s.end.x)]
    want_box = (A(0, 0)[0], A(W, H)[0])
    if not edges or abs(min(xs) - want_box[0]) > 1e-3 or abs(max(xs) - want_box[1]) > 1e-3:
        if edges:
            b.remove_items(edges)
        b.create_items(outline_items())
    fps = {ref_of(fp): fp for fp in b.get_footprints()}
    missing = sorted(set(want) - set(fps))
    if missing:
        raise SystemExit(f"not on the board: {missing}")
    # parts with no place yet wait in a grid left of the board, out of the way
    for i, ref in enumerate(sorted(set(fps) - set(want))):
        want[ref] = (-30.0 + (i % 6) * 4.0, 2.0 + (i // 6) * 4.0, 0, "B")
    to_flip = [fps[r] for r, (_, _, _, side) in want.items() if (side == "B") != (fps[r].layer == BoardLayer.BL_B_Cu)]
    if to_flip:
        b.flip_items(to_flip)
        fps = {ref_of(fp): fp for fp in b.get_footprints()}
    changed = []
    for ref, (x, y, rot, side) in want.items():
        fp = fps[ref]
        pos = Vector2.from_xy_mm(*A(x, y))
        if fp.position != pos or abs(((fp.orientation.degrees - rot) + 180) % 360 - 180) > 1e-6:
            fp.position = pos
            fp.orientation = Angle.from_degrees(rot)
            changed.append(fp)
    if changed:
        b.update_items(changed)
    print(f"placed {len(want)} of {len(fps)} parts; moved {len(changed)}, flipped {len(to_flip)}")
    print("parked:", sorted(r for r, v in want.items() if v[0] < -5))
