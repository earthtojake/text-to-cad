from cadgen import step

from math import tau
from lib.geometry import RING_COLOR, RING_TEETH, _make_internal_ring_gear

@step(out="../STEP/ring_gear.step")
def ring_gear():
    return _make_internal_ring_gear(
        label="ring_gear_60_internal_teeth", phase=-(tau / RING_TEETH) / 2.0, color=RING_COLOR,
    )


if __name__ == "__main__":
    ring_gear()
