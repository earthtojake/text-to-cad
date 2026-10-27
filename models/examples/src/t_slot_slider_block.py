from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: T-slot slider block with central channel, side relief cuts, and mounting holes.

from lib.simple_model_library import make_t_slot_slider_block


@model
def t_slot_slider_block():
    part = make_t_slot_slider_block()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    t_slot_slider_block()
