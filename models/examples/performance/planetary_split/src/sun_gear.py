from cadgen import step

from math import tau
from lib.geometry import (
    SUN_BORE_DIAMETER, SUN_COLOR, SUN_OUTSIDE_DIAMETER, SUN_ROOT_DIAMETER,
    SUN_TEETH, _make_external_gear,
)

@step(out="../STEP/sun_gear.step")
def sun_gear():
    return _make_external_gear(
        label="sun_gear_24_teeth", teeth=SUN_TEETH, root_diameter=SUN_ROOT_DIAMETER,
        outside_diameter=SUN_OUTSIDE_DIAMETER, phase=-(tau / SUN_TEETH) / 2.0,
        bore_diameter=SUN_BORE_DIAMETER, color=SUN_COLOR,
    )


if __name__ == "__main__":
    sun_gear()
