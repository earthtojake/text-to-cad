from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Retainer plate with elongated slot, two circular holes, and chamfered perimeter.

from lib.simple_model_library import make_retainer_plate


@model
def retainer_plate():
    part = make_retainer_plate()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Low-carbon mild steel, cold drawn bar', metalness=1.0, roughness=0.4),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    retainer_plate()
