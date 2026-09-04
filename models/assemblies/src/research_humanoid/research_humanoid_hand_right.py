"""Research humanoid: the right dexterous hand as its own model.

Fifteen articulated axes (three per digit) in the robot frame, built by
`lib.research_humanoid_lib.build_hand("right")`. The left hand is its
mirror image and therefore a separate model from the same factory — STEP
cannot express a reflection. `research_humanoid.py` links both.
"""

from __future__ import annotations

from cadgen import step

from lib.research_humanoid_lib import build_hand


@step(out="../../STEP/research_humanoid/research_humanoid_hand_right.step")
def research_humanoid_hand_right():
    return build_hand("right")


if __name__ == "__main__":
    research_humanoid_hand_right()
