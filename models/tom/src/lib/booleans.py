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
    a multi-element list becomes a Compound, and a plain Shape passes through.
    An empty result (``None`` or an empty list) becomes an empty Compound."""
    if result is None:
        return build123d.Compound(children=[])
    if isinstance(result, build123d.ShapeList):
        if len(result) == 1:
            return result[0]
        return build123d.Compound(children=list(result))
    return result


