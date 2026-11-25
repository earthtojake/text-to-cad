"""Does it fit? The assembly as built: every part of the board's STEP (the PCB and its 172 parts) against the
baffle, the diffuser and the stand, and the printed parts against each other.

    cad run src/check_fit.py

Prints (and writes to tmp/fit.txt) the interference volume of every pair whose envelopes meet (0 everywhere is the pass), and the
clearances the design intends: the baffle over the tallest part in a pocket, the slot round the stack, the
plug pocket round the receptacle.
"""
import sys
from pathlib import Path

import build123d as bd
from cad.build123d import closest_points, overlap_volume

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orbit import orbit  # noqa: E402


def world_parts(node, parent=None):
    here = (bd.Location() if parent is None else parent) * node.location
    if node.children:
        for child in node.children:
            yield from world_parts(child, here)
    else:
        yield node.located(here)


def meets(a, b, pad=0.0):
    p, q = a.bounding_box(optimal=False), b.bounding_box(optimal=False)
    return (p.min.X - pad <= q.max.X and q.min.X - pad <= p.max.X and p.min.Y - pad <= q.max.Y
            and q.min.Y - pad <= p.max.Y and p.min.Z - pad <= q.max.Z and q.min.Z - pad <= p.max.Z)


clock = orbit().shape
groups = {child.label: child for child in clock.children}
printed = {name: [s for p in world_parts(groups[name]) for s in p.solids()] for name in ("baffle", "diffuser", "stand")}
board = [(p.label, s) for p in world_parts(groups["board"]) for s in p.solids()]
print(f"board: {len(board)} solids; printed: " + ", ".join(f"{k} {len(v)}" for k, v in printed.items()))

# Pairwise, each board solid against the part of a printed body near it: the printed body cropped to the
# board solid's envelope grown by 1 mm (a box boolean), then the exact interference and distance on the crop.
import time  # noqa: E402
LOG = Path(__file__).resolve().parent.parent / "tmp" / "fit.txt"
LOG.parent.mkdir(exist_ok=True)
log = open(LOG, "w")


def say(text):
    print(text, flush=True)
    log.write(text + "\n")
    log.flush()


t0 = time.time()
for name, solids in printed.items():
    body = solids[0]
    total, nearest, n = 0.0, [], 0
    for label, s in board:
        if not meets(s, body, 1.0):
            continue
        bb = s.bounding_box()
        box = bd.Pos(bb.center()) * bd.Box(bb.size.X + 2, bb.size.Y + 2, bb.size.Z + 2)
        crop = body & box
        if crop is None or not crop.solids():
            continue
        n += 1
        piece = crop.solids()[0] if len(crop.solids()) == 1 else crop
        v = sum(overlap_volume(s, c) for c in crop.solids())
        total += v
        if v > 1e-6:
            say(f"  INTERFERENCE {label} x {name}: {v:.4f} mm3")
        nearest.append((closest_points(s, piece).distance, label))
    nearest.sort()
    say(f"board x {name}: {n} board solids within 1 mm, interference {total:.6f} mm3; nearest "
        + ", ".join(f"{label} {d:.3f} mm" for d, label in nearest[:6]) + f"  [{time.time() - t0:.0f} s]")
for a, b in (("baffle", "diffuser"), ("baffle", "stand"), ("diffuser", "stand")):
    v = sum(overlap_volume(s, t) for s in printed[a] for t in printed[b] if meets(s, t))
    d = min(closest_points(s, t).distance for s in printed[a] for t in printed[b])
    say(f"{a} x {b}: interference {v:.6f} mm3, closest {d:.3f} mm")
