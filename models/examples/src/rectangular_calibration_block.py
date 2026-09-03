from __future__ import annotations
from cadgen import step
from cadgen import build123d as bd

from lib.part_common import line_edges_at_z, safe_chamfer


LENGTH = 100.0
WIDTH = 60.0
HEIGHT = 20.0
HOLE_DIAMETER = 8.0
HOLE_LOCATIONS = ((-35.0, -20.0), (-35.0, 20.0), (35.0, -20.0), (35.0, 20.0))
TOP_CHAMFER = 2.0


@step(out="../STEP/rectangular_calibration_block.step")
def rectangular_calibration_block():
    """Return the rectangular calibration block model in millimeters."""
    with bd.BuildPart() as block:
        bd.Box(LENGTH, WIDTH, HEIGHT, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))

        for x_pos, y_pos in HOLE_LOCATIONS:
            with bd.Locations(bd.Location((x_pos, y_pos, -1.0))):
                bd.Cylinder(
                    radius=HOLE_DIAMETER / 2.0,
                    height=HEIGHT + 2.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.SUBTRACT,
                )

    part = block.part
    part = safe_chamfer(part, line_edges_at_z(part, HEIGHT), length=TOP_CHAMFER)
    part.label = "rectangular_calibration_block"
    return part


if __name__ == "__main__":
    rectangular_calibration_block()
