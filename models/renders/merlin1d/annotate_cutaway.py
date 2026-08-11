"""Composite thin leader-line labels onto the cutaway front-ortho render.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Run:  <venv-python> annotate_cutaway.py
Reads renders/cutaway_front_ortho.png (2400x1600, ortho from +Y, padding 0.12)
and writes renders/cutaway_annotated.png. World->pixel mapping is calibrated
to that framing; re-calibrate S/CX/CY if the render framing changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SRC = HERE / "renders" / "cutaway_front_ortho.png"
DST = HERE / "renders" / "cutaway_annotated.png"

# world (mm) -> pixel calibration for the fixed cutaway_front_ortho framing
S = 0.4887          # px per mm
CX = 1212.0         # image x of world x=0 (world +X maps to image LEFT)
CY = 1542.0         # image y of world z=0

INK = (40, 46, 56, 255)
FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"

# label text, world anchor (x, z), side ("L" = left margin, "R" = right margin)
LABELS = [
    ("LOX feed line (blue: schematic flow)", (470, 2620), "L"),
    ("RP-1 feed line (amber: schematic flow)", (710, 2450), "L"),
    ("main valve housings - schematic, no internals", (470, 2250), "L"),
    ("gas generator - placeholder, no internals", (470, 2030), "L"),
    ("LOX pump - placeholder volume", (470, 1700), "L"),
    ("RP-1 pump - placeholder volume", (470, 1445), "L"),
    ("single-shaft turbine - placeholder", (470, 1230), "L"),
    ("turbine exhaust duct (open cycle)", (620, 620), "L"),
    ("gimbal block + kerosene-hydraulic TVC", (0, 2380), "R"),
    ("injector dome - pintle type, no element detail", (-140, 1900), "R"),
    ("schematic injector region disk", (-160, 1765), "R"),
    ("main chamber volume (orange: hot gas)", (-140, 1580), "R"),
    ("throat (est. 260 mm dia)", (-120, 1165), "R"),
    ("regen cooling band - simplified annulus", (-260, 1000), "R"),
    ("nozzle expansion volume (16:1 est.)", (-260, 520), "R"),
    ("exit plane Z=0 (dia 1040 mm est.)", (-520, 20), "R"),
]

TITLE = "MERLIN 1D  -  SCHEMATIC CUTAWAY"
SUBTITLE = "Educational public-source reconstruction - internals schematic / inferred / non-functional"
DISCLAIMER = ("Educational, non-functional public-source reconstruction. "
              "Not suitable for manufacture, propulsion, testing, or operational engineering.")
LEGEND = [((40, 90, 200), "LOX"), ((205, 145, 40), "RP-1 / regen"),
          ((230, 105, 35), "hot gas"), ((150, 150, 158), "inferred / placeholder")]


def to_px(wx: float, wz: float) -> tuple[float, float]:
    return (CX - S * wx, CY - S * wz)


PAD = 700  # extra canvas per side so label text never clips


def main() -> int:
    render = Image.open(SRC).convert("RGBA")
    background = render.getpixel((4, 4))
    image = Image.new("RGBA", (render.width + 2 * PAD, render.height), background)
    image.paste(render, (PAD, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT_PATH, 30)
    font_small = ImageFont.truetype(FONT_PATH, 24)
    font_title = ImageFont.truetype(FONT_PATH, 44)

    lane_l, lane_r = {}, {}
    for text, (wx, wz), side in LABELS:
        ax, ay = to_px(wx, wz)
        ax += PAD
        margin_x = 660 if side == "L" else image.width - 660
        lanes = lane_l if side == "L" else lane_r
        ly = round(ay / 56) * 56
        while ly in lanes.values():
            ly += 56
        lanes[text] = ly
        elbow_x = margin_x + (40 if side == "L" else -40)
        draw.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], fill=INK)
        draw.line([(ax, ay), (elbow_x, ly)], fill=INK, width=2)
        draw.line([(elbow_x, ly), (margin_x, ly)], fill=INK, width=2)
        anchor = "rm" if side == "L" else "lm"
        draw.text((margin_x - 8 if side == "L" else margin_x + 8, ly), text,
                  fill=INK, font=font, anchor=anchor)

    draw.text((60, 48), TITLE, fill=INK, font=font_title)
    draw.text((60, 106), SUBTITLE, fill=INK, font=font_small)
    x = 60
    for color, name in LEGEND:
        draw.rectangle([x, 150, x + 34, 174], fill=color + (255,))
        draw.text((x + 42, 162), name, fill=INK, font=font_small, anchor="lm")
        x += 42 + int(draw.textlength(name, font=font_small)) + 46
    draw.text((image.width / 2, image.height - 34), DISCLAIMER, fill=INK,
              font=font_small, anchor="mm")

    image.convert("RGB").save(DST)
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
