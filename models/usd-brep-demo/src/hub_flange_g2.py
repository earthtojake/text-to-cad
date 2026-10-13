"""A hub flange whose hub-to-plate blend is curvature-continuous (G2).

The showcase for what usd-brep adds: build123d/OpenCascade fillets are circular (G1, a
curvature jump where the round meets each face), while usd-brep's blend cross-section can
be G2. ``bd.blend`` is the package's one extension to build123d's language for it; the rest
is plain build123d. The exact NURBS blend surface is written to OpenUSD.
"""
from __future__ import annotations

from pathlib import Path

import usd_brep_build123d as bd

PLATE_RADIUS = 40.0
PLATE_THICKNESS = 8.0
HUB_RADIUS = 14.0
HUB_HEIGHT = 18.0
BORE_RADIUS = 8.0
BOLT_COUNT = 6
BOLT_RADIUS = 3.0
BOLT_CIRCLE_RADIUS = 30.0
BLEND = 4.0  # hub-to-plate G2 blend
EDGE_ROUND = 1.0
OUT = Path(__file__).resolve().parents[1] / "USD" / "hub_flange_g2.usda"


def hub_flange_g2():
    with bd.BuildPart() as hub:
        bd.Cylinder(PLATE_RADIUS, PLATE_THICKNESS, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        with bd.Locations((0, 0, PLATE_THICKNESS)):
            bd.Cylinder(HUB_RADIUS, HUB_HEIGHT, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        bd.Hole(BORE_RADIUS)
        with bd.PolarLocations(BOLT_CIRCLE_RADIUS, BOLT_COUNT):
            bd.Hole(BOLT_RADIUS)
        circles = hub.edges().filter_by(bd.GeomType.CIRCLE)
        bd.blend(circles.filter_by(lambda e: abs(e.radius - HUB_RADIUS) < 1e-6).group_by(bd.Axis.Z)[0], radius=BLEND, continuity=2)
        rims = hub.edges().filter_by(bd.GeomType.CIRCLE).filter_by(lambda e: abs(e.radius - PLATE_RADIUS) < 1e-6)
        bd.fillet(rims, radius=EDGE_ROUND)
    hub.part.label = "hub_flange_g2"
    return hub.part


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    bd.export_usd(hub_flange_g2(), OUT)
    print(f"wrote {OUT}")
