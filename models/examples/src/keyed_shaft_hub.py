from __future__ import annotations
from cadgen import step
# Prompt: Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern.

from lib.simple_model_library import make_keyed_shaft_hub


@step(out="../STEP/keyed_shaft_hub.step")
def keyed_shaft_hub():
    return make_keyed_shaft_hub()


if __name__ == "__main__":
    keyed_shaft_hub()
