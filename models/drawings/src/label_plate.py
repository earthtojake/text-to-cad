# Prompt: A laser-cut label plate that exercises the marking set: an engraved
# serial number and an OPEN polyline on the engrave layer (a score that must
# render as a line on the surface, never a solid).
#
# The serial number is bd.Text OUTLINES, not a DXF TEXT entity: cut and marking
# toolchains consume geometry, and font rendering inside CAM is unreliable.
# (The retired ezdxf generator emitted a real TEXT entity here; TEXT-entity
# PARSING is covered by unit fixtures in packages/cadgen-js/src/lib/dxf/.)

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import dxf

PLATE_LENGTH_MM = 120.0
PLATE_WIDTH_MM = 50.0
HOLE_DIAMETER_MM = 4.5
HOLE_INSET_MM = 8.0

SERIAL_TEXT = "SN-1042"
SERIAL_HEIGHT_MM = 9.0
SERIAL_ORIGIN_MM = (28.0, 21.0)

# An OPEN score line under the label: a zigzag underline that never closes, so
# it must survive as a score overlay rather than being dropped.
SCORE_POINTS_MM = ((28.0, 15.0), (48.0, 12.0), (68.0, 15.0), (88.0, 12.0))


@dxf(out="../DXF/label_plate.dxf")
def label_plate():
    with bd.BuildSketch() as cut:
        with bd.Locations((PLATE_LENGTH_MM / 2.0, PLATE_WIDTH_MM / 2.0)):
            bd.Rectangle(PLATE_LENGTH_MM, PLATE_WIDTH_MM)
        hole_xs = (HOLE_INSET_MM, PLATE_LENGTH_MM - HOLE_INSET_MM)
        hole_ys = (HOLE_INSET_MM, PLATE_WIDTH_MM - HOLE_INSET_MM)
        with bd.Locations(*[(x, y) for x in hole_xs for y in hole_ys]):
            bd.Circle(HOLE_DIAMETER_MM / 2.0, mode=bd.Mode.SUBTRACT)

    with bd.BuildSketch() as serial:
        with bd.Locations(SERIAL_ORIGIN_MM):
            bd.Text(SERIAL_TEXT, font_size=SERIAL_HEIGHT_MM, align=bd.Align.MIN)

    score = bd.Polyline(*SCORE_POINTS_MM)

    return {"CUT": cut.sketch, "ENGRAVE": [serial.sketch, score]}


if __name__ == "__main__":
    label_plate()
