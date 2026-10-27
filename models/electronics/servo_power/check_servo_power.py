"""Checks servo_power.kicad_pcb the way the pcb skill's checks do: no detours, decoupling at
the regulator's pins, a ground via beside every surface-mount ground pad, the signal bus at one
spacing, and ground under every top-layer signal. Prints what fails as board references
(`#U1.3`, `#net:S2`); prints nothing when the board is clean.

    python check_servo_power.py [board.kicad_pcb]
"""
import math
import sys
from pathlib import Path

from cadgen.engine.formats.kicad.board_index import read_board
from cadgen.engine.formats.kicad.geometry import inside

board = read_board(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("servo_power.kicad_pcb"))
POWER = {"+5V", "+3V3"}  # U1's input and output
BUS = ["S1", "S2", "S3"]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def shortest_tree(points):
    left, total, tree = list(points[1:]), 0.0, [points[0]]
    while left:
        d, p = min((min(dist(p, t) for t in tree), p) for p in left)
        total, left = total + d, [q for q in left if q is not p]
        tree.append(p)
    return total


# No detours: each net's routed length under 1.3x the shortest tree through its pads.
for net in board.nets:
    if len(net.pads) < 2 or not net.tracks:
        continue
    routed = sum(dist(a, b) for track in net.tracks for a, b in zip(track.points, track.points[1:]))
    shortest = shortest_tree([pad.at for pad in net.pads])
    if routed > 1.3 * shortest:
        print(f"{net.selector}: {routed:.1f} mm routed for {shortest:.1f} mm between {' '.join(pad.selector for pad in net.pads)}")

# Decoupling: a capacitor pad on each regulator power pin's net within 3 mm. A pin of several
# pads (U1's pin 2 is the pin and the tab) is decoupled at whichever of its pads is nearest.
for part in board.parts:
    if not part.ref.startswith("U"):
        continue
    pins = {}
    for pad in part.pads:
        if pad.net in POWER:
            pins.setdefault(pad.number, []).append(pad)
    for number, pin in pins.items():
        caps = [p for p in board.net(pin[0].net).pads if p.part.startswith("C")]
        near = min(((dist(c.at, q.at), q, c) for q in pin for c in caps), default=None, key=lambda found: found[0])
        if near is None or near[0] > 3.0:
            print(f"{pin[0].selector}: nearest capacitor " + (f"{near[2].selector} {near[0]:.2f} mm away" if near else "none"))

# Ground vias: every surface-mount ground pad within 1.5 mm of a ground via.
gnd = board.net("GND")
for pad in gnd.pads:
    if pad.side == "both":
        continue
    near = min((dist(pad.at, via.at) for via in gnd.vias), default=math.inf)
    if near > 1.5:
        print(f"{pad.selector}: nearest GND via {near:.2f} mm away")


# The bus: adjacent signals' parallel, overlapping runs all at one spacing.
def runs(net):
    return [(a, b) for track in net.tracks for a, b in zip(track.points, track.points[1:])]


for first, second in zip(BUS, BUS[1:]):
    spacings = set()
    for a0, a1 in runs(board.net(first)):
        for b0, b1 in runs(board.net(second)):
            ua, ub = (a1[0] - a0[0], a1[1] - a0[1]), (b1[0] - b0[0], b1[1] - b0[1])
            if abs(ua[0] * ub[1] - ua[1] * ub[0]) > 1e-6 * dist(a0, a1) * dist(b0, b1):
                continue  # not parallel
            la = dist(a0, a1)
            offset = abs((b0[0] - a0[0]) * ua[1] - (b0[1] - a0[1]) * ua[0]) / la
            along = sorted(((p[0] - a0[0]) * ua[0] + (p[1] - a0[1]) * ua[1]) / la for p in (b0, b1))
            if along[1] > 0 and along[0] < la:  # the runs overlap along the bus
                spacings.add(round(offset, 2))
    if len(spacings) != 1:
        print(f"#net:{first} to #net:{second}: spacings {sorted(spacings) or 'none (no parallel runs)'}")

# Ground under every top-layer signal: the bottom pour beneath it, sampled every 0.5 mm from
# 2 mm in at each end (pads and vias cut the pour where a segment ends).
fills = [fill for zone in board.zones if (zone.layer, zone.net) == ("B.Cu", "GND") for fill in zone.fills]
for track in board.tracks:
    if track.layer != "F.Cu" or track.net in ("GND", None):
        continue
    for a, b in zip(track.points, track.points[1:]):
        length = math.dist(a, b)
        for along in [2.0 + 0.5 * i for i in range(int((length - 4.0) / 0.5) + 1)]:
            p = (a[0] + (b[0] - a[0]) * along / length, a[1] + (b[1] - a[1]) * along / length)
            if not any(inside(p, fill) for fill in fills):
                print(f"#net:{track.net}@x{p[0]:.1f}y{p[1]:.1f}: no GND on B.Cu under it")
                break
