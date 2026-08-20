"""Center stand entry: folded-up pose under the floor pan, bike frame."""

from build123d import Compound

import _chassis as B


DISPLAY_NAME = "Motorbike center stand"


def gen_step():
    built = B.build_center_stand()
    if isinstance(built, list):
        return Compound(children=built, label="center_stand")
    return built
