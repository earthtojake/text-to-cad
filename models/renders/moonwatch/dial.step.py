"""Dial + hands entry: black three-register step dial with applied indices,
printed tracks, snailed registers, and the full hand stack at 10:09:38.

Positioned in the WATCH frame (`_spec.py`): dial top at S.DIAL_Z, +Z up,
12 o'clock at +Y. Unbranded — numerals and scale markings only.
"""

from build123d import Compound

import _dial
import _materials as M


def gen_step():
    compound = Compound(children=_dial.build_dial_parts(), label="dial")
    M.apply(compound)
    return compound
