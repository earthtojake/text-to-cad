"""Edit one part of the fixed nine-part STEP without rebuilding its gears."""

import math
from pathlib import Path

from cadgen import build123d as bd
from cadgen import step
from cadgen.step_scene import read_step

CARRIER_DIAMETER = 105.0
CARRIER_OFFSET_Z = 0.0


@step(out="../STEP/planetary.step")
def planetary_gear_assembly():
    assembly = read_step(Path(__file__).resolve().parents[1] / "input/planetary.step")
    parts = list(assembly.children)
    carriers = [index for index, part in enumerate(parts) if part.label == "carrier_plate"]
    if len(parts) != 9 or len(carriers) != 1:
        raise ValueError("Expected the nine-part planetary STEP with one carrier_plate")
    index = carriers[0]
    carrier = parts[index]
    if CARRIER_DIAMETER != 105.0:
        replacement = bd.Solid.make_cylinder(
            CARRIER_DIAMETER / 2, 4, bd.Plane(origin=(0, 0, -5))
        )
        for hole in range(3):
            angle = math.tau * hole / 3
            cutter = bd.Solid.make_cylinder(
                3.2, 4.2,
                bd.Plane(origin=(42 * math.cos(angle), 42 * math.sin(angle), -5.1)),
            )
            replacement = replacement.cut(cutter)
        replacement.label = carrier.label
        replacement.color = carrier.color
        carrier = replacement
    if CARRIER_OFFSET_Z:
        carrier = carrier.moved(bd.Location((0.0, 0.0, CARRIER_OFFSET_Z)))
    parts[index] = carrier
    result = bd.Compound(obj=parts, children=parts, label=assembly.label)
    result.color = assembly.color
    return result


if __name__ == "__main__":
    planetary_gear_assembly()
