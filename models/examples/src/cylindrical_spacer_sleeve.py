from __future__ import annotations
from cadgen import materials, model
# Prompt: Cylindrical spacer sleeve with a central through-bore and rounded rim edges.

from lib.simple_model_library import make_cylindrical_spacer_sleeve


@model
def cylindrical_spacer_sleeve():
    part = make_cylindrical_spacer_sleeve()
    part.material = materials.aluminium_6061.but(color=None)
    return part


if __name__ == "__main__":
    cylindrical_spacer_sleeve()
