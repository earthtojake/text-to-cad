"""Keyless and motion works entry: stem, winding + sliding pinions, setting
lever + spring + screws, yoke, cannon pinion, minute wheel + pinion, hour
wheel of the caliber-321-lineage movement.

Movement local frame (see `lib/spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface; these parts hang on the dial side (z < -1.5)
around the stem axis at 3 o'clock.
"""

from cadgen import build123d as bd
from cadgen import step

from lib import materials
from lib import mvt_keyless as K


@step(out="../STEP/keyless_works.step")
def keyless_works():
    compound = bd.Compound(children=K.build_keyless(), label="keyless_works")
    materials.apply(compound)
    return compound


if __name__ == "__main__":
    keyless_works()
