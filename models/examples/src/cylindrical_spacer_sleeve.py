from __future__ import annotations
from cadgen import step
# Prompt: Cylindrical spacer sleeve with a central through-bore and rounded rim edges.

from lib.simple_model_library import make_cylindrical_spacer_sleeve


@step(out="../STEP/cylindrical_spacer_sleeve.step")
def cylindrical_spacer_sleeve():
    return make_cylindrical_spacer_sleeve()


if __name__ == "__main__":
    cylindrical_spacer_sleeve()
