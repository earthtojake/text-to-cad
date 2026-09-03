from __future__ import annotations
from cadgen import glb, step, stl, threemf
# Prompt: Spur gear blank with central bore, raised hub, and simplified perimeter teeth.

from lib.simple_model_library import make_spur_gear_blank


@step(out="../STEP/spur_gear_blank.step")
@stl(out="../STL/spur_gear_blank.stl")
@threemf(out="../3MF/spur_gear_blank.3mf")
@glb(out="../GLB/spur_gear_blank.glb")
def spur_gear_blank():
    return make_spur_gear_blank()


if __name__ == "__main__":
    spur_gear_blank()
