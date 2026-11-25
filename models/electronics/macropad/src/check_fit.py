"""Does the case fit the board? Overlap volume between every printed or bought part and every solid of
the board's STEP (its parts included), and the clearances the case was designed to: board edge to
tray wall, tallest bottom part to the tray floor, encoder body to the knob, switch housing to the plate
cut-out, keycap skirt to switch housing. Run: cad run src/check_fit.py   (exits 1 on any overlap)"""
import build123d as bd
from cad.build123d import closest_points, overlap_volume

from assembly import nine
from case import CUT, FLOOR_TOP, GAP, KEYCAP_Z, KNOB_Z, PLATE_BOT


def world_parts(node, parent=None):
    here = (bd.Location() if parent is None else parent) * node.location
    if node.children:
        for child in node.children:
            yield from world_parts(child, here)
    else:
        part = node.moved(here * node.location.inverse()) if parent is not None else node
        part.label = node.label
        yield part


tree = nine().shape
groups = {c.label: c for c in tree.children}
board = [p for p in world_parts(groups["board"])]
board_solids = [(p.label, s) for p in board for s in p.solids()]


def solids(label):
    return [(p.label, s) for p in world_parts(groups[label]) for s in p.solids()]


def boxes_touch(a, b, pad=0.01):
    A, B = a.bounding_box(), b.bounding_box()
    return not (A.max.X < B.min.X - pad or B.max.X < A.min.X - pad or A.max.Y < B.min.Y - pad or
                B.max.Y < A.min.Y - pad or A.max.Z < B.min.Z - pad or B.max.Z < A.min.Z - pad)


bad, pairs = [], 0
case_parts = {name: solids(name) for name in ("tray", "plate", "switches", "caps", "knob")}
checks = [(name, board_solids) for name in case_parts]
checks += [("switches", case_parts["plate"]), ("caps", case_parts["switches"]), ("caps", case_parts["plate"]),
           ("knob", case_parts["plate"]), ("tray", case_parts["plate"])]
for name, others in checks:
    for la, a in case_parts[name]:
        for lb, b in others:
            if not boxes_touch(a, b):
                continue
            pairs += 1
            v = overlap_volume(a, b)
            if v > 1e-6:
                bad.append((la, lb, round(v, 4)))
print(f"{pairs} pairs whose boxes meet; overlaps: {bad if bad else 'none'}")

# clearances
pcb = max(board, key=lambda p: p.volume)          # the bare board (the largest solid)
bb = pcb.bounding_box()
low = min(s.bounding_box().min.Z for _, s in board_solids)
print(f"board {bb.size.X:.2f} x {bb.size.Y:.2f} x {bb.size.Z:.2f} mm; lowest part at z {low:.2f}; "
      f"tray floor at z {FLOOR_TOP}: {low - FLOOR_TOP:.2f} mm under the lowest part")
tray = groups["tray"]
print(f"board edge to tray wall: {GAP} mm by design; measured {closest_points(pcb, tray).distance:.3f} mm "
      "(0 = the board rests on the bosses)")
plate = groups["plate"]
print(f"board top to plate underside: {PLATE_BOT - bb.max.Z:.2f} mm (MX: 3.5)")
enc = [s for l, s in board_solids if "EC11" in l or "Alps" in l or "ec11" in l.lower()]
knob = groups["knob"]
if enc:
    print(f"knob to encoder: {min(closest_points(knob, e).distance for e in enc):.2f} mm (the shaft in the bore)")
caps = [p for p in world_parts(groups["caps"])]
sw = [p for p in world_parts(groups["switches"])]
print(f"keycap to its switch: {closest_points(caps[0], sw[0]).distance:.2f} mm; plate cut-out {CUT} mm for a 13.9 mm housing")
if bad:
    raise SystemExit(f"{len(bad)} overlapping pair(s)")
