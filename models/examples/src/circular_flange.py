from __future__ import annotations
from cadgen import step
from math import tau

from cadgen import build123d as bd

from lib.part_common import circular_edges, polar_point, safe_fillet


OUTER_DIAMETER = 80.0
THICKNESS = 10.0
CENTRAL_BORE_DIAMETER = 30.0
BOLT_HOLE_COUNT = 6
BOLT_HOLE_DIAMETER = 6.0
BOLT_CIRCLE_DIAMETER = 60.0
OUTER_FILLET = 1.5


@step(out="../STEP/circular_flange.step")
def circular_flange():
    """Return the circular flange model in millimeters."""
    with bd.BuildPart() as flange:
        bd.Cylinder(
            radius=OUTER_DIAMETER / 2.0,
            height=THICKNESS,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
        )

        with bd.Locations(bd.Location((0.0, 0.0, -1.0))):
            bd.Cylinder(
                radius=CENTRAL_BORE_DIAMETER / 2.0,
                height=THICKNESS + 2.0,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.SUBTRACT,
            )

        for index in range(BOLT_HOLE_COUNT):
            x_pos, y_pos = polar_point(BOLT_CIRCLE_DIAMETER / 2.0, tau * index / BOLT_HOLE_COUNT)
            with bd.Locations(bd.Location((x_pos, y_pos, -1.0))):
                bd.Cylinder(
                    radius=BOLT_HOLE_DIAMETER / 2.0,
                    height=THICKNESS + 2.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.SUBTRACT,
                )

    part = flange.part
    edges = []
    edges.extend(circular_edges(part, radius=OUTER_DIAMETER / 2.0, axis="z", coordinate=0.0))
    edges.extend(circular_edges(part, radius=OUTER_DIAMETER / 2.0, axis="z", coordinate=THICKNESS))
    part = safe_fillet(part, edges, radius=OUTER_FILLET)
    part.label = "circular_flange_bolt_pattern"
    return part


if __name__ == "__main__":
    circular_flange()
