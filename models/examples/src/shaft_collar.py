from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Shaft collar with a central bore, radial set-screw hole, and chamfered faces.

from lib.simple_model_library import make_shaft_collar


@model
def shaft_collar():
    part = make_shaft_collar()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Low-carbon mild steel, cold drawn bar', metalness=1.0, roughness=0.4),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    shaft_collar()
