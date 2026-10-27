from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import glb, stl, threemf
# Prompt: Mounting plate with central circular cutout, elongated side slot, four corner holes, and rounded edges.

from lib.simple_model_library import make_mounting_plate


@stl(out="../STL/mounting_plate.stl")
@threemf(out="../3MF/mounting_plate.3mf")
@glb(out="../GLB/mounting_plate.glb")
def mounting_plate():
    part = make_mounting_plate()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    mounting_plate()
