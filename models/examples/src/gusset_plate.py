from __future__ import annotations
from cadgen import step
# Prompt: Gusset plate with a triangular web, base holes, and softened perimeter edges.

from lib.simple_model_library import make_gusset_plate


@step(out="../STEP/gusset_plate.step")
def gusset_plate():
    return make_gusset_plate()


if __name__ == "__main__":
    gusset_plate()
