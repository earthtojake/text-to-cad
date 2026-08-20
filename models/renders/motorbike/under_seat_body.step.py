"""Under-seat body entry: rear body panel carrying seat and tail, bike frame."""

from build123d import Compound

import _bodywork as B


DISPLAY_NAME = "Motorbike under-seat body"


def gen_step():
    built = B.build_under_seat_body()
    if isinstance(built, list):
        return Compound(children=built, label="under_seat_body")
    return built
