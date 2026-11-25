"""The fit, measured: every solid of the panel and the hardware against every solid of the board (KiCad's STEP
with its parts) and against each other; zero overlap volume is the requirement, and the clearances the design
intends are printed: each bushing to its panel hole, each jack body to the panel's back face, each LED dome to
the panel's front face, and the panel's seat on the pots.
Run: cad run src/check_fit.py"""

import build123d as bd
from cad.build123d import closest_points, overlap_volume

from assembly import twin_orbit_assembly
from lib.twin_orbit import HOLE_D, PANEL_BACK_Z, PANEL_FRONT_Z, panel_parts


def world_parts(node, parent=None):
    here = (bd.Location() if parent is None else parent) * node.location
    if node.children:
        for child in node.children:
            yield from world_parts(child, here)
    else:
        yield node.located(here)


kit = twin_orbit_assembly().shape
groups = {c.label: list(world_parts(c)) for c in kit.children}
board = [s for s in groups["board"] if s.volume > 1e-6]
mine = [(g, s) for g in ("panel", "spacers", "nuts", "knobs") for s in groups[g] if s.volume > 1e-6]
worst = 0.0
pairs = 0
for g, s in mine:
    sb = s.bounding_box()
    for t in board:
        tb = t.bounding_box()
        if sb.min.X > tb.max.X or tb.min.X > sb.max.X or sb.min.Y > tb.max.Y or tb.min.Y > sb.max.Y or sb.min.Z > tb.max.Z or tb.min.Z > sb.max.Z:
            continue
        pairs += 1
        v = overlap_volume(s, t)
        if v > 1e-6:
            print(f"OVERLAP {v:.4f} mm^3: {g}/{s.label} x board/{t.label}")
        worst = max(worst, v)
for i, (g1, a) in enumerate(mine):
    for g2, b in mine[i + 1:]:
        v = overlap_volume(a, b)
        if v > 1e-6:
            print(f"OVERLAP {v:.4f} mm^3: {g1}/{a.label} x {g2}/{b.label}")
        worst = max(worst, v)
print(f"checked {pairs} panel/hardware x board pairs (bounding boxes touching) and {len(mine) * (len(mine) - 1) // 2} hardware pairs; worst overlap {worst:.6f} mm^3")

plate = next(s for s in groups["panel"] if s.label == "plate")
by_name = {}
for t in board:
    by_name.setdefault(t.label, []).append(t)
print("intended clearances:")
for p in panel_parts():
    x, y = p["asm"]
    hole_r = HOLE_D[p["kind"]] / 2
    near = [t for t in board if abs(t.bounding_box().center().X - x) < 6 and abs(t.bounding_box().center().Y - y) < 8
            and t.bounding_box().max.Z > PANEL_BACK_Z]
    gap = min(closest_points(plate, t).distance for t in near) if near else float("nan")
    print(f"  {p['ref']:6s} {p['kind']:4s} hole {2 * hole_r:.1f} mm: nearest board part through the panel {gap:.3f} mm away")
