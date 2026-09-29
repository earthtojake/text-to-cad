"""Signed distance fields as an expression tree.

Every :class:`Field` answers two questions for a batch of points ``(N, 3)``:
the signed distance to its surface (``distance``: negative inside, positive
outside, in the author's units -- millimetres by convention) and which
*leaf* of the tree owns the nearest surface (``evaluate`` returns both). The
leaf is the primitive the author wrote, so a mesh vertex, a probe or a
measurement always maps back to a line of code: the "annotated field".

Primitives are exact distance fields (the unit-gradient property: the value
IS the distance, so offsets, shells, thickness and clearance are metric).
Booleans and transforms keep exactness where they can (union, intersection,
rigid transforms) and give a *bound* -- never larger than the true distance
in magnitude at the surface -- where they cannot (smooth blends, uniform
scale is exact, non-uniform scale is not offered).

The tree is immutable data. ``Field.to_dict`` / :func:`from_dict` make it
JSON so a part can be saved as a tape beside its mesh (``tape.py``).

Only numpy is used, and numpy is already a cadgen dependency: this module
must never import the CAD kernel.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

__all__ = [
    "Bounds",
    "Field",
    "Profile",
    "Sphere",
    "Box",
    "Cylinder",
    "Capsule",
    "Cone",
    "Torus",
    "HalfSpace",
    "Extrude",
    "Revolve",
    "Custom",
    "Brep",
    "Union",
    "Intersection",
    "Subtraction",
    "Translate",
    "Rotate",
    "Scale",
    "Mirror",
    "Repeat",
    "Offset",
    "Shell",
    "Elongate",
    "Circle",
    "Rect",
    "Polygon",
    "RegularPolygon",
    "union",
    "intersect",
    "subtract",
    "from_dict",
    "leaves",
]

Vec3 = tuple[float, float, float]
_EPS = 1e-12


# --------------------------------------------------------------------------- #
# Bounds
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Bounds:
    """An axis-aligned box the surface is guaranteed to lie inside.

    Bounds are *conservative*: a node's bounds may be larger than its surface
    but never smaller. They give the mesher its grid, so a field whose bounds
    are wrong meshes wrong -- primitives compute theirs, booleans combine them,
    and a :class:`Custom` field must declare them.
    """

    min: Vec3
    max: Vec3

    @property
    def size(self) -> Vec3:
        return tuple(float(b - a) for a, b in zip(self.min, self.max))  # type: ignore[return-value]

    @property
    def center(self) -> Vec3:
        return tuple(float((a + b) / 2) for a, b in zip(self.min, self.max))  # type: ignore[return-value]

    @property
    def diagonal(self) -> float:
        return float(math.sqrt(sum(s * s for s in self.size)))

    def pad(self, r: float) -> Bounds:
        return Bounds(
            tuple(float(a - r) for a in self.min),  # type: ignore[arg-type]
            tuple(float(b + r) for b in self.max),  # type: ignore[arg-type]
        )

    def union(self, other: Bounds) -> Bounds:
        return Bounds(
            tuple(float(min(a, b)) for a, b in zip(self.min, other.min)),  # type: ignore[arg-type]
            tuple(float(max(a, b)) for a, b in zip(self.max, other.max)),  # type: ignore[arg-type]
        )

    def intersection(self, other: Bounds) -> Bounds:
        lo = tuple(float(max(a, b)) for a, b in zip(self.min, other.min))
        hi = tuple(float(max(l, min(a, b))) for l, a, b in zip(lo, self.max, other.max))
        return Bounds(lo, hi)  # type: ignore[arg-type]

    def corners(self) -> np.ndarray:
        lo, hi = np.asarray(self.min, float), np.asarray(self.max, float)
        return np.array([[hi[0] if i & 1 else lo[0], hi[1] if i & 2 else lo[1], hi[2] if i & 4 else lo[2]] for i in range(8)])

    @staticmethod
    def of_points(points: np.ndarray) -> Bounds:
        p = np.asarray(points, float).reshape(-1, 3)
        return Bounds(tuple(map(float, p.min(axis=0))), tuple(map(float, p.max(axis=0))))  # type: ignore[arg-type]

    def to_dict(self) -> dict:
        return {"min": list(self.min), "max": list(self.max)}


# --------------------------------------------------------------------------- #
# Source attribution
# --------------------------------------------------------------------------- #

_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _caller_site() -> str | None:
    """``file:line`` of the first frame outside cadgen: where the author wrote the primitive."""
    frame = sys._getframe(1)
    while frame is not None:
        filename = frame.f_code.co_filename
        if not os.path.abspath(filename).startswith(_PACKAGE_ROOT) and "<frozen" not in filename:
            return f"{os.path.basename(filename)}:{frame.f_lineno}"
        frame = frame.f_back
    return None


# --------------------------------------------------------------------------- #
# The node
# --------------------------------------------------------------------------- #


def _vec(v: Sequence[float] | float, n: int = 3) -> tuple[float, ...]:
    if isinstance(v, (int, float)):
        return (float(v),) * n
    out = tuple(float(x) for x in v)
    if len(out) != n:
        raise ValueError(f"expected {n} components, got {out!r}")
    return out


def _points(points: Any) -> np.ndarray:
    p = np.asarray(points, dtype=float)
    if p.ndim == 1 and p.shape[0] == 3:
        p = p[None, :]
    if p.ndim != 2 or p.shape[1] != 3:
        raise ValueError(f"points must be (N, 3), got shape {p.shape}")
    return p


class Field:
    """A signed distance field: a node of the expression tree.

    Subclasses implement :meth:`_eval` (distance and leaf id for each point)
    and :meth:`_bounds`. The operators build the tree: ``a | b`` unions,
    ``a & b`` intersects, ``a - b`` subtracts; ``.translate``, ``.rotate``,
    ``.scale``, ``.mirror``, ``.repeat`` place; ``.offset``, ``.shell``,
    ``.round`` modify. Nothing here evaluates until asked.
    """

    kind: str = "field"

    def __init__(self, *, label: str | None = None, site: str | None = None) -> None:
        self.label = label
        self.site = site

    # -- evaluation ----------------------------------------------------------
    def _eval(self, p: np.ndarray, ids: dict[int, int]) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def _bounds(self) -> Bounds:
        raise NotImplementedError

    def evaluate(self, points: Any) -> tuple[np.ndarray, np.ndarray]:
        """Signed distance and owning leaf index (into :func:`leaves`) per point."""
        p = _points(points)
        ids = {id(leaf): i for i, leaf in enumerate(leaves(self))}
        d, owner = self._eval(p, ids)
        return np.asarray(d, float), np.asarray(owner, np.int32)

    def distance(self, points: Any) -> np.ndarray:
        """Signed distance per point: negative inside, positive outside."""
        return self.evaluate(points)[0]

    def __call__(self, points: Any) -> np.ndarray:
        return self.distance(points)

    def contains(self, points: Any) -> np.ndarray:
        return self.distance(points) <= 0.0

    def gradient(self, points: Any, h: float | None = None) -> np.ndarray:
        """Numerical gradient (central differences); unit length where the field is exact."""
        p = _points(points)
        if h is None:
            h = max(self.bounds.diagonal * 1e-5, 1e-6)
        g = np.empty_like(p)
        for axis in range(3):
            e = np.zeros(3)
            e[axis] = h
            g[:, axis] = (self.distance(p + e) - self.distance(p - e)) / (2 * h)
        return g

    def normal(self, points: Any) -> np.ndarray:
        g = self.gradient(points)
        n = np.linalg.norm(g, axis=1, keepdims=True)
        return g / np.where(n < _EPS, 1.0, n)

    @property
    def bounds(self) -> Bounds:
        return self._bounds()

    def prepare(self, resolution: float) -> None:
        """Tell every leaf the grid spacing it is about to be sampled at (a B-rep leaf builds its sampler)."""
        for child in self.children():
            child.prepare(resolution)

    # -- naming ---------------------------------------------------------------
    def named(self, label: str) -> Field:
        """The same field carrying ``label``: what its leaves are called in a mesh.

        On a primitive it names that leaf. On anything built from primitives
        (a moved box, a union) it names every leaf underneath that has no
        name of its own, so ``(a | b).named("bracket")`` labels both.
        """

        def stamp(leaf: Field) -> Field:
            if leaf.label:
                return leaf
            clone = leaf._clone()
            clone.label = label
            return clone

        clone = self._map_leaves(stamp)
        clone.label = label
        return clone

    def _map_leaves(self, fn: Callable[[Field], Field]) -> Field:
        """A copy of the tree with ``fn`` applied to every leaf (nodes are shallow-cloned)."""
        children = self.children()
        clone = self._clone()
        if not children:
            return fn(clone)
        clone._replace_children(tuple(child._map_leaves(fn) for child in children))
        return clone

    def _replace_children(self, children: tuple[Field, ...]) -> None:
        raise NotImplementedError

    def _clone(self) -> Field:
        clone = object.__new__(type(self))
        clone.__dict__.update(self.__dict__)
        return clone

    # -- operators ------------------------------------------------------------
    def __or__(self, other: Field) -> Field:
        return Union((self, other))

    def __and__(self, other: Field) -> Field:
        return Intersection((self, other))

    def __sub__(self, other: Field) -> Field:
        return Subtraction(self, other)

    def __neg__(self) -> Field:
        return Custom(lambda p: -self.distance(p), bounds=self.bounds, label="complement")

    # -- placement ------------------------------------------------------------
    def translate(self, x: float | Sequence[float] = 0.0, y: float = 0.0, z: float = 0.0) -> Field:
        offset = _vec(x) if not isinstance(x, (int, float)) else (float(x), float(y), float(z))
        return Translate(self, offset)

    def rotate(self, angle_deg: float, axis: Sequence[float] = (0.0, 0.0, 1.0)) -> Field:
        """Rotate about an axis through the origin (degrees, right-hand rule)."""
        return Rotate(self, float(angle_deg), _vec(axis))

    def scale(self, factor: float) -> Field:
        """Uniform scale about the origin (distances stay exact)."""
        return Scale(self, float(factor))

    def mirror(self, axis: str = "x") -> Field:
        """Union of the field and its reflection across the plane normal to ``axis``."""
        return Mirror(self, axis)

    def repeat(self, spacing: Sequence[float], count: Sequence[int]) -> Field:
        """A finite grid of copies: ``count`` copies at ``spacing`` along each axis, centred on the original."""
        return Repeat(self, _vec(spacing), tuple(int(c) for c in count))

    # -- modifiers ------------------------------------------------------------
    def offset(self, r: float) -> Field:
        """Grow (``r > 0``) or shrink the solid by a metric distance."""
        return Offset(self, float(r))

    def shell(self, thickness: float) -> Field:
        """The skin of the solid: a wall ``thickness`` thick, centred on the surface."""
        return Shell(self, float(thickness))

    def round(self, r: float) -> Field:
        """Round every edge and corner by ``r`` (shrink then grow: a morphological opening).

        Exact for convex solids; concave edges keep their sharpness (round
        those at the boolean: ``union(a, b, round=r)``).
        """
        return Offset(Offset(self, -float(r)), float(r))

    def elongate(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Field:
        """Stretch the field by a flat section of the given lengths along each axis."""
        return Elongate(self, (float(x), float(y), float(z)))

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict:
        d = {"kind": self.kind, **self._params()}
        if self.label:
            d["label"] = self.label
        if self.site:
            d["site"] = self.site
        return d

    def _params(self) -> dict:
        raise NotImplementedError

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v!r}" for k, v in self._params().items() if not isinstance(v, (Field, list, tuple, dict)))
        return f"{type(self).__name__}({params})"


def leaves(field: Field) -> list[Field]:
    """The primitives of a tree, in depth-first author order. Their index is the leaf id."""
    found: list[Field] = []

    def walk(node: Field) -> None:
        children = node.children()
        if not children:
            found.append(node)
        for child in children:
            walk(child)

    walk(field)
    return found


# The default: a node has no children.
Field.children = lambda self: ()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# 2D profiles (for extrude / revolve)
# --------------------------------------------------------------------------- #


class Profile:
    """A 2D signed distance field in the plane, ``(N, 2)`` points in."""

    kind: str = "profile"

    def distance(self, q: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def bounds2(self) -> tuple[tuple[float, float], tuple[float, float]]:
        raise NotImplementedError

    def to_dict(self) -> dict:
        return {"kind": self.kind, **self._params()}

    def _params(self) -> dict:
        raise NotImplementedError


class Circle(Profile):
    kind = "circle"

    def __init__(self, radius: float) -> None:
        self.radius = float(radius)

    def distance(self, q: np.ndarray) -> np.ndarray:
        return np.linalg.norm(q, axis=1) - self.radius

    def bounds2(self):
        r = self.radius
        return ((-r, -r), (r, r))

    def _params(self):
        return {"radius": self.radius}


class Rect(Profile):
    """A rectangle ``width`` by ``height`` centred at the origin, corners rounded by ``radius``."""

    kind = "rect"

    def __init__(self, width: float, height: float, radius: float = 0.0) -> None:
        self.width, self.height, self.radius = float(width), float(height), float(radius)

    def distance(self, q: np.ndarray) -> np.ndarray:
        half = np.array([self.width / 2 - self.radius, self.height / 2 - self.radius])
        d = np.abs(q) - half
        outside = np.linalg.norm(np.maximum(d, 0.0), axis=1)
        inside = np.minimum(np.max(d, axis=1), 0.0)
        return outside + inside - self.radius

    def bounds2(self):
        return ((-self.width / 2, -self.height / 2), (self.width / 2, self.height / 2))

    def _params(self):
        return {"width": self.width, "height": self.height, "radius": self.radius}


class Polygon(Profile):
    """A simple polygon from its vertices (either winding); exact distance."""

    kind = "polygon"

    def __init__(self, points: Sequence[Sequence[float]]) -> None:
        v = np.asarray(points, float)
        if v.ndim != 2 or v.shape[1] != 2 or len(v) < 3:
            raise ValueError("a polygon needs at least three (x, y) points")
        self.points = v

    def distance(self, q: np.ndarray) -> np.ndarray:
        v = self.points
        n = len(v)
        d = np.full(len(q), np.inf)
        sign = np.ones(len(q))
        for i in range(n):
            j = (i - 1) % n
            e = v[j] - v[i]
            w = q - v[i]
            t = np.clip((w @ e) / max(e @ e, _EPS), 0.0, 1.0)
            b = w - e[None, :] * t[:, None]
            d = np.minimum(d, np.einsum("ij,ij->i", b, b))
            c1 = q[:, 1] >= v[i][1]
            c2 = q[:, 1] < v[j][1]
            c3 = e[0] * w[:, 1] > e[1] * w[:, 0]
            flip = (c1 & c2 & c3) | (~c1 & ~c2 & ~c3)
            sign = np.where(flip, -sign, sign)
        return sign * np.sqrt(d)

    def bounds2(self):
        lo, hi = self.points.min(axis=0), self.points.max(axis=0)
        return ((float(lo[0]), float(lo[1])), (float(hi[0]), float(hi[1])))

    def _params(self):
        return {"points": self.points.tolist()}


class RegularPolygon(Profile):
    """``sides`` sides, ``radius`` to a vertex, one vertex on +X."""

    kind = "regular_polygon"

    def __init__(self, sides: int, radius: float) -> None:
        if sides < 3:
            raise ValueError("a regular polygon needs at least three sides")
        self.sides, self.radius = int(sides), float(radius)
        angles = np.arange(sides) * (2 * math.pi / sides)
        self._poly = Polygon(np.stack([np.cos(angles), np.sin(angles)], axis=1) * self.radius)

    def distance(self, q):
        return self._poly.distance(q)

    def bounds2(self):
        return self._poly.bounds2()

    def _params(self):
        return {"sides": self.sides, "radius": self.radius}


_PROFILES: dict[str, type[Profile]] = {c.kind: c for c in (Circle, Rect, Polygon, RegularPolygon)}


def profile_from_dict(d: dict) -> Profile:
    kind = d.get("kind")
    cls = _PROFILES.get(kind)
    if cls is None:
        raise ValueError(f"unknown profile kind {kind!r}")
    params = {k: v for k, v in d.items() if k != "kind"}
    return cls(**params)


# --------------------------------------------------------------------------- #
# Primitives (leaves)
# --------------------------------------------------------------------------- #


class _Leaf(Field):
    def __init__(self, *, label: str | None = None, site: str | None = None) -> None:
        super().__init__(label=label, site=site or _caller_site())

    def _eval(self, p, ids):
        d = self._distance(p)
        return d, np.full(len(p), ids[id(self)], np.int32)

    def _distance(self, p: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class Sphere(_Leaf):
    kind = "sphere"

    def __init__(self, radius: float, **kw) -> None:
        super().__init__(**kw)
        self.radius = float(radius)

    def _distance(self, p):
        return np.linalg.norm(p, axis=1) - self.radius

    def _bounds(self):
        r = self.radius
        return Bounds((-r, -r, -r), (r, r, r))

    def _params(self):
        return {"radius": self.radius}


class Box(_Leaf):
    """A box of the given size centred at the origin; ``radius`` rounds every edge."""

    kind = "box"

    def __init__(self, size: Sequence[float] | float, radius: float = 0.0, **kw) -> None:
        super().__init__(**kw)
        self.size = _vec(size)
        self.radius = float(radius)
        if self.radius > min(self.size) / 2:
            raise ValueError("box radius exceeds half its smallest side")

    def _distance(self, p):
        half = np.asarray(self.size) / 2 - self.radius
        q = np.abs(p) - half
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
        inside = np.minimum(np.max(q, axis=1), 0.0)
        return outside + inside - self.radius

    def _bounds(self):
        h = tuple(s / 2 for s in self.size)
        return Bounds(tuple(-x for x in h), h)  # type: ignore[arg-type]

    def _params(self):
        return {"size": list(self.size), "radius": self.radius}


class Cylinder(_Leaf):
    """A cylinder along Z: ``radius``, ``height`` (centred), ``radius_edge`` rounds the rims."""

    kind = "cylinder"

    def __init__(self, radius: float, height: float, radius_edge: float = 0.0, **kw) -> None:
        super().__init__(**kw)
        self.radius, self.height, self.radius_edge = float(radius), float(height), float(radius_edge)

    def _distance(self, p):
        re = self.radius_edge
        d = np.stack([np.linalg.norm(p[:, :2], axis=1) - self.radius + re, np.abs(p[:, 2]) - self.height / 2 + re], axis=1)
        return np.minimum(np.max(d, axis=1), 0.0) + np.linalg.norm(np.maximum(d, 0.0), axis=1) - re

    def _bounds(self):
        r, h = self.radius, self.height / 2
        return Bounds((-r, -r, -h), (r, r, h))

    def _params(self):
        return {"radius": self.radius, "height": self.height, "radius_edge": self.radius_edge}


class Capsule(_Leaf):
    """A capsule from ``a`` to ``b`` with ``radius`` (a sphere-swept segment)."""

    kind = "capsule"

    def __init__(self, a: Sequence[float], b: Sequence[float], radius: float, **kw) -> None:
        super().__init__(**kw)
        self.a, self.b, self.radius = _vec(a), _vec(b), float(radius)

    def _distance(self, p):
        a, b = np.asarray(self.a), np.asarray(self.b)
        pa, ba = p - a, b - a
        h = np.clip((pa @ ba) / max(ba @ ba, _EPS), 0.0, 1.0)
        return np.linalg.norm(pa - ba[None, :] * h[:, None], axis=1) - self.radius

    def _bounds(self):
        return Bounds.of_points(np.array([self.a, self.b])).pad(self.radius)

    def _params(self):
        return {"a": list(self.a), "b": list(self.b), "radius": self.radius}


class Cone(_Leaf):
    """A (truncated) cone along Z: ``radius_bottom`` at ``-height/2``, ``radius_top`` at ``+height/2``."""

    kind = "cone"

    def __init__(self, radius_bottom: float, radius_top: float, height: float, **kw) -> None:
        super().__init__(**kw)
        self.radius_bottom, self.radius_top, self.height = float(radius_bottom), float(radius_top), float(height)

    def _distance(self, p):
        # Quilez's capped cone, exact.
        r1, r2, h = self.radius_bottom, self.radius_top, self.height / 2
        q = np.stack([np.linalg.norm(p[:, :2], axis=1), p[:, 2]], axis=1)
        k1 = np.array([r2, h])
        k2 = np.array([r2 - r1, 2 * h])
        ca = np.stack([q[:, 0] - np.minimum(q[:, 0], np.where(q[:, 1] < 0, r1, r2)), np.abs(q[:, 1]) - h], axis=1)
        t = np.clip(((k1 - q) @ k2) / max(k2 @ k2, _EPS), 0.0, 1.0)
        cb = q - k1 + k2[None, :] * t[:, None]
        s = np.where((cb[:, 0] < 0) & (ca[:, 1] < 0), -1.0, 1.0)
        return s * np.sqrt(np.minimum(np.einsum("ij,ij->i", ca, ca), np.einsum("ij,ij->i", cb, cb)))

    def _bounds(self):
        r, h = max(self.radius_bottom, self.radius_top), self.height / 2
        return Bounds((-r, -r, -h), (r, r, h))

    def _params(self):
        return {"radius_bottom": self.radius_bottom, "radius_top": self.radius_top, "height": self.height}


class Torus(_Leaf):
    """A torus in the XY plane: ``radius`` to the tube centre, ``tube`` the tube radius."""

    kind = "torus"

    def __init__(self, radius: float, tube: float, **kw) -> None:
        super().__init__(**kw)
        self.radius, self.tube = float(radius), float(tube)

    def _distance(self, p):
        q = np.stack([np.linalg.norm(p[:, :2], axis=1) - self.radius, p[:, 2]], axis=1)
        return np.linalg.norm(q, axis=1) - self.tube

    def _bounds(self):
        r, t = self.radius + self.tube, self.tube
        return Bounds((-r, -r, -t), (r, r, t))

    def _params(self):
        return {"radius": self.radius, "tube": self.tube}


class HalfSpace(_Leaf):
    """The half of space that ``normal`` points into, from the plane through ``origin``.

    ``part - half_space((0, 0, 1), (0, 0, 10))`` removes everything above
    z = 10; ``part & half_space((0, 0, -1), (0, 0, 10))`` keeps what is below.
    Unbounded: it contributes no bounds of its own, so use it inside an
    intersection or subtraction with a bounded solid (a cut), never alone.
    """

    kind = "half_space"

    def __init__(self, normal: Sequence[float] = (0.0, 0.0, 1.0), origin: Sequence[float] = (0.0, 0.0, 0.0), **kw) -> None:
        super().__init__(**kw)
        n = np.asarray(_vec(normal))
        self.normal = tuple(map(float, n / max(np.linalg.norm(n), _EPS)))
        self.origin = _vec(origin)

    def _distance(self, p):
        # Inside is the normal's side: distance grows AGAINST the normal.
        return -((p - np.asarray(self.origin)) @ np.asarray(self.normal))

    def _bounds(self):
        big = 1e9
        return Bounds((-big, -big, -big), (big, big, big))

    def _params(self):
        return {"normal": list(self.normal), "origin": list(self.origin)}


class Extrude(_Leaf):
    """A 2D profile extruded along Z by ``height`` (centred); exact."""

    kind = "extrude"

    def __init__(self, profile: Profile, height: float, **kw) -> None:
        super().__init__(**kw)
        self.profile, self.height = profile, float(height)

    def _distance(self, p):
        d = self.profile.distance(p[:, :2])
        w = np.stack([d, np.abs(p[:, 2]) - self.height / 2], axis=1)
        return np.minimum(np.max(w, axis=1), 0.0) + np.linalg.norm(np.maximum(w, 0.0), axis=1)

    def _bounds(self):
        (x0, y0), (x1, y1) = self.profile.bounds2()
        h = self.height / 2
        return Bounds((x0, y0, -h), (x1, y1, h))

    def _params(self):
        return {"profile": self.profile.to_dict(), "height": self.height}


class Revolve(_Leaf):
    """A 2D profile in the (radius, z) half-plane revolved about Z; exact for profiles that stay at ``r >= 0``."""

    kind = "revolve"

    def __init__(self, profile: Profile, **kw) -> None:
        super().__init__(**kw)
        self.profile = profile

    def _distance(self, p):
        q = np.stack([np.linalg.norm(p[:, :2], axis=1), p[:, 2]], axis=1)
        return self.profile.distance(q)

    def _bounds(self):
        (r0, z0), (r1, z1) = self.profile.bounds2()
        r = max(abs(r0), abs(r1))
        return Bounds((-r, -r, z0), (r, r, z1))

    def _params(self):
        return {"profile": self.profile.to_dict()}


class Custom(_Leaf):
    """Any distance function ``fn(points (N,3)) -> (N,)`` with declared bounds.

    It is a leaf like a primitive, but it cannot be written to a tape: a
    part that uses one meshes and measures normally and saves no tape.
    """

    kind = "custom"

    def __init__(self, fn: Callable[[np.ndarray], np.ndarray], bounds: Bounds | tuple, **kw) -> None:
        super().__init__(**kw)
        self.fn = fn
        self._declared = bounds if isinstance(bounds, Bounds) else Bounds(_vec(bounds[0]), _vec(bounds[1]))  # type: ignore[arg-type]

    def _distance(self, p):
        return np.asarray(self.fn(p), float).reshape(len(p))

    def _bounds(self):
        return self._declared

    def _params(self):
        return {"bounds": self._declared.to_dict()}


class Brep(_Leaf):
    """A build123d shape as a leaf: the way a STEP enters the field.

    The distance comes from the shape's tessellation (``brep_field.py``), exact
    to a small fraction of the grid cell it is sampled at; the shape itself is
    kept, so ``to_brep`` returns it unchanged and a boolean with a primitive
    leaves as an exact STEP. ``source`` is the STEP the shape was read from,
    which is what a tape records; a shape with no source is, like a custom
    field, not tapeable.
    """

    kind = "brep"

    def __init__(self, shape: Any, source: str | os.PathLike | None = None, **kw) -> None:
        super().__init__(**kw)
        self.shape = shape
        # Kept absolute; a tape writes it relative to itself (tape.py).
        self.source = os.path.abspath(os.fspath(source)) if source is not None else None
        self._sampler = None
        from cadgen._internal.implicit.brep_field import shape_bounds

        lo, hi = shape_bounds(shape)
        self._box = Bounds(lo, hi)

    def prepare(self, resolution: float) -> None:
        from cadgen._internal.implicit.brep_field import BrepSampler

        spacing = max(float(resolution), 1e-6)
        if self._sampler is None or self._sampler.spacing > spacing * 1.001:
            self._sampler = BrepSampler(self.shape, spacing)

    def _distance(self, p):
        if self._sampler is None:
            self.prepare(self._box.diagonal / 300.0)
        return self._sampler.distance(p)

    def _bounds(self):
        return self._box

    def _params(self):
        if self.source is None:
            return {"bounds": self._box.to_dict()}
        return {"source": self.source}


# --------------------------------------------------------------------------- #
# Booleans
# --------------------------------------------------------------------------- #


def _smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Polynomial smooth minimum: a fillet of radius ~``k`` at the join (Quilez)."""
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def _chamfer_min(a: np.ndarray, b: np.ndarray, r: float) -> np.ndarray:
    return np.minimum(np.minimum(a, b), (a + b - r) * math.sqrt(0.5))


