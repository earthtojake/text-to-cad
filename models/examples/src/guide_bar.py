from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
import build123d as bd


LENGTH = 600.0
DIAMETER = 20.0
SPIGOT_LENGTH = 30.0
SPIGOT_DIAMETER = 12.0
CROSS_HOLE_DIAMETER = 6.0
CROSS_HOLE_INSET = 20.0   # from each end of the bar
END_CHAMFER = 1.0


@model
def guide_bar():
    """A 600 mm round bar with a spigot on one end and a cross hole near each end:
    a long part of constant section, which a drawing breaks. Millimetres."""
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    along_x = bd.Rot(0, 90, 0)
    part = along_x * bd.Cylinder(DIAMETER / 2, LENGTH, align=up)
    part = bd.chamfer(part.edges().filter_by(bd.GeomType.CIRCLE).group_by(bd.Axis.X)[0], END_CHAMFER)
    part += bd.Pos(LENGTH, 0, 0) * along_x * bd.Cylinder(SPIGOT_DIAMETER / 2, SPIGOT_LENGTH, align=up)
    for x in (CROSS_HOLE_INSET, LENGTH - CROSS_HOLE_INSET):
        part -= bd.Pos(x, 0, 0) * bd.Cylinder(CROSS_HOLE_DIAMETER / 2, DIAMETER * 2)
    part.label = "guide_bar"
    part.material = FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Chromium-molybdenum alloy steel for shafts and gears', metalness=1.0,
            roughness=0.4),
    )
    return part


if __name__ == "__main__":
    guide_bar()
