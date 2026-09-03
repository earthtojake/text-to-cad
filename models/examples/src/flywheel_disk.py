from __future__ import annotations
from cadgen import step
# Prompt: Flywheel disk with central bore, annular rim, and lightening holes.

from lib.simple_model_library import make_flywheel_disk


@step(out="../STEP/flywheel_disk.step")
def flywheel_disk():
    return make_flywheel_disk()


if __name__ == "__main__":
    flywheel_disk()
