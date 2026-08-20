"""Engine entry: unit powertrain (swingarm engine + CVT + covers), bike frame."""

from build123d import Compound

import _drivetrain as B


DISPLAY_NAME = "Motorbike engine"


def gen_step():
    built = B.build_engine()
    if isinstance(built, list):
        return Compound(children=built, label="engine")
    return built
