from __future__ import annotations
from cadgen import step
# Prompt: Rectangular clamp block with a split slot and two transverse screw holes.

from lib.simple_model_library import make_rectangular_clamp_block


@step(out="../STEP/rectangular_clamp_block.step")
def rectangular_clamp_block():
    return make_rectangular_clamp_block()


if __name__ == "__main__":
    rectangular_clamp_block()
