from cadgen import step

from lib.geometry import _make_carrier_plate

CARRIER_DIAMETER = 105.0

@step(out="../STEP/carrier_plate.step")
def carrier_plate():
    return _make_carrier_plate(diameter=CARRIER_DIAMETER)


if __name__ == "__main__":
    carrier_plate()
