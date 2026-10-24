from __future__ import annotations
from cadgen import materials, model
# Prompt: Small enclosure cover with raised rim, corner screw holes, and shallow recessed center.

from lib.simple_model_library import make_small_enclosure_cover


@model
def small_enclosure_cover():
    part = make_small_enclosure_cover()
    part.material = materials.abs.but(color=None)
    return part


if __name__ == "__main__":
    small_enclosure_cover()
