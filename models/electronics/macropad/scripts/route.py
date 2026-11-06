"""Layout step 3: every track and via on the board, by hand (no autorouter): each net's path as points,
computed from the pads it joins (read back from the board), octolinear. The script states the whole
routing: it removes the board's tracks and vias and writes these, then refills the pours.

Layers: B.Cu (the parts' side) carries the signals and power; F.Cu is a ground pour, crossed by the
key lines in the channels between the key columns (they run under the switches, where nothing else
is) and by a few short hops. Run: cad run scripts/route.py
"""
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE.parent)

from cad import kicad_pcb  # noqa: E402

BOARD = "macropad.kicad_pcb"
R = kicad_pcb.read(BOARD)
PADS = {}
for part in R.parts:
    for pad in part.pads:
        PADS.setdefault((part.ref, pad.number), pad.at)


def P(ref, num):
    x, y = PADS[(ref, str(num))]
    return (round(x, 4), round(y, 4))


TRACKS = []   # (net, layer, width, [points])
VIAS = []     # (net, (x, y))
W_SIG, W_USB, W_SUP, W_PWR = 0.2, 0.25, 0.3, 0.5


def t(net, *pts, w=W_SIG, layer="B.Cu"):
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    TRACKS.append((net, layer, w, pts))


def v(net, xy):
    VIAS.append((net, xy))


def hop(net, a, b, *mid, w=W_SIG):
    """A short F.Cu hop: via at a, F.Cu through mid to b, via at b."""
    v(net, a)
    v(net, b)
    t(net, a, *mid, b, w=w, layer="F.Cu")


def dn(p, d):   # helpers for octolinear steps
    return (p[0], p[1] + d)


def rt(p, d):
    return (p[0] + d, p[1])


def diag(p, dx, dy):
    """A 45-degree step: |dx| == |dy|."""
    assert abs(abs(dx) - abs(dy)) < 1e-6, (dx, dy)
    return (round(p[0] + dx, 4), round(p[1] + dy, 4))


def to45(a, b):
    """From a to b: a 45-degree leg then a straight one (the straight one last)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = min(abs(dx), abs(dy))
    return diag(a, math.copysign(m, dx), math.copysign(m, dy))


# U1's pad rows (the RP2040 at its place, 0.4 mm pitch)
U1x, U1y = P("U1", 57)
OUT = 3.875          # a pad's outer end from the centre
IN = 3.0             # its inner end
LANE = 2.3           # the ring between the pads and the exposed pad


def u1_out(n):
    x, y = P("U1", n)
    if n <= 14:
        return (U1x + OUT, y)
    if n <= 28:
        return (x, U1y + OUT)
    if n <= 42:
        return (U1x - OUT, y)
    return (x, U1y - OUT)


def u1_in(n):
    x, y = P("U1", n)
    if n <= 14:
        return (U1x + IN, y)
    if n <= 28:
        return (x, U1y + IN)
    if n <= 42:
        return (U1x - IN, y)
    return (x, U1y - IN)


import route_strip  # noqa: E402  (the back strip: USB, power, MCU, flash, crystal)
import route_keys   # noqa: E402  (the key lines, LEDs and their power)

route_strip.build(sys.modules[__name__])
route_keys.build(sys.modules[__name__])

if "--dry" in sys.argv:
    print(len(TRACKS), "tracks,", len(VIAS), "vias")
    raise SystemExit

from kicode.board_types import Net, Track, Via  # noqa: E402
from kicode.geometry import Vector2  # noqa: E402
from kicode.proto.board.board_types_pb2 import BoardLayer  # noqa: E402
from kicode.util.units import from_mm  # noqa: E402

LAYER = {"F.Cu": BoardLayer.BL_F_Cu, "B.Cu": BoardLayer.BL_B_Cu}
NETS = {p.net for part in R.parts for p in part.pads if p.net}
for net, *_ in TRACKS + [(n, None) for n, _ in VIAS]:
    if net not in NETS:
        raise SystemExit(f"no net {net!r} on the board")

with kicad_pcb.edit(BOARD) as b:
    old = list(b.get_tracks()) + list(b.get_vias())
    if old:
        b.remove_items(old)
    items = []
    for net, layer, w, pts in TRACKS:
        for a, c in zip(pts, pts[1:]):
            tr = Track()
            tr.start, tr.end = Vector2.from_xy_mm(*a), Vector2.from_xy_mm(*c)
            tr.width, tr.layer, tr.net = from_mm(w), LAYER[layer], Net(name=net)
            items.append(tr)
    for net, (x, y) in VIAS:
        via = Via()
        via.position = Vector2.from_xy_mm(x, y)
        via.diameter, via.drill_diameter, via.net = from_mm(0.6), from_mm(0.3), Net(name=net)
        items.append(via)
    b.create_items(items)
    import zones  # noqa: E402
    zones.ensure(b)
    b.refill_zones()
print(f"{sum(len(p) - 1 for *_, p in TRACKS)} track segments, {len(VIAS)} vias")
