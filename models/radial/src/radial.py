"""Nine-cylinder supercharged radial — the full, sectioned assembly.

The eighteen system models (`lib/systems.py`, in explode order) are CALLED here
and linked as occurrences; each builds in its own worker. A system joins as soon
as its `lib/<name>.py` exists. The choreography is `lib/clips.py`'s ANIMATION:
Python clips that pose parts by label from `lib/kin.py` and the explode
layouts, baked to keyframes in the sidecar as this builds.
Build through `tools/engine.py build` (it serialises assembly builds and renders).
"""

from __future__ import annotations

import importlib

from cadgen import build123d as bd
from cadgen import step

from lib.clips import ANIMATION
from lib.systems import ready


@step(out="../STEP/radial.step", animation=ANIMATION)
def radial():
    systems = [getattr(importlib.import_module(name), name)() for name in ready()]
    if not systems:
        raise RuntimeError("no system is ready (lib/<name>.py)")
    return bd.Compound(children=systems, label="radial")


if __name__ == "__main__":
    radial()
