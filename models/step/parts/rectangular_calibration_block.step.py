from build123d import Align, Box, BuildPart, Cylinder, Location, Locations, Mode

from part_common import line_edges_at_z, safe_chamfer


LENGTH = 100.0
WIDTH = 60.0
HEIGHT = 20.0
HOLE_DIAMETER = 8.0
HOLE_LOCATIONS = ((-35.0, -20.0), (-35.0, 20.0), (35.0, -20.0), (35.0, 20.0))
TOP_CHAMFER = 2.0


def gen_step():
    """Return the rectangular calibration block model in millimeters."""
    with BuildPart() as block:
        Box(LENGTH, WIDTH, HEIGHT, align=(Align.CENTER, Align.CENTER, Align.MIN))

        for x_pos, y_pos in HOLE_LOCATIONS:
            with Locations(Location((x_pos, y_pos, -1.0))):
                Cylinder(
                    radius=HOLE_DIAMETER / 2.0,
                    height=HEIGHT + 2.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    part = block.part
    part = safe_chamfer(part, line_edges_at_z(part, HEIGHT), length=TOP_CHAMFER)
    part.label = "rectangular_calibration_block"
    return part
