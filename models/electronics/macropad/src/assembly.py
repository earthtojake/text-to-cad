"""Nine, assembled: the tray, the board with its parts (KiCad's STEP export, read as an xbf), the switch
plate, nine MX switches, nine keycaps and the knob, each where the board puts it. Its animation lifts
the layers apart in order (board, plate, switches, caps, knob), holds, and sets them back.

    cad run src/assembly.py
    cad model export <id> STEP/nine.step GLB/nine.glb

The board is KiCad's STEP of it with every part, converted once to an xbf (README: "Rebuild"):
`cad kicad_pcb export macropad.kicad_pcb --to step -o STEP`, then `cad step export STEP/macropad.step
XBF/macropad.xbf`. Export both again after a board change.
"""
from pathlib import Path

import build123d as bd
from cad import model, xbf
from cad.build123d import animation

from lib import board_geometry
from case import KEYCAP_Z, KNOB_Z, THICK, keycap, knob, plate, tray
from vendor_parts import mx_switch

BOARD_XBF = Path(__file__).resolve().parent.parent / "XBF" / "macropad.xbf"


@model
def nine():
    g = board_geometry.read()
    pcb = xbf.read(BOARD_XBF)
    pcb.label = "board"
    sw, cap = mx_switch().shape, keycap().shape
    switches, caps = [], []
    for ref in sorted(g["keys"], key=lambda r: int(r[2:])):
        x, y = g["keys"][ref]
        s = bd.Pos(x, y, THICK) * sw
        s.label = f"switch_{ref[2:]}"
        c = bd.Pos(x, y, KEYCAP_Z) * cap
        c.label = f"cap_{ref[2:]}"
        switches.append(s)
        caps.append(c)
    sx, sy = g["encoder"]["shaft"]
    k = bd.Pos(sx, sy, KNOB_Z) * bd.Rot(0, 0, g["encoder"]["rotation"]) * knob().shape
    k.label = "knob"
    t, p = tray().shape, plate().shape
    t.label, p.label = "tray", "plate"
    nine = bd.Compound(children=[t, pcb, p, bd.Compound(children=switches, label="switches"),
                                 bd.Compound(children=caps, label="caps"), k], label="nine")

    show = animation(nine, "explode", duration=9)
    lift = [("board", 12), ("plate", 14), ("switches", 14), ("caps", 14), ("knob", 10)]
    above = ["board", "plate", "switches", "caps", "knob"]
    for i, (name, dz) in enumerate(lift):        # each layer rises, carrying everything above it
        for part in above[i:]:
            show.translation(part, by=(0, 0, dz), start=0.3 + 0.7 * i, end=0.3 + 0.7 * (i + 1))
    for i, (name, dz) in enumerate(reversed(lift)):   # and back down, top first
        layer = len(lift) - 1 - i
        for part in above[layer:]:
            show.translation(part, by=(0, 0, -dz), start=5.2 + 0.7 * i, end=5.2 + 0.7 * (i + 1))
    return nine


LIFT = {"board": 12, "plate": 26, "switches": 40, "caps": 54, "knob": 64}   # the explode's end, for a still


@model
def nine_exploded():
    """The explode's open pose as a model of its own (a snapshot never plays an animation)."""
    parts = []
    for child in nine().shape.children:
        moved = bd.Pos(0, 0, LIFT.get(child.label, 0)) * child
        moved.label = child.label
        parts.append(moved)
    return bd.Compound(children=parts, label="nine_exploded")


if __name__ == "__main__":
    nine()
    nine_exploded()
