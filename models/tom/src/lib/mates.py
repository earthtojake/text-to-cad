"""The arm's mates as plain data: what `cadgen.revolute`/`cadgen.fastened` used to return.

The revision layers compute the arm's kinematics as a list of typed mates, and the build reads
them as data: `lib/joint_zero.py` re-places the arm at joint zero by their axes and
`lib/joint_limits.py` audits their ranges. The engine has no typed mates, so the same records
live here, field for field (`name`, `kind`, `parent`, `child`, `axis`, `limits`), and
`lib/joints.py` turns the final list into build123d joints on the built parts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

__all__ = ["Mate", "revolute", "fastened"]


@dataclass(frozen=True)
class Mate:
    """One relationship between two occurrences (``#label`` refs). ``axis`` is
    ``{"origin": [x, y, z], "dir": [x, y, z]}`` (empty for a fastened mate); ``limits`` is
    ``{"value": [lo, hi]}`` in degrees (empty for a fastened mate)."""

    name: str
    kind: str
    parent: str
    child: str
    axis: dict[str, Any]
    limits: dict[str, list[float]]


def _ref(value: object, what: str, name: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("#") or len(text) < 2:
        raise ValueError(f"mate {name!r} {what} must be an occurrence ref like '#link', got {value!r}")
    return text


def _vector(value: object, what: str, name: str) -> list[float]:
    vector = [float(v) for v in value]
    if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
        raise ValueError(f"mate {name!r} {what} must be three finite numbers, got {value!r}")
    return vector


def revolute(name, *, parent, child, origin, direction, limits) -> Mate:
    """A rotation about ``origin``/``direction``; degrees, zero = the authored placement."""
    lo, hi = (float(v) for v in limits)
    if not hi > lo:
        raise ValueError(f"mate {name!r} limits must be (lo, hi) with hi > lo, got {limits!r}")
    return Mate(str(name), "revolute", _ref(parent, "parent", name), _ref(child, "child", name),
                {"origin": _vector(origin, "origin", name), "dir": _vector(direction, "direction", name)},
                {"value": [lo, hi]})


def fastened(name, *, parent, child) -> Mate:
    """A rigid attachment: the child rides the parent."""
    return Mate(str(name), "fastened", _ref(parent, "parent", name), _ref(child, "child", name), {}, {})
