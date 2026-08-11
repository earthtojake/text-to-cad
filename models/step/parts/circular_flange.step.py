from math import tau

from build123d import Align, BuildPart, Cylinder, Location, Locations, Mode

from part_common import circular_edges, polar_point, safe_fillet


OUTER_DIAMETER = 80.0
THICKNESS = 10.0
CENTRAL_BORE_DIAMETER = 30.0
BOLT_HOLE_COUNT = 6
BOLT_HOLE_DIAMETER = 6.0
BOLT_CIRCLE_DIAMETER = 60.0
OUTER_FILLET = 1.5


def gen_step():
    """Return the circular flange model in millimeters."""
    with BuildPart() as flange:
        Cylinder(
            radius=OUTER_DIAMETER / 2.0,
            height=THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )

        with Locations(Location((0.0, 0.0, -1.0))):
            Cylinder(
                radius=CENTRAL_BORE_DIAMETER / 2.0,
                height=THICKNESS + 2.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        for index in range(BOLT_HOLE_COUNT):
            x_pos, y_pos = polar_point(BOLT_CIRCLE_DIAMETER / 2.0, tau * index / BOLT_HOLE_COUNT)
            with Locations(Location((x_pos, y_pos, -1.0))):
                Cylinder(
                    radius=BOLT_HOLE_DIAMETER / 2.0,
                    height=THICKNESS + 2.0,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                    mode=Mode.SUBTRACT,
                )

    part = flange.part
    edges = []
    edges.extend(circular_edges(part, radius=OUTER_DIAMETER / 2.0, axis="z", coordinate=0.0))
    edges.extend(circular_edges(part, radius=OUTER_DIAMETER / 2.0, axis="z", coordinate=THICKNESS))
    part = safe_fillet(part, edges, radius=OUTER_FILLET)
    part.label = "circular_flange_bolt_pattern"
    return part
