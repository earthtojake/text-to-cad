"""Mid-engine hypercar -- full assembly.

Body panels are cut from one master surface (see ``hypercar_parts/surfaces.py``),
so highlight lines cross every shutline without a kink and every panel gap is a
real constant-width gap.

Assembly tree is grouped BY SYSTEM, which is also how the explode parameter in
the ``hypercar.step.js`` sidecar moves things:

    o1.1 body        painted panels, pillars, aero skins
    o1.2 glazing     DLO glass + lamp lenses
    o1.3 lighting    lamp internals + light signature
    o1.4 chassis     monocoque tub, subframes, crash structures
    o1.5 suspension  wishbones, uprights, pushrods, rockers, coilovers, ARBs
    o1.6 wheels      rims, tyres
    o1.7 brakes      discs, calipers, hubs
    o1.8 powertrain  engine, intake, exhaust, transaxle, driveshafts
    o1.9 interior    seats, wheel, dash, console, pedals, door cards
    o1.10 aero       splitter, diffuser, wing
    o1.11 hinge      dihedral synchro-helix door mechanism
    o1.12 details    mirrors, badges, filler, vents, fasteners
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build123d import Compound

# Order here IS the occurrence order (o1.1, o1.2, ...) and the sidecar's
# feature refs depend on it -- do not reorder without updating hypercar.step.js.
SYSTEMS = [
    "body",
    "glazing",
    "lighting",
    "chassis",
    "suspension_front",
    "suspension_rear",
    "wheels",
    "brakes",
    "powertrain",
    "interior",
    "aero",
    "hinge",
    "details",
]


def _load(name):
    """Import a part module and build it.

    IMPORTANT: this runs at MODULE IMPORT time, not inside gen_step().  The CAD
    CLI restores sys.path after loading the generator, so a
    ``hypercar_parts.*`` import attempted inside gen_step() would fail to
    resolve.  Missing or still-broken modules are skipped with a note rather
    than failing the whole car, so the assembly stays renderable while
    individual part builders are still iterating.
    """
    try:
        return __import__(f"hypercar_parts.{name}", fromlist=["build"])
    except Exception as exc:  # noqa: BLE001
        print(f"[hypercar] skip {name}: import failed: {exc}", file=sys.stderr)
        return None


_MODULES = [(name, _load(name)) for name in SYSTEMS]


def gen_step():
    groups = []
    for name, module in _MODULES:
        if module is None:
            continue
        try:
            groups.append(module.build())
        except Exception as exc:  # noqa: BLE001
            print(f"[hypercar] skip {name}: build failed: {exc}", file=sys.stderr)
    if not groups:
        raise RuntimeError("no hypercar part modules built")
    car = Compound(children=groups, label="mid_engine_hypercar")
    return {"shape": car, "params": "hypercar.step.js"}
