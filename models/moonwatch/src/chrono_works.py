"""Chronograph works entry: column wheel, levers, clutch, runners, hammers —
the grey-steel chronograph layer of the caliber-321-lineage movement.

Movement local frame (see `lib/spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface. Chronograph parts ride z ~ 2.85..4.1 above the
bridges; the hour recorder lives on the dial side (z < -1.5).
"""

import build123d as bd
from cadgen import memo

from lib import materials
from lib import mvt_chrono as C


@memo
def chrono_works():
    parts = materials.apply_materials(C.build_chrono(), "chrono_works")
    compound = bd.Compound(children=parts, label="chronograph_works")
    return compound
