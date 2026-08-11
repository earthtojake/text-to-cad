from __future__ import annotations

import build123d

from tom_gripper_clamp import build_relieved_gripper


def gen_step() -> build123d.Shape:
    return build_relieved_gripper()


if __name__ == "__main__":
    gen_step()
