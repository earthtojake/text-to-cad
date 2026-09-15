from cadgen import step

from math import tau
from lib.geometry import (
    PLANET_BORE_DIAMETER, PLANET_COLORS, PLANET_COUNT, PLANET_OUTSIDE_DIAMETER,
    PLANET_ROOT_DIAMETER, PLANET_TEETH, _make_external_gear, _planet_center,
)

@step(out="../STEP/planet_gear_2.step")
def planet_gear_2():
    return _make_external_gear(
        label="planet_gear_2_18_teeth", teeth=PLANET_TEETH,
        root_diameter=PLANET_ROOT_DIAMETER, outside_diameter=PLANET_OUTSIDE_DIAMETER,
        phase=tau * 1 / PLANET_COUNT, center=_planet_center(1),
        bore_diameter=PLANET_BORE_DIAMETER, color=PLANET_COLORS[1],
    )


if __name__ == "__main__":
    planet_gear_2()