def _blend_min(a: np.ndarray, b: np.ndarray, round: float, chamfer: float) -> np.ndarray:
    if round > 0:
        return _smin(a, b, round)
    if chamfer > 0:
        return _chamfer_min(a, b, chamfer)
    return np.minimum(a, b)


class _Boolean(Field):
    def __init__(self, operands: Sequence[Field], round: float = 0.0, chamfer: float = 0.0, **kw) -> None:
        super().__init__(**kw)
        if len(operands) < 1:
            raise ValueError("a boolean needs at least one operand")
        if round and chamfer:
            raise ValueError("choose round or chamfer, not both")
        self.operands = tuple(operands)
        self.round, self.chamfer = float(round), float(chamfer)

    def children(self):
        return self.operands

    def _replace_children(self, children):
        self.operands = tuple(children)

    def _params(self):
        d: dict = {"operands": [o.to_dict() for o in self.operands]}
        if self.round:
            d["round"] = self.round
        if self.chamfer:
            d["chamfer"] = self.chamfer
        return d


class Union(_Boolean):
    kind = "union"

    def _eval(self, p, ids):
        d, owner = self.operands[0]._eval(p, ids)
        for op in self.operands[1:]:
            d2, owner2 = op._eval(p, ids)
            owner = np.where(d2 < d, owner2, owner)
            d = _blend_min(d, d2, self.round, self.chamfer)
        return d, owner

    def _bounds(self):
        b = self.operands[0].bounds
        for op in self.operands[1:]:
            b = b.union(op.bounds)
        return b.pad(max(self.round, self.chamfer))


