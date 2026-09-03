"""Rear fender entry: cream arc over the rear tire, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import bodywork as B


@step(out="../STEP/rear_fender.step")
def rear_fender():
    built = B.build_rear_fender()
    if isinstance(built, list):
        return bd.Compound(children=built, label="rear_fender")
    return built


if __name__ == "__main__":
    rear_fender()
