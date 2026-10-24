"""Movement base entry: main plate, barrel + winding layer, going train,
bridges, escapement and balance of the caliber-321-lineage movement.

Movement local frame (see `lib/spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface.
"""

import build123d as bd
from cadgen import memo

from lib import materials
from lib import mvt_base as M


@memo
def movement_base():
    parts = materials.apply_materials(M.build_base(), "movement_base")
    compound = bd.Compound(children=parts, label="movement_base")
    return compound
