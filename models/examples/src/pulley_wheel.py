from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Pulley wheel with a central hub, outer groove, and circular through-bore.

from lib.simple_model_library import make_pulley_wheel


@model
def pulley_wheel():
    part = make_pulley_wheel()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.aluminum().material,
        pbr=PbrProperties.create('Aluminum 6061-T6', metalness=1.0, roughness=0.35, anisotropy=0.3),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    pulley_wheel()
