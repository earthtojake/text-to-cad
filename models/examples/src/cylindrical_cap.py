from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Cylindrical cap with hollow interior, top boss, and rounded external edges.

from lib.simple_model_library import make_cylindrical_cap


@model
def cylindrical_cap():
    part = make_cylindrical_cap()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    cylindrical_cap()
