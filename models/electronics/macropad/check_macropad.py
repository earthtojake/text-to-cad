"""Checks macropad.kicad_pcb the way the pcb skill's checks do, with this board's own properties: every
pad on its schematic pin's net, segments at 45-degree steps, no detours on two-pad nets, tracks wide
enough for their current, each decoupler beside the pin it serves, and ground under the USB pairs.
Prints what fails as board references (`#C13.1`, `#net:+5V`); prints nothing when the board is clean.

    cad run check_macropad.py [board.kicad_pcb]
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

from cad import kicad_pcb, kicad_sch
from cad.kicad_pcb import inside

BOARD = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("macropad.kicad_pcb")
board = kicad_pcb.read(BOARD)
sch = kicad_sch.read(BOARD.with_suffix(".kicad_sch"))

# The board against the schematic: every pad on its pin's net.
want = {(pin.ref, pin.number): pin.net for pin in sch.pins if not pin.ref.startswith("#")}
have = {}
for pad in board.pads:
    have.setdefault((pad.part, pad.number), pad.net)
for ref, number in sorted(set(want) | set(have)):
    drawn, laid = want.get((ref, number)), have.get((ref, number))
    if drawn != laid and not (drawn is None and laid in (None, "")):
        print(f"#{ref}.{number}: on {laid!r} on the board, {drawn!r} in the schematic")

# Octolinear: every straight segment at a multiple of 45 degrees (arcs excluded).
for track in board.tracks:
    if track.arc:
        continue
    for (x0, y0), (x1, y1) in zip(track.points, track.points[1:]):
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 45
        if min(angle, 45 - angle) > 0.5:
            print(f"{track.selector} ({track.net}): a segment {angle:.1f} degrees off the 45-degree grid")

# Detours: a two-pad net's copper under 1.6x the straight line between its pads. CC2 hops under the
# receptacle to R2 on purpose: the receptacle's own pads stand in the direct path.
DETOURS = {"/USB & Power/CC2"}
length = defaultdict(float)
for track in board.tracks:
    length[track.net] += sum(math.dist(a, b) for a, b in zip(track.points, track.points[1:]))
for net in board.nets:
    if len(net.pads) != 2 or net.name in DETOURS:
        continue
    straight = math.dist(net.pads[0].at, net.pads[1].at)
    if straight > 1 and length[net.name] / straight > 1.6:
        print(f"{net.selector}: {length[net.name]:.1f} mm routed for {straight:.1f} mm between its pads")


# Width for current (IPC-2221, outer layer, 10 C rise, 1 oz): the nine LEDs at full white draw 0.54 A
# from +5V; the RP2040 and the flash 0.1 A from +3V3.
def amps(width, rise=10.0, copper=35.0):
    return 0.048 * rise ** 0.44 * ((width / 0.0254) * (copper / 25.4)) ** 0.725


NEEDS = {"+5V": 0.6, "VBUS": 0.6, "+3V3": 0.1, "+1V1": 0.05}
for track in board.tracks:
    if track.net in NEEDS and amps(track.width) < NEEDS[track.net]:
        print(f"{track.selector} ({track.net}): {track.width} mm carries {amps(track.width):.2f} A, "
              f"under {NEEDS[track.net]} A")

# Decoupling: each capacitor's supply pad within 3 mm of the pin it serves, pad to pad. C13 (USB_VDD and
# IOVDD 49) sits 4.5 mm up their shared stub: the place beside the pins holds the USB pair and the QSPI
# fan-out (README: the review).
SERVES = {"C7": ("U1", "1"), "C8": ("U1", "10"), "C10": ("U1", "33"), "C11": ("U1", "42"), "C13": ("U1", "48"),
          "C14": ("U1", "43"), "C15": ("U1", "44"), "C16": ("U1", "45"), "C17": ("U1", "23"), "C4": ("U2", "8"),
          "C1": ("U3", "1"), "C2": ("U3", "5"), "C28": ("U5", "5")}
SERVES.update({f"C{19 + k}": (f"D{k + 1}", "3") for k in range(9)})
LIMIT = {"C13": 5.0}
for cap, (ic, number) in SERVES.items():
    pad, pin = board.part(cap).pad("1"), board.part(ic).pad(number)
    if math.dist(pad.at, pin.at) > LIMIT.get(cap, 3.0):
        print(f"{pad.selector}: {math.dist(pad.at, pin.at):.2f} mm from {pin.selector}, which it decouples")

# The USB pairs, routed on B.Cu: the F.Cu ground pour under every point of them, every 0.25 mm.
fills = [fill for zone in board.zones if (zone.layer, zone.net) == ("F.Cu", "GND") for fill in zone.fills]
for name in ("/USB & Power/USB_D+", "/USB & Power/USB_D-", "/MCU/RP_D+", "/MCU/RP_D-"):
    for track in board.net(name).tracks:
        if track.layer != "B.Cu":
            continue
        for a, b in zip(track.points, track.points[1:]):
            steps = max(1, math.ceil(math.dist(a, b) / 0.25))
            points = [(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps) for i in range(steps + 1)]
            bare = [p for p in points if not any(inside(p, fill) for fill in fills)]
            if bare:
                print(f"{track.selector} ({name}): no GND on F.Cu under ({bare[0][0]:.1f}, {bare[0][1]:.1f})")
                break
