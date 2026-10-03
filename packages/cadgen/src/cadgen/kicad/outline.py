"""build123d 2D geometry as KiCad board graphics and polygons.

A board's outline, a zone's area and a keepout's area are build123d faces in
the XY plane, in millimetres, y up -- the contract ``@dxf`` drawings use. This
module reads them two ways:

- :func:`outline_segments`: every edge of every face as a line, an arc or a
  circle, exactly (a filleted corner stays an arc on ``Edge.Cuts``); other
  curves are sampled finely into lines;
- :func:`polygon_rings`: each face's outer boundary as a closed list of points,
  arcs sampled, which is what a KiCad zone polygon is.

Geometry off the XY plane is refused rather than flattened, as a drawing's is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

__all__ = ["OutlineError", "Segment", "outline_bounds", "outline_segments", "polygon_rings"]

_PLANE_TOLERANCE = 1e-6
# A sampled curve's chord stays within this of the true curve (millimetres).
_CHORD_TOLERANCE = 0.005


class OutlineError(ValueError):
    """A shape that cannot be a board outline or a zone area."""


@dataclass(frozen=True)
class Segment:
    """``kind`` is ``line`` (start, end), ``arc`` (start, mid, end) or ``circle`` (center, radius)."""

    kind: str
    points: tuple[tuple[float, float], ...]
    radius: float | None = None


def _round(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _xy(vector) -> tuple[float, float]:
    if abs(float(vector.Z)) > _PLANE_TOLERANCE:
        raise OutlineError(
            f"a board shape must lie in the XY plane (z = 0), but a point sits at z = {float(vector.Z):g}; "
            "move it with bd.Location((0, 0, -z)) * face"
        )
    return _round(vector.X), _round(vector.Y)


def _faces(shape: Any, *, what: str) -> list:
    faces_of = getattr(shape, "faces", None)
    if faces_of is None:
        raise OutlineError(f"{what} must be build123d 2D geometry (a face or sketch), got {type(shape).__name__}")
    faces = list(faces_of())
    if not faces:
        raise OutlineError(f"{what} has no faces: draw a closed 2D shape, for example bd.Rectangle(40, 30)")
    return faces


def _samples(edge) -> int:
    length = float(edge.length)
    if edge.geom_type.name == "CIRCLE" and getattr(edge, "radius", 0):
        radius = float(edge.radius)
        if radius > _CHORD_TOLERANCE:
            step = 2 * math.acos(max(-1.0, 1 - _CHORD_TOLERANCE / radius))
            return max(4, math.ceil((length / radius) / step))
    return max(4, math.ceil(length / 0.25))


def _edge_segments(edge) -> list[Segment]:
    kind = edge.geom_type.name
    if kind == "LINE":
        return [Segment("line", (_xy(edge.position_at(0)), _xy(edge.position_at(1))))]
    if kind == "CIRCLE":
        if edge.is_closed:
            return [Segment("circle", (_xy(edge.arc_center),), radius=_round(edge.radius))]
        return [Segment("arc", (_xy(edge.position_at(0)), _xy(edge.position_at(0.5)), _xy(edge.position_at(1))))]
    count = _samples(edge)
    points = [_xy(edge.position_at(index / count)) for index in range(count + 1)]
    return [Segment("line", (a, b)) for a, b in zip(points, points[1:]) if a != b]


def outline_segments(shape: Any, *, what: str = "outline") -> list[Segment]:
    """Every boundary edge of ``shape``'s faces: outer boundaries and their holes."""
    segments: list[Segment] = []
    for face in _faces(shape, what=what):
        for wire in (face.outer_wire(), *face.inner_wires()):
            for edge in wire.edges():
                segments.extend(_edge_segments(edge))
    return segments


def _ring(wire) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for edge in wire.edges():
        kind = edge.geom_type.name
        count = 1 if kind == "LINE" else _samples(edge)
        for index in range(count):
            point = _xy(edge.position_at(index / count))
            if not points or points[-1] != point:
                points.append(point)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points


def polygon_rings(shape: Any, *, what: str) -> list[list[tuple[float, float]]]:
    """Each face's outer boundary as points (a KiCad zone is one polygon per face)."""
    rings: list[list[tuple[float, float]]] = []
    for face in _faces(shape, what=what):
        if face.inner_wires():
            raise OutlineError(
                f"{what} has a hole; a KiCad zone cannot, so cover the hole with a keepout "
                "(board.keepout(shape=...)) instead"
            )
        ring = _ring(face.outer_wire())
        if len(ring) < 3:
            raise OutlineError(f"{what} is degenerate: its boundary has fewer than three points")
        rings.append(ring)
    return rings


def outline_bounds(shape: Any) -> tuple[float, float, float, float]:
    """``(min_x, min_y, max_x, max_y)`` of the faces, y up."""
    box = None
    for face in _faces(shape, what="outline"):
        face_box = face.bounding_box()
        box = face_box if box is None else box.add(face_box)
    return (_round(box.min.X), _round(box.min.Y), _round(box.max.X), _round(box.max.Y))
