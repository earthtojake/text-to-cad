from __future__ import annotations
from cadgen import glb, step, stl, threemf
# Prompt: Mounting plate with central circular cutout, elongated side slot, four corner holes, and rounded edges.

from lib.simple_model_library import make_mounting_plate


@step(out="../STEP/mounting_plate.step")
@stl(out="../STL/mounting_plate.stl")
@threemf(out="../3MF/mounting_plate.3mf")
@glb(out="../GLB/mounting_plate.glb")
def mounting_plate():
    return make_mounting_plate()


if __name__ == "__main__":
    mounting_plate()
