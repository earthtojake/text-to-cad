"""Grumman F-14D Super Tomcat -- full assembly.

Wings at 20 degrees, canopy closed, gear down, on the deck.  Clean airframe:
empty pylon stations, no external stores.

The airframe skin is ONE lofted solid (``f14_parts/body.py``) built from
full-width blended sections, so the glove flows into the forward fuselage, the
nacelles flow into the pancake tunnel, and the fin roots sit on a continuous
surface.  Nothing in the primary surface is filleted, because nothing there is
joined.

Assembly tree is grouped BY SYSTEM, which is also how the explode parameter
moves things:

    o1.1  airframe    the one-piece blended skin, cut and detailed
    o1.2  cockpit     tub, panels, seats, HUD, canopy, windscreen
    o1.3  glove       pivot boxes, vane bays, seal fairings
    o1.4  wings       panels, slats, flaps, spoilers, tip lights
    o1.5  inlets      ramps, splitters, bleed slots, ducts
    o1.6  engines     F110-GE-400 cores and compressor faces
    o1.7  nozzles     C-D nozzles, petals, actuator rings
    o1.8  empennage   fins, rudders, stabilators, ventral fins
    o1.9  aft         speed brakes, beavertail, tailhook, dump mast
    o1.10 nose_gear   leg, wheels, launch bar, doors, bay
    o1.11 main_gear   legs, wheels, brakes, doors, bays
    o1.12 details     antennas, probes, lights, wicks, vents, panels
    o1.13 markings    insignia, BuNo, squadron heraldry, stencils
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build123d import Compound

# Order here IS the occurrence order (o1.1, o1.2, ...).
SYSTEMS = [
    "airframe",
    "cockpit",
    "glove",
    "wings",
    "inlets",
    "engines",
    "nozzles",
    "empennage",
    "aft",
    "nose_gear",
    "main_gear",
    "details",
    "markings",
]


def _load(name):
    """Import a part module at MODULE IMPORT time, not inside gen_step().

    The CAD CLI restores sys.path after loading the generator, so an
    ``f14_parts.*`` import attempted inside gen_step() would fail to resolve.
    Missing or still-broken modules are skipped with a note rather than failing
    the whole aircraft, so the assembly stays renderable while individual part
    builders are still iterating.
    """
    try:
        return __import__(f"f14_parts.{name}", fromlist=["build"])
    except ModuleNotFoundError as exc:
        if name not in str(exc):
            print(f"[f14d] skip {name}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[f14d] skip {name}: import failed: {exc}", file=sys.stderr)
        return None


_MODULES = [(name, _load(name)) for name in SYSTEMS]

# ---------------------------------------------------------------------------
# Cosmetic skin cutters are DROPPED.  Measured against this skin, subtracting
# the 41 shallow panel recesses published by `details` and `aft` did not finish
# in 15 minutes, and a full 44-cutter build ran over seven hours without
# completing; the 3 structural cutters (diverter slot, cockpit opening) cost
# 348 s and are kept.  The skin is one B-spline surface of ~4,900 control
# points, so every boolean tool forces a full-surface classification -- the cost
# is per-tool, not per-unit-of-material-removed.
#
# Nothing visual is lost.  At 19 m rendered to 1920 px, 1 px is about 10 mm, so
# a 4 mm groove is sub-pixel: panel lines read because the renderer's edge
# overlay draws feature edges, not because the groove is resolvable.
# ---------------------------------------------------------------------------
COSMETIC_CUTTER_MODULES = ("details", "aft")

for _name in COSMETIC_CUTTER_MODULES:
    _mod = sys.modules.get(f"f14_parts.{_name}")
    if _mod is not None and getattr(_mod, "SKIN_CUTTERS", None):
        print(f"[f14d] dropping {len(_mod.SKIN_CUTTERS)} cosmetic skin cutters "
              f"from {_name}", file=sys.stderr)
        _mod.SKIN_CUTTERS = []


def gen_step():
    groups = []
    for name, module in _MODULES:
        if module is None:
            continue
        try:
            groups.append(module.build())
        except Exception as exc:  # noqa: BLE001
            print(f"[f14d] skip {name}: build failed: {exc}", file=sys.stderr)
    if not groups:
        raise RuntimeError("no F-14 part modules built")
    return Compound(children=groups, label="f14d_super_tomcat")
