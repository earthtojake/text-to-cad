"""A printed open-top case for the servo power board: the board on four standoffs, its USB-C port
through the left wall. The board is its own model; the case composes its 3D export.
"""

from cadgen import build123d as bd
from cadgen import step

from servo_power import HEIGHT, HOLES, THICKNESS, USB_AT, WIDTH, servo_power

WALL, GAP, FLOOR, STANDOFF = 2.0, 0.6, 2.0, 4.0
TALL = 18.0  # the servo headers stand about 11 mm above the board
BOARD_Z = FLOOR + STANDOFF  # the board's bottom face


@step(out="../STEP/servo_case.step")
def servo_case():
    C, MIN = bd.Align.CENTER, bd.Align.MIN
    outer_w, outer_h = WIDTH + 2 * (WALL + GAP), HEIGHT + 2 * (WALL + GAP)
    shell = bd.Box(outer_w, outer_h, TALL, align=(C, C, MIN))
    shell -= bd.Pos(0, 0, FLOOR) * bd.Box(outer_w - 2 * WALL, outer_h - 2 * WALL, TALL, align=(C, C, MIN))
    for x, y in HOLES:
        post = bd.Pos(x, y, FLOOR) * bd.Cylinder(3.0, STANDOFF, align=(C, C, MIN))
        shell += post - bd.Pos(x, y, FLOOR) * bd.Cylinder(1.25, STANDOFF, align=(C, C, MIN))
    # The receptacle sits on the board's top face at its left edge, its opening 1.6 mm up.
    port_z = BOARD_Z + THICKNESS + 1.6
    shell -= bd.Pos(-outer_w / 2, USB_AT[1], port_z) * bd.Box(4 * WALL, 10.0, 4.5)
    shell.label = "shell"
    return bd.Compound(children=[shell, bd.Pos(0, 0, BOARD_Z) * servo_power()], label="servo_case")


if __name__ == "__main__":
    servo_case()
