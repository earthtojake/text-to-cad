"""Movement base entry: main plate, barrel + winding layer, going train,
bridges, escapement and balance of the caliber-321-lineage movement.

Movement local frame (see `lib/spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface.
"""

from cadgen import build123d as bd
from cadgen import step

from lib import materials
from lib import mvt_base as M


@step(out="../STEP/movement_base.step")
def movement_base():
    compound = bd.Compound(children=M.build_base(), label="movement_base")
    materials.apply(compound)
    return compound


if __name__ == "__main__":
    movement_base()
