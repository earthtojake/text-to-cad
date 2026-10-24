from __future__ import annotations
from cadgen import materials, model
# Prompt: T-slot slider block with central channel, side relief cuts, and mounting holes.

from lib.simple_model_library import make_t_slot_slider_block


@model
def t_slot_slider_block():
    part = make_t_slot_slider_block()
    part.material = materials.aluminium_6061.but(color=None)
    return part


if __name__ == "__main__":
    t_slot_slider_block()
