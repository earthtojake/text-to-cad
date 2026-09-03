from __future__ import annotations
from cadgen import step
# Prompt: Pulley wheel with a central hub, outer groove, and circular through-bore.

from lib.simple_model_library import make_pulley_wheel


@step(out="../STEP/pulley_wheel.step")
def pulley_wheel():
    return make_pulley_wheel()


if __name__ == "__main__":
    pulley_wheel()
