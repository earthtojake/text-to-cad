from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cad import xbf
# Prompt: Square mounting block with a vertical through-hole and two side clearance holes.

from lib.simple_model_library import make_square_mounting_block


@xbf
def square_mounting_block():
    part = make_square_mounting_block()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    square_mounting_block()
