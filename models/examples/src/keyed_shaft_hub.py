from __future__ import annotations
from cadgen import materials, model
# Prompt: Keyed shaft hub with central bore, keyway slot, and bolt-hole pattern.

from lib.simple_model_library import make_keyed_shaft_hub


@model
def keyed_shaft_hub():
    part = make_keyed_shaft_hub()
    part.material = materials.steel_1018.but(color=None)
    return part


if __name__ == "__main__":
    keyed_shaft_hub()
