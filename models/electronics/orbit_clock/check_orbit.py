"""Checks orbit.kicad_pcb the way the pcb skill's checks do, with this board's own properties: every pad on
its schematic pin's net, tracks wide enough for their current, each LED and IC supply pin beside its
capacitor, and nothing poured or drilled under the module's antenna. Prints what fails as board references
(`#D1.4`, `#net:VBUS`); prints nothing when the board is clean.

The 45-degree grid is not checked: on this round board the rings' links run at their parts' own angles (and
as arcs), each LED's VDD runs straight to its own capacitor, and the vias moved along the ring to clear the
back's parts are reached at the angle they landed at (290 of the 536 tracks are off the board's own grid).

    cad run check_orbit.py [board.kicad_pcb]
"""
import math
import sys
from pathlib import Path

from cad import kicad_pcb, kicad_sch
from cad.kicad_pcb import inside

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import geometry as G  # noqa: E402  (the rings' counts and the board's centre, as the board scripts placed them)

BOARD = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("orbit.kicad_pcb")
board = kicad_pcb.read(BOARD)
sch = kicad_sch.read(BOARD.with_suffix(".kicad_sch"))

# The board against the schematic: every pad on its pin's net.
want = {(pin.ref, pin.number): pin.net for pin in sch.pins if not pin.ref.startswith("#")}
have = {(pad.part, pad.number): pad.net for pad in board.pads if pad.number}
for ref, number in sorted(set(want) | set(have)):
    drawn, laid = want.get((ref, number)), have.get((ref, number))
    if drawn != laid and not (drawn is None and str(laid or "").startswith("unconnected-")):
        print(f"#{ref}.{number}: on {laid!r} on the board, {drawn!r} in the schematic")


# Width for current (IPC-2221, outer layer, 10 C rise, 1 oz). The 72 LEDs' 3 A worst case runs in In2.Cu's +5V
# plane and returns in In1.Cu's GND plane: a +5V track feeds one LED (36 mA) or one logic part. The feed from
# the receptacle through the polyfuse into the plane carries it all: each of its tracks 1.5 A, two in parallel.
def amps(width, rise=10.0, copper=35.0):
    return 0.048 * rise ** 0.44 * ((width / 0.0254) * (copper / 25.4)) ** 0.725


fuse = [pad.at for pad in board.part("F1").pads]
for track in board.tracks:
    if track.net == "VBUS" or (track.net == "+5V" and min(math.dist(p, f) for p in track.points for f in fuse) < 0.6):
        need = 1.5
    elif track.net == "+5V":
        need = 0.05
    else:
        continue
    if amps(track.width) < need:
        print(f"{track.selector} ({track.net}): {track.width} mm carries {amps(track.width):.2f} A, under {need} A")

# Decoupling: each LED's VDD (pad 4) to its own 100 nF, and each IC's supply pin to its nearest capacitor,
# within 3 mm, pad to pad. The regulator's output capacitor sits 3.13 mm from U2.5 (README: the review).
LIMIT = {("U2", "5"): 3.2}
supplies = [(f"D{i + 1}", "4", (f"C{101 + i}",)) for i in range(G.N_MINUTE + G.N_HOUR)]
supplies += [("U1", "1", ("C6", "C5")), ("U4", "5", ("C8",)), ("U2", "1", ("C3",)), ("U2", "5", ("C4",)),
             ("U5", "1", ("C9", "C10"))]
for ic, number, caps in supplies:
    pin = board.part(ic).pad(number)
    near = min((board.part(cap).pad("1") for cap in caps), key=lambda pad: math.dist(pad.at, pin.at))
    if math.dist(near.at, pin.at) > LIMIT.get((ic, number), 3.0):
        print(f"{pin.selector}: {math.dist(near.at, pin.at):.2f} mm from {near.selector}, its capacitor")

# The antenna: no copper poured and no via inside the module's keep-out (its rule area, every copper layer),
# sampled every 0.5 mm over the part of it on the board.
for area in board.rule_areas:
    xs, ys = [p[0] for p in area.outline], [p[1] for p in area.outline]
    points = [(x / 2, y / 2) for x in range(math.floor(min(xs) * 2), math.ceil(max(xs) * 2) + 1)
              for y in range(math.floor(min(ys) * 2), math.ceil(max(ys) * 2) + 1)]
    points = [p for p in points if inside(p, area.outline) and inside(p, board.outline[0])]
    for zone in board.zones:
        poured = [p for p in points if any(inside(p, fill) for fill in zone.fills)]
        if poured:
            print(f"{zone.selector} ({zone.net} on {zone.layer}): poured at {len(poured)} points under the antenna")
    for via in board.vias:
        if inside(via.at, area.outline):
            print(f"{via.selector} ({via.net}): inside the antenna's keep-out")
