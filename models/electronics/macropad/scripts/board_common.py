"""What the layout steps share: the board's geometry and where every part goes.

KiCad's frame: millimetres, x right, y down, seen from the top. Every SMD part is on the bottom
(one-sided assembly; the hot-swap sockets and the reverse-mount LEDs must be there anyway), the
switches' footprints included (their sockets solder to the bottom); the top holds only the switches
themselves and the encoder. A bottom part's position is where its centre is, seen from the top.
"""
import math

PITCH = 19.05                    # MX key pitch
GRID_C = (100.0, 101.5)          # the centre key's centre
X0, X1, Y0, Y1 = 70.5, 129.5, 47.5, 131.0   # board outline (a rounded rectangle)
CORNER = 3.0
THICKNESS = 1.6


def key_xy(i):
    """SW1..SW9 row-major from the top left, as the person looking down at the keys reads them."""
    row, col = divmod(i, 3)
    return (GRID_C[0] + (col - 1) * PITCH, GRID_C[1] + (row - 1) * PITCH)


# LED chain: serpentine, so each DOUT is next to the next DIN. LED k sits in key LED_KEY[k]'s window.
LED_KEY = [0, 1, 2, 5, 4, 3, 6, 7, 8]
LED_DOWN = 5.08                  # the MX LED window is 5.08 below the switch centre (KiCad y)

HOLES = {"H1": (GRID_C[0] - PITCH / 2, GRID_C[1] - PITCH / 2), "H2": (GRID_C[0] + PITCH / 2, GRID_C[1] - PITCH / 2),
         "H3": (GRID_C[0] - PITCH / 2, GRID_C[1] + PITCH / 2), "H4": (GRID_C[0] + PITCH / 2, GRID_C[1] + PITCH / 2),
         "H5": (72.6, 49.5), "H6": (127.4, 49.5)}

ENC_SHAFT = (121.0, 60.5)       # encoder shaft centre; its footprint's origin is pad A, 7.5 left and 2.5 up
USB_X = 90.0
USB_EDGE = Y0                    # the receptacle's mating face on the back edge


def placements():
    """ref -> (x, y, degrees, side)."""
    p = {}
    for i in range(9):
        x, y = key_xy(i)
        p[f"SW{i + 1}"] = (x, y, 0, "B")
    for k, key in enumerate(LED_KEY):
        x, y = key_xy(key)
        row = key // 3
        # a row run left to right wants DOUT on the right: the flipped footprint at 180; right to left: 0
        p[f"D{k + 1}"] = (x, y + LED_DOWN, 180 if row % 2 == 0 else 0, "B")
    for ref, (x, y) in HOLES.items():
        p[ref] = (x, y, 0, "F")
    # turned a quarter: A, C, B in a row in front of the shaft (toward the keys), the switch's pins behind
    p["SW10"] = (ENC_SHAFT[0] - 2.5, ENC_SHAFT[1] + 7.5, 90, "F")
    p["J1"] = (USB_X, USB_EDGE + 3.675, 180, "B")
    return p
