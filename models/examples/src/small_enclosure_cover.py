from __future__ import annotations

from bd_materials import FinishedMaterial, plastics
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Small enclosure cover with raised rim, corner screw holes, and shallow recessed center.

from lib.simple_model_library import make_small_enclosure_cover


@model
def small_enclosure_cover():
    part = make_small_enclosure_cover()
    authored_color = part.color
    part.material = FinishedMaterial(
        plastics.abs_().material,
        pbr=PbrProperties.create('Acrylonitrile butadiene styrene, moulded or printed', metalness=0.0,
            roughness=0.55),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    small_enclosure_cover()
