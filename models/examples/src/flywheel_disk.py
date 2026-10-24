from __future__ import annotations
from cadgen import materials, model
# Prompt: Flywheel disk with central bore, annular rim, and lightening holes.

from lib.simple_model_library import make_flywheel_disk


@model
def flywheel_disk():
    part = make_flywheel_disk()
    part.material = materials.steel_1018.but(color=None)
    return part


if __name__ == "__main__":
    flywheel_disk()
