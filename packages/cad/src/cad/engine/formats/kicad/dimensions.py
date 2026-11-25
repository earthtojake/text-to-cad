"""A board's dimensions as the lines KiCad draws for them (``pcb_dimension.cpp``'s ``updateGeometry``).

A ``(dimension ...)`` stores what it measures, not what it draws: its two points, its
height or leader, its style; KiCad builds the extension lines, the crossbar and the
arrows from those each time it draws one. :func:`dimension_shapes` builds them the same
way for the five kinds, and for a KiCad 5 dimension (``feature1``, ``feature2`` and
``crossbar``, which KiCad reads as an aligned one). The text is the dimension's
``gr_text`` as KiCad last wrote it, where it wrote it: the plot draws it as any text.

A crossbar or leader that would run through the text stops at the text's box, as KiCad
knocks it out; the box is the stroke font's, so it is close to KiCad's, not KiCad's.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.geometry import XY

__all__ = ["Dimension", "dimension_shapes"]

_ARROW_ANGLE = 27.5  # degrees each side of the line an arrowhead's barbs open
_INWARD_ARROW_RATIO = 2  # an inward arrow's tail, in arrowhead lengths
_ARROW_LENGTH = 1.27  # 50 mils: KiCad's default arrow length, mm
# The text's box: ``text_box(gr_text, grow_x, grow_y)`` is its four corners, grown by ``grow_x`` along
# the text and ``grow_y`` across it (negative shrinks), turned with the text; its width along the
# text; its centre.
TextBox = Callable[[list, float, float], tuple[list[XY], float, XY]]


class Dimension:
    """What KiCad draws for one dimension: its segments, circles, line width and text."""

    def __init__(self, layer: str | None, width: float, segments: list[tuple[XY, XY]], circles: list[tuple[XY, float]],
                 text: list | None):
        self.layer = layer
        self.width = width
        self.segments = segments
        self.circles = circles
        self.text = text  # the dimension's gr_text node, or None


def _sub(a: XY, b: XY) -> XY:
    return a[0] - b[0], a[1] - b[1]


def _add(a: XY, b: XY) -> XY:
    return a[0] + b[0], a[1] + b[1]


def _resize(vector: XY, length: float) -> XY:
    """KiCad's ``VECTOR2::Resize``: the vector's direction, ``length`` long (negative turns it round)."""
    norm = math.hypot(*vector)
    if norm == 0:
        return 0.0, 0.0
    return vector[0] * length / norm, vector[1] * length / norm


def _turn(vector: XY, degrees: float) -> XY:
    """KiCad's ``RotatePoint``: counter-clockwise on screen in its y-down frame."""
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return vector[0] * cos + vector[1] * sin, vector[1] * cos - vector[0] * sin


def _angle(vector: XY) -> float:
    """KiCad's ``EDA_ANGLE( vector )``: atan2 in its y-down frame, degrees."""
    return math.degrees(math.atan2(vector[1], vector[0])) if vector != (0, 0) else 0.0


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _arrow(segments: list, at: XY, angle: float, length: float, tail: float = 0.0) -> None:
    """``drawAnArrow``: two barbs from ``at`` along ``angle``, and a tail first when it has one."""
    if tail:
        segments.append((at, _add(at, _turn((tail, 0.0), -angle))))
    segments.append((at, _add(at, _turn((length, 0.0), -angle + _ARROW_ANGLE))))
    segments.append((at, _add(at, _turn((length, 0.0), -angle - _ARROW_ANGLE))))


def _inside(point: XY, polygon: Sequence[XY]) -> bool:
    found = False
    for index in range(len(polygon)):
        (x1, y1), (x2, y2) = polygon[index], polygon[(index + 1) % len(polygon)]
        if (y1 > point[1]) != (y2 > point[1]) and point[0] < x1 + (point[1] - y1) * (x2 - x1) / (y2 - y1):
            found = not found
    return found


