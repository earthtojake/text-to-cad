"""Motorcycle shock absorber fidget with a Cherry MX switch socket.

A palm-size coilover damper desk toy: the switch snaps into the gland-nut
head on top, and clicking it feels like the shock compressing.

Layout
------
* Units: millimeters; origin on the pedestal bottom center; +Z up.
* Free-standing on the flat pedestal bottom.
* MX socket: plate top at the gland-nut head top face (z = 80); the milled
  wrench flats on the head open into the socket pocket as switch-removal
  windows.

Parts (z map)
-------------
* pedestal + bottom mounting eye (titanium): z 0..22
* damper shank + body + spring perches (graphite): z 18..65
* preload collar (anodized red): z 26..32
* coil spring (yellow): z 38..60
* gland-nut socket head (pale aluminum): z 64..80
"""

from __future__ import annotations
from cadgen import step

from math import cos, sin, tau

from cadgen import build123d as bd

from cadgen import srgb

from lib.mx_switch_socket import MX_PLATE, mx_socket_cutter


DISPLAY_NAME = "Motorcycle shock absorber MX fidget"


# pedestal / mounts
PEDESTAL_OD = 38.0
PEDESTAL_HEIGHT = 4.0
PEDESTAL_TIER_OD = 34.0
PEDESTAL_TIER_HEIGHT = 2.0

EYE_OD = 20.0
EYE_BORE = 8.0
EYE_WIDTH = 8.0
EYE_CENTER_Z = 12.0

SHANK_BOTTOM_Z = 18.0
SHANK_TOP_Z = 28.0
SHANK_BOTTOM_R = 8.0

# damper body
BODY_R = 14.0
BODY_BOTTOM_Z = 24.0
BODY_TOP_Z = 65.0

COLLAR_R = 15.5
COLLAR_BOTTOM_Z = 26.0
COLLAR_TOP_Z = 32.0
COLLAR_GROOVE_MINOR_R = 0.8

# spring
SPRING_BOTTOM_Z = 38.0
SPRING_TOP_Z = 60.0
SPRING_MEAN_R = 19.5
SPRING_WIRE_R = 2.75
SPRING_TURNS = 3.5

LOWER_PERCH_BOTTOM_Z = 32.5
LOWER_PERCH_TOP_Z = SPRING_BOTTOM_Z
PERCH_OUTER_R = 18.5
UPPER_PERCH_BOTTOM_Z = SPRING_TOP_Z
UPPER_PERCH_TOP_Z = 65.0
UPPER_PERCH_TOP_R = 14.5

# socket head
HEAD_R = 15.0
HEAD_BOTTOM_Z = 64.0
PLATE_TOP_Z = 80.0
FLAT_HALF_WIDTH = 11.0        # milled wrench flats, also removal windows
FLAT_BOTTOM_Z = 68.0
FLAT_TOP_Z = PLATE_TOP_Z - MX_PLATE


# (sRGB hex, alpha) pairs: _part() turns them into Colors with srgb() at use, so
# importing this module never loads the CAD kernel (srgb() builds a bd.Color).
COLORS = {
    "titanium": ("#3A4750", 1.0),
    "graphite": ("#2E3742", 1.0),
    "anodized_red": ("#C1121F", 1.0),
    "spring_yellow": ("#F6BE00", 1.0),
    "pale_aluminum": ("#C9CDD1", 1.0),
}


def _part(shape, name, *details, color):
    shape.label = ":".join([name, *(str(d) for d in details)])
    shape.color = srgb(*color)
    return shape


def _axis_cylinder(center, axis, radius, height):
    """Cylinder of given radius/height centered on `center`, axis along `axis`."""
    z_dir = bd.Vector(axis).normalized()
    plane = bd.Plane(origin=center, z_dir=z_dir)
    return bd.Cylinder(radius, height).moved(plane.location)


def _coil_spring(bottom_z, top_z, mean_r, wire_r, turns, segments_per_turn=20):
    """Compression coil as tangent-aligned overlapping cylinder segments."""
    height = top_z - bottom_z
    segments = max(8, round(turns * segments_per_turn))
    points = [
        bd.Vector(
            mean_r * cos(turns * tau * i / segments),
            mean_r * sin(turns * tau * i / segments),
            bottom_z + height * i / segments,
        )
        for i in range(segments + 1)
    ]
    links = [
        _axis_cylinder(
            tuple((start + end) * 0.5), tuple((end - start).normalized()),
            wire_r, (end - start).length + 2.0 * wire_r,
        )
        for start, end in zip(points, points[1:])
    ]
    return links[0].fuse(*links[1:])


