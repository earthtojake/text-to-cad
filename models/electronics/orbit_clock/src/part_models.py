"""3D models for the two footprints KiCad ships without one, drawn from their datasheets' package drawings.

- WS2812B-2020 (Worldsemi, datasheet V1.3): 2.0 x 2.0 mm body, 0.84 mm tall, a white housing with a clear
  lens over the die and four pads under its corners.
- LTR-303ALS-01 (Lite-On, datasheet BNS-OD-FC002): 2.0 x 2.0 x 0.7 mm ChipLED, a dark body with a clear window.

Each is a model in KiCad's footprint frame (origin at the footprint's, +Z up from the board's top) that declares
the STEP the project's footprints name (`${KIPRJMOD}/orbit.3dshapes/...`), which every run writes: run the
script before opening the board in 3D or exporting its STEP or GLB. The folder is gitignored.

    cad run src/part_models.py
"""
import build123d as bd
from cad import step


def led_2020():
    body = bd.Box(2.0, 2.0, 0.6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), 0.1)
    body.label, body.color = "housing", "#f4f4f0"
    lens = bd.Pos(0, 0, 0.6) * bd.Box(1.7, 1.7, 0.24, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    lens.label, lens.color = "lens", "#fff6d8"
    pads = []
    for i, (x, y) in enumerate([(-0.915, -0.55), (-0.915, 0.55), (0.915, 0.55), (0.915, -0.55)]):
        pad = bd.Pos(x, -y, 0) * bd.Box(0.5, 0.5, 0.05, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        pad.label, pad.color = f"pad{i + 1}", "#c8a24a"
        pads.append(pad)
    return bd.Compound(children=[body, lens, *pads], label="WS2812B-2020")


def ltr303():
    body = bd.Box(2.0, 2.0, 0.55, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    body.label, body.color = "body", "#2b2b2b"
    window = bd.Pos(0, 0, 0.55) * bd.Box(1.2, 1.2, 0.15, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    window.label, window.color = "window", "#9ab8c8"
    return bd.Compound(children=[body, window], label="LTR-303ALS-01")


@step("../orbit.3dshapes/LED_WS2812B-2020_PLCC4_2.0x2.0mm.step")
def ws2812b_2020():
    return led_2020()


@step("../orbit.3dshapes/Lite-On_LTR-303ALS-01.step")
def ltr_303als_01():
    return ltr303()


if __name__ == "__main__":
    ws2812b_2020()
    ltr_303als_01()
