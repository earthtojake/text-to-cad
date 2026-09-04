"""Research humanoid: the left dexterous hand as its own model.

Fifteen articulated axes (three per digit) in the robot frame, built by
`lib.research_humanoid_lib.build_hand("left")`. The right hand is its
mirror image and therefore a separate model from the same factory — STEP
cannot express a reflection. `research_humanoid.py` links both.
"""

from __future__ import annotations

from cadgen import step

from lib.research_humanoid_lib import build_hand


@step(out="../../STEP/research_humanoid/research_humanoid_hand_left.step")
def research_humanoid_hand_left():
    return build_hand("left")


if __name__ == "__main__":
    research_humanoid_hand_left()
