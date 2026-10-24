from __future__ import annotations
from cadgen import materials, model
# Prompt: Shaft collar with a central bore, radial set-screw hole, and chamfered faces.

from lib.simple_model_library import make_shaft_collar


@model
def shaft_collar():
    part = make_shaft_collar()
    part.material = materials.steel_1018.but(color=None)
    return part


if __name__ == "__main__":
    shaft_collar()
