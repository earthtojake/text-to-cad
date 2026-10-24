"""Leg shield entry: cream step-through apron, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import bodywork as B


@model
def leg_shield():
    built = B.build_leg_shield()
    if isinstance(built, list):
        return bd.Compound(children=built, label="leg_shield")
    return built


if __name__ == "__main__":
    leg_shield()
