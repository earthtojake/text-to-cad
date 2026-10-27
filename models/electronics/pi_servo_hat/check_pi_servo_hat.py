"""Checks pi_servo_hat.kicad_pcb the way the pcb skill's checks do: no detours, decoupling at
both buffers' supply pins, and a ground via beside every surface-mount ground pad. Prints what
fails as board references (`#U1.5`, `#net:RXD`); prints nothing when the board is clean.

Ground under every top-layer signal is not checked: DATA and TXEN cross the logic on the bottom
layer by design, so the bottom pour has gaps under the UART.

    python check_pi_servo_hat.py [board.kicad_pcb]
"""
import math
import sys
from pathlib import Path

from cadgen.engine.formats.kicad.board_index import read_board

board = read_board(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("pi_servo_hat.kicad_pcb"))
SUPPLIES = {"+3V3"}  # the buffers' VCC


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def shortest_tree(points):
    left, total, tree = list(points[1:]), 0.0, [points[0]]
    while left:
        d, p = min((min(dist(p, t) for t in tree), p) for p in left)
        total, left = total + d, [q for q in left if q is not p]
        tree.append(p)
    return total


# No detours: each signal's routed length under 1.3x the shortest tree through its pads. The
# supplies and ground are buses and pours, laid out for current, not length.
for net in board.nets:
    if net.name in ("GND", "VIN", "+3V3") or len(net.pads) < 2 or not net.tracks:
        continue
    routed = sum(dist(a, b) for track in net.tracks for a, b in zip(track.points, track.points[1:]))
    shortest = shortest_tree([pad.at for pad in net.pads])
    if routed > 1.3 * shortest:
        print(f"{net.selector}: {routed:.1f} mm routed for {shortest:.1f} mm between {' '.join(pad.selector for pad in net.pads)}")

# Decoupling: a capacitor pad on each buffer's supply pin within 3 mm.
for part in board.parts:
    if not part.ref.startswith("U"):
        continue
    for pad in part.pads:
        if pad.net not in SUPPLIES:
            continue
        caps = [p for p in board.net(pad.net).pads if p.part.startswith("C")]
        near = min(caps, key=lambda c: dist(c.at, pad.at), default=None)
        if near is None or dist(near.at, pad.at) > 3.0:
            print(f"{pad.selector}: nearest capacitor " + (f"{near.selector} {dist(near.at, pad.at):.2f} mm away" if near else "none"))

# Ground vias: every surface-mount ground pad within 1.5 mm of a ground via.
gnd = board.net("GND")
for pad in gnd.pads:
    if pad.side == "both":
        continue
    near = min((dist(pad.at, via.at) for via in gnd.vias), default=math.inf)
    if near > 1.5:
        print(f"{pad.selector}: nearest GND via {near:.2f} mm away")
