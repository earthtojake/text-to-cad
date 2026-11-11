"""Galatea's actuators on a bench: the five RobStride models it uses, each on a mounting plate
with its output hub through it, so the joint packaging can be read off one picture."""

from cad import model

from lib import geo
from lib.dims import ACTUATORS, PLATE_T
from lib.hardware import Hardware, mount_bores
from lib.kit import group, part


@model
def galatea_actuators():
    hw = Hardware()
    stations, x = [], 0.0
    for size, spec in ACTUATORS.items():
        R = spec["ears"] or spec["front"][0]
        x += R + 14.0
        origin = (x, 0.0, R + 12.0)
        stator, rotor = hw.actuator(size, origin, (0, -1, 0))
        # The parent link's mounting plate: it lies on the actuator's face, and the output passes through it.
        outline = geo.bones([(x, R + 12.0, R + 3.0), (x, 3.0, 12.0)])
        plate = part(geo.plate_xz(outline, -PLATE_T, 0.0) - mount_bores(size, origin, (0, -1, 0)), "mount_plate", "frame")
        foot = part(geo.box(2 * R + 6.0, 60.0, 6.0, (x, 16.0, -3.0)), "foot", "link")
        stations.append(group(size.lower(), stator, rotor, plate, foot))
        x += R + 14.0
    return group("galatea_actuators", stations)


if __name__ == "__main__":
    galatea_actuators()
