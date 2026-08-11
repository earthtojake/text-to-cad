"""Add leader-line annotations to the Raptor 2 orthographic renders.

Educational, non-functional public-source reconstruction. Not suitable for
manufacture, propulsion, testing, or operational engineering.

Works on orthographic snapshot PNGs: detects the model's pixel bounding box
against the uniform background, maps the known world-space bbox onto it, and
draws thin leader lines with sans-serif labels plus a title and the mandatory
disclaimer footer.

    <venv-python> annotate_renders.py <cutaway_front.png> <exterior_front.png> <out_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Helvetica.ttc"
INK = (28, 32, 40, 255)
LINE = (70, 76, 88, 255)
DISCLAIMER = (
    "Educational, non-functional public-source reconstruction. Not suitable for "
    "manufacture, propulsion, testing, or operational engineering."
)


def _content_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Pixel bbox of non-background content (background = corner color)."""
    rgb = img.convert("RGB")
    px = rgb.load()
    bg = px[2, 2]
    w, h = rgb.size
    xmin, ymin, xmax, ymax = w, h, 0, 0
    step = 2
    for y in range(0, h, step):
        for x in range(0, w, step):
            p = px[x, y]
            # threshold high enough to ignore the faint viewer floor grid,
            # horizon gradient, and soft ground shadow; the model's dark edge
            # strokes keep the true silhouette above it
            if (abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2])) > 110:
                if x < xmin:
                    xmin = x
                if x > xmax:
                    xmax = x
                if y < ymin:
                    ymin = y
                if y > ymax:
                    ymax = y
    return xmin, ymin, xmax, ymax


class OrthoMap:
    """world (x, z) -> pixel for a Z-up orthographic side view."""

    def __init__(self, img, world_x, world_z, flip_x):
        L, T, R, B = _content_bbox(img)
        self.sx = (R - L) / (world_x[1] - world_x[0])
        self.sz = (B - T) / (world_z[1] - world_z[0])
        self.L, self.T = L, T
        self.world_x, self.world_z = world_x, world_z
        self.flip_x = flip_x

    def to_px(self, x: float, z: float) -> tuple[float, float]:
        if self.flip_x:
            px = self.L + (self.world_x[1] - x) * self.sx
        else:
            px = self.L + (x - self.world_x[0]) * self.sx
        py = self.T + (self.world_z[1] - z) * self.sz
        return px, py


def annotate(src, dst, world_x, world_z, flip_x, title, labels):
    img = Image.open(src).convert("RGBA")
    m = OrthoMap(img, world_x, world_z, flip_x)
    d = ImageDraw.Draw(img)
    f_label = ImageFont.truetype(FONT, 26)
    f_title = ImageFont.truetype(FONT, 40)
    f_foot = ImageFont.truetype(FONT, 22)
    W, H = img.size
    for text, (wx, wz), side, ty in labels:
        ax, ay = m.to_px(wx, wz)
        tx = 40 if side == "L" else W - 40
        anchor = "lm" if side == "L" else "rm"
        bbox = d.multiline_textbbox((tx, ty), text, font=f_label, anchor=anchor)
        # start the leader just past the text block, elbow, then to the feature
        sx = bbox[2] + 12 if side == "L" else bbox[0] - 12
        ex = sx + (40 if side == "L" else -40)
        d.line([(sx, ty), (ex, ty), (ax, ay)], fill=LINE, width=2)
        d.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], outline=LINE, width=2)
        d.multiline_text((tx, ty), text, font=f_label, fill=INK, anchor=anchor)
    d.text((40, 34), title, font=f_title, fill=INK)
    d.text((40, H - 44), DISCLAIMER, font=f_foot, fill=(60, 66, 78, 255))
    img.convert("RGB").save(dst, quality=95)
    print("wrote", dst)


CUTAWAY_LABELS = [
    # (text, world (x, z), text side, text y in px)
    ("Gimbal mount (simplified)", (0, 2795), "R", 180),
    ("CH4 main inlet - fuel side", (-430, 2990), "R", 260),
    ("Fuel-rich preburner - placeholder\nvolume (schematic)", (-430, 2470), "R", 420),
    ("Fuel turbopump - exterior\nplaceholder, no internals", (-430, 2000), "R", 580),
    ("Regen cooling band - simplified\nannulus (schematic, inferred)", (-480, 780), "R", 900),
    ("CH4 regen downcomer (schematic)", (-620, 1000), "R", 740),
    ("Hot-gas expansion volume\n(schematic)", (0, 450), "R", 1120),
    ("LOX main inlet - oxygen side", (430, 2990), "L", 260),
    ("Ox-rich preburner - placeholder\nvolume (schematic)", (430, 2470), "L", 420),
    ("Ox turbopump - exterior\nplaceholder, no internals", (430, 2000), "L", 580),
    ("Schematic injector region -\nno element detail", (0, 2180), "L", 760),
    ("Main combustion chamber\nvolume (schematic)", (0, 1950), "L", 920),
    ("Throat (public estimate,\n~240 mm dia)", (-120, 1560), "L", 1080),
]

EXTERIOR_LABELS = [
    ("Vehicle interface flanges", (-430, 3090), "L", 200),
    ("Main valve plate (schematic,\nno internals)", (-430, 2760), "L", 360),
    ("Fuel turbopump + preburner\n(exterior placeholder)", (-430, 2200), "L", 540),
    ("CH4 regen downcomers\n(schematic routing)", (-580, 1100), "L", 760),
    ("Nozzle fuel manifold ring\n(schematic)", (-600, 450), "L", 960),
    ("Heat-tint bands (decorative)", (-330, 1350), "L", 1085),
    ("Gimbal mount + vehicle plate\n(simplified)", (0, 2860), "R", 220),
    ("TVC actuator housing\n(schematic)", (180, 2650), "R", 400),
    ("Ox turbopump + preburner\n(exterior placeholder)", (430, 2200), "R", 580),
    ("Combustion chamber envelope\n(photogrammetric)", (245, 2000), "R", 780),
    ("Nozzle bell - Rao approximation\n(photogrammetric)", (480, 700), "R", 1000),
    ("Exit stiffener ring", (655, 30), "R", 1120),
]


def main() -> int:
    cut_src, ext_src, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    annotate(
        cut_src, out_dir / "cutaway_annotated.png",
        world_x=(-678.0, 678.0), world_z=(0.0, 3100.0), flip_x=True,
        title="SpaceX Raptor 2 - schematic cutaway (public-source reconstruction)",
        labels=CUTAWAY_LABELS,
    )
    annotate(
        ext_src, out_dir / "exterior_annotated.png",
        world_x=(-678.0, 678.0), world_z=(0.0, 3100.0), flip_x=False,
        title="SpaceX Raptor 2 - exterior (public-source reconstruction)",
        labels=EXTERIOR_LABELS,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
