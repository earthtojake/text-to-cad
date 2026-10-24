from __future__ import annotations
from cadgen import materials, model
# Prompt: Pulley wheel with a central hub, outer groove, and circular through-bore.

from lib.simple_model_library import make_pulley_wheel


@model
def pulley_wheel():
    part = make_pulley_wheel()
    part.material = materials.aluminium_6061.but(color=None)
    return part


if __name__ == "__main__":
    pulley_wheel()
