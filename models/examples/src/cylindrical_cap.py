from __future__ import annotations
from cadgen import materials, model
# Prompt: Cylindrical cap with hollow interior, top boss, and rounded external edges.

from lib.simple_model_library import make_cylindrical_cap


@model
def cylindrical_cap():
    part = make_cylindrical_cap()
    part.material = materials.aluminium_6061.but(color=None)
    return part


if __name__ == "__main__":
    cylindrical_cap()
