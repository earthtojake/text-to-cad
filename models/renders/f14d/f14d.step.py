"""Grumman F-14D Super Tomcat -- full assembly.

Wings at 20 degrees, canopy closed, gear down, on the deck.  Clean airframe:
empty pylon stations, no external stores.

The airframe skin is ONE lofted solid (``f14_parts/body.py``) built from
full-width blended sections, so the glove flows into the forward fuselage, the
nacelles flow into the pancake tunnel, and the fin roots sit on a continuous
surface.  Nothing in the primary surface is filleted, because nothing there is
joined.

Assembly tree is grouped BY SYSTEM, which is also how the explode parameter
moves things.

OCCURRENCE ORDER IS BY WHAT ACTUALLY BUILDS, not by the SYSTEMS list below.
A system that is missing or that raises is skipped rather than failing the
aircraft, so it takes no occurrence number and everything after it shifts up.
Three of the thirteen produce no group today -- ``glove``, ``engines`` and
``markings`` have no module yet -- so the built aircraft is these ten, and
``f14d.params.js`` refs are numbered against them:

    o1.1  airframe    the one-piece blended skin, cut and detailed
    o1.2  cockpit     tub, panels, seats, HUD, canopy, windscreen
    o1.3  wings       panels, slats, flaps, spoilers, tip lights
    o1.4  inlets      ramps, splitters, bleed slots, ducts
    o1.5  nozzles     C-D nozzles, petals, seals, actuator rings
    o1.6  empennage   fins, rudders, stabilators, ventral fins
    o1.7  aft         speed brakes, beavertail, tailhook, dump mast
    o1.8  nose_gear   leg, wheels, launch bar, doors, bay
    o1.9  main_gear   legs, wheels, brakes, doors, bays
    o1.10 details     antennas, probes, lights, wicks, vents, panels

    (no group: glove, engines, markings -- no module)

Adding any missing module RENUMBERS every occurrence after it, so
``f14d.params.js`` has to be renumbered in the same commit.  ``nozzles`` is the
worked example: it silently dropped out of the aircraft for a while because its
revolve raised ``TopoDS::Solid``, and restoring it moved five systems by one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build123d import Compound

from cadgen import track

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
    # Report the walk through the systems. This phase is ~85% of the build (10 minutes of a
    # 12-minute run, measured), and without this it is the one stretch that says nothing at
    # all -- the viewer and the CLI both sat on "Building geometry" for its whole duration.
    #
    # The systems are counted AFTER dropping the ones that failed to import, so the
    # denominator is work that will actually run. Note the units are nowhere near equal:
    # `airframe` alone is over half the phase (see the cutter note above), so 1/13 sits for
    # minutes and the tail ticks past quickly. The count is true, not linear.
    buildable = [(name, module) for name, module in _MODULES if module is not None]
    groups = []
    for name, module in track(buildable, label=lambda entry: entry[0]):
        try:
            groups.append(module.build())
        except Exception as exc:  # noqa: BLE001
            print(f"[f14d] skip {name}: build failed: {exc}", file=sys.stderr)
    if not groups:
        raise RuntimeError("no F-14 part modules built")
    return {
        "shape": Compound(children=groups, label="f14d_super_tomcat"),
        # Exploded-view animation. Declared here because a generated model owns
        # its sidecar -- --params-path is rejected for one, and without this the
        # file is just an unreferenced .js next to the generator.
        "params": "f14d.params.js",
    }
