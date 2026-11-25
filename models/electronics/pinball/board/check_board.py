# /// script
# dependencies = ["shapely>=2"]
# ///
"""The board's own properties, measured from the saved files; prints what breaks, then a summary. DRC and ERC stay
the authority on rules. Run from this folder: cad run check_board.py

  - every pad on its schematic pin's net (pin by pin);
  - every straight track segment at a multiple of 45 degrees;
  - each power net's width for its current (IPC-2221, the skill's formula), its necks by the pads reported;
  - each IC's decoupling capacitors, pad to pad;
  - ground under the USB pair.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

from cad import kicad_pcb, kicad_sch

HERE = Path(__file__).resolve().parent
sch, board = kicad_sch.read(str(HERE / "pinball.kicad_sch")), kicad_pcb.read(str(HERE / "pinball.kicad_pcb"))
problems = 0

# 1. pin by pin
want = {(pin.ref, pin.number): pin.net for pin in sch.pins if not pin.ref.startswith("#")}
have = {}
for part in board.parts:
    for pad in part.pads:
        if pad.number:
            have[(part.ref, pad.number)] = pad.net
differ = [k for k in sorted(set(want) | set(have)) if want.get(k) != have.get(k) and not (want.get(k) or "").startswith("unconnected")]
for k in differ[:20]:
    print("pin", k, "schematic:", want.get(k), "board:", have.get(k))
print(f"board vs schematic: {len(want)} pins, {len(differ)} differ")
problems += len(differ)

# 2. octolinear
off = []
length = defaultdict(float)
widths = defaultdict(list)
for t in board.tracks:
    pts = t.points
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if t.arc:
            continue
        a = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 45
        if min(a, 45 - a) > 0.5 and math.dist((x0, y0), (x1, y1)) > 0.1:   # joins under 0.1 mm meet a via off the grid
            off.append((t.net, t.layer, round(x0, 2), round(y0, 2)))
        length[t.net] += math.dist((x0, y0), (x1, y1))
        widths[t.net].append((t.width, math.dist((x0, y0), (x1, y1))))
print(f"segments off 45 degrees: {len(off)}", off[:6])
print(f"copper: {sum(length.values()) / 1000:.2f} m, {len(board.tracks)} segments, {len(board.vias)} vias")
problems += len(off)


# 3. width for current (IPC-2221, outer 1 oz, 10 C rise: the skill's formula); inner layers derated (k 0.024, 0.5 oz)
def amps(width_mm, rise_c=10.0, copper_um=35.0, k=0.048):
    return k * rise_c ** 0.44 * ((width_mm / 0.0254) * (copper_um / 25.4)) ** 0.725


# peak currents from ../src/physics.py: 2.02 A at 9 V (coils 1.13 A + the buck's input), 1.45 A on the 5 V rail
NEEDS = {"+9V": 2.02, "VBUS": 2.02, "+5V": 1.45, "+3V3": 0.3, "+1V1": 0.1,
         "/Flippers/COIL_L_DRAIN": 0.6, "/Flippers/COIL_R_DRAIN": 0.6, "/Power/BUCK_SW": 1.5}
for net, need in NEEDS.items():
    ws = widths.get(net, [])
    if not ws:
        continue
    main = max(w for w, _ in ws)
    neck = min(w for w, _ in ws)
    print(f"{net}: {main} mm carries {amps(main):.2f} A (needs {need} A), necks to {neck} mm by the pads over "
          f"{sum(ln for w, ln in ws if w < main):.1f} mm in {sum(1 for w, _ in ws if w < main)} short runs")
    if amps(main) < need:
        print(f"  narrow: {net}")
        problems += 1

# 4. decoupling, pad to pad
caps = {("U1", "1", "C20"), ("U1", "10", "C21"), ("U1", "22", "C22"), ("U1", "23", "C30"), ("U1", "33", "C23"), ("U1", "42", "C24"),
        ("U1", "49", "C25"), ("U1", "48", "C26"), ("U1", "50", "C31"), ("U1", "43", "C27"), ("U1", "44", "C28"), ("U1", "45", "C29"),
        ("U2", "8", "C32"), ("U5", "3", "C3"), ("U6", "1", "C7"), ("U6", "5", "C8"), ("U7", "5", "C50"), ("U8", "7", "C71"), ("U9", "14", "C40")}
for ref, pin, cap in sorted(caps):
    p = board.part(ref).pad(pin)
    c = board.part(cap).pad("1")
    d = math.dist(p.at, c.at)
    print(f"  {ref}.{pin} - {cap}: {d:.2f} mm" + ("" if d <= 8.0 else "  (review: over 8 mm)"))

# 5. ground under the USB pair
from cad.kicad_pcb import inside  # noqa: E402

fills = [f for z in board.zones if z.net == "GND" and z.layer == "In1.Cu" for f in z.fills]
missing = 0
for t in board.tracks:
    if t.net and "USB" in t.net and "U1" not in t.net and t.layer == "B.Cu":
        for (x0, y0), (x1, y1) in zip(t.points, t.points[1:]):
            for i in range(max(1, int(math.dist((x0, y0), (x1, y1)) / 0.5)) + 1):
                n = max(1, int(math.dist((x0, y0), (x1, y1)) / 0.5))
                pt = (x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n)
                if not any(inside(pt, f) for f in fills):
                    missing += 1
print(f"USB pair: {missing} sample points without the In1 plane under them")
lp = sum(length[n] for n in ("/Power/USB_D+", "Net-(U1-USB_DP)"))
lm = sum(length[n] for n in ("/Power/USB_D-", "Net-(U1-USB_DM)"))
print(f"USB pair: D+ {lp:.1f} mm, D- {lm:.1f} mm of track from the connector to U1 (skew {abs(lp - lm):.1f} mm; full speed tolerates it)")
print(f"{'clean' if not problems else f'{problems} problems'}")
sys.exit(1 if problems else 0)
