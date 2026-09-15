from cadgen import step

from lib.geometry import _make_planet_pin, _planet_center

@step(out="../STEP/planet_pin_1.step")
def planet_pin_1():
    return _make_planet_pin(label="planet_pin_1", center=_planet_center(0))


if __name__ == "__main__":
    planet_pin_1()
