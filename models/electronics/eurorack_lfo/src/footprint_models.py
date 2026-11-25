"""3D models for the two footprints KiCad's installed library has no STEP for: the Thonkiconn PJ398SM jack
and the Alpha RD901F-40 9 mm vertical pot. Each is drawn in KiCad's 3D-model frame for its footprint
(origin at the footprint's origin, x right, y = -(footprint y), z up from the board's top face) and written
as the STEP the project's footprints name (``${KIPRJMOD}/3dmodels/...``).

Dimensions: Thonk's "Thonkiconn 3.5mm switching jack socket" drawing (PJ398SM): body 9 x 10.5 x 9 mm high,
barrel 6.48 mm from the sleeve pin, M6 bushing 5.5 mm, pins 3.5 mm below. Alpha's RD901F-40-15K drawing
(SP17090051, SLH-211-208): body 9.5 x 11.35, 10 mm to the mounting face, M7x0.75 bushing 5 mm, 6 mm shaft
15 mm from the mounting face with an 18-tooth knurl 6 mm long, pins 3.5 mm below.

Each model declares the STEP the footprints name, which every run writes into 3dmodels/ (gitignored): run
this before opening the board in 3D or exporting its STEP or GLB.

Run: cad run src/footprint_models.py"""

import build123d as bd
from cad import step

BLACK, NICKEL, BRASS = "#1c1c1e", "#c9cbce", "#b8a26a"

# --- Thonkiconn PJ398SM (footprint Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical) -----------------------
JACK_BARREL = (0.0, -6.48)       # footprint (0, 6.48)
JACK_BODY_H = 9.0
JACK_BUSHING_L = 5.5
JACK_THREAD_D = 6.0
JACK_PINS = {"S": 0.0, "TN": -3.1, "T": -11.4}


def jack_body():
    bx, by = JACK_BARREL
    body = bd.Pos(0, (-1.98 - 12.48) / 2, JACK_BODY_H / 2) * bd.Box(9.0, 10.5, JACK_BODY_H)
    # the raised square face round the barrel
    collar = bd.Pos(bx, by, JACK_BODY_H + 0.25) * bd.Box(6.0, 6.0, 0.5)
    body = body + collar
    body.label, body.color = "housing", BLACK
    bushing = bd.Pos(bx, by, JACK_BODY_H + 0.5 + (JACK_BUSHING_L - 0.5) / 2) * bd.Cylinder(JACK_THREAD_D / 2, JACK_BUSHING_L - 0.5)
    bushing = bushing - bd.Pos(bx, by, JACK_BODY_H + JACK_BUSHING_L / 2) * bd.Cylinder(3.6 / 2, JACK_BUSHING_L + 1)
    bushing.label, bushing.color = "bushing", NICKEL
    pins = []
    for name, y in JACK_PINS.items():
        pin = bd.Pos(0, y, -3.5 / 2 + 0.25) * bd.Box(0.6 if name != "S" else 0.8, 1.5, 4.0)
        pin.label, pin.color = f"pin_{name}", NICKEL
        pins.append(pin)
    return bd.Compound(children=[body, bushing, *pins], label="Thonkiconn_PJ398SM")


@step("../3dmodels/Thonkiconn_PJ398SM.step")
def thonkiconn_pj398sm():
    return jack_body()


# --- Alpha RD901F-40 9 mm vertical pot (footprint Potentiometer_Alpha_RD901F-40-00D_Single_Vertical) ---
POT_SHAFT = (7.5, -2.5)          # footprint (7.5, 2.5)
POT_FACE_H = 10.0                # PCB to the mounting face
POT_BUSHING_D, POT_BUSHING_L = 7.0, 5.0
POT_SHAFT_D, POT_SHAFT_L, POT_KNURL_L = 6.0, 15.0, 6.0


def pot_body():
    sx, sy = POT_SHAFT
    cx, cy = (1.0 + 12.35) / 2, -2.5
    plastic = bd.Pos(cx, cy, 2.75) * bd.Box(11.35, 9.5, 5.5)
    plastic.label, plastic.color = "housing", BLACK
    can = bd.Pos(cx, cy, 5.5 + 2.25) * bd.Box(11.35, 9.5, 4.5)
    can.label, can.color = "frame", NICKEL
    bushing = bd.Pos(sx, sy, POT_FACE_H + POT_BUSHING_L / 2) * bd.Cylinder(POT_BUSHING_D / 2, POT_BUSHING_L)
    bushing.label, bushing.color = "bushing", BRASS
    plain_l = POT_SHAFT_L - POT_BUSHING_L - POT_KNURL_L
    shaft = bd.Pos(sx, sy, POT_FACE_H + POT_BUSHING_L + plain_l / 2) * bd.Cylinder(POT_SHAFT_D / 2, plain_l)
    knurl = bd.Pos(sx, sy, POT_FACE_H + POT_SHAFT_L - POT_KNURL_L / 2) * bd.Cylinder(POT_SHAFT_D / 2, POT_KNURL_L)
    for i in range(18):
        tooth = bd.Rot(0, 0, i * 20) * bd.Pos(POT_SHAFT_D / 2, 0, 0) * bd.Box(0.5, 0.5, POT_KNURL_L + 0.2)
        knurl = knurl - bd.Pos(sx, sy, POT_FACE_H + POT_SHAFT_L - POT_KNURL_L / 2) * bd.Rot(0, 0, 45) * tooth
    slot = bd.Pos(sx, sy, POT_FACE_H + POT_SHAFT_L - 0.5) * bd.Box(1.0, POT_SHAFT_D + 1, 1.0)
    shaft = shaft + knurl - slot
    shaft.label, shaft.color = "shaft", NICKEL
    parts = [plastic, can, bushing, shaft]
    for i, y in enumerate((0.0, -2.5, -5.0), start=1):
        pin = bd.Pos(0, y, -3.5 / 2 + 0.5) * bd.Box(0.9, 0.5, 4.5)
        pin.label, pin.color = f"pin_{i}", NICKEL
        parts.append(pin)
    for i, y in enumerate((2.3, -7.3), start=1):
        tab = bd.Pos(7.5, y, -1.0) * bd.Box(1.8, 0.4, 4.0)
        tab.label, tab.color = f"tab_{i}", NICKEL
        parts.append(tab)
    return bd.Compound(children=parts, label="Alpha_RD901F-40")


@step("../3dmodels/Alpha_RD901F-40_9mm.step")
def alpha_rd901f_40():
    return pot_body()


if __name__ == "__main__":
    thonkiconn_pj398sm()
    alpha_rd901f_40()
