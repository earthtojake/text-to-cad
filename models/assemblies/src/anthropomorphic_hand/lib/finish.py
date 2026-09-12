"""Naming a surface language at authoring time.

The table itself lives in :mod:`lib.palette`, which owns every colour the hand
ships. This module is the verb: ``finish(shape, language, label)``. The hardware
languages are ``aluminum``, ``dark``, ``steel`` and ``pad``; a cord names its
motion and its side, e.g. ``cord_flexion_positive`` or ``cord_tip_negative``.
The old generic ``tendon_flex`` / ``tendon_extend`` pair is retired -- a cord's
colour now says which joint it drives.
"""
from lib.palette import FINISHES


def finish(shape, language, label):
    from cadgen import srgb
    color, material = FINISHES[language]
    shape.label = label
    shape.color = srgb(color)
    shape.cad_material = dict(material)
    return shape
