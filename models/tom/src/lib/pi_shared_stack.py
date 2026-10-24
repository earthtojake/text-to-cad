"""Restored Pi 5 / Waveshare HAT A, using standard M2.5 mounting hardware.

10 mm base / 10 mm Pi-to-HAT / 20 mm carrier spacers, all nominal 5 AF.
10 mm through-threaded lower spacer: Harwin R25-1001002.
Pi-to-HAT spacer is a nominal 10 mm body with a 6 mm male stud.
20+5, 5 AF, >=5 mm female thread: Harwin R25-3002002.
These exact products were absent from step.parts; the generic catalog's
6.25 AF M2.5 bodies do not represent these products. Spacers below are
documented nominal envelopes, with threads represented by major bores.
The user explicitly selected a shared structural/PCB spacer stack. PCB
mounting lands are consequently in the clamp load path; this is a fit
prototype, not a qualified structural mounting system.

Pi STEP PCB is 1.6 mm; separate mounting-pad rings protrude 0.1 mm below it.
Seat these pads on the lower posts; preserve the supplied connector geometry.
Ports point rearwards (+X), with HAT power/servo connections accessible
from the sides. No cooler, wiring or plug envelopes are fitted yet.
"""
from pathlib import Path
import build123d as b
from cadgen import read_step
from lib.booleans import as_single_shape as one
from lib.materials import STANDOFF_COLOR, SCREW_COLOR
from lib.common_base_plate import BOARD_XY
from purchased.raspberry_pi_5 import raspberry_pi_5
from purchased.bus_servo_driver_hat_a import bus_servo_driver_hat_a

LOWER_SPACER = 10.0
HAT_SPACER = 10.0
UPPER_SPACER = 20.0
PI_T = 1.6
PI_PAD = 0.1
HAT_T = 1.6
STACK_HEIGHT = LOWER_SPACER + PI_PAD + PI_T + HAT_SPACER + HAT_T + UPPER_SPACER
PI_CENTER_X = BOARD_XY[0][0] + 39.0


def standoff(body_length, stud_length):
    """Male stud faces -Z, body begins at Z=0; nominal M2.5 threads."""
    p = b.extrude(b.RegularPolygon(5.0 / 3**.5, 6), amount=body_length)
    if stud_length:
        p = one(p.fuse(b.Solid.make_cylinder(1.25, stud_length,
                     b.Plane(origin=(0, 0, -stud_length)))))
    bore_length = 5.0 if stud_length else body_length
    p = one(p.cut(b.Solid.make_cylinder(1.25, bore_length,
                 b.Plane(origin=(0, 0, body_length-bore_length))))).clean()
    assert p.is_valid and len(p.solids()) == 1
    p.color = STANDOFF_COLOR
    return p


def shared_stack(floor_top, carrier_top):
    pi_bottom = floor_top + LOWER_SPACER + PI_PAD
    pi_top = pi_bottom + PI_T
    hat_bottom = pi_top + HAT_SPACER
    hat_top = hat_bottom + HAT_T
    # Same orientation and mechanical hole datums as the earlier Pi/HAT stack.
    pi = raspberry_pi_5().moved(b.Pos(PI_CENTER_X, 0, pi_bottom) * b.Rot(X=90))
    pi.label = 'raspberry_pi_5'
    hat = bus_servo_driver_hat_a().moved(
        b.Pos(PI_CENTER_X+22.5, -28, hat_top) * b.Rot(Z=90))
    hat.label = 'bus_servo_driver_hat_a'
    out = [pi, hat]
    upper_screw = read_step(Path(__file__).resolve().parents[2] /
        'STEP/imported/hardware/iso4762_socket_head_cap_screw_m2p5x6.step')
    for i, (x, y) in enumerate(BOARD_XY, 1):
        for stage, length, stud, z in (
            ('base', LOWER_SPACER, 0, floor_top),
            ('pi_hat', HAT_SPACER, 6, pi_top),
            ('carrier', UPPER_SPACER, 5, hat_top),
        ):
            p = standoff(length, stud).moved(b.Pos(x, y, z))
            p.label = f'{stage}_m2p5_{length:g}mm_spacer_{i}'
            out.append(p)
        # Catalog screw has its bearing face at Z=0 and shank on -Z.
        p = upper_screw.moved(b.Pos(x, y, carrier_top))
        p.label = f'carrier_upper_m2p5x6_{i}'
        p.color = SCREW_COLOR
        out.append(p)
    return out
