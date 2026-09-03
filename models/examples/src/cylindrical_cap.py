from __future__ import annotations
from cadgen import step
# Prompt: Cylindrical cap with hollow interior, top boss, and rounded external edges.

from lib.simple_model_library import make_cylindrical_cap


@step(out="../STEP/cylindrical_cap.step")
def cylindrical_cap():
    return make_cylindrical_cap()


if __name__ == "__main__":
    cylindrical_cap()
