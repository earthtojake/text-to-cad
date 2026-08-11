# Prompt: Rectangular gasket with rounded corners, four bolt holes, and a
# center cutout, plus an engraved alignment crosshair.

from __future__ import annotations

import math

import ezdxf

WIDTH_MM = 80.0
HEIGHT_MM = 50.0
CORNER_RADIUS_MM = 8.0
BOLT_HOLE_DIAMETER_MM = 5.0
BOLT_INSET_MM = 10.0
CENTER_CUTOUT_DIAMETER_MM = 24.0
# Longer than the center cutout so the marks land on material.
CROSSHAIR_LENGTH_MM = 32.0

# Bulge for a 90-degree counterclockwise corner arc.
_QUARTER_ARC_BULGE = math.tan(math.radians(90.0 / 4.0))


def _rounded_rect_vertices(width: float, height: float, radius: float):
    b = _QUARTER_ARC_BULGE
    return [
        (radius, 0.0, 0.0),
        (width - radius, 0.0, b),
        (width, radius, 0.0),
        (width, height - radius, b),
        (width - radius, height, 0.0),
        (radius, height, b),
        (0.0, height - radius, 0.0),
        (0.0, radius, b),
    ]


def gen_dxf():
    document = ezdxf.new("R2010")
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT")
    document.layers.add("ENGRAVE")

    modelspace.add_lwpolyline(
        _rounded_rect_vertices(WIDTH_MM, HEIGHT_MM, CORNER_RADIUS_MM),
        format="xyb",
        close=True,
        dxfattribs={"layer": "CUT"},
    )

    for x in (BOLT_INSET_MM, WIDTH_MM - BOLT_INSET_MM):
        for y in (BOLT_INSET_MM, HEIGHT_MM - BOLT_INSET_MM):
            modelspace.add_circle(
                (x, y),
                BOLT_HOLE_DIAMETER_MM / 2.0,
                dxfattribs={"layer": "CUT"},
            )

    center = (WIDTH_MM / 2.0, HEIGHT_MM / 2.0)
    modelspace.add_circle(
        center,
        CENTER_CUTOUT_DIAMETER_MM / 2.0,
        dxfattribs={"layer": "CUT"},
    )

    half = CROSSHAIR_LENGTH_MM / 2.0
    modelspace.add_line(
        (center[0] - half, center[1]),
        (center[0] + half, center[1]),
        dxfattribs={"layer": "ENGRAVE"},
    )
    modelspace.add_line(
        (center[0], center[1] - half),
        (center[0], center[1] + half),
        dxfattribs={"layer": "ENGRAVE"},
    )
    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
