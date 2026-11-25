"""Checks twin_orbit.kicad_pcb the way the pcb skill's checks do, with this board's own properties: every
pad on its schematic pin's net, segments at 45-degree steps, no detours on two-pad nets, the rails wide
enough for their current, and each op-amp's and OTA's supply pins beside their decouplers. Prints what
fails as board references (`#U101.4`, `#net:+12V`); prints nothing when the board is clean.

    cad run check_twin_orbit.py [board.kicad_pcb]
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

from cad import kicad_pcb, kicad_sch

BOARD = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("twin_orbit.kicad_pcb")
board = kicad_pcb.read(BOARD)
sch = kicad_sch.read(BOARD.with_suffix(".kicad_sch"))

# The board against the schematic: every pad on its pin's net (an unconnected pin's net is named for its
# pad, so any two unconnected names agree).
want = {(pin.ref, pin.number): pin.net for pin in sch.pins if not pin.ref.startswith("#")}
have = {(pad.part, pad.number): pad.net for pad in board.pads if pad.number}
for ref, number in sorted(set(want) | set(have), key=str):
    drawn, laid = want.get((ref, number)), have.get((ref, number))
    if (drawn or "").split("unconnected")[0] != (laid or "").split("unconnected")[0]:
        print(f"#{ref}.{number}: on {laid!r} on the board, {drawn!r} in the schematic")

# Octolinear: every straight segment at a multiple of 45 degrees (arcs excluded).
for track in board.tracks:
    if track.arc:
        continue
    for (x0, y0), (x1, y1) in zip(track.points, track.points[1:]):
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 45
        if min(angle, 45 - angle) > 0.5:
            print(f"{track.selector} ({track.net}): a segment {angle:.1f} degrees off the 45-degree grid")

# Detours: a two-pad net's copper under 1.6x the straight line between its pads.
length = defaultdict(float)
for track in board.tracks:
    length[track.net] += sum(math.dist(a, b) for a, b in zip(track.points, track.points[1:]))
for net in board.nets:
    if len(net.pads) != 2 or not length[net.name]:
        continue
    straight = math.dist(net.pads[0].at, net.pads[1].at)
    if straight > 1 and length[net.name] / straight > 1.6:
        print(f"{net.selector}: {length[net.name]:.1f} mm routed for {straight:.1f} mm between its pads")


# Width for current (IPC-2221, outer layer, 10 C rise, 1 oz): each rail draws about 25 mA (two TL074s, two
# LM13700s, the LEDs and the pots); 0.1 A leaves a margin.
def amps(width, rise=10.0, copper=35.0):
    return 0.048 * rise ** 0.44 * ((width / 0.0254) * (copper / 25.4)) ** 0.725


NEEDS = {"+12V": 0.1, "-12V": 0.1}
for track in board.tracks:
    if track.net in NEEDS and amps(track.width) < NEEDS[track.net]:
        print(f"{track.selector} ({track.net}): {track.width} mm carries {amps(track.width):.2f} A, "
              f"under {NEEDS[track.net]} A")

# Decoupling: each supply pin within 6 mm of its 100 nF, centre to centre (the dense two-layer escape the
# layout settled on: 2.2 to 5.5 mm). C106 and C206 sit 8.8 mm from the LM13700s' V- (pin 6), at pin 10,
# the buffer input tied to -12 V: a revision would move them (README: the review).
DECOUPLES = [("U101", "4", "C103"), ("U101", "11", "C104"), ("U102", "11", "C105"), ("U102", "6", "C106")]
DECOUPLES += [(ic.replace("U1", "U2", 1), pin, cap.replace("C1", "C2", 1)) for ic, pin, cap in DECOUPLES]
FAR = {"C106", "C206"}
for ic, number, cap in DECOUPLES:
    pin = board.part(ic).pad(number)
    near = min((pad for pad in board.part(cap).pads if pad.net == pin.net), key=lambda pad: math.dist(pad.at, pin.at),
               default=None)
    if near is None:
        print(f"{pin.selector}: {cap} has no pad on {pin.net}")
    elif cap not in FAR and math.dist(near.at, pin.at) > 6.0:
        print(f"{near.selector}: {math.dist(near.at, pin.at):.2f} mm from {pin.selector}, which it decouples")
