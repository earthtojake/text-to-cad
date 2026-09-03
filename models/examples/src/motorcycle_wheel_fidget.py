"""Motorcycle wheel fidget with a Cherry MX switch socket.

A palm-size knobby motorcycle wheel lying flat: hold the tire, thumb the
switch in the hub like a horn button. Five-spoke mag wheel look with open
windows between hub and rim.

Layout
------
* Units: millimeters; origin on the wheel spin axis at the tire center
  plane; +Z up (the wheel lies flat and stands on the tire).
* Free-standing on the tire ring (ground at z = -10).
* MX socket: plate top at the hub top face (z = 10); the hub floor below
  the pocket carries a 10 mm finger hole so the switch can be pushed out
  from below (the hub bottom floats above the ground plane).

Parts
-----
* tire (rubber) + 16 tread knobs on the outer equator
* rim band (graphite) fused into the tire inner diameter
* 5 tapered-position mag spokes (anodized red) from hub to rim
* hub (silver) hosting the MX socket
* valve stem (chrome) poking out of the rim
"""

from __future__ import annotations
from cadgen import step

from math import cos, radians, sin, tau

from cadgen import build123d as bd

from cadgen import srgb

from lib.mx_switch_socket import MX_POCKET_DEPTH, mx_socket_cutter


DISPLAY_NAME = "Motorcycle wheel MX fidget"


# tire
TIRE_RING_R = 36.0            # torus centerline radius
TIRE_TUBE_R = 10.0            # torus tube radius
TIRE_OD = 2.0 * (TIRE_RING_R + TIRE_TUBE_R)
KNOB_COUNT = 16
KNOB_R = 3.2
KNOB_LEN = 7.0

# rim
RIM_INNER_R = 24.0
RIM_OUTER_R = 27.0
RIM_HALF_HEIGHT = 5.0

# spokes
SPOKE_COUNT = 5
SPOKE_RADIAL_LEN = 13.0       # spans r 12..25, embedded in hub and rim
SPOKE_CENTER_R = 18.5
SPOKE_WIDTH = 9.0
SPOKE_THICKNESS = 7.0

# hub + socket
HUB_R = 14.0
HUB_BOTTOM_Z = -6.0
PLATE_TOP_Z = 10.0            # hub top face; pocket floor lands at z = -4
REMOVAL_HOLE_D = 10.0

# valve stem
VALVE_ANGLE_DEG = 25.0        # between two spokes
VALVE_TILT_DEG = 30.0         # kicked up from the rim plane
VALVE_R = 1.5
VALVE_LEN = 9.0


# (sRGB hex, alpha) pairs: _part() turns them into Colors with srgb() at use, so
# importing this module never loads the CAD kernel (srgb() builds a bd.Color).
COLORS = {
    "rubber": ("#1A1A1E", 1.0),
    "graphite": ("#2E3742", 1.0),
    "anodized_red": ("#C1121F", 1.0),
    "pale_aluminum": ("#C9CDD1", 1.0),
    "chrome": ("#E8EAED", 1.0),
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


def _make_parts():
    parts = []

    tire = bd.Torus(TIRE_RING_R, TIRE_TUBE_R)
    parts.append(_part(tire, "tire", color=COLORS["rubber"]))

    for index in range(KNOB_COUNT):
        angle = tau * index / KNOB_COUNT
        direction = (cos(angle), sin(angle), 0.0)
        center = tuple((TIRE_RING_R + TIRE_TUBE_R) * d for d in direction)
        knob = _axis_cylinder(center, direction, KNOB_R, KNOB_LEN)
        parts.append(_part(knob, "tread_knob", index + 1, color=COLORS["rubber"]))

    rim = bd.Cylinder(RIM_OUTER_R, 2.0 * RIM_HALF_HEIGHT) - bd.Cylinder(
        RIM_INNER_R, 2.0 * RIM_HALF_HEIGHT + 2.0
    )
    parts.append(_part(rim, "rim", color=COLORS["graphite"]))

    for index in range(SPOKE_COUNT):
        angle_deg = 360.0 * index / SPOKE_COUNT
        angle = radians(angle_deg)
        spoke = bd.Box(SPOKE_RADIAL_LEN, SPOKE_WIDTH, SPOKE_THICKNESS).moved(
            bd.Location(
                (SPOKE_CENTER_R * cos(angle), SPOKE_CENTER_R * sin(angle), 0.0),
                (0.0, 0.0, angle_deg),
            )
        )
        parts.append(_part(spoke, "mag_spoke", index + 1, color=COLORS["anodized_red"]))

    pocket_floor_z = PLATE_TOP_Z - 1.5 - MX_POCKET_DEPTH
    hub = bd.Cylinder(HUB_R, PLATE_TOP_Z - HUB_BOTTOM_Z).moved(
        bd.Location((0.0, 0.0, (HUB_BOTTOM_Z + PLATE_TOP_Z) / 2.0))
    )
    hub = hub - mx_socket_cutter(plate_top_z=PLATE_TOP_Z)
    # finger/tool hole through the pocket floor and hub bottom, so the switch
    # can be pushed back out from below
    removal = bd.Cylinder(
        REMOVAL_HOLE_D / 2.0, pocket_floor_z - HUB_BOTTOM_Z + 1.0
    ).moved(bd.Location((0.0, 0.0, (HUB_BOTTOM_Z - 1.0 + pocket_floor_z) / 2.0)))
    hub = hub - removal
    parts.append(_part(hub, "hub", "mx_socket", color=COLORS["pale_aluminum"]))

    tilt = radians(VALVE_TILT_DEG)
    base_angle = radians(VALVE_ANGLE_DEG)
    radial = (cos(base_angle), sin(base_angle), 0.0)
    direction = (
        cos(tilt) * radial[0], cos(tilt) * radial[1], sin(tilt),
    )
    center = tuple(RIM_OUTER_R * d + VALVE_LEN / 2.0 * c
                   for d, c in zip(radial, direction))
    center = (center[0], center[1], 2.0 + direction[2] * VALVE_LEN / 2.0)
    valve = _axis_cylinder(center, direction, VALVE_R, VALVE_LEN)
    parts.append(_part(valve, "valve_stem", color=COLORS["chrome"]))

    return parts


@step(out="../STEP/motorcycle_wheel_fidget.step")
def motorcycle_wheel_fidget():
    compound = bd.Compound(children=_make_parts())
    compound.label = "motorcycle_wheel_fidget"
    return compound


if __name__ == "__main__":
    motorcycle_wheel_fidget()
