"""Engine entry: unit powertrain (swingarm engine + CVT + covers), bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import drivetrain as B


@model
def engine():
    built = B.build_engine()
    if isinstance(built, list):
        return bd.Compound(children=built, label="engine")
    return built


if __name__ == "__main__":
    engine()
