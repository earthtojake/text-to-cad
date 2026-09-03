from __future__ import annotations
from cadgen import step
# Prompt: Small enclosure cover with raised rim, corner screw holes, and shallow recessed center.

from lib.simple_model_library import make_small_enclosure_cover


@step(out="../STEP/small_enclosure_cover.step")
def small_enclosure_cover():
    return make_small_enclosure_cover()


if __name__ == "__main__":
    small_enclosure_cover()
