from build123d import Align, Box, BuildPart, Cylinder, Location, Locations, Mode

from part_common import circular_edges, safe_chamfer


TOTAL_LENGTH = 120.0
LEFT_LENGTH = 30.0
MIDDLE_LENGTH = 60.0
RIGHT_LENGTH = 30.0
SMALL_DIAMETER = 20.0
MIDDLE_DIAMETER = 30.0
END_CHAMFER = 1.0

KEYWAY_X_START = 40.0
KEYWAY_X_END = 80.0
KEYWAY_WIDTH = 6.0
KEYWAY_DEPTH = 3.0


def _add_shaft_section(x_start: float, x_end: float, diameter: float):
    with Locations(Location(((x_start + x_end) / 2.0, 0.0, 0.0))):
        Cylinder(
            radius=diameter / 2.0,
            height=x_end - x_start,
            rotation=(0.0, 90.0, 0.0),
            align=(Align.CENTER, Align.CENTER, Align.CENTER),
            mode=Mode.ADD,
        )


def gen_step():
    """Return the stepped shaft with keyway model in millimeters."""
    with BuildPart() as shaft:
        _add_shaft_section(0.0, LEFT_LENGTH, SMALL_DIAMETER)
        _add_shaft_section(LEFT_LENGTH, LEFT_LENGTH + MIDDLE_LENGTH, MIDDLE_DIAMETER)
        _add_shaft_section(LEFT_LENGTH + MIDDLE_LENGTH, TOTAL_LENGTH, SMALL_DIAMETER)

        with Locations(Location(((KEYWAY_X_START + KEYWAY_X_END) / 2.0, 0.0, MIDDLE_DIAMETER / 2.0 - KEYWAY_DEPTH))):
            Box(
                KEYWAY_X_END - KEYWAY_X_START,
                KEYWAY_WIDTH,
                KEYWAY_DEPTH + 2.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    part = shaft.part
    end_edges = []
    end_edges.extend(circular_edges(part, radius=SMALL_DIAMETER / 2.0, axis="x", coordinate=0.0))
    end_edges.extend(circular_edges(part, radius=SMALL_DIAMETER / 2.0, axis="x", coordinate=TOTAL_LENGTH))
    part = safe_chamfer(part, end_edges, length=END_CHAMFER)
    part.label = "stepped_shaft_keyway"
    return part
