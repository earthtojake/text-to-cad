from __future__ import annotations
from cadgen import step
# Prompt: Square mounting block with a vertical through-hole and two side clearance holes.

from lib.simple_model_library import make_square_mounting_block


@step(out="../STEP/square_mounting_block.step")
def square_mounting_block():
    return make_square_mounting_block()


if __name__ == "__main__":
    square_mounting_block()
