from __future__ import annotations
from cadgen import step
from cadgen import build123d as bd


OUTER_LENGTH = 100.0
OUTER_WIDTH = 70.0
OUTER_HEIGHT = 30.0
WALL_THICKNESS = 3.0
FLOOR_THICKNESS = 3.0
OUTER_CORNER_FILLET_RADIUS = 2.0

STANDOFF_DIAMETER = 10.0
STANDOFF_HEIGHT = 12.0
STANDOFF_HOLE_DIAMETER = 3.0
STANDOFF_HOLE_DEPTH = 8.0
STANDOFF_LOCATIONS = (
    (-35.0, -25.0),
    (-35.0, 25.0),
    (35.0, -25.0),
    (35.0, 25.0),
)


@step(out="../STEP/electronics_enclosure_base.step")
def electronics_enclosure_base():
    """Return a single solid open-top electronics enclosure base in millimeters."""
    inner_length = OUTER_LENGTH - 2.0 * WALL_THICKNESS
    inner_width = OUTER_WIDTH - 2.0 * WALL_THICKNESS
    cavity_height = OUTER_HEIGHT - FLOOR_THICKNESS
    standoff_top_z = FLOOR_THICKNESS + STANDOFF_HEIGHT

    with bd.BuildPart() as enclosure:
        with bd.BuildSketch(bd.Plane.XY):
            bd.RectangleRounded(
                OUTER_LENGTH,
                OUTER_WIDTH,
                OUTER_CORNER_FILLET_RADIUS,
                align=(bd.Align.CENTER, bd.Align.CENTER),
            )
        bd.extrude(amount=OUTER_HEIGHT)

        with bd.Locations(bd.Location((0.0, 0.0, FLOOR_THICKNESS))):
            bd.Box(
                inner_length,
                inner_width,
                cavity_height,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.SUBTRACT,
            )

        for x_pos, y_pos in STANDOFF_LOCATIONS:
            with bd.Locations(bd.Location((x_pos, y_pos, FLOOR_THICKNESS))):
                bd.Cylinder(
                    radius=STANDOFF_DIAMETER / 2.0,
                    height=STANDOFF_HEIGHT,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.ADD,
                )
            with bd.Locations(bd.Location((x_pos, y_pos, standoff_top_z))):
                bd.Cylinder(
                    radius=STANDOFF_HOLE_DIAMETER / 2.0,
                    height=STANDOFF_HOLE_DEPTH,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX),
                    mode=bd.Mode.SUBTRACT,
                )

    part = enclosure.part
    part.label = "electronics_enclosure_base"
    return part


if __name__ == "__main__":
    electronics_enclosure_base()
