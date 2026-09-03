from __future__ import annotations
from cadgen import step
# Prompt: Shaft collar with a central bore, radial set-screw hole, and chamfered faces.

from lib.simple_model_library import make_shaft_collar


@step(out="../STEP/shaft_collar.step")
def shaft_collar():
    return make_shaft_collar()


if __name__ == "__main__":
    shaft_collar()