class Intersection(_Boolean):
    kind = "intersection"

    def _eval(self, p, ids):
        d, owner = self.operands[0]._eval(p, ids)
        for op in self.operands[1:]:
            d2, owner2 = op._eval(p, ids)
            owner = np.where(d2 > d, owner2, owner)
            d = -_blend_min(-d, -d2, self.round, self.chamfer)
        return d, owner

    def _bounds(self):
        b = self.operands[0].bounds
        for op in self.operands[1:]:
            b = b.intersection(op.bounds)
        return b


class Subtraction(_Boolean):
    """``base`` minus every ``tool``: ``max(base, -tool)``."""

    kind = "subtraction"

    def __init__(self, base: Field, *tools: Field, round: float = 0.0, chamfer: float = 0.0, **kw) -> None:
        super().__init__((base, *tools), round=round, chamfer=chamfer, **kw)

    def _eval(self, p, ids):
        d, owner = self.operands[0]._eval(p, ids)
        for tool in self.operands[1:]:
            d2, owner2 = tool._eval(p, ids)
            owner = np.where(-d2 > d, owner2, owner)
            d = -_blend_min(-d, d2, self.round, self.chamfer)
        return d, owner

    def _bounds(self):
        return self.operands[0].bounds


def union(*fields: Field, round: float = 0.0, chamfer: float = 0.0) -> Field:
    """The union of the fields; ``round`` fillets the joins, ``chamfer`` bevels them."""
    return Union(fields, round=round, chamfer=chamfer)


