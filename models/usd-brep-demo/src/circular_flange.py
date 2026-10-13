"""examples/src/circular_flange.py on NVIDIA's usd-brep kernel: the same build123d code,
importing usd_brep_build123d instead of build123d, written as OpenUSD instead of STEP.
"""
from __future__ import annotations

from math import cos, sin, tau
from pathlib import Path

import usd_brep_build123d as bd

OUTER_DIAMETER = 80.0
THICKNESS = 10.0
CENTRAL_BORE_DIAMETER = 30.0
BOLT_HOLE_COUNT = 6
BOLT_HOLE_DIAMETER = 6.0
BOLT_CIRCLE_DIAMETER = 60.0
OUTER_FILLET = 1.5
OUT = Path(__file__).resolve().parents[1] / "USD" / "circular_flange.usda"


def circular_edges(part, *, radius, z, tol=0.05):
    return [
        edge for edge in part.edges()
        if edge.geom_type == bd.GeomType.CIRCLE and abs(edge.radius - radius) < tol and abs(edge.arc_center.Z - z) < tol
    ]


def circular_flange():
    """Return the circular flange model in millimeters."""
    with bd.BuildPart() as flange:
        bd.Cylinder(radius=OUTER_DIAMETER / 2.0, height=THICKNESS, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        with bd.Locations(bd.Location((0.0, 0.0, -1.0))):
            bd.Cylinder(
                radius=CENTRAL_BORE_DIAMETER / 2.0,
                height=THICKNESS + 2.0,
                align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                mode=bd.Mode.SUBTRACT,
            )
        for index in range(BOLT_HOLE_COUNT):
            angle = tau * index / BOLT_HOLE_COUNT
            x_pos, y_pos = BOLT_CIRCLE_DIAMETER / 2.0 * cos(angle), BOLT_CIRCLE_DIAMETER / 2.0 * sin(angle)
            with bd.Locations(bd.Location((x_pos, y_pos, -1.0))):
                bd.Cylinder(
                    radius=BOLT_HOLE_DIAMETER / 2.0,
                    height=THICKNESS + 2.0,
                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
                    mode=bd.Mode.SUBTRACT,
                )

    part = flange.part
    rims = circular_edges(part, radius=OUTER_DIAMETER / 2.0, z=0.0) + circular_edges(part, radius=OUTER_DIAMETER / 2.0, z=THICKNESS)
    part = bd.fillet(rims, radius=OUTER_FILLET)
    part.label = "circular_flange_bolt_pattern"
    return part


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    bd.export_usd(circular_flange(), OUT)
    print(f"wrote {OUT}")
