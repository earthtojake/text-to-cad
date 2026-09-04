# Prompt: Rectangular gasket with rounded corners, four bolt holes, and a
# center cutout, plus an engraved alignment crosshair.

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

WIDTH_MM = 80.0
HEIGHT_MM = 50.0
CORNER_RADIUS_MM = 8.0
BOLT_HOLE_DIAMETER_MM = 5.0
BOLT_INSET_MM = 10.0
CENTER_CUTOUT_DIAMETER_MM = 24.0
# Longer than the center cutout so the marks land on material.
CROSSHAIR_LENGTH_MM = 32.0


@dxf(out="../DXF/gasket_plate.dxf")
def gasket_plate():
    with bd.BuildSketch() as cut:
        bd.RectangleRounded(WIDTH_MM, HEIGHT_MM, CORNER_RADIUS_MM)
        bd.Circle(CENTER_CUTOUT_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)
        bolt_x = WIDTH_MM / 2.0 - BOLT_INSET_MM
        bolt_y = HEIGHT_MM / 2.0 - BOLT_INSET_MM
        with bd.Locations(
            (-bolt_x, -bolt_y), (bolt_x, -bolt_y), (-bolt_x, bolt_y), (bolt_x, bolt_y)
        ):
            bd.Circle(BOLT_HOLE_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)

    # Open geometry, so it belongs on a marking layer: the cut layer must close.
    half = CROSSHAIR_LENGTH_MM / 2.0
    crosshair = [bd.Line((-half, 0), (half, 0)), bd.Line((0, -half), (0, half))]

    return {"CUT": cut.sketch, "ENGRAVE": crosshair}


if __name__ == "__main__":
    gasket_plate()