def _make_parts():
    parts = []

    pedestal = bd.Cylinder(PEDESTAL_OD / 2.0, PEDESTAL_HEIGHT).moved(
        bd.Location((0.0, 0.0, PEDESTAL_HEIGHT / 2.0))
    ) + bd.Cylinder(PEDESTAL_TIER_OD / 2.0, PEDESTAL_TIER_HEIGHT).moved(
        bd.Location((0.0, 0.0, PEDESTAL_HEIGHT + PEDESTAL_TIER_HEIGHT / 2.0))
    )
    parts.append(_part(pedestal, "pedestal_base", color=COLORS["titanium"]))

    eye_center = (0.0, 0.0, EYE_CENTER_Z)
    eye = _axis_cylinder(eye_center, (0.0, 1.0, 0.0), EYE_OD / 2.0, EYE_WIDTH) - \
        _axis_cylinder(eye_center, (0.0, 1.0, 0.0), EYE_BORE / 2.0, EYE_WIDTH + 2.0)
    parts.append(_part(eye, "mounting_eye", "lower", color=COLORS["titanium"]))

    shank = bd.Cone(
        bottom_radius=SHANK_BOTTOM_R, top_radius=BODY_R,
        height=SHANK_TOP_Z - SHANK_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (SHANK_BOTTOM_Z + SHANK_TOP_Z) / 2.0)))
    parts.append(_part(shank, "eye_shank", color=COLORS["graphite"]))

    body = bd.Cylinder(BODY_R, BODY_TOP_Z - BODY_BOTTOM_Z).moved(
        bd.Location((0.0, 0.0, (BODY_BOTTOM_Z + BODY_TOP_Z) / 2.0))
    )
    parts.append(_part(body, "damper_body", color=COLORS["graphite"]))

    collar_center_z = (COLLAR_BOTTOM_Z + COLLAR_TOP_Z) / 2.0
    collar = bd.Cylinder(COLLAR_R, COLLAR_TOP_Z - COLLAR_BOTTOM_Z).moved(
        bd.Location((0.0, 0.0, collar_center_z))
    )
    for groove_z in (collar_center_z - 1.8, collar_center_z + 1.8):
        collar = collar - bd.Torus(
            major_radius=COLLAR_R, minor_radius=COLLAR_GROOVE_MINOR_R,
        ).moved(bd.Location((0.0, 0.0, groove_z)))
    parts.append(_part(collar, "preload_collar", color=COLORS["anodized_red"]))

    lower_perch = bd.Cone(
        bottom_radius=BODY_R, top_radius=PERCH_OUTER_R,
        height=LOWER_PERCH_TOP_Z - LOWER_PERCH_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (LOWER_PERCH_BOTTOM_Z + LOWER_PERCH_TOP_Z) / 2.0)))
    parts.append(_part(lower_perch, "lower_spring_perch", color=COLORS["graphite"]))

    upper_perch = bd.Cone(
        bottom_radius=PERCH_OUTER_R, top_radius=UPPER_PERCH_TOP_R,
        height=UPPER_PERCH_TOP_Z - UPPER_PERCH_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (UPPER_PERCH_BOTTOM_Z + UPPER_PERCH_TOP_Z) / 2.0)))
    parts.append(_part(upper_perch, "upper_spring_perch", color=COLORS["graphite"]))

    spring = _coil_spring(
        SPRING_BOTTOM_Z, SPRING_TOP_Z, SPRING_MEAN_R, SPRING_WIRE_R, SPRING_TURNS,
    )
    parts.append(_part(spring, "coil_spring", color=COLORS["spring_yellow"]))

    head = bd.Cylinder(HEAD_R, PLATE_TOP_Z - HEAD_BOTTOM_Z).moved(
        bd.Location((0.0, 0.0, (HEAD_BOTTOM_Z + PLATE_TOP_Z) / 2.0))
    )
    flats = bd.Box(
        2.0 * HEAD_R + 2.0, 2.0 * FLAT_HALF_WIDTH, FLAT_TOP_Z - FLAT_BOTTOM_Z,
    ).moved(bd.Location((0.0, 0.0, (FLAT_BOTTOM_Z + FLAT_TOP_Z) / 2.0)))
    head = head - flats - mx_socket_cutter(plate_top_z=PLATE_TOP_Z)
    parts.append(_part(head, "gland_nut_socket_head", "mx_socket", color=COLORS["pale_aluminum"]))

    return parts


@step(out="../../STEP/motorcycle_fidgets/motorcycle_shock_fidget.step")
def motorcycle_shock_fidget():
    compound = bd.Compound(children=_make_parts())
    compound.label = "motorcycle_shock_fidget"
    return compound


if __name__ == "__main__":
    motorcycle_shock_fidget()
