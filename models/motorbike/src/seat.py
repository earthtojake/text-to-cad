"""Seat entry: brown saddle on the under-seat body, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import bodywork as B


@step(out="../STEP/seat.step")
def seat():
    built = B.build_seat()
    if isinstance(built, list):
        return bd.Compound(children=built, label="seat")
    return built


if __name__ == "__main__":
    seat()
