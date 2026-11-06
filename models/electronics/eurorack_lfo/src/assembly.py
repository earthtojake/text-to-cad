"""Twin Orbit assembled: the board (KiCad's STEP of twin_orbit.kicad_pcb, with its parts), the panel at the
pots' mounting face, a spacer washer under the panel on each jack, a nut on every jack and pot, and a
Davies-style knob on each pot. Every placement comes from the board's own part axes (lib/twin_orbit.py).

The animation "explode" pulls the knobs, the nuts and the panel forward, then puts them back.

The board STEP is KiCad's export, with its origin at the board's top-left corner (the typed export takes no
origin), an input like a vendor STEP; export it again after a board change:
    cad run kicad-cli pcb export step --force --subst-models --user-origin 100x50mm \
        -o STEP/twin_orbit.step twin_orbit.kicad_pcb
Run: cad run src/assembly.py"""

from pathlib import Path

import build123d as bd
from cad import model, step
from cad.build123d import animation

from hardware import hex_nut, knob_body, washer
from panel import panel
from lib.twin_orbit import PANEL_BACK_Z, PANEL_FRONT_Z, PCB_T, panel_parts

BOARD_STEP = Path(__file__).resolve().parent.parent / "STEP" / "twin_orbit.step"
JACK_BODY_TOP = PCB_T + 9.5          # Thonkiconn body (9.0, Thonk drawing) and its 0.5 mm square collar
NUT_T = 2.0
KNOB_LIFT = 1.3                      # the knob clears its pot nut and the bushing (10 + 5 mm above the board)


@model
def board():
    pcb = step.read(BOARD_STEP)
    pcb.label = "board"
    return pcb


@model
def twin_orbit_assembly():
    parts = panel_parts()
    knobs, nuts, spacers = [], [], []
    for p in parts:
        x, y = p["asm"]
        if p["kind"] == "pot":
            k = bd.Pos(x, y, PANEL_FRONT_Z + NUT_T + KNOB_LIFT) * bd.Rot(0, 0, -135) * knob_body()
            k.label = f"knob_{p['ref']}"
            knobs.append(k)
            n = bd.Pos(x, y, PANEL_FRONT_Z) * hex_nut(10.0, NUT_T, 7.05, f"nut_{p['ref']}")
            nuts.append(n)
        elif p["kind"] == "jack":
            n = bd.Pos(x, y, PANEL_FRONT_Z) * hex_nut(8.0, NUT_T, 6.05, f"nut_{p['ref']}")
            nuts.append(n)
            s = bd.Pos(x, y, JACK_BODY_TOP) * washer(8.6, 6.3, PANEL_BACK_Z - JACK_BODY_TOP, f"spacer_{p['ref']}", "#3a3a3a")
            spacers.append(s)
    front = panel().shape
    front.label = "panel"
    kit = bd.Compound(children=[board().shape, front, bd.Compound(children=spacers, label="spacers"),
                                bd.Compound(children=nuts, label="nuts"), bd.Compound(children=knobs, label="knobs")],
                      label="twin_orbit")
    show = animation(kit, "explode", duration=6)
    show.translation("knobs", by=(0, 0, 36), start=0.5, end=2.2)
    show.translation("nuts", by=(0, 0, 24), start=0.8, end=2.4)
    show.translation("panel", by=(0, 0, 14), start=1.1, end=2.6)
    show.translation("knobs", by=(0, 0, -36), start=4.0, end=5.6)
    show.translation("nuts", by=(0, 0, -24), start=3.8, end=5.4)
    show.translation("panel", by=(0, 0, -14), start=3.6, end=5.2)
    return kit


if __name__ == "__main__":
    board()
    twin_orbit_assembly()
