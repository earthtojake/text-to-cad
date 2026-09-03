from __future__ import annotations
from cadgen import step
# Prompt: T-slot slider block with central channel, side relief cuts, and mounting holes.

from lib.simple_model_library import make_t_slot_slider_block


@step(out="../STEP/t_slot_slider_block.step")
def t_slot_slider_block():
    return make_t_slot_slider_block()


if __name__ == "__main__":
    t_slot_slider_block()
