from __future__ import annotations
from cadgen import materials, model
# Prompt: Square mounting block with a vertical through-hole and two side clearance holes.

from lib.simple_model_library import make_square_mounting_block


@model
def square_mounting_block():
    part = make_square_mounting_block()
    part.material = materials.aluminium_6061.but(color=None)
    return part


if __name__ == "__main__":
    square_mounting_block()
