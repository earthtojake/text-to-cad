"""Demo: a pillow-block bearing mount with a ball bearing, a shaft and two M6 cap screws.

Millimetres, +Z up. The shaft runs along Y; the base sits on z=0.
"""

import math

import build123d as bd
from cad import model

# Housing
BASE_W, BASE_D, BASE_T = 90, 30, 10
AXIS_Z = 32            # shaft centre height above the base's underside
HOUSING_R = 24
BOLT_X = 34            # mounting holes at x = +/-BOLT_X
BOLT_CLEAR_D = 6.6     # M6 clearance
CBORE_D, CBORE_DEPTH = 11, 6

# Bearing (6002-like: 15 x 32 x 9)
BRG_OD, BRG_ID, BRG_W = 32, 15, 9
BALL_D, BALL_COUNT = 4, 9

SHAFT_L = 80


def along_y(shape):
    """A shape built on the Z axis, turned onto the shaft's Y axis at shaft height."""
    return bd.Pos(0, 0, AXIS_Z) * bd.Rot(90, 0, 0) * shape


def housing():
    base = bd.Pos(0, 0, BASE_T / 2) * bd.Box(BASE_W, BASE_D, BASE_T)
    base = bd.fillet(base.edges().filter_by(bd.Axis.Z), 4)
    web = bd.Pos(0, 0, AXIS_Z / 2) * bd.Box(2 * HOUSING_R, BASE_D, AXIS_Z)
    barrel = along_y(bd.Cylinder(HOUSING_R, BASE_D))
    body = base + web + barrel

    body -= along_y(bd.Cylinder(BRG_OD / 2, BASE_D))
    for x in (-BOLT_X, BOLT_X):
        body -= bd.Pos(x, 0, BASE_T / 2) * bd.Cylinder(BOLT_CLEAR_D / 2, BASE_T)
        body -= bd.Pos(x, 0, BASE_T - CBORE_DEPTH / 2) * bd.Cylinder(CBORE_D / 2, CBORE_DEPTH)

    body.label = "housing"
    body.color = "#3f6fb5"
    return body


def bearing():
    outer = bd.Cylinder(BRG_OD / 2, BRG_W) - bd.Cylinder(BRG_OD / 2 - 2.25, BRG_W)
    inner = bd.Cylinder(BRG_ID / 2 + 2.25, BRG_W) - bd.Cylinder(BRG_ID / 2, BRG_W)
    pitch_r = (BRG_OD + BRG_ID) / 4
    balls = [
        bd.Pos(pitch_r * math.cos(a), pitch_r * math.sin(a), 0) * bd.Sphere(BALL_D / 2)
        for a in (2 * math.pi * i / BALL_COUNT for i in range(BALL_COUNT))
    ]

    parts = []
    for label, shape, color in (
        ("outer_ring", outer, "#c9ccd1"),
        ("inner_ring", inner, "#c9ccd1"),
        ("balls", bd.Compound(balls), "#f2f2f2"),
    ):
        placed = along_y(shape)
        placed.label = label
        placed.color = color
        parts.append(placed)
    return bd.Compound(label="bearing", children=parts)


def shaft():
    rod = bd.Cylinder(BRG_ID / 2, SHAFT_L)
    rod = bd.chamfer(rod.edges().filter_by(bd.GeomType.CIRCLE), 1)
    rod = along_y(rod)
    rod.label = "shaft"
    rod.color = "#8a8f98"
    return rod


def cap_screw(label, x):
    """An M6 socket-head cap screw, head flush with the top of the base."""
    head = bd.Pos(0, 0, -3) * bd.Cylinder(5, 6)
    socket = bd.Pos(0, 0, -1.5) * bd.extrude(bd.RegularPolygon(2.9, 6), 1.5, both=True)
    shank = bd.Pos(0, 0, -6 - 6) * bd.Cylinder(3, 12)
    screw = bd.Pos(x, 0, BASE_T) * (head - socket + shank)
    screw.label = label
    screw.color = "#2b2d31"
    return screw


@model
def pillow_block():
    return bd.Compound(
        label="pillow_block",
        children=[
            housing(),
            bearing(),
            shaft(),
            cap_screw("screw_left", -BOLT_X),
            cap_screw("screw_right", BOLT_X),
        ],
    )


if __name__ == "__main__":
    pillow_block()
