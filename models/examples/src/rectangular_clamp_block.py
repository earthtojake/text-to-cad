from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Rectangular clamp block with a split slot and two transverse screw holes.

from lib.simple_model_library import make_rectangular_clamp_block


@model
def rectangular_clamp_block():
    part = make_rectangular_clamp_block()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    rectangular_clamp_block()
