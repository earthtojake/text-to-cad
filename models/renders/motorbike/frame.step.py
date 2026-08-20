"""Frame entry: welded underbone frame + floor pan, bike frame (fixed root)."""

from build123d import Compound

import _chassis as B


DISPLAY_NAME = "Motorbike frame"


def gen_step():
    built = B.build_frame()
    if isinstance(built, list):
        return Compound(children=built, label="frame")
    return built
