"""Version-robust build123d boolean-result normalization.

build123d 0.11 changed ``Shape.intersect()`` to always return a ``ShapeList``
(and multi-piece booleans may return lists rather than a fused ``Shape``).
These helpers restore the single-``Shape`` semantics the part generators are
written against, independent of the installed build123d version.
"""

from __future__ import annotations

import build123d


def as_single_shape(result: object) -> build123d.Shape:
    """Normalize a boolean result to one Shape: a single-element list unwraps,
    a multi-element list becomes a Compound, and a plain Shape passes through."""
    if isinstance(result, build123d.ShapeList):
        if len(result) == 1:
            return result[0]
        return build123d.Compound(children=list(result))
    return result


def intersection_volume(a: build123d.Shape, b: build123d.Shape) -> float:
    """Total intersection volume of two shapes across build123d versions."""
    result = a.intersect(b)
    if isinstance(result, build123d.ShapeList):
        return float(sum(shape.volume for shape in result))
    return float(result.volume)
