"""3D models for the footprints KiCad's library has none for, drawn from their datasheets' package drawings.

- WS2812B-2020 (Worldsemi, datasheet V1.3): 2.0 x 2.0 mm body, 0.84 mm tall, a white housing with a clear lens.
- HRO TYPE-C-31-M-12: a mid-mount USB-C receptacle, its shell 8.94 x 7.35 x 3.16 mm, the opening at +y (the
  footprint's front), its tabs through the board.

Each is a model in KiCad's footprint frame (origin at the footprint's, +Z up from the board's top) that declares the
STEP the project's footprints name (`${KIPRJMOD}/pinball.3dshapes/...`). Run it before opening the board in 3D or
exporting its STEP or GLB; the folder is gitignored.

    cad run scripts/part_models.py
"""
import build123d as bd
from cad import step

MIN_Z = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


def led_2020():
    body = bd.Box(2.0, 2.0, 0.6, align=MIN_Z)
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), 0.1)
    body.label, body.color = "housing", "#f4f4f0"
    lens = bd.Pos(0, 0, 0.6) * bd.Box(1.7, 1.7, 0.24, align=MIN_Z)
    lens.label, lens.color = "lens", "#fff6d8"
    pads = []
    for i, (x, y) in enumerate([(-0.915, -0.55), (-0.915, 0.55), (0.915, 0.55), (0.915, -0.55)]):
        pad = bd.Pos(x, -y, 0) * bd.Box(0.5, 0.5, 0.05, align=MIN_Z)
        pad.label, pad.color = f"pad{i + 1}", "#c8a24a"
        pads.append(pad)
    return bd.Compound(children=[body, lens, *pads], label="WS2812B-2020")


def usb_c():
    w, d, h = 8.94, 7.35, 3.16
    shell = bd.Pos(0, 0, 0) * bd.Box(w, d, h, align=MIN_Z)
    shell = bd.fillet(shell.edges().filter_by(bd.Axis.Y), 1.3)
    cavity = bd.Pos(0, 0.8, 0.45) * bd.Box(w - 0.7, d - 1.6 + 0.2, h - 0.9, align=MIN_Z)
    cavity = bd.fillet(cavity.edges().filter_by(bd.Axis.Y), 0.9)
    shell = shell - cavity
    shell.label, shell.color = "shell", "#c8ccd0"
    tongue = bd.Pos(0, 1.0, h / 2 - 0.35) * bd.Box(6.6, 5.0, 0.7, align=MIN_Z)
    tongue.label, tongue.color = "tongue", "#1a1a1a"
    pins = []
    for i, x in enumerate((-3.25, -2.45, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75, 2.45, 3.25)):
        pin = bd.Pos(x, -4.04, 0) * bd.Box(0.3 if abs(x) < 2 else 0.6, 1.0, 0.12, align=MIN_Z)
        pin.label, pin.color = f"pin{i + 1}", "#c8a24a"
        pins.append(pin)
    tabs = []
    for i, (x, y) in enumerate(((-4.32, -3.13), (4.32, -3.13), (-4.32, 1.05), (4.32, 1.05))):
        tab = bd.Pos(x, y, -1.4) * bd.Box(0.5, 1.0, 1.4, align=MIN_Z)
        tab.label, tab.color = f"tab{i + 1}", "#c8ccd0"
        tabs.append(tab)
    return bd.Compound(children=[shell, tongue, *pins, *tabs], label="HRO TYPE-C-31-M-12")


@step("../pinball.3dshapes/LED_WS2812B-2020_PLCC4_2.0x2.0mm.step")
def ws2812b_2020():
    return led_2020()


@step("../pinball.3dshapes/USB_C_Receptacle_HRO_TYPE-C-31-M-12.step")
def type_c_31_m_12():
    return usb_c()


if __name__ == "__main__":
    ws2812b_2020()
    type_c_31_m_12()
