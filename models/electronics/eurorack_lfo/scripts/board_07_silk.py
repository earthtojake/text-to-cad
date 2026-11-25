# /// script
# dependencies = ["shapely"]
# ///
"""Step 7: references that read. Every reference (JLCPCB's minimum legible text, 1.0 mm with a 0.15 mm stroke) is
put at the nearest free spot around its part (above, below, beside, or on the body where no pad is), clear of
every pad and mask opening, every other silkscreen line and reference, and the board edge. A part with no free spot
keeps its reference on the fabrication layer only (it stays in the assembly drawing). Run: cad run scripts/board_07_silk.py"""
import sys
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD, H, W, X0, Y0  # noqa: E402

from cad import kicad_pcb  # noqa: E402
from kicode.geometry import Vector2  # noqa: E402

SIZE, STROKE, GAP = 1.0, 0.15, 0.15    # every footprint's reference is already 1.0 mm / 0.15 mm
board = kicad_pcb.read(BOARD)
inner = box(X0 + 0.5, Y0 + 0.5, X0 + W - 0.5, Y0 + H - 0.5)


def side_of(layer):
    return "F" if layer.startswith("F") else "B"


copper = {"F": [], "B": []}
for pad in board.pads:
    poly = Polygon(pad.polygon).buffer(GAP)
    for s in ("F", "B") if pad.drill or pad.side == "both" else (side_of(pad.side.replace("top", "F").replace("bottom", "B")),):
        copper[s].append(poly)
silk = {"F": [], "B": []}
crt = {}
for s in board.shapes:
    if s.layer in ("F.SilkS", "B.SilkS") and len(s.points) > 1:
        silk[s.layer[0]].append(LineString(s.points).buffer((s.width or 0.12) / 2 + GAP))
    if s.layer in ("F.CrtYd", "B.CrtYd") and s.part:
        crt.setdefault(s.part, []).extend(s.points)
blocked = {k: unary_union(copper[k] + silk[k]) for k in "FB"}

placed = {"F": [], "B": []}
moves, hidden = {}, []
with kicad_pcb.edit(BOARD) as b:
    fps = {fp.reference_field.text.value: fp for fp in b.get_footprints()}
    # KiCad's stroke font: about 0.85 x size per character plus the stroke (a field has no id to ask KiCad's box)
    ext = {ref: (0.85 * SIZE * len(ref) + STROKE, SIZE + STROKE) for ref in fps}
    # big parts first: they have the fewest spots
    order = sorted(fps, key=lambda r: -len(board.part(r).pads))
    for ref in order:
        part = board.part(ref)
        s = "B" if part.side == "bottom" else "F"
        pts = crt.get(ref) or [p.at for p in part.pads]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        w, h = ext[ref]
        cands = [(cx, cy, 0), (cx, cy, 90)]
        # a field's text angle set over the API is not saved: each reference keeps the angle KiCad
        # gave it (its part's rotation), so only spots in that orientation count
        turn = round(fps[ref].reference_field.text.attributes.angle) % 180
        for d in (0.0, 0.4, 0.8, 1.4):
            for slide in (0, -1, 1, -2, 2):
                cands += [(cx + slide, y0 - d - h / 2, 0), (cx + slide, y1 + d + h / 2, 0),
                          (x0 - d - h / 2, cy + slide, 90), (x1 + d + h / 2, cy + slide, 90)]
        mine = unary_union(placed[s]) if placed[s] else None
        for x, y, a in [c for c in cands if c[2] == turn]:
            rect = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2) if a == 0 else box(x - h / 2, y - w / 2, x + h / 2, y + w / 2)
            if not inner.contains(rect) or rect.intersects(blocked[s]) or (mine is not None and rect.buffer(GAP).intersects(mine)):
                continue
            placed[s].append(rect)
            moves[ref] = (x, y, a)
            break
        else:
            hidden.append(ref)
    for ref, fp in fps.items():
        f = fp.reference_field
        if ref in moves:
            x, y, a = moves[ref]
            f.text.position = Vector2.from_xy_mm(x, y)
            f.visible = True
        else:
            f.visible = False
    b.update_items(list(fps.values()))
print(f"references placed {len(moves)}, kept on the fabrication layer only {len(hidden)}: {sorted(hidden)}")
