"""Exhaust entry: head pipe + oval chrome muffler on the rider right, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import drivetrain as B


@step(out="../STEP/exhaust.step")
def exhaust():
    built = B.build_exhaust()
    if isinstance(built, list):
        return bd.Compound(children=built, label="exhaust")
    return built


if __name__ == "__main__":
    exhaust()
