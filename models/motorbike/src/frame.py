"""Frame entry: welded underbone frame + floor pan, bike frame (fixed root)."""

from __future__ import annotations

import build123d as bd
from cad import xbf

from lib import chassis as B


@xbf
def frame():
    built = B.build_frame()
    if isinstance(built, list):
        return bd.Compound(children=built, label="frame")
    return built


if __name__ == "__main__":
    frame()
