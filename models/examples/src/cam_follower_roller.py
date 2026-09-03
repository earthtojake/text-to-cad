from __future__ import annotations
from cadgen import step
# Prompt: Cam follower roller with central bearing bore and rounded outer profile.

from lib.simple_model_library import make_cam_follower_roller


@step(out="../STEP/cam_follower_roller.step")
def cam_follower_roller():
    return make_cam_follower_roller()


if __name__ == "__main__":
    cam_follower_roller()
