"""Chronograph works entry: column wheel, levers, clutch, runners, hammers —
the grey-steel chronograph layer of the caliber-321-lineage movement.

Movement local frame (see `_spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface. Chronograph parts ride z ~ 2.85..4.1 above the
bridges; the hour recorder lives on the dial side (z < -1.5).
"""

from build123d import Compound

import _mvt_chrono as C


def gen_step():
    return Compound(children=C.build_chrono(), label="chronograph_works")
