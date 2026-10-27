from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern.

from lib.simple_model_library import make_keyed_shaft_hub


@model
def keyed_shaft_hub():
    part = make_keyed_shaft_hub()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.mild_steel(metals.MildSteel.G1018_COLD_DRAWN).material,
        pbr=PbrProperties.create('Low-carbon mild steel, cold drawn bar', metalness=1.0, roughness=0.4),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    keyed_shaft_hub()
