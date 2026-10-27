from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import glb, stl, threemf
# Prompt: Spur gear blank with central bore, raised hub, and simplified perimeter teeth.

from lib.simple_model_library import make_spur_gear_blank


@stl(out="../STL/spur_gear_blank.stl")
@threemf(out="../3MF/spur_gear_blank.3mf")
@glb(out="../GLB/spur_gear_blank.glb")
def spur_gear_blank():
    part = make_spur_gear_blank()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.brass().material,
        pbr=PbrProperties.create('Free-machining leaded brass', metalness=1.0, roughness=0.35),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    spur_gear_blank()
