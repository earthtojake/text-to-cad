from cadgen import build123d as bd
from cadgen import step

from carrier_plate import carrier_plate
from ring_gear import ring_gear
from sun_gear import sun_gear
from planet_gear_1 import planet_gear_1
from planet_pin_1 import planet_pin_1
from planet_gear_2 import planet_gear_2
from planet_pin_2 import planet_pin_2
from planet_gear_3 import planet_gear_3
from planet_pin_3 import planet_pin_3

CARRIER_OFFSET_Z = 0.0


@step(out="../STEP/planetary.step")
def planetary_gear_assembly():
    """The nine-part fixture composed through ordinary decorated child calls."""
    parts = [
        carrier_plate(),
        ring_gear(),
        sun_gear(),
        planet_gear_1(),
        planet_pin_1(),
        planet_gear_2(),
        planet_pin_2(),
        planet_gear_3(),
        planet_pin_3(),
    ]
    # Submit every child before reading any geometry to apply this placement.
    parts[0] = parts[0].moved(bd.Location((0.0, 0.0, CARRIER_OFFSET_Z)))
    names = (
        "carrier_plate", "ring_gear_60_internal_teeth", "sun_gear_24_teeth",
        "planet_gear_1_18_teeth", "planet_pin_1", "planet_gear_2_18_teeth",
        "planet_pin_2", "planet_gear_3_18_teeth", "planet_pin_3",
    )
    for part, name in zip(parts, names, strict=True):
        part.label = name
    return bd.Compound(obj=parts, children=parts, label="simplified_planetary_gear_assembly")


if __name__ == "__main__":
    planetary_gear_assembly()
