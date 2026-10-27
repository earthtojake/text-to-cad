from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Cylindrical spacer sleeve with a central through-bore and rounded rim edges.

from lib.simple_model_library import make_cylindrical_spacer_sleeve


@model
def cylindrical_spacer_sleeve():
    part = make_cylindrical_spacer_sleeve()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    cylindrical_spacer_sleeve()
