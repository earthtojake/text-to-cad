from __future__ import annotations

import build123d

from tom_gripper_o1_5 import build_o1_5


def gen_step() -> build123d.Shape:
    return build_o1_5(rotate_m2_pattern=True)


if __name__ == "__main__":
    gen_step()
