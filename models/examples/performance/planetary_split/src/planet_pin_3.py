from cadgen import step

from lib.geometry import _make_planet_pin, _planet_center

@step(out="../STEP/planet_pin_3.step")
def planet_pin_3():
    return _make_planet_pin(label="planet_pin_3", center=_planet_center(2))


if __name__ == "__main__":
    planet_pin_3()
