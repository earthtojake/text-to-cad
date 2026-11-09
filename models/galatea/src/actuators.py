"""Galatea's actuator family on a bench: the five frame sizes, each on a mounting plate
with its output flange through it, so the joint packaging can be read off one picture."""

import build123d as bd
from cad import model

from lib import geo
from lib.dims import ACTUATORS, PLATE_T
from lib.hardware import Hardware
from lib.kit import group, part


@model
def galatea_actuators():
    hw = Hardware()
    stations, x = [], 0.0
    for size, spec in ACTUATORS.items():
        R = spec["R"]
        x += R + 14.0
        origin = (x, 0.0, R + 12.0)
        stator, rotor = hw.actuator(size, origin, (0, -1, 0))
        # The parent link's mounting plate: the stator bolts to its back, the output passes through.
        outline = geo.bones([(x, R + 12.0, R + 3.0), (x, 3.0, 12.0)], holes=[(x, R + 12.0, spec["r_out"] + 1.0)])
        plate = part(geo.plate_xz(outline, -PLATE_T, 0.0), "mount_plate", "gunmetal")
        foot = part(geo.box(2 * R + 6.0, 60.0, 6.0, (x, 16.0, -3.0)), "foot", "slate")
        stations.append(group(size.lower(), stator, rotor, plate, foot))
        x += R + 14.0
    return group("galatea_actuators", stations)


if __name__ == "__main__":
    galatea_actuators()
