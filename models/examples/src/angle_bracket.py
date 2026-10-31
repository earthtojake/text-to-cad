from __future__ import annotations
from math import cos, radians, sin

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
import build123d as bd


BASE_LENGTH = 80.0
BASE_WIDTH = 50.0
THICKNESS = 8.0
BASE_HOLE_DIAMETER = 8.0
BASE_HOLE_X = -25.0
TAB_HEIGHT = 40.0
TAB_LEAN = 30.0          # degrees off vertical, toward +X
TAB_HOLE_DIAMETER = 10.0
TAB_HOLE_HEIGHT = 25.0   # along the tab, from its foot
#: A point on the tab's inner face, square through its hole: what the drawing's
#: auxiliary view looks at.
TAB_FACE_POINT = (
    BASE_LENGTH / 2 - THICKNESS * cos(radians(TAB_LEAN)) + TAB_HOLE_HEIGHT * sin(radians(TAB_LEAN)),
    0.0,
    THICKNESS * sin(radians(TAB_LEAN)) + TAB_HOLE_HEIGHT * cos(radians(TAB_LEAN)),
)


@model
def angle_bracket():
    """A base plate with a mounting hole and a tab leaning 30 degrees, a hole
    square through the tab: a face no principal view shows true. Millimetres."""
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    base = bd.Box(BASE_LENGTH, BASE_WIDTH, THICKNESS, align=up)
    base -= bd.Pos(BASE_HOLE_X, 0, 0) * bd.Cylinder(BASE_HOLE_DIAMETER / 2, THICKNESS, align=up)
    tab = bd.Box(THICKNESS, BASE_WIDTH, TAB_HEIGHT, align=(bd.Align.MAX, bd.Align.CENTER, bd.Align.MIN))
    tab -= bd.Pos(-THICKNESS / 2, 0, TAB_HOLE_HEIGHT) * bd.Rot(0, 90, 0) * bd.Cylinder(TAB_HOLE_DIAMETER / 2, THICKNESS)
    part = (base + bd.Location((BASE_LENGTH / 2, 0, 0), (0, 1, 0), TAB_LEAN) * tab).clean()
    part.label = "angle_bracket"
    part.material = FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Low-carbon mild steel, cold drawn bar', metalness=1.0, roughness=0.4),
    )
    return part


if __name__ == "__main__":
    angle_bracket()
