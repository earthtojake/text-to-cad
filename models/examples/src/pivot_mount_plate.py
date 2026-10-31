from __future__ import annotations

from bd_materials import FinishedMaterial, metals, plastics
from threejs_materials import PbrProperties

from cadgen import model
import build123d as bd


# The plate is modelled from its datum corner: X from datum C (the end face at X = 0),
# Y from datum B (the side face at Y = 0), Z from datum A (the mounting face at Z = 0).
PLATE_LENGTH = 100.0
PLATE_WIDTH = 70.0
PLATE_THICKNESS = 10.0
CORNER_RADIUS = 5.0

# Four M6 clearance holes, each 12 in from the plate's edges (2D edge distance).
BOLT_HOLE_DIAMETER = 6.6
BOLT_HOLE_INSET = 12.0
BOLT_PITCH_X = PLATE_LENGTH - 2 * BOLT_HOLE_INSET
BOLT_PITCH_Y = PLATE_WIDTH - 2 * BOLT_HOLE_INSET
BOLT_HOLES = tuple((BOLT_HOLE_INSET + i * BOLT_PITCH_X, BOLT_HOLE_INSET + j * BOLT_PITCH_Y)
                   for j in (0, 1) for i in (0, 1))

# The pivot bore in the middle of the plate, which takes a lined bushing pressed in
# flush on both faces: a CRES sleeve with a PTFE fabric liner bonded in its bore.
BORE_X = PLATE_LENGTH / 2
BORE_Y = PLATE_WIDTH / 2
BORE_DIAMETER = 16.0
BUSHING_BORE = 12.5
LINER_THICKNESS = 0.25
PIN_DIAMETER = BUSHING_BORE - 2 * LINER_THICKNESS   # the liner's bore, which the pivot pin runs in


def _sleeve(outer: float, inner: float):
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    sleeve = bd.Cylinder(outer / 2, PLATE_THICKNESS, align=up) - bd.Cylinder(inner / 2, PLATE_THICKNESS, align=up)
    return bd.Pos(BORE_X, BORE_Y, 0) * sleeve


def _plate():
    corner = (bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    plate = bd.Box(PLATE_LENGTH, PLATE_WIDTH, PLATE_THICKNESS, align=corner)
    plate = bd.fillet(plate.edges().filter_by(bd.Axis.Z), CORNER_RADIUS)
    for x, y in BOLT_HOLES:
        plate -= bd.Pos(x, y, 0) * bd.Cylinder(BOLT_HOLE_DIAMETER / 2, PLATE_THICKNESS, align=up)
    plate -= bd.Pos(BORE_X, BORE_Y, 0) * bd.Cylinder(BORE_DIAMETER / 2, PLATE_THICKNESS, align=up)
    plate.label = "mount_plate"
    plate.material = FinishedMaterial(
        metals.aluminum(metals.Alu.G7075_T6).material,
        pbr=PbrProperties.create('Aluminum 7075-T651 plate', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    return plate


@model
def pivot_mount_plate():
    """A machined pivot mounting plate with its lined bushing pressed in: the plate
    (Aluminum 7075-T651), the bushing's CRES sleeve and the PTFE fabric liner bonded
    in its bore, each a part of the assembly. Millimetres."""
    bushing = _sleeve(BORE_DIAMETER, BUSHING_BORE)
    bushing.label = "bushing"
    bushing.material = FinishedMaterial(
        metals.stainless(metals.Stainless.G303_ANNEALED).material,
        pbr=PbrProperties.create('Corrosion-resistant steel 303', metalness=1.0, roughness=0.3),
    )
    liner = _sleeve(BUSHING_BORE, PIN_DIAMETER)
    liner.label = "liner"
    liner.material = FinishedMaterial(
        plastics.ptfe().material,
        pbr=PbrProperties.create('PTFE fabric liner', metalness=0.0, roughness=0.8),
    )
    return bd.Compound(children=[_plate(), bushing, liner], label="pivot_mount_plate")


if __name__ == "__main__":
    pivot_mount_plate()
