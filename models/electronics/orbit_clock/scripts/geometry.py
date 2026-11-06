"""The board's geometry, in KiCad's frame (millimetres, x right, y DOWN), as the board scripts place it.

The CAD model never imports this: it reads the saved board (kicad_pcb.read) for the outline, the holes and
every LED, so the baffle's cells come from where the parts really are.
"""
import math

CX, CY = 100.0, 100.0          # the board's centre on KiCad's page
R_BOARD = 60.0                 # 120 mm across
FLAT_Y = 59.4                  # the flat at the bottom, from the centre: the USB-C receptacle's edge line

N_MINUTE, R_MINUTE = 60, 50.0  # the minute ring: D1..D60, D1 at 12 o'clock, clockwise
N_HOUR, R_HOUR = 12, 38.0      # the hour ring: D61..D72

# Each LED: its local +y points out of the ring, its local -x along the ring clockwise (the next LED).
# WS2812B-2020 pads (KiCad's footprint): 1 DOUT (-0.915,-0.55), 2 VSS (-0.915,0.55), 3 DIN (0.915,0.55),
# 4 VDD (0.915,-0.55): DOUT faces the next LED on the inner row, DIN the previous one on the outer row.
CAP_LOCAL = (0.0, -2.45)       # its 100 nF capacitor, inside the ring, along the ring (pad 1 +5V on +x)
VDD_VIA_LOCAL = (0.775, -3.75)  # the +5V via under the capacitor's pad 1
GND_VIA_LOCAL = (-0.775, -3.75)  # the GND via under its pad 2
VSS_VIA_LOCAL = (-0.915, 1.75)  # a GND via outside the ring at the LED's VSS pad

# JLCPCB 4-layer standard (skills/pcb/references/manufacturing.md, read 2026-11-04): 0.09/0.09 mm track/space,
# 0.15 mm drill, 0.15 mm ring (0.20 advised), 0.2 mm copper to edge, 1.0/0.15 mm silkscreen.
CLEARANCE = 0.15
MIN_TRACK = 0.15
SIGNAL = 0.2
VIA_D, VIA_DRILL = 0.6, 0.3
EDGE_CLEARANCE = 0.3
# Power: 72 LEDs x 3 colours x 12 mA = 2.59 A, + ESP32-C3 RF peak ~0.35 A, + the rest: ~3.0 A worst case,
# what a USB-C source gives at most at 5 V. IPC-2221, outer 1 oz, 10 C rise: 3 A needs 1.37 mm.
POWER_WIDTH = 1.5

MOUNT_R, MOUNT_ANGLES = 42.5, (45.0, 135.0, 225.0, 315.0)   # M3, between the rings (degrees clockwise from 12)

MODULE_AT = (2.6, -45.6)       # ESP32-C3-WROOM-02 on the back, antenna up, its end 1.3 mm in from the edge
USB_AT = (0.0, FLAT_Y - 3.675)  # USB-C on the back, its edge line on the flat


def polar(r, deg):
    """A point at radius r, `deg` clockwise from 12 o'clock, relative to the centre (y down)."""
    a = math.radians(deg)
    return (r * math.sin(a), -r * math.cos(a))


def led_angle(index, count):
    return 360.0 * index / count


def led_rotation(deg):
    """KiCad's footprint orientation (degrees, counter-clockwise on screen) that points local +y outward."""
    return (180.0 - deg) % 360.0


def local_to_board(local, center, deg):
    """A footprint-local point (y down) of an LED at `center` turned for its angle `deg`."""
    x, y = local
    t = (math.cos(math.radians(deg)), math.sin(math.radians(deg)))   # clockwise tangent = local -x
    u = (math.sin(math.radians(deg)), -math.cos(math.radians(deg)))  # outward = local +y
    return (center[0] - x * t[0] + y * u[0], center[1] - x * t[1] + y * u[1])


def outline_arc():
    """The outline's arc (from the flat's left end, over the top, to its right end) and a point on it."""
    half = math.sqrt(R_BOARD ** 2 - FLAT_Y ** 2)
    return (CX - half, CY + FLAT_Y), (CX + half, CY + FLAT_Y), (CX, CY - R_BOARD)
