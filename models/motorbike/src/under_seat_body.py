"""Under-seat body entry: rear body panel carrying seat and tail, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import bodywork as B


@step(out="../STEP/under_seat_body.step")
def under_seat_body():
    built = B.build_under_seat_body()
    if isinstance(built, list):
        return bd.Compound(children=built, label="under_seat_body")
    return built


if __name__ == "__main__":
    under_seat_body()
