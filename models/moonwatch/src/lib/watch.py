"""The watch's documents as plain functions, each its parts with their finishes set: what
`case.py`, `dial.py` and `bracelet.py` declare and what `moonwatch.py` composes. Each is
authored in the WATCH frame (`spec.py`), so composing them is placing them as they are. Each
imports its builder itself, so a document's closure holds its own builder's module alone."""

from __future__ import annotations

import build123d as bd
from cadgen import paint

from lib import materials as M


def _grained_top(ring):
    """The bezel ring's snailed top annulus (r 20.55-20.85 at z 9.20): its faces only,
    not the polished walls and rim chamfers around it."""
    top = ring.bounding_box().max.Z
    faces = []
    for face in ring.faces():
        box = face.bounding_box()
        if box.min.Z > top - 0.05 and max(abs(box.min.X), abs(box.max.X), abs(box.min.Y), abs(box.max.Y)) < 20.9:
            faces.append(face)
    return faces


def case():
    """The case cluster: middle, bezel stack, crystal, caseback, crown, pushers, lugs."""
    from lib import case as C

    parts = M.apply_materials(C.build_case_parts(), "case")
    # A face finish: the bezel ring is polished steel, its grained top annulus satin.
    ring = next(part for part in parts if part.label == "bezel_ring")
    paint(ring, _grained_top(ring), M.FINISHES["satin_steel"])
    return bd.Compound(children=parts, label="case")


def dial():
    """The step dial, its applied indices and printed tracks, and the hand stack at 10:09:38."""
    from lib import dial as D

    return bd.Compound(children=M.apply_materials(D.build_dial_parts(), "dial"), label="dial")


def bracelet():
    """The three-link bracelet: two straps of rows on pins, end links and the fold-over clasp."""
    from lib.bracelet import build_bracelet

    (made,) = M.apply_materials([build_bracelet()], "bracelet")
    return made
