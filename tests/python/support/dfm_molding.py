"""What the injection-molding check's tests share: the check on a live shape, the face a ref names, and the
drafted tray most of them cut their features into (``tests/python/packages/cad/test_dfm_molding_*.py``)."""

from __future__ import annotations

import math
from typing import Any

import build123d as bd

import cad
from cad.build123d import _dfm_brep

A = bd.Align
BOTTOM = (A.CENTER, A.CENTER, A.MIN)


def _check(shape: Any, **options: Any) -> Any:
    return cad.build123d.molding(shape, material=options.pop("material", "abs"), **options)


def _face(result: Any, shape: Any, location: str) -> Any:
    """The face a ref names, on the document the live shape reads as."""
    owner, _, ordinal = location.rpartition("face ")
    part = next(part for part in _dfm_brep.parts_of(shape).parts if part.owner == owner.rstrip("/"))
    return part.faces()[int(ordinal) - 1]


def _tray(draft: float = 3.0, wall: float = 2.0) -> Any:
    outer = bd.extrude(bd.Rectangle(60, 40), 20, taper=-draft)
    inset = wall / math.cos(math.radians(draft)) - wall * math.tan(math.radians(draft))
    return outer - bd.Pos(0, 0, wall) * bd.extrude(bd.Rectangle(60 - 2 * inset, 40 - 2 * inset), 20, taper=-draft)
