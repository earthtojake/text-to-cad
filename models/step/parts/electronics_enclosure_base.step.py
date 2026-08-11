from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Location,
    Locations,
    Mode,
    Plane,
    RectangleRounded,
    extrude,
)


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


def gen_step():
    """Return a single solid open-top electronics enclosure base in millimeters."""
    inner_length = OUTER_LENGTH - 2.0 * WALL_THICKNESS
    inner_width = OUTER_WIDTH - 2.0 * WALL_THICKNESS
    cavity_height = OUTER_HEIGHT - FLOOR_THICKNESS
    standoff_top_z = FLOOR_THICKNESS + STANDOFF_HEIGHT

    with BuildPart() as enclosure:
        with BuildSketch(Plane.XY):
            RectangleRounded(
                OUTER_LENGTH,
                OUTER_WIDTH,
                OUTER_CORNER_FILLET_RADIUS,
                align=(Align.CENTER, Align.CENTER),
            )
        extrude(amount=OUTER_HEIGHT)

        with Locations(Location((0.0, 0.0, FLOOR_THICKNESS))):
            Box(
                inner_length,
                inner_width,
                cavity_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        for x_pos, y_pos in STANDOFF_LOCATIONS:
            with Locations(Location((x_pos, y_pos, FLOOR_THICKNESS))):
                Cylinder(
                    radius=STANDOFF_DIAMETER / 2.0,
                    height=STANDOFF_HEIGHT,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.ADD,
                )
            with Locations(Location((x_pos, y_pos, standoff_top_z))):
                Cylinder(
                    radius=STANDOFF_HOLE_DIAMETER / 2.0,
                    height=STANDOFF_HOLE_DEPTH,
                    align=(Align.CENTER, Align.CENTER, Align.MAX),
                    mode=Mode.SUBTRACT,
                )

    part = enclosure.part
    part.label = "electronics_enclosure_base"
    return part
