"""Motorcycle pillion (backseat) fidget with a Cherry MX switch socket.

A palm-size quilted passenger seat: rest it in a palm and thumb the
switch set into the center of the pad like a whoopee cushion. A rear grab
rail arcs over the tail.

Layout
------
* Units: millimeters; origin at the base plate bottom center; +Z up; the
  seat faces +X (rider forward), taillight at the rear.
* Free-standing on the flat base plate.
* MX socket: the graphite pod on the seat top is the plate top
  (z = 21); the pocket floor lands at z = 7 and a 10 mm hole through the
  base plate lets a finger or tool push the switch back out.

Parts
-----
* base plate (black plastic) with red taillight lens on the tail face
* quilted seat pad (tan leather) with two longitudinal and two
  transverse stitch grooves
* switch pod (graphite) at the seat center
* grab rail (steel half-hoop) over the tail on two legs
"""

from __future__ import annotations

from build123d import (
    Axis,
    Box,
    Compound,
    Cylinder,
    Location,
    Torus,
    fillet,
)

from cadgen import srgb

from mx_switch_socket import MX_POCKET_DEPTH, mx_socket_cutter


DISPLAY_NAME = "Motorcycle pillion seat MX fidget"


# base plate
BASE_L = 58.0
BASE_W = 34.0
BASE_H = 4.0
BASE_EDGE_FILLET = 5.0      # vertical corners only

# seat pad
PAD_L = 54.0
PAD_W = 30.0
PAD_H = 14.0                # spans z 4..18
PAD_TOP_Z = BASE_H + PAD_H
PAD_FILLET = 6.0            # all edges

# quilting
STITCH_R = 1.3
STITCH_LONG_Y = 5.0         # longitudinal grooves at y = +/- 5
STITCH_LONG_Z = 17.4
STITCH_TRANS_X = 16.0       # transverse grooves at x = +/- 16

# switch pod
POD_R = 13.0
POD_BOTTOM_Z = 15.5
PLATE_TOP_Z = 21.0
REMOVAL_HOLE_D = 10.0

# grab rail
RAIL_CENTER = (-22.0, 0.0, 22.0)
RAIL_MAJOR_R = 10.0
RAIL_TUBE_R = 2.5
RAIL_LEG_R = 2.2
RAIL_LEG_Z_BOTTOM = 16.5
RAIL_LEG_Z_TOP = 22.5
RAIL_LEG_Y = 10.0

# taillight
LENS_L = 3.0
LENS_W = 14.0
LENS_H = 2.5
LENS_X = -28.5


COLORS = {
    "trim_black": srgb("#17191C"),
    "tan_leather": srgb("#8A6642"),
    "graphite": srgb("#2E3742"),
    "steel": srgb("#BFC5CC"),
    "lens_red": srgb("#D01317"),
}


def _part(shape, name, *details, color):
    shape.label = ":".join([name, *(str(d) for d in details)])
    shape.color = color
    return shape


def _axis_cylinder_x(radius, length, center):
    return Cylinder(radius, length).moved(Location(center, (0.0, 90.0, 0.0)))


def _axis_cylinder_y(radius, length, center):
    return Cylinder(radius, length).moved(Location(center, (90.0, 0.0, 0.0)))


def _make_parts():
    parts = []

    pocket_floor_z = PLATE_TOP_Z - 1.5 - MX_POCKET_DEPTH
    # finger/tool hole through the pocket floor, pad floor, and base plate so
    # the switch can be pushed back out from below
    removal = Cylinder(
        REMOVAL_HOLE_D / 2.0, pocket_floor_z + 1.0
    ).moved(Location((0.0, 0.0, (pocket_floor_z - 1.0) / 2.0)))

    plate = Box(BASE_L, BASE_W, BASE_H).moved(Location((0.0, 0.0, BASE_H / 2.0)))
    plate = fillet(plate.edges().filter_by(Axis.Z), radius=BASE_EDGE_FILLET)
    plate = plate - removal
    parts.append(_part(plate, "seat_base_plate", color=COLORS["trim_black"]))

    lens = Box(LENS_L, LENS_W, LENS_H).moved(Location((LENS_X, 0.0, BASE_H / 2.0)))
    parts.append(_part(lens, "taillight_lens", color=COLORS["lens_red"]))

    pad = Box(PAD_L, PAD_W, PAD_H).moved(Location((0.0, 0.0, BASE_H + PAD_H / 2.0)))
    pad = fillet(pad.edges(), radius=PAD_FILLET)
    grooves = [
        _axis_cylinder_x(STITCH_R, PAD_L - 2.0, (0.0, y, STITCH_LONG_Z))
        for y in (STITCH_LONG_Y, -STITCH_LONG_Y)
    ] + [
        _axis_cylinder_y(STITCH_R, PAD_W + 2.0, (x, 0.0, STITCH_LONG_Z))
        for x in (STITCH_TRANS_X, -STITCH_TRANS_X)
    ]
    pad = pad - grooves[0].fuse(*grooves[1:]) - removal
    parts.append(_part(pad, "seat_pad", "quilted", color=COLORS["tan_leather"]))

    pod = Cylinder(POD_R, PLATE_TOP_Z - POD_BOTTOM_Z).moved(
        Location((0.0, 0.0, (POD_BOTTOM_Z + PLATE_TOP_Z) / 2.0))
    )
    pod = pod - mx_socket_cutter(plate_top_z=PLATE_TOP_Z)
    parts.append(_part(pod, "switch_pod", "mx_socket", color=COLORS["graphite"]))

    rail = Torus(RAIL_MAJOR_R, RAIL_TUBE_R).moved(Location(RAIL_CENTER))
    front_half = Box(60.0, 40.0, 20.0).moved(Location((10.0, 0.0, RAIL_CENTER[2])))
    rail = rail - front_half
    parts.append(_part(rail, "grab_rail", color=COLORS["steel"]))

    for side, y_sign in (("left", 1.0), ("right", -1.0)):
        leg = Cylinder(RAIL_LEG_R, RAIL_LEG_Z_TOP - RAIL_LEG_Z_BOTTOM).moved(
            Location((RAIL_CENTER[0], y_sign * RAIL_LEG_Y,
                      (RAIL_LEG_Z_BOTTOM + RAIL_LEG_Z_TOP) / 2.0))
        )
        parts.append(_part(leg, "grab_rail_leg", side, color=COLORS["steel"]))

    return parts


def gen_step():
    compound = Compound(children=_make_parts())
    compound.label = "motorcycle_seat_fidget"
    return compound
