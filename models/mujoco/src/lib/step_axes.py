"""Joint axes and travel read from a maker's STEP: what a careful engineer measures on the CAD.

A revolute joint is where two parts share a bearing: coaxial cylindrical faces, a bore on one and a
journal or a bore on the other. ``cylinder_lines`` lists a part's cylindrical faces by the line they
turn about (direction, a point, radii, area); ``shared_axis`` finds the line two parts share, the one
with the most bearing area, nearest a hint (the occurrence frame the maker placed at the joint, a
cross-check rather than the source). A slide is a direction in which a part translates against its
parent without its interference growing: ``free_directions`` ranks candidate directions by how much the
overlap changes over a small move, and ``free_travel`` sweeps along one until it grows (a stop).

Directions are unsigned here: which way is positive is the joint's convention, set by the model.
Everything is in the STEP's world frame, millimetres. Plain build123d; no engine call.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import build123d as bd


@dataclass
class Line:
    """A line some cylindrical faces turn about: a unit direction (sign canonical: its largest
    component positive), its point closest to the origin, and the faces' radii and total area."""

    direction: tuple[float, float, float]
    point: tuple[float, float, float]
    radii: list[float] = field(default_factory=list)
    area: float = 0.0

    def axis(self) -> bd.Axis:
        return bd.Axis(self.point, self.direction)

    def distance_to(self, at: tuple[float, float, float]) -> float:
        """The distance from a point to this line (mm)."""
        d = [at[i] - self.point[i] for i in range(3)]
        along = sum(d[i] * self.direction[i] for i in range(3))
        return math.sqrt(max(0.0, sum(c * c for c in d) - along * along))

    def offset_from(self, other: "Line") -> float:
        """How far this (parallel) line stands from another (mm)."""
        return other.distance_to(self.point)


def _canonical(direction: bd.Vector, position: bd.Vector) -> tuple[tuple, tuple]:
    d = [direction.X, direction.Y, direction.Z]
    norm = math.sqrt(sum(c * c for c in d))
    # Snap the kernel's noise (1e-17) to zero: build123d picks a Plane's default X from the exact
    # components, so (1e-17, 1, 0) and (0, 1, 0) get X directions 90 degrees apart, and a revolute joint
    # whose RigidJoint plane and axis frame disagree that way turns its child 90 degrees at angle 0.
    d = [0.0 if abs(c / norm) < 1e-9 else c / norm for c in d]
    big = max(range(3), key=lambda i: abs(d[i]))
    if d[big] < 0:
        d = [-c for c in d]
    p = [position.X, position.Y, position.Z]
    along = sum(p[i] * d[i] for i in range(3))
    return tuple(d), tuple(p[i] - along * d[i] for i in range(3))


def _parallel(a: tuple, b: tuple, tolerance: float = 1e-3) -> bool:
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    return math.sqrt(sum(c * c for c in cross)) < tolerance


def cylinder_lines(shape: bd.Shape, tolerance: float = 0.05) -> list[Line]:
    """Every line ``shape``'s cylindrical faces turn about, in world coordinates, the faces about one
    line (within ``tolerance`` mm) gathered; most area first."""
    lines: list[Line] = []
    for face in shape.faces():
        if face.geom_type != bd.GeomType.CYLINDER:
            continue
        axis = face.axis_of_rotation
        direction, point = _canonical(axis.direction, axis.position)
        for line in lines:
            if _parallel(line.direction, direction) and line.distance_to(point) < tolerance:
                break
        else:
            line = Line(direction, point)
            lines.append(line)
        line.radii.append(round(face.radius, 3))
        line.area += face.area
    return sorted(lines, key=lambda line: -line.area)


@dataclass
class Shared:
    """The line two parts share: each part's own line (they may stand a little apart where the CAD's
    mate is not exact), and the bearing area each has about it."""

    parent: Line
    child: Line

    @property
    def offset(self) -> float:
        return self.child.offset_from(self.parent)


def shared_axis(parent: bd.Shape, child: bd.Shape, near: tuple[float, float, float] | None = None,
                tolerance: float = 1.0, min_area: float = 50.0) -> Shared:
    """The line ``parent`` and ``child`` both have cylindrical faces about (parallel, within
    ``tolerance`` mm), each with at least ``min_area`` mm^2 of them: the one with the most area
    together, or, given ``near``, the one passing nearest that point among those within 2 mm of it
    (falling back to the most area). Raises when they share none."""
    found: list[Shared] = []
    for a in cylinder_lines(parent):
        if a.area < min_area:
            continue
        for b in cylinder_lines(child):
            if b.area >= min_area and _parallel(a.direction, b.direction) and b.offset_from(a) < tolerance:
                found.append(Shared(a, b))
    if not found:
        raise ValueError("the two parts share no cylinder axis: no bearing between them")
    if near is not None:
        close = [s for s in found if s.parent.distance_to(near) < 2.0]
        if close:
            return min(close, key=lambda s: s.parent.distance_to(near))
    return max(found, key=lambda s: s.parent.area + s.child.area)


def overlap(a: bd.Shape, b: bd.Shape) -> float:
    """The volume two shapes share (mm^3)."""
    common = a & b
    return sum(solid.volume for solid in common.solids()) if common else 0.0


def free_directions(moving: bd.Shape, fixed: bd.Shape, candidates: list[tuple[float, float, float]],
                    step: float = 2.0) -> list[tuple[tuple[float, float, float], float]]:
    """Each candidate direction with how much ``moving``'s interference with ``fixed`` changes over a
    move of ``step`` mm either way along it (mm^3): a slide's direction changes it least. Dummy CAD
    often interferes as built (a rack drawn inside its housing), so it is the change that tells."""
    rest = overlap(moving, fixed)
    ranked = []
    for direction in candidates:
        v = bd.Vector(*direction).normalized() * step
        change = sum(abs(overlap(moving.moved(bd.Location(v * sign)), fixed) - rest) for sign in (1, -1))
        ranked.append((tuple(direction), change))
    return sorted(ranked, key=lambda item: item[1])


def free_travel(moving: list[bd.Shape], fixed: list[bd.Shape], direction: tuple[float, float, float],
                limit: float, step: float = 1.0, rate: float = 20.0, resolution: float = 0.1) -> float:
    """How far ``moving`` (a link's parts) translates along ``direction`` from where it stands before
    it runs into ``fixed`` (mm): the first move where the interference grows faster than ``rate``
    mm^3 per mm (a stop: a rack sliding inside a dummy housing keeps its interference steady), found
    by stepping ``step`` mm up to ``limit`` and bisecting to ``resolution``; ``limit`` if never."""
    unit = bd.Vector(*direction).normalized()

    def interference(at: float) -> float:
        where = bd.Location(unit * at)
        return sum(overlap(part.moved(where), other) for part in moving for other in fixed)

    before, at = interference(0.0), 0.0
    while at + step <= limit:
        now = interference(at + step)
        if now - before > rate * step:
            low, high, low_value = at, at + step, before
            while high - low > resolution:
                mid = (low + high) / 2
                value = interference(mid)
                if value - low_value > rate * (mid - low):
                    high = mid
                else:
                    low, low_value = mid, value
            return low
        before, at = now, at + step
    return limit
