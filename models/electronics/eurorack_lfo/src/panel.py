"""Twin Orbit's front panel: 10HP x 3U, 2 mm 5052 aluminium, black anodised, white print.

- panel_cut: the CUT layer alone, the DXF a laser-cutting service takes (outline, holes, rail slots).
- panel_art: CUT plus the ENGRAVE layer (title and labels as text outlines), for print or engraving.
- panel:     the 3D part, in the assembly frame (lib/twin_orbit.py), with its legend as a separate thin body.

The holes are the board's: twin_orbit.panel_parts() reads each jack, pot and LED axis from the
.kicad_pcb, and the labels are the parts' own values from the schematic (RATE, SHAPE, CV, TRI, ...).

Run: cad run src/panel.py"""

import build123d as bd
from cad import model

from lib.twin_orbit import (HOLE_D, MOUNT_X, MOUNT_Y, PANEL_FRONT_Z, PANEL_H, PANEL_T, PANEL_W, PANEL_X0,
                        PANEL_Y_TOP, SLOT_TRAVEL, SLOT_W, panel_parts)

CORNER_R = 0.5
TITLE, SUBTITLE = "TWIN ORBIT", "DUAL LFO"
LABEL_H, TITLE_H = 2.4, 3.6
PRINT_T = 0.03


def label_of(part: dict) -> str | None:
    words = part["value"].upper().split()
    if part["kind"] == "pot":
        return words[-1]                     # "B100k RATE" -> RATE
    if part["kind"] == "jack":
        return words[0]                      # "TRI OUT" -> TRI
    return None


def cut_face() -> bd.Face:
    with bd.BuildSketch() as s:
        with bd.Locations((PANEL_W / 2, PANEL_H / 2)):
            bd.RectangleRounded(PANEL_W, PANEL_H, CORNER_R)
        for p in panel_parts():
            with bd.Locations(p["panel"]):
                bd.Circle(HOLE_D[p["kind"]] / 2, mode=bd.Mode.SUBTRACT)
        for x in MOUNT_X:
            for y in MOUNT_Y:
                with bd.Locations((x, y)):
                    bd.SlotCenterToCenter(SLOT_TRAVEL, SLOT_W, mode=bd.Mode.SUBTRACT)
    return s.sketch.faces()[0]


def art_faces() -> list:
    """The print: the title, the subtitle, a label over each knob and jack, A and B by the LEDs."""
    parts = panel_parts()
    items = []

    def text(s, x, y, h):
        with bd.BuildSketch() as t:
            with bd.Locations((x, y)):
                bd.Text(s, font_size=h, font_style=bd.FontStyle.BOLD, align=(bd.Align.CENTER, bd.Align.CENTER))
        items.extend(t.sketch.faces())

    text(TITLE, PANEL_W / 2, PANEL_H - 6.5, TITLE_H)
    text(SUBTITLE, PANEL_W / 2, 6.0, LABEL_H)
    for p in parts:
        x, y = p["panel"]
        lab = label_of(p)
        if p["kind"] == "pot":
            text(lab, x, y + 9.4, LABEL_H)
        elif p["kind"] == "jack":
            text(lab, x, y + 6.9, LABEL_H)
        elif p["kind"] == "led":
            text("A" if p["ref"][-3] == "1" else "B", x + 4.2, y, LABEL_H)
    return items


@model
def panel_cut():
    face = cut_face()
    face.label = "CUT"
    return face


@model
def panel_art():
    profile = cut_face()
    profile.label = "CUT"
    marks = bd.Compound(art_faces(), label="ENGRAVE")
    return bd.Compound(children=[profile, marks], label="panel_art")


def place(shape):
    """Panel frame (origin bottom-left, z = 0 its back) -> assembly frame."""
    return bd.Pos(PANEL_X0, PANEL_Y_TOP - PANEL_H, PANEL_FRONT_Z - PANEL_T) * shape


@model
def panel():
    plate = place(bd.extrude(cut_face(), PANEL_T))
    plate.label, plate.color = "plate", "#1d1f22"
    legend = place(bd.Pos(0, 0, PANEL_T) * bd.extrude(bd.Sketch(art_faces()), PRINT_T))
    legend.label, legend.color = "legend", "#f2f2ee"
    return bd.Compound(children=[plate, legend], label="panel")


if __name__ == "__main__":
    panel_cut()
    panel_art()
    panel()
