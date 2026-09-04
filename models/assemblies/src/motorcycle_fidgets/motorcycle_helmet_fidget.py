"""Motorcycle helmet fidget with a Cherry MX switch socket.

A palm-size full-face motorcycle helmet: palm the shell, thumb the switch
set into the crown like a helmet-mounted button. Pressing the switch feels
like bonking the helmet.

Layout
------
* Units: millimeters; origin at the helmet sphere center; +Z up through
  the crown; the visor faces +X.
* Free-standing on the flat neck rim (ground at z = -14).
* MX socket: the graphite crown pod's top face is the plate top
  (z = 19.5); the pocket below opens into the hollow helmet interior, and
  the switch is pushed back out through the open neck (bottom) if ever
  needed.

Parts
-----
* shell: 2.5 mm wall dome, flat neck rim at z = -14, flat crown ring at
  z = 17, rounded eye-port window cut through the front
* crown socket pod (graphite) fused over the flattened crown
* smoke visor wrapping the eye port on two pivot discs
* rear spoiler wedge + center vent rib
"""

from __future__ import annotations
from cadgen import step

from math import cos, radians, sin

from cadgen import build123d as bd

from cadgen import srgb

from lib.mx_switch_socket import mx_socket_cutter


DISPLAY_NAME = "Motorcycle helmet MX fidget"


# shell
SHELL_OUTER_R = 21.0
SHELL_WALL = 2.5
SHELL_INNER_R = SHELL_OUTER_R - SHELL_WALL
NECK_RIM_Z = -14.0            # flat bottom cut
CROWN_FLAT_Z = 17.0           # flat top cut under the socket pod

# eye port
EYE_PORT_HALF_WIDTH_Y = 10.5
EYE_PORT_BOTTOM_Z = -6.0
EYE_PORT_TOP_Z = 4.0
EYE_PORT_CORNER_R = 4.0

# crown socket pod
POD_R = 14.0
POD_BOTTOM_Z = 14.5
PLATE_TOP_Z = 19.5

# visor
VISOR_INNER_R = 21.4
VISOR_OUTER_R = 22.6
VISOR_BOTTOM_Z = -7.0
VISOR_TOP_Z = 6.0
VISOR_HALF_ANGLE_DEG = 52.0   # each side of +X

# pivots
PIVOT_R = 3.0
PIVOT_LEN = 4.0
PIVOT_X = 13.5
PIVOT_Y = 16.9
PIVOT_Z = -0.5

# rear spoiler + vent (positions on the upper back shell)
SPOILER_CENTER = (-17.97, 0.0, 13.1)
SPOILER_ROT_DEG = -54.0
VENT_CENTER = (-15.39, 0.0, 13.08)
VENT_ROT_DEG = -50.0


# (sRGB hex, alpha) pairs: _part() turns them into Colors with srgb() at use, so
# importing this module never loads the CAD kernel (srgb() builds a bd.Color).
COLORS = {
    "shell_red": ("#D01317", 1.0),
    "graphite": ("#2E3742", 1.0),
    "visor_smoke": ("#20262B", 0.5),
    "trim_black": ("#17191C", 1.0),
}


def _part(shape, name, *details, color):
    shape.label = ":".join([name, *(str(d) for d in details)])
    shape.color = srgb(*color)
    return shape


def _make_shell():
    dome = bd.Sphere(SHELL_OUTER_R) - bd.Sphere(SHELL_INNER_R)
    keep = bd.Box(80.0, 80.0, CROWN_FLAT_Z - NECK_RIM_Z).moved(
        bd.Location((0.0, 0.0, (CROWN_FLAT_Z + NECK_RIM_Z) / 2.0))
    )
    shell = dome & keep

    port = bd.Box(
        24.0 - 6.0,
        2.0 * EYE_PORT_HALF_WIDTH_Y,
        EYE_PORT_TOP_Z - EYE_PORT_BOTTOM_Z,
    ).moved(bd.Location((15.0, 0.0, (EYE_PORT_TOP_Z + EYE_PORT_BOTTOM_Z) / 2.0)))
    port_edges = port.edges().filter_by(bd.Axis.X)
    port = bd.fillet(port_edges, radius=EYE_PORT_CORNER_R)
    return shell - port


def _make_visor():
    # profile lives in the radial-vertical plane at the sweep start angle;
    # that plane contains the revolve axis (Z) and its local y maps to -Z
    start_angle = radians(-VISOR_HALF_ANGLE_DEG)
    plane = bd.Plane(
        origin=(0.0, 0.0, 0.0),
        x_dir=(cos(start_angle), sin(start_angle), 0.0),
        z_dir=(-sin(start_angle), cos(start_angle), 0.0),
    )
    radial_center = (VISOR_INNER_R + VISOR_OUTER_R) / 2.0
    v_center = -(VISOR_TOP_Z + VISOR_BOTTOM_Z) / 2.0  # local y = -Z
    profile = bd.Rectangle(
        VISOR_OUTER_R - VISOR_INNER_R, VISOR_TOP_Z - VISOR_BOTTOM_Z
    ).moved(plane.location * bd.Location((radial_center, v_center, 0.0)))
    return bd.revolve(profile, axis=bd.Axis.Z, revolution_arc=2.0 * VISOR_HALF_ANGLE_DEG)


def _make_parts():
    parts = []

    shell = _make_shell()
    pod = bd.Cylinder(POD_R, PLATE_TOP_Z - POD_BOTTOM_Z).moved(
        bd.Location((0.0, 0.0, (POD_BOTTOM_Z + PLATE_TOP_Z) / 2.0))
    )
    socket = mx_socket_cutter(plate_top_z=PLATE_TOP_Z)

    parts.append(_part(shell - socket, "helmet_shell", color=COLORS["shell_red"]))
    parts.append(_part(pod - socket, "socket_pod", "mx_socket", color=COLORS["graphite"]))
    parts.append(_part(_make_visor(), "visor", "smoke", color=COLORS["visor_smoke"]))

    for side, y_sign in (("left", 1.0), ("right", -1.0)):
        pivot = bd.Cylinder(PIVOT_R, PIVOT_LEN).moved(
            bd.Location((PIVOT_X, y_sign * PIVOT_Y, PIVOT_Z), (90.0, 0.0, 0.0))
        )
        parts.append(_part(pivot, "visor_pivot", side, color=COLORS["trim_black"]))

    spoiler = bd.Box(7.0, 14.0, 2.5).moved(
        bd.Location(SPOILER_CENTER, (0.0, SPOILER_ROT_DEG, 0.0))
    )
    parts.append(_part(spoiler, "rear_spoiler", color=COLORS["trim_black"]))

    vent = bd.Box(9.0, 6.0, 2.0).moved(
        bd.Location(VENT_CENTER, (0.0, VENT_ROT_DEG, 0.0))
    )
    parts.append(_part(vent, "crown_vent", color=COLORS["trim_black"]))

    return parts


@step(out="../../STEP/motorcycle_fidgets/motorcycle_helmet_fidget.step")
def motorcycle_helmet_fidget():
    compound = bd.Compound(children=_make_parts())
    compound.label = "motorcycle_helmet_fidget"
    return compound


if __name__ == "__main__":
    motorcycle_helmet_fidget()
