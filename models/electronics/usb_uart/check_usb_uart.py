"""Checks usb_uart.kicad_pcb the way the pcb skill's checks do: no detours, decoupling at the
bridge's and the ESD diode's supply pins, and a ground via beside every surface-mount ground pad.
The USB pair's coupling and skew are DRC rules (usb_uart.kicad_dru). Prints what fails as board
references (`#U1.3`, `#net:DTR`); prints nothing when the board is clean.

    python check_usb_uart.py [board.kicad_pcb]
"""
import math
import sys
from pathlib import Path

from cadgen.engine.formats.kicad.board_index import read_board

board = read_board(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("usb_uart.kicad_pcb"))
# Supply pins: the bridge's VIO (1), VDD5 (3) and V3 (6), the ESD diode's VBUS (5). The bridge's
# VBUS pin (9) only senses the bus, so it draws nothing to decouple.
POWER = {"U1": {"1", "3", "6"}, "U2": {"5"}}


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

# Decoupling: a capacitor pad on each supply pin's net within 3 mm.
for part in board.parts:
    if part.ref not in POWER:
        continue
    pins = {}
    for pad in part.pads:
        if pad.number in POWER[part.ref]:
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
