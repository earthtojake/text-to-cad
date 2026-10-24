# Prompt: Laser-cut profile DXF for the clamp plate, projected from the
# clamp plate's own 3D topology rather than redrawn by hand.
#
# The top face of the solid in lib/clamp_plate_profile.py, laid onto z=0: the
# rounded corners stay ARCs and the holes CIRCLEs, exactly as the solid has them.

from __future__ import annotations

from cadgen import model

import build123d as bd

from lib import clamp_plate_profile


@model
def clamp_plate():
    top = clamp_plate_profile.plate().faces().sort_by(bd.Axis.Z)[-1]
    return bd.Pos(0, 0, -clamp_plate_profile.THICKNESS_MM) * top


if __name__ == "__main__":
    clamp_plate()