def _crossing(a: XY, b: XY, c: XY, d: XY) -> XY | None:
    """Where segment ``a``-``b`` meets segment ``c``-``d``, if it does."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-12:
        return None
    t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / denominator
    u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / denominator
    if 0 <= t <= 1 and 0 <= u <= 1:
        return a[0] + t * rx, a[1] + t * ry
    return None


def _hit(polygon: Sequence[XY], a: XY, b: XY) -> XY | None:
    """``segPolyIntersection``: walking from ``a`` towards ``b``, the first point on the polygon."""
    if _inside(a, polygon):
        return None
    end, best = b, None
    for index in range(len(polygon)):
        point = _crossing(a, b, polygon[index], polygon[(index + 1) % len(polygon)])
        if point is not None and math.dist(point, a) < math.dist(end, a):
            end, best = point, point
    return best


def _knocked_out(polygon: Sequence[XY], a: XY, b: XY) -> list[tuple[XY, XY]]:
    """``CollectKnockedOutSegments``: the segment, with the part inside the polygon taken out."""
    first, last = _hit(polygon, a, b), _hit(polygon, b, a)
    out = []
    if first is not None:
        out.append((a, first))
    if last is not None and not (first is not None and math.dist(last, a) < 1e-9 and math.dist(first, b) < 1e-9):
        out.append((last, b))
    if not _inside(a, polygon) and not _inside(b, polygon) and first is None and last is None:
        out.append((a, b))
    return out


def _points(node: list) -> list[XY]:
    pts = sexpr.find(node, "pts")
    return [sexpr.pair(point) for point in sexpr.find_all(pts, "xy")] if pts is not None else []


def _style(node: list) -> dict:
    style = sexpr.find(node, "style")
    values = {"thickness": 0.2, "arrow_length": _ARROW_LENGTH, "extension_offset": 0.0, "arrow_direction": "outward",
              "extension_height": _ARROW_LENGTH * math.sin(math.radians(_ARROW_ANGLE)), "text_frame": 0}
    if style is not None:
        for key in ("thickness", "arrow_length", "extension_offset", "extension_height", "text_frame"):
            if sexpr.value(style, key) is not None:
                values[key] = sexpr.number(sexpr.value(style, key), values[key])
        if sexpr.value(style, "arrow_direction") is not None:
            values["arrow_direction"] = str(sexpr.value(style, "arrow_direction"))
    return values


def dimension_shapes(node: list, text_box: TextBox) -> Dimension | None:
    """What KiCad draws for the ``(dimension ...)`` ``node``, in its own (the board's) frame.

    ``text_box`` answers the dimension's text box (:data:`TextBox`), for the crossbar and the
    leader to stop at, grown as each kind grows it (KiCad: by half a glyph's width along the
    text, and by the pen across it).
    """
    layer = sexpr.value(node, "layer")
    layer = str(layer) if layer is not None else None
    gr_text = sexpr.find(node, "gr_text")
    legacy = sexpr.find(node, "width") is not None and sexpr.find(node, "type") is None
    kind = "aligned" if legacy else str(sexpr.value(node, "type") or "aligned")
    style = _style(node)
    width = sexpr.number(sexpr.value(node, "width"), style["thickness"]) if legacy else style["thickness"]
    arrow, offset, extension_height = style["arrow_length"], style["extension_offset"], style["extension_height"]
    inward = style["arrow_direction"] == "inward"
    segments: list[tuple[XY, XY]] = []
    circles: list[tuple[XY, float]] = []
    if legacy:
        # KiCad 5 stored what it drew; KiCad reads it as an aligned dimension: feature1's and feature2's
        # first points, and a height from the crossbar (read backwards, as KiCad reads it).
        first, second, crossbar = (_points(sexpr.find(node, key) or []) for key in ("feature1", "feature2", "crossbar"))
        if not first or not second:
            return None
        start, end = first[0], second[0]
        height = 0.0
        if len(crossbar) >= 2:
            bar_start, bar_end = crossbar[1], crossbar[0]
            along, across = _sub(bar_start, start), _sub(bar_end, bar_start)
            height = math.hypot(*along) * (-1 if along[0] * across[1] - along[1] * across[0] > 0 else 1)
    else:
        points = _points(node)
        if len(points) < 2:
            return None
        start, end = points[0], points[1]
        height = sexpr.number(sexpr.value(node, "height"), 0.0)
    glyph = _glyph_width(gr_text)
    pen = _pen(gr_text)

    def box(grow_y: float) -> list[XY] | None:
        return text_box(gr_text, glyph / 2, grow_y)[0] if gr_text is not None else None

    if kind in ("aligned", "orthogonal"):
        if kind == "orthogonal":
            horizontal = int(sexpr.number(sexpr.value(node, "orientation"), 0)) == 0
            extension = (0.0, height) if horizontal else (height, 0.0)
        else:
            dimension = _sub(end, start)
            extension = (-dimension[1], dimension[0]) if height > 0 else (dimension[1], -dimension[0])
        reach = abs(height) - offset + extension_height
        foot = _add(start, _resize(extension, offset))
        segments.append((foot, _add(foot, _resize(extension, reach))))
        bar_start = _add(start, _resize(extension, _sign(height) * height))
        if kind == "orthogonal":
            bar_end = (end[0], bar_start[1]) if horizontal else (bar_start[0], end[1])
            back = (0.0, end[1] - bar_end[1]) if horizontal else (end[0] - bar_end[0], 0.0)
            foot = _sub(bar_end, _resize(back, extension_height))
            segments.append((foot, _add(foot, _resize(back, math.hypot(*back) - offset + extension_height))))
        else:
            bar_end = _add(end, _resize(extension, _sign(height) * height))
            foot = _add(end, _resize(extension, offset))
            segments.append((foot, _add(foot, _resize(extension, reach))))
        polygon = box(-pen if kind == "aligned" else pen)
        segments.extend(_knocked_out(polygon, bar_start, bar_end) if polygon else [(bar_start, bar_end)])
        along = _angle(_sub(bar_end, bar_start)) if kind == "orthogonal" else _angle(_sub(end, start))
        if inward:
            _arrow(segments, bar_start, along + 180, arrow, arrow * _INWARD_ARROW_RATIO)
            _arrow(segments, bar_end, along, arrow, arrow * _INWARD_ARROW_RATIO)
        else:
            _arrow(segments, bar_start, along, arrow)
            _arrow(segments, bar_end, along + 180, arrow)
    elif kind == "center":
        arm = _sub(end, start)
        segments.append((_sub(start, arm), _add(start, arm)))
        arm = _turn(arm, -90)
        segments.append((_sub(start, arm), _add(start, arm)))
    elif kind == "radial":
        arm = (0.0, arrow)
        segments.append((_sub(start, arm), _add(start, arm)))
        arm = _turn(arm, -90)
        segments.append((_sub(start, arm), _add(start, arm)))
        radial = _resize(_sub(end, start), sexpr.number(sexpr.value(node, "leader_length"), arrow * 3))
        knee = _add(end, radial)
        at = sexpr.pair(sexpr.find(gr_text, "at")) if gr_text is not None else None
        polygon = box(pen)
        for a, b in ((end, knee), (knee, at)) if at else ((end, knee),):
            segments.extend(_knocked_out(polygon, a, b) if polygon else [(a, b)])
        _arrow(segments, end, _angle(radial), arrow)
    elif kind == "leader":
        line = _sub(end, start)
        begin = _add(start, _resize(line, offset))
        at = sexpr.pair(sexpr.find(gr_text, "at")) if gr_text is not None else None
        frame = int(style["text_frame"])
        polygon = box(pen * 2)
        circle = None
        if frame == 2 and gr_text is not None:
            _corners, across, centre = text_box(gr_text, glyph / 2, pen * 2)
            circle = (centre, across / 2 - pen / 2)
        stop = _hit(polygon, start, end) if polygon and frame != 2 else None
        if circle is not None:
            stop = _circle_hit(circle, start, end)
        stop = stop or end
        segments.append((begin, stop))
        _arrow(segments, begin, _angle(line), arrow)
        if frame == 1 and polygon:
            segments.extend((polygon[index], polygon[(index + 1) % 4]) for index in range(4))
        elif circle is not None:
            circles.append(circle)
        if at and stop == end:
            text_stop = (_circle_hit(circle, end, at) if circle is not None else _hit(polygon, end, at) if polygon else None)
            if text_stop is not None:
                segments.append((end, text_stop))
    else:
        return None
    return Dimension(layer, width, segments, circles, gr_text)


def _glyph_width(gr_text: list | None) -> float:
    """The width of one glyph of the text, KiCad's ``GetTextWidth``: its font's size across."""
    font = sexpr.find(sexpr.find(gr_text, "effects") or [], "font") if gr_text is not None else None
    size = sexpr.pair(sexpr.find(font, "size"), (1.0, 1.0)) if font is not None else (1.0, 1.0)
    return abs(size[1])


def _pen(gr_text: list | None) -> float:
    """The text's stroke, KiCad's ``GetEffectiveTextPenWidth``: its thickness, else a size's eighth."""
    font = sexpr.find(sexpr.find(gr_text, "effects") or [], "font") if gr_text is not None else None
    thickness = sexpr.number(sexpr.value(font, "thickness"), 0.0) if font is not None else 0.0
    size = sexpr.pair(sexpr.find(font, "size"), (1.0, 1.0)) if font is not None else (1.0, 1.0)
    return thickness or min(abs(size[0]), abs(size[1])) / 8


def _circle_hit(circle: tuple[XY, float], a: XY, b: XY) -> XY | None:
    """``segCircleIntersection``: walking from ``a`` towards ``b``, the first point on the circle."""
    (cx, cy), radius = circle
    if math.dist(a, (cx, cy)) <= radius:
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    fx, fy = a[0] - cx, a[1] - cy
    qa, qb, qc = dx * dx + dy * dy, 2 * (fx * dx + fy * dy), fx * fx + fy * fy - radius * radius
    disc = qb * qb - 4 * qa * qc
    if qa == 0 or disc < 0:
        return None
    hits = [t for t in ((-qb - math.sqrt(disc)) / (2 * qa), (-qb + math.sqrt(disc)) / (2 * qa)) if 0 <= t <= 1]
    return (a[0] + min(hits) * dx, a[1] + min(hits) * dy) if hits else None
