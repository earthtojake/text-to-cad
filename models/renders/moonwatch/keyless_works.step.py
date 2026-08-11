"""Keyless and motion works entry: stem, winding + sliding pinions, setting
lever + spring + screws, yoke, cannon pinion, minute wheel + pinion, hour
wheel of the caliber-321-lineage movement.

Movement local frame (see `_spec.py`): bridge side up, z = 0 at the main
plate's bridge-side surface; these parts hang on the dial side (z < -1.5)
around the stem axis at 3 o'clock.
"""

from build123d import Compound

import _materials
import _mvt_keyless as K


def gen_step():
    compound = Compound(children=K.build_keyless(), label="keyless_works")
    _materials.apply(compound)
    return compound
