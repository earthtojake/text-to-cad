from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Gusset plate with a triangular web, base holes, and softened perimeter edges.

from lib.simple_model_library import make_gusset_plate


@model
def gusset_plate():
    part = make_gusset_plate()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.mild_steel(metals.MildSteel.GA36_HOT_ROLLED).material,
        pbr=PbrProperties.create('Hot-rolled structural steel plate and section, mill scale on',
            metalness=1.0, roughness=0.6),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    gusset_plate()
