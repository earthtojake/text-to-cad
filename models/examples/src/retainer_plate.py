from __future__ import annotations
from cadgen import materials, model
# Prompt: Retainer plate with elongated slot, two circular holes, and chamfered perimeter.

from lib.simple_model_library import make_retainer_plate


@model
def retainer_plate():
    part = make_retainer_plate()
    part.material = materials.steel_1018.but(color=None)
    return part


if __name__ == "__main__":
    retainer_plate()
