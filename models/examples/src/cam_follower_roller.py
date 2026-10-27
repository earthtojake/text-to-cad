from __future__ import annotations

from bd_materials import FinishedMaterial, metals
from threejs_materials import PbrProperties

from cadgen import model
# Prompt: Cam follower roller with central bearing bore and rounded outer profile.

from lib.simple_model_library import make_cam_follower_roller


@model
def cam_follower_roller():
    part = make_cam_follower_roller()
    authored_color = part.color
    part.material = FinishedMaterial(
        metals.alloy_steel().material,
        pbr=PbrProperties.create('Chromium-molybdenum alloy steel for shafts and gears', metalness=1.0,
            roughness=0.4),
    )
    part.color = authored_color
    return part


if __name__ == "__main__":
    cam_follower_roller()
