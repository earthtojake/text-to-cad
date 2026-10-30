from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
import build123d as bd


LENGTH = 160.0
WIDTH = 100.0
THICKNESS = 8.0
CORNER_RADIUS = 5.0
SMALL_HOLE_DIAMETER = 6.0
SMALL_HOLE_XS = (-60.0, -30.0, 0.0, 30.0, 60.0)
SMALL_HOLE_Y = 35.0
DOWEL_HOLE_DIAMETER = 10.0
DOWEL_HOLE_X = 60.0
BORE_DIAMETER = 24.0
SLOT_CENTRE_X = 30.0
SLOT_LENGTH = 24.0
SLOT_WIDTH = 8.0


@model
def perforated_plate():
    """A plate with rows of holes, two dowel holes, a bore and a slot: the part a
    hole table documents. Millimetres."""
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    part = bd.Box(LENGTH, WIDTH, THICKNESS, align=up)
    part = bd.fillet(part.edges().filter_by(bd.Axis.Z), CORNER_RADIUS)
    for x in SMALL_HOLE_XS:
        for y in (-SMALL_HOLE_Y, SMALL_HOLE_Y):
            part -= bd.Pos(x, y, 0) * bd.Cylinder(SMALL_HOLE_DIAMETER / 2, THICKNESS, align=up)
    for x in (-DOWEL_HOLE_X, DOWEL_HOLE_X):
        part -= bd.Pos(x, 0, 0) * bd.Cylinder(DOWEL_HOLE_DIAMETER / 2, THICKNESS, align=up)
    part -= bd.Cylinder(BORE_DIAMETER / 2, THICKNESS, align=up)
    part -= bd.Pos(SLOT_CENTRE_X, 0, 0) * bd.extrude(bd.SlotCenterToCenter(SLOT_LENGTH - SLOT_WIDTH, SLOT_WIDTH),
                                                     THICKNESS)
    part.label = "perforated_plate"
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    return part


if __name__ == "__main__":
    perforated_plate()
