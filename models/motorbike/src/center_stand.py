"""Center stand entry: folded-up pose under the floor pan, bike frame."""

from __future__ import annotations

import build123d as bd
from cadgen import model

from lib import chassis as B


@model
def center_stand():
    built = B.build_center_stand()
    if isinstance(built, list):
        return bd.Compound(children=built, label="center_stand")
    return built


if __name__ == "__main__":
    center_stand()
