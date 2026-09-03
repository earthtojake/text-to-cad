from __future__ import annotations
from cadgen import step
# Prompt: Retainer plate with elongated slot, two circular holes, and chamfered perimeter.

from lib.simple_model_library import make_retainer_plate


@step(out="../STEP/retainer_plate.step")
def retainer_plate():
    return make_retainer_plate()


if __name__ == "__main__":
    retainer_plate()
