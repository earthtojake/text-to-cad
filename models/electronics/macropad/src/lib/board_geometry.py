"""What the case is built around, read from the board file itself (macropad.kicad_pcb), never retyped:
the outline, the mounting holes, each key switch, the encoder's shaft and body, the USB receptacle's
mating face, the BOOT and RESET buttons. Move one on the board, run the case again, and the case
follows.

Frame: the board's STEP export (KiCad's own): x as the board's, y = -(the board's y), z = 0 at the
board's bottom face, z = 1.6 at its top.
"""
import math
from pathlib import Path

from cad import kicad_pcb

BOARD_FILE = Path(__file__).resolve().parents[2] / "macropad.kicad_pcb"   # the project folder's
THICK = 1.6


def _xy(p):
    return (round(p[0], 4), round(-p[1], 4))


def _area(poly):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])) / 2


def read():
    b = kicad_pcb.read(str(BOARD_FILE))
    outline = max(b.outline, key=lambda poly: abs(_area(poly)))
    g = {"outline": [_xy(p) for p in outline]}
    g["holes"] = {h.part: (_xy(h.at), h.diameter) for h in b.holes if h.part.startswith("H")}
    g["keys"] = {p.ref: _xy(p.at) for p in b.parts if p.ref in {f"SW{i}" for i in range(1, 10)}}
    enc = b.part("SW10")
    th = math.radians(enc.rotation or 0)
    fx, fy = 7.5, 2.5                      # the shaft, in the footprint's frame (pad A at its origin)
    sx = enc.at[0] + fx * math.cos(th) + fy * math.sin(th)
    sy = enc.at[1] - fx * math.sin(th) + fy * math.cos(th)
    quarter = round((enc.rotation or 0) / 90) % 2 == 1
    # the shaft's D-flat faces the footprint's +x, turned with it (the knob's bore turns to match)
    g["encoder"] = {"shaft": _xy((sx, sy)), "body": (12.4, 11.7) if quarter else (11.7, 12.4),
                    "rotation": enc.rotation or 0}
    # the receptacle's mating face: its footprint's "PCB Edge" line, 3.675 mm from its origin, on the
    # side away from its pads
    j1 = b.part("J1")
    pads_y = sum(p.at[1] for p in j1.pads if p.number.startswith("A")) / 8
    face_y = j1.at[1] - 3.675 if pads_y > j1.at[1] else j1.at[1] + 3.675
    g["usb"] = {"x": round(j1.at[0], 4), "face_y": round(-face_y, 4)}
    g["buttons"] = {r: _xy(b.part(r).at) for r in ("SW11", "SW12")}
    xs = [p[0] for p in g["outline"]]
    ys = [p[1] for p in g["outline"]]
    g["box"] = (min(xs), min(ys), max(xs), max(ys))
    # the outline is a rounded rectangle: its corner radius, where the straight top edge begins
    top = [x for x, y in g["outline"] if abs(y - max(ys)) < 1e-6]
    g["corner"] = round(min(top) - min(xs), 3)
    return g
