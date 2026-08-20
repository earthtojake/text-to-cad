"""Rear shock entry: coilover between the frame lug and engine boss, bike frame."""

from build123d import Compound

import _drivetrain as B


DISPLAY_NAME = "Motorbike rear shock"


def gen_step():
    built = B.build_rear_shock()
    if isinstance(built, list):
        return Compound(children=built, label="rear_shock")
    return built
