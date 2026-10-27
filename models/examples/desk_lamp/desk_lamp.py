"""Desk lamp concept; dimensions in mm. Bulb and socket are simplified.

The straight arm is 300 mm end to end. Assumed base: Ø180 × 20;
shade: Ø130 mouth, Ø40 crown, 90 high, 2 mm radial wall.
"""
from math import radians, sin, cos

from cadgen import build123d as bd
from cadgen import srgb, step

ARM_LENGTH = 300.0
ARM_TILT = 12.0
BASE_RADIUS = 90.0
BASE_HEIGHT = 20.0
SHADE_HEIGHT = 90.0
SHADE_TILT = -35.0


def finish(shape, label, color):
    shape.label = label
    shape.color = srgb(color)
    return shape


@step
def desk_lamp():
    bottom = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    base = bd.Cylinder(BASE_RADIUS, BASE_HEIGHT, align=bottom)
    base = bd.fillet(base.edges().filter_by(bd.GeomType.CIRCLE), radius=3)
    base = finish(base, "round_base", "#243C3B")

    arm_frame = bd.Pos(-35, 0, BASE_HEIGHT) * bd.Rot(0, ARM_TILT, 0)
    arm = arm_frame * bd.Cylinder(6, ARM_LENGTH, align=bottom)
    arm = finish(arm, "straight_arm_300mm", "#C5A46A")
    collar = bd.Pos(-35, 0, BASE_HEIGHT) * bd.Cylinder(11, 12, align=bottom)
    collar = finish(collar, "base_collar", "#243C3B")

    tip_x = -35 + ARM_LENGTH * sin(radians(ARM_TILT))
    tip_z = BASE_HEIGHT + ARM_LENGTH * cos(radians(ARM_TILT))
    head_frame = bd.Pos(tip_x, 0, tip_z) * bd.Rot(0, SHADE_TILT, 0) * bd.Pos(0, 0, -SHADE_HEIGHT)
    # Open mouth at z=0; crown has a 2 mm solid cap for the socket.
    shade = bd.Cone(65, 20, SHADE_HEIGHT, align=bottom)
    cavity = bd.Pos(0, 0, -1) * bd.Cone(63.5, 19, 89, align=bottom)
    shade = head_frame * (shade - cavity)
    shade = finish(shade, "conical_shade", "#243C3B")
    socket = head_frame * (bd.Pos(0, 0, 59) * bd.Cylinder(14, 29, align=bottom))
    socket = finish(socket, "bulb_socket", "#44464A")
    neck = head_frame * (bd.Pos(0, 0, 39) * bd.Cylinder(11, 20, align=bottom))
    neck = finish(neck, "bulb_neck", "#D4C9B4")
    bulb = head_frame * (bd.Pos(0, 0, 20) * bd.Sphere(24))
    bulb = finish(bulb, "bulb", "#FFF1CE")
    switch = bd.Pos(38, 0, BASE_HEIGHT) * bd.Cylinder(8, 3, align=bottom)
    switch = finish(switch, "power_switch", "#C5A46A")
    return bd.Compound(children=[base, collar, arm, shade, socket, neck, bulb, switch], label="desk_lamp")


if __name__ == "__main__":
    desk_lamp()