def intersect(*fields: Field, round: float = 0.0, chamfer: float = 0.0) -> Field:
    return Intersection(fields, round=round, chamfer=chamfer)


def subtract(base: Field, *tools: Field, round: float = 0.0, chamfer: float = 0.0) -> Field:
    """``base`` with every tool removed; ``round`` fillets the cut edges."""
    return Subtraction(base, *tools, round=round, chamfer=chamfer)


# --------------------------------------------------------------------------- #
# Transforms
# --------------------------------------------------------------------------- #


class _Unary(Field):
    def __init__(self, child: Field, **kw) -> None:
        super().__init__(**kw)
        self.child = child

    def children(self):
        return (self.child,)

    def _replace_children(self, children):
        (self.child,) = children


def _rotation_matrix(angle_deg: float, axis: Sequence[float]) -> np.ndarray:
    a = np.asarray(axis, float)
    a = a / max(np.linalg.norm(a), _EPS)
    t = math.radians(angle_deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = a
    return np.array(
        [
            [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
            [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
            [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
        ]
    )


class Translate(_Unary):
    kind = "translate"

    def __init__(self, child: Field, offset: Sequence[float], **kw) -> None:
        super().__init__(child, **kw)
        # Stored as ``shift``, not ``offset``: an instance attribute named ``offset``
        # would shadow ``Field.offset`` and make ``box().translate(...).offset(r)`` fail.
        self.shift = _vec(offset)

    def _eval(self, p, ids):
        return self.child._eval(p - np.asarray(self.shift), ids)

    def _bounds(self):
        b = self.child.bounds
        o = self.shift
        return Bounds(tuple(a + t for a, t in zip(b.min, o)), tuple(a + t for a, t in zip(b.max, o)))  # type: ignore[arg-type]

    def _params(self):
        return {"child": self.child.to_dict(), "offset": list(self.shift)}


class Rotate(_Unary):
    kind = "rotate"

    def __init__(self, child: Field, angle_deg: float, axis: Sequence[float] = (0.0, 0.0, 1.0), **kw) -> None:
        super().__init__(child, **kw)
        self.angle_deg, self.axis = float(angle_deg), _vec(axis)
        self._matrix = _rotation_matrix(self.angle_deg, self.axis)

    def _eval(self, p, ids):
        return self.child._eval(p @ self._matrix, ids)  # p @ R == R^T applied to each row: the inverse rotation

    def _bounds(self):
        return Bounds.of_points(self.child.bounds.corners() @ self._matrix.T)

    def _params(self):
        return {"child": self.child.to_dict(), "angle_deg": self.angle_deg, "axis": list(self.axis)}


class Scale(_Unary):
    kind = "scale"

    def __init__(self, child: Field, factor: float, **kw) -> None:
        super().__init__(child, **kw)
        if factor <= 0:
            raise ValueError("scale factor must be positive")
        self.factor = float(factor)

    def _eval(self, p, ids):
        d, owner = self.child._eval(p / self.factor, ids)
        return d * self.factor, owner

    def _bounds(self):
        b = self.child.bounds
        f = self.factor
        return Bounds(tuple(a * f for a in b.min), tuple(a * f for a in b.max))  # type: ignore[arg-type]

    def _params(self):
        return {"child": self.child.to_dict(), "factor": self.factor}


class Mirror(_Unary):
    kind = "mirror"

    def __init__(self, child: Field, axis: str = "x", **kw) -> None:
        super().__init__(child, **kw)
        if axis not in ("x", "y", "z"):
            raise ValueError("mirror axis must be 'x', 'y' or 'z'")
        self.axis = axis

    def _eval(self, p, ids):
        q = p.copy()
        i = "xyz".index(self.axis)
        q[:, i] = np.abs(q[:, i])
        return self.child._eval(q, ids)

    def _bounds(self):
        b = self.child.bounds
        i = "xyz".index(self.axis)
        m = max(abs(b.min[i]), abs(b.max[i]))
        lo, hi = list(b.min), list(b.max)
        lo[i], hi[i] = -m, m
        return Bounds(tuple(lo), tuple(hi))  # type: ignore[arg-type]

    def _params(self):
        return {"child": self.child.to_dict(), "axis": self.axis}


class Repeat(_Unary):
    kind = "repeat"

    def __init__(self, child: Field, spacing: Sequence[float], count: Sequence[int], **kw) -> None:
        super().__init__(child, **kw)
        self.spacing, self.count = _vec(spacing), tuple(int(c) for c in count)
        if len(self.count) != 3 or min(self.count) < 1:
            raise ValueError("repeat count must be three positive integers")

    def _eval(self, p, ids):
        s = np.asarray(self.spacing)
        n = np.asarray(self.count, float)
        lim = (n - 1) / 2
        with np.errstate(divide="ignore", invalid="ignore"):
            cell = np.where(s > 0, np.clip(np.round(p / np.where(s > 0, s, 1.0)), -lim, lim), 0.0)
        return self.child._eval(p - cell * s, ids)

    def _bounds(self):
        b = self.child.bounds
        ext = tuple((c - 1) / 2 * s for c, s in zip(self.count, self.spacing))
        return Bounds(tuple(a - e for a, e in zip(b.min, ext)), tuple(a + e for a, e in zip(b.max, ext)))  # type: ignore[arg-type]

    def _params(self):
        return {"child": self.child.to_dict(), "spacing": list(self.spacing), "count": list(self.count)}


class Elongate(_Unary):
    kind = "elongate"

    def __init__(self, child: Field, lengths: Sequence[float], **kw) -> None:
        super().__init__(child, **kw)
        self.lengths = _vec(lengths)

    def _eval(self, p, ids):
        h = np.asarray(self.lengths) / 2
        q = p - np.clip(p, -h, h)
        return self.child._eval(q, ids)

    def _bounds(self):
        return self.child.bounds.pad(0).__class__(
            tuple(a - l / 2 for a, l in zip(self.child.bounds.min, self.lengths)),  # type: ignore[arg-type]
            tuple(a + l / 2 for a, l in zip(self.child.bounds.max, self.lengths)),  # type: ignore[arg-type]
        )

    def _params(self):
        return {"child": self.child.to_dict(), "lengths": list(self.lengths)}


# --------------------------------------------------------------------------- #
# Modifiers
# --------------------------------------------------------------------------- #


class Offset(_Unary):
    kind = "offset"

    def __init__(self, child: Field, r: float, **kw) -> None:
        super().__init__(child, **kw)
        self.r = float(r)

    def _eval(self, p, ids):
        d, owner = self.child._eval(p, ids)
        return d - self.r, owner

    def _bounds(self):
        return self.child.bounds.pad(max(self.r, 0.0))

    def _params(self):
        return {"child": self.child.to_dict(), "r": self.r}


class Shell(_Unary):
    kind = "shell"

    def __init__(self, child: Field, thickness: float, **kw) -> None:
        super().__init__(child, **kw)
        if thickness <= 0:
            raise ValueError("shell thickness must be positive")
        self.thickness = float(thickness)

    def _eval(self, p, ids):
        d, owner = self.child._eval(p, ids)
        return np.abs(d) - self.thickness / 2, owner

    def _bounds(self):
        return self.child.bounds.pad(self.thickness / 2)

    def _params(self):
        return {"child": self.child.to_dict(), "thickness": self.thickness}


# --------------------------------------------------------------------------- #
# Deserialization
# --------------------------------------------------------------------------- #

_LEAVES: dict[str, type[Field]] = {c.kind: c for c in (Sphere, Box, Cylinder, Capsule, Cone, Torus, HalfSpace)}


def from_dict(d: dict, *, base_dir: str | os.PathLike | None = None) -> Field:
    """Rebuild a tree from ``Field.to_dict``. A ``custom`` node cannot come back.

    base_dir: where a ``brep`` node's relative ``source`` STEP is looked up (the tape's folder).
    """
    kind = d.get("kind")
    label, site = d.get("label"), d.get("site")
    kw = {"label": label, "site": site}
    if kind == "brep":
        source = d.get("source")
        if not source:
            raise ValueError("a brep leaf with no source STEP cannot be rebuilt from a tape")
        path = source if os.path.isabs(source) or base_dir is None else os.path.join(os.fspath(base_dir), source)
        if not os.path.exists(path):
            raise ValueError(f"the tape's brep leaf reads {source}, which is not beside it ({path})")
        from cadgen import build123d as bd

        return Brep(bd.import_step(path), source=source, **kw)
    child = lambda key: from_dict(d[key], base_dir=base_dir)  # noqa: E731
    if kind in _LEAVES:
        params = {k: v for k, v in d.items() if k not in ("kind", "label", "site")}
        return _LEAVES[kind](**params, **kw)
    if kind == "extrude":
        return Extrude(profile_from_dict(d["profile"]), d["height"], **kw)
    if kind == "revolve":
        return Revolve(profile_from_dict(d["profile"]), **kw)
    if kind == "custom":
        raise ValueError("a custom field is a Python function and cannot be rebuilt from a tape")
    if kind in ("union", "intersection"):
        ops = [from_dict(o, base_dir=base_dir) for o in d["operands"]]
        cls = Union if kind == "union" else Intersection
        return cls(ops, round=d.get("round", 0.0), chamfer=d.get("chamfer", 0.0), **kw)
    if kind == "subtraction":
        ops = [from_dict(o, base_dir=base_dir) for o in d["operands"]]
        return Subtraction(*ops, round=d.get("round", 0.0), chamfer=d.get("chamfer", 0.0), **kw)
    if kind == "translate":
        return Translate(child("child"), d["offset"], **kw)
    if kind == "rotate":
        return Rotate(child("child"), d["angle_deg"], d["axis"], **kw)
    if kind == "scale":
        return Scale(child("child"), d["factor"], **kw)
    if kind == "mirror":
        return Mirror(child("child"), d["axis"], **kw)
    if kind == "repeat":
        return Repeat(child("child"), d["spacing"], d["count"], **kw)
    if kind == "elongate":
        return Elongate(child("child"), d["lengths"], **kw)
    if kind == "offset":
        return Offset(child("child"), d["r"], **kw)
    if kind == "shell":
        return Shell(child("child"), d["thickness"], **kw)
    raise ValueError(f"unknown field kind {kind!r}")
