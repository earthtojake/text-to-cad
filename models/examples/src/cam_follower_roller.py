from __future__ import annotations
from cadgen import materials, model
# Prompt: Cam follower roller with central bearing bore and rounded outer profile.

from lib.simple_model_library import make_cam_follower_roller


@model
def cam_follower_roller():
    part = make_cam_follower_roller()
    part.material = materials.steel_4140.but(color=None)
    return part


if __name__ == "__main__":
    cam_follower_roller()
