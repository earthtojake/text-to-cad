"""Leg shield entry: cream step-through apron, bike frame."""

from __future__ import annotations

from cadgen import build123d as bd
from cadgen import step

from lib import bodywork as B


@step(out="../STEP/leg_shield.step")
def leg_shield():
    built = B.build_leg_shield()
    if isinstance(built, list):
        return bd.Compound(children=built, label="leg_shield")
    return built


if __name__ == "__main__":
    leg_shield()
