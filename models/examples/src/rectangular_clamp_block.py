from __future__ import annotations
from cadgen import materials, model
# Prompt: Rectangular clamp block with a split slot and two transverse screw holes.

from lib.simple_model_library import make_rectangular_clamp_block


@model
def rectangular_clamp_block():
    part = make_rectangular_clamp_block()
    part.material = materials.aluminium_6061.but(color=None)
    return part


if __name__ == "__main__":
    rectangular_clamp_block()
