# Prompt: Laser-cut profile DXF for the clamp plate, projected from the
# clamp plate's own 3D topology rather than redrawn by hand.
#
# The STEP-projection workflow, sourced from a lib helper instead of a @step
# model: `flatten.flat_pattern` selects the top face, lays it into XY and
# unions it, so the rounded corners stay ARCs and the holes stay CIRCLEs.

from __future__ import annotations

from cadgen import dxf, flatten

from lib import clamp_plate_profile


@dxf(out="../DXF/clamp_plate.dxf")
def clamp_plate(kerf: float = 0.0):
    return flatten.flat_pattern(
        clamp_plate_profile.plate(),
        normal_axis="z",
        normal_sign=1.0,
        coordinate_axis="z",
        coordinate=clamp_plate_profile.THICKNESS_MM,
        kerf=kerf,
    )


if __name__ == "__main__":
    clamp_plate()
