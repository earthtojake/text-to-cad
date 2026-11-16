"""Points and polygons the KiCad readers share.

A point is ``(x, y)`` in millimetres, in whatever frame the caller works in;
nothing here changes frames. Distances are between
copper as KiCad's connectivity sees it: a pad is its polygon, a track a segment
of a width, a via a disc, a pour its filled polygons, and two pieces touch when
the distance between them is zero.

Every result here is the same bits on every platform. The angles are this module's own
(:func:`cos_sin`, :func:`cos_sin_degrees`, :func:`atan2`), written with IEEE-754's + - * / and
sqrt alone, which every platform rounds the same way, never the C library's sin, cos, atan2 or
acos, which differ in the last bit between glibc, Apple's libm and the MSVC runtime. Lengths are
CPython's ``math.hypot`` and ``math.dist``, its own code on every platform. So a reader that
decides something from these points (the router's clearance fields above all) decides it alike
on Linux, macOS and Windows.
"""

from __future__ import annotations

import functools
import math
from typing import Iterable, Iterator, Sequence

__all__ = [
    "CHORD_TOLERANCE",
    "XY",
    "arc_points",
    "area",
    "atan2",
    "bezier_points",
    "box",
    "chords",
    "cos_sin",
    "cos_sin_degrees",
    "disc",
    "format_xy",
    "hull",
    "inside",
    "pen_outlines",
    "polygon_distance",
    "polygons_overlap",
    "polyline_distance",
    "rotate",
    "segment_distance",
    "segments_distance",
    "union",
]

XY = tuple[float, float]


# --- angles: IEEE arithmetic alone ------------------------------------------------------
#
# The C library's sin, cos, atan2 and acos are not correctly rounded, and glibc, Apple's libm and the MSVC
# runtime round some arguments differently in the last bit. These are written with + - * / and sqrt, which
# IEEE-754 rounds correctly (so alike everywhere), and Python's round and math.fmod, which are exact. Each is
# within a unit in the last place of the true value (measured against mpmath when they were written), and within
# two of the C library's (the router's determinism test holds them to it).

# Taylor's coefficients, each the double nearest (-1)^k / n! (an int over an int: correctly rounded).
_S1, _S2, _S3, _S4, _S5, _S6, _S7, _S8, _S9 = ((-1) ** k / math.factorial(2 * k + 1) for k in range(1, 10))
_C1, _C2, _C3, _C4, _C5, _C6, _C7, _C8, _C9 = ((-1) ** k / math.factorial(2 * k) for k in range(1, 10))
# pi/2 in two parts, fdlibm's (e_rem_pio2.c: pio2_1, pio2_1t): the first 33 bits, so n * _PIO2_HI is exact for
# any |n| < 2^20, and the rest.
_PIO2_HI = float.fromhex("0x1.921fb544p+0")
_PIO2_LO = 6.07710050650619224932e-11
_TWO_OVER_PI = 2 / math.pi
_MAX_RADIANS = 2.0 ** 19 * _PIO2_HI
_DEGREE = math.pi / 180.0  # what math.radians multiplies by


def _kernel(x: float) -> XY:
    """cos and sin of ``x``, |x| <= pi/4 (a little over is as good): the Taylor series to x^19, whose next term
    is below 1e-19 there."""
    z = x * x
    s = _S1 + z * (_S2 + z * (_S3 + z * (_S4 + z * (_S5 + z * (_S6 + z * (_S7 + z * (_S8 + z * _S9)))))))
    c = _C1 + z * (_C2 + z * (_C3 + z * (_C4 + z * (_C5 + z * (_C6 + z * (_C7 + z * (_C8 + z * _C9)))))))
    return 1.0 + z * c, x + x * (z * s)


def _quadrant(n: int, c: float, s: float) -> XY:
    """cos and sin of ``t + n * 90 degrees``, given those of ``t``; ``0.0 - v`` so a zero is never -0.0."""
    n %= 4
    if n == 0:
        return c, s
    if n == 1:
        return 0.0 - s, c
    if n == 2:
        return 0.0 - c, 0.0 - s
    return s, 0.0 - c


def cos_sin(radians: float) -> XY:
    """``(cos(radians), sin(radians))``, the same bits on every platform. Reduced by the nearest multiple of pi/2
    (fdlibm's two-part pi/2, so exact enough), |radians| under 8e5 (an angle this module makes is a few turns at
    most); a larger one is a ``ValueError``."""
    if not abs(radians) < _MAX_RADIANS:
        raise ValueError(f"cos_sin takes an angle under {_MAX_RADIANS:.0f} radians, not {radians!r}")
    n = round(radians * _TWO_OVER_PI)
    t = (radians - n * _PIO2_HI) - n * _PIO2_LO
    return _quadrant(n, *_kernel(t))


@functools.lru_cache(maxsize=4096)
def cos_sin_degrees(degrees: float) -> XY:
    """``(cos, sin)`` of an angle in degrees, the same bits on every platform; a multiple of 90 degrees exactly
    (0, 1, -1), as KiCad's own rotation gives it. Reduced exactly: ``math.fmod`` by 360, then the nearest
    multiple of 90 taken off (exact: the two are within a factor of 2 of each other, Sterbenz)."""
    if not math.isfinite(degrees):
        raise ValueError(f"cos_sin_degrees takes a finite angle, not {degrees!r}")
    turn = math.fmod(degrees, 360.0)
    n = round(turn / 90.0)
    t = turn - n * 90.0
    if t == 0.0:
        return _quadrant(n, 1.0, 0.0)
    return _quadrant(n, *_kernel(t * _DEGREE))


# fdlibm's arctangent (s_atan.c): atan(x) for x >= 0 is atan(c) + atan((x - c) / (1 + x c)) about the nearest of
# c = 1/2, 1, 3/2, infinity, then an odd polynomial of degree 23.
_ATAN_HI = (4.63647609000806093515e-01, 7.85398163397448278999e-01, 9.82793723247329054082e-01,
            1.57079632679489655800e+00)
_ATAN_LO = (2.26987774529616870924e-17, 3.06161699786838301793e-17, 1.39033110312309984516e-17,
            6.12323399573676603587e-17)
_AT = (3.33333333333329318027e-01, -1.99999999998764832476e-01, 1.42857142725034663711e-01,
       -1.11111104054623557880e-01, 9.09088713343650656196e-02, -7.69187620504482999495e-02,
       6.66107313738753120669e-02, -5.83357013379057348645e-02, 4.97687799461593236017e-02,
       -3.65315727442169155270e-02, 1.62858201153657823623e-02)
_PI_LO = 1.2246467991473531772e-16  # pi - math.pi


def _atan(x: float) -> float:
    """atan(x) for x >= 0, fdlibm's (s_atan.c)."""
    if x < 0.4375:
        if x < 2.0 ** -27:
            return x
        part = -1
    elif x < 0.6875:
        part, x = 0, (2.0 * x - 1.0) / (2.0 + x)
    elif x < 1.1875:
        part, x = 1, (x - 1.0) / (x + 1.0)
    elif x < 2.4375:
        part, x = 2, (x - 1.5) / (1.0 + 1.5 * x)
    else:
        part, x = 3, -1.0 / x
    z = x * x
    w = z * z
    s1 = z * (_AT[0] + w * (_AT[2] + w * (_AT[4] + w * (_AT[6] + w * (_AT[8] + w * _AT[10])))))
    s2 = w * (_AT[1] + w * (_AT[3] + w * (_AT[5] + w * (_AT[7] + w * _AT[9]))))
    if part < 0:
        return x - x * (s1 + s2)
    return _ATAN_HI[part] - ((x * (s1 + s2) - _ATAN_LO[part]) - x)


def atan2(y: float, x: float) -> float:
    """The angle of ``(x, y)``, in (-pi, pi], as ``math.atan2`` answers it, the same bits on every platform
    (fdlibm's e_atan2.c, finite arguments): the axes exactly (0, +-pi/2, pi)."""
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"atan2 takes finite numbers, not {y!r}, {x!r}")
    if y == 0.0:
        return y if math.copysign(1.0, x) > 0 else math.copysign(math.pi, y)
    if x == 0.0:
        return math.copysign(math.pi / 2, y)
    ratio = abs(y / x)
    if ratio > 2.0 ** 60:
        z = math.pi / 2 + 0.5 * _PI_LO
    elif x < 0 and ratio < 2.0 ** -60:
        z = 0.0
    else:
        z = _atan(ratio)
    if x > 0:
        return z if y > 0 else -z
    return math.pi - (z - _PI_LO) if y > 0 else (z - _PI_LO) - math.pi


def _acos(x: float) -> float:
    """acos(x) for 0 <= x <= 1: the angle of ``(x, sqrt(1 - x^2))``, 1 - x^2 as (1 - x)(1 + x)."""
    return atan2(math.sqrt((1.0 - x) * (1.0 + x)), x)


_ARC_STEP = math.radians(10)
#: How far a board graphic's chord may stray from its arc or circle, millimetres (an Edge.Cuts outline, a
#: courtyard, a fabrication circle): a fit or an offset made from the points is off by less than this.
CHORD_TOLERANCE = 0.005


def chords(radius: float, sweep: float, tolerance: float | None = None) -> int:
    """How many chords an arc of ``radius`` turning ``sweep`` radians is drawn with: one each 10 degrees at
    least, and with ``tolerance``, as many more as keep each chord within it of the arc (a 120 mm circle
    is 244 at :data:`CHORD_TOLERANCE`)."""
    steps = max(2, math.ceil(abs(sweep) / _ARC_STEP))
    if tolerance is not None and radius > tolerance:
        steps = max(steps, math.ceil(abs(sweep) / (2 * _acos(1 - tolerance / radius))))
    return steps


def format_xy(point: XY) -> str:
    return f"({point[0]:g}, {point[1]:g})"


def rotate(x: float, y: float, degrees: float) -> XY:
    """KiCad's rotation of a point in its y-down frame: counter-clockwise on screen."""
    if not degrees:
        return x, y
    cos, sin = cos_sin_degrees(degrees)
    return x * cos + y * sin, -x * sin + y * cos


def arc_points(start: XY, mid: XY, end: XY, tolerance: float | None = None) -> list[XY]:
    """Points along the circular arc from ``start`` through ``mid`` to ``end``: one each 10 degrees, or as
    :func:`chords` keeps them within ``tolerance`` of it."""
    (ax, ay), (bx, by), (cx, cy) = start, mid, end
    determinant = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(determinant) < 1e-12:
        return [start, end]
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / determinant
    oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / determinant
    radius = math.hypot(ax - ox, ay - oy)
    first = atan2(ay - oy, ax - ox)
    through = (atan2(by - oy, bx - ox) - first) % (2 * math.pi)
    sweep = (atan2(cy - oy, cx - ox) - first) % (2 * math.pi)
    if through > sweep:  # the mid point lies the other way round
        sweep -= 2 * math.pi
    steps = chords(radius, sweep, tolerance)
    points = []
    for step in range(steps):
        cos, sin = cos_sin(first + sweep * step / steps)
        points.append((ox + radius * cos, oy + radius * sin))
    return points + [end]


def bezier_points(points: Sequence[XY], segments: int = 16) -> list[XY]:
    """The cubic Bezier of four control points as ``segments`` + 1 points, both ends included."""
    if len(points) != 4:
        return list(points)
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    out = []
    for step in range(segments + 1):
        t = step / segments
        u = 1 - t
        out.append((
            u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
            u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3,
        ))
    return out


def area(polygon: Sequence[XY]) -> float:
    """The signed area: positive when the points run counter-clockwise (in a y-up frame)."""
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, [*polygon[1:], polygon[0]])) if polygon else 0.0


def inside(point: XY, polygon: Sequence[XY]) -> bool:
    """Even-odd: KiCad's fills are single outlines with their holes cut in by slits."""
    x, y = point
    found = False
    count = len(polygon)
    for index in range(count):
        (x1, y1), (x2, y2) = polygon[index], polygon[(index + 1) % count]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            found = not found
    return found


def hull(points: Iterable[XY]) -> list[XY]:
    """The convex hull, counter-clockwise (in a y-up frame), without repeated points."""
    unique = sorted(set(points))
    if len(unique) < 3:
        return unique

    def cross(o: XY, a: XY, b: XY) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[XY] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[XY] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def box(points: Iterable[XY]) -> list[XY]:
    """The corners of the box round ``points``; none for no points."""
    points = list(points)
    if not points:
        return []
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]


# --- distances -----------------------------------------------------------------------


def segment_distance(point: XY, a: XY, b: XY) -> float:
    """How far ``point`` is from the segment ``a``-``b``."""
    (px, py), (ax, ay), (bx, by) = point, a, b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def polyline_distance(point: XY, points: Sequence[XY]) -> float:
    """How far ``point`` is from the open polyline ``points``."""
    if len(points) == 1:
        return math.hypot(point[0] - points[0][0], point[1] - points[0][1])
    return min(segment_distance(point, a, b) for a, b in zip(points, points[1:]))


def polygon_distance(point: XY, polygon: Sequence[XY]) -> float:
    """0 inside ``polygon``, else the distance to its edge."""
    if len(polygon) >= 3 and inside(point, polygon):
        return 0.0
    if not polygon:
        return math.inf
    return polyline_distance(point, [*polygon, polygon[0]])


def _orientation(a: XY, b: XY, c: XY) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a: XY, b: XY, c: XY, d: XY) -> bool:
    """Whether the segments ``a``-``b`` and ``c``-``d`` meet (a shared point counts)."""
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and o1 != 0 and o2 != 0 and o3 != 0 and o4 != 0:
        return True
    # Collinear or touching: an end of one lies on the other.
    return any(
        _orientation(p, q, r) == 0 and min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
        for p, q, r in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))
    )


def segments_distance(a: XY, b: XY, c: XY, d: XY) -> float:
    """How far the segment ``a``-``b`` is from the segment ``c``-``d``: 0 when they meet."""
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(segment_distance(a, c, d), segment_distance(b, c, d), segment_distance(c, a, b), segment_distance(d, a, b))


def _bounds(points: Sequence[XY]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _edges_in(points: Sequence[XY], region: tuple[float, float, float, float]) -> list[tuple[XY, XY]]:
    """The polygon's edges whose bounding box reaches ``region``: only those can meet an edge inside it."""
    left, top, right, bottom = region
    return [(a, b) for a, b in zip(points, [*points[1:], points[0]])
            if min(a[0], b[0]) <= right and max(a[0], b[0]) >= left and min(a[1], b[1]) <= bottom and max(a[1], b[1]) >= top]


# Below this many edge pairs every pair is tested; above it the second polygon's edges are bucketed.
_PAIRS_DIRECT = 4096


def polygons_overlap(first: Sequence[XY], second: Sequence[XY]) -> bool:
    """Whether two polygons share any area or touch: a point of one inside the other, or two
    edges that meet.

    Only edges inside the region both polygons' boxes share can meet, and each is tested only against
    the other's edges in the same cells of a grid over that region: two pours of thousands of vertices
    that do not touch cost about their edge counts, not their product."""
    if len(first) < 3 or len(second) < 3:
        return False
    if inside(first[0], second) or inside(second[0], first):
        return True
    a_box, b_box = _bounds(first), _bounds(second)
    region = (max(a_box[0], b_box[0]), max(a_box[1], b_box[1]), min(a_box[2], b_box[2]), min(a_box[3], b_box[3]))
    if region[0] > region[2] or region[1] > region[3]:
        return False
    mine, theirs = _edges_in(first, region), _edges_in(second, region)
    if not mine or not theirs:
        return False
    if len(mine) * len(theirs) <= _PAIRS_DIRECT:
        return any(_segments_cross(a, b, c, d) for a, b in mine for c, d in theirs)
    across = max(1, math.isqrt(len(theirs)))
    left, top = region[0], region[1]
    width = max(region[2] - left, 1e-9) / across
    height = max(region[3] - top, 1e-9) / across

    def cells(a: XY, b: XY) -> Iterator[tuple[int, int]]:
        x0 = min(across - 1, max(0, int((min(a[0], b[0]) - left) / width)))
        x1 = min(across - 1, max(0, int((max(a[0], b[0]) - left) / width)))
        y0 = min(across - 1, max(0, int((min(a[1], b[1]) - top) / height)))
        y1 = min(across - 1, max(0, int((max(a[1], b[1]) - top) / height)))
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield x, y

    grid: dict[tuple[int, int], list[int]] = {}
    for index, (c, d) in enumerate(theirs):
        for cell in cells(c, d):
            grid.setdefault(cell, []).append(index)
    for a, b in mine:
        tested: set[int] = set()
        for cell in cells(a, b):
            for index in grid.get(cell, ()):
                if index not in tested:
                    tested.add(index)
                    c, d = theirs[index]
                    if _segments_cross(a, b, c, d):
                        return True
    return False


# --- union -----------------------------------------------------------------------------

# Points this close are one point (mm): what the union's edges are joined by.
_SNAP = 1e-6
# How far off an edge the union looks to see which side is inside (mm): above the snap, far below any copper.
_PROBE = 1e-5


def pen_outlines(points: Sequence[XY], width: float, *, closed: bool = False, tolerance: float = CHORD_TOLERANCE) -> list[list[XY]]:
    """What a round pen ``width`` wide covers along ``points``, as polygons to unite (:func:`union`): a
    stadium round each segment (round caps, so the joins are round too), a disc for a single point; with
    ``closed``, the segment back to the first point as well. A cap's chords lie within ``tolerance`` of it."""
    half = width / 2
    if half <= 0 or not points:
        return []
    steps = max(4, math.ceil(math.pi / (2 * _acos(1 - tolerance / half)))) if half > tolerance else 4
    pts = list(points)
    pairs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if closed and len(pts) > 2 else [])
    if not pairs:
        return [disc(pts[0], half, tolerance=tolerance)]
    out: list[list[XY]] = []
    for (ax, ay), (bx, by) in pairs:
        length = math.hypot(bx - ax, by - ay)
        if length < _SNAP:
            out.append(disc((ax, ay), half, tolerance=tolerance))
            continue
        heading = atan2(by - ay, bx - ax)
        outline = []
        for centre, start in (((bx, by), heading - math.pi / 2), ((ax, ay), heading + math.pi / 2)):
            for step in range(steps + 1):
                cos, sin = cos_sin(start + math.pi * step / steps)
                outline.append((centre[0] + half * cos, centre[1] + half * sin))
        out.append(outline)
    return out


def disc(centre: XY, radius: float, *, tolerance: float = CHORD_TOLERANCE) -> list[XY]:
    """A circle as a polygon, its chords within ``tolerance`` of it (24 at least)."""
    steps = max(24, chords(radius, 2 * math.pi, tolerance))
    return [(centre[0] + radius * cos, centre[1] + radius * sin)
            for cos, sin in (cos_sin(2 * math.pi * k / steps) for k in range(steps))]


def _key(point: XY) -> tuple[int, int]:
    return round(point[0] / _SNAP), round(point[1] / _SNAP)


def _cuts(p: XY, r: XY, q: XY, s: XY, mine: list[float], theirs: list[float]) -> None:
    """Where the segments ``p + t r`` and ``q + u s`` meet, as ``t`` on ``mine`` and ``u`` on ``theirs``
    (both ends of a shared run where they lie along each other)."""
    cross = r[0] * s[1] - r[1] * s[0]
    qp = (q[0] - p[0], q[1] - p[1])
    rr, ss = math.hypot(*r), math.hypot(*s)
    if rr < _SNAP or ss < _SNAP:
        return
    if abs(cross) > 1e-12 * rr * ss:
        t = (qp[0] * s[1] - qp[1] * s[0]) / cross
        u = (qp[0] * r[1] - qp[1] * r[0]) / cross
        slack_t, slack_u = _SNAP / rr, _SNAP / ss
        if -slack_t <= t <= 1 + slack_t and -slack_u <= u <= 1 + slack_u:
            mine.append(min(1.0, max(0.0, t)))
            theirs.append(min(1.0, max(0.0, u)))
        return
    if abs(qp[0] * r[1] - qp[1] * r[0]) / rr > _SNAP:
        return  # parallel, apart
    # Along each other: each end of one that lies within the other cuts it.
    for end in (q, (q[0] + s[0], q[1] + s[1])):
        t = ((end[0] - p[0]) * r[0] + (end[1] - p[1]) * r[1]) / (rr * rr)
        if 0 < t < 1:
            mine.append(t)
    for end in (p, (p[0] + r[0], p[1] + r[1])):
        u = ((end[0] - q[0]) * s[0] + (end[1] - q[1]) * s[1]) / (ss * ss)
        if 0 < u < 1:
            theirs.append(u)


def union(polygons: Iterable[Sequence[XY]]) -> list[tuple[list[XY], list[list[XY]]]]:
    """The region any of ``polygons`` covers (each a simple polygon, running either way; overlapping,
    touching or apart), as its pieces: each an outline counter-clockwise (in a y-up frame) with the
    outlines of its holes clockwise, the largest piece first.

    The standard library alone: every edge is cut where another meets it, and a cut edge is kept where
    one side of it is covered and the other is not (looked at :data:`_PROBE` off it), so an edge two
    polygons share, or one that runs inside another, drops out; the kept edges are then joined into rings."""
    shapes: list[tuple[list[XY], tuple[float, float, float, float]]] = []
    for polygon in polygons:
        ring: list[XY] = []
        for point in polygon:
            if not ring or _key(point) != _key(ring[-1]):
                ring.append((float(point[0]), float(point[1])))
        if len(ring) > 1 and _key(ring[0]) == _key(ring[-1]):
            ring.pop()
        if len(ring) >= 3 and abs(area(ring)) > _SNAP * _SNAP:
            shapes.append((ring, _bounds(ring)))
    if not shapes:
        return []
    if len(shapes) == 1:
        ring = shapes[0][0]
        return [(ring if area(ring) > 0 else ring[::-1], [])]
    edges = [(a, b) for ring, _box in shapes for a, b in zip(ring, [*ring[1:], ring[0]])]
    spans = [(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for a, b in edges]
    cuts: list[list[float]] = [[0.0, 1.0] for _ in edges]
    order = sorted(range(len(edges)), key=lambda index: spans[index][0])
    for position, i in enumerate(order):
        (p, pe), (_x0, y0, x1, y1) = edges[i], spans[i]
        r = (pe[0] - p[0], pe[1] - p[1])
        for j in order[position + 1:]:
            other = spans[j]
            if other[0] > x1 + _SNAP:
                break
            if other[1] > y1 + _SNAP or other[3] < y0 - _SNAP:
                continue
            q, qe = edges[j]
            _cuts(p, r, q, (qe[0] - q[0], qe[1] - q[1]), cuts[i], cuts[j])

    # The shapes filed in a grid by their boxes: a point is tested against the few whose box holds it.
    left = min(box[0] for _ring, box in shapes) - _PROBE
    top = min(box[1] for _ring, box in shapes) - _PROBE
    across = max(1, math.isqrt(len(shapes)))
    cell_w = (max(box[2] for _ring, box in shapes) + _PROBE - left) / across or 1.0
    cell_h = (max(box[3] for _ring, box in shapes) + _PROBE - top) / across or 1.0
    grid: dict[tuple[int, int], list[int]] = {}
    for number, (_ring, box) in enumerate(shapes):
        for gx in range(int((box[0] - left) / cell_w), int((box[2] - left) / cell_w) + 1):
            for gy in range(int((box[1] - top) / cell_h), int((box[3] - top) / cell_h) + 1):
                grid.setdefault((gx, gy), []).append(number)

    # Each shape's edges filed in horizontal bands: a point's winding number reads the edges of its band alone.
    bands: list[tuple[float, float, dict[int, list[tuple[XY, XY]]]]] = []
    for ring, box in shapes:
        rows = max(1, len(ring) // 4)
        height = (box[3] - box[1]) / rows or 1.0
        filed: dict[int, list[tuple[XY, XY]]] = {}
        for a, b in zip(ring, [*ring[1:], ring[0]]):
            for row in range(int((min(a[1], b[1]) - box[1]) / height), int((max(a[1], b[1]) - box[1]) / height) + 1):
                filed.setdefault(row, []).append((a, b))
        bands.append((box[1], height, filed))

    def winds(point: XY, number: int) -> bool:
        x, y = point
        base, height, filed = bands[number]
        turns = 0
        for a, b in filed.get(int((y - base) / height), ()):
            if a[1] <= y:
                if b[1] > y and _orientation(a, b, point) > 0:
                    turns += 1
            elif b[1] <= y and _orientation(a, b, point) < 0:
                turns -= 1
        return turns != 0

    def covered(point: XY) -> bool:
        x, y = point
        for number in grid.get((int((x - left) / cell_w), int((y - top) / cell_h)), ()):
            box = shapes[number][1]
            if box[0] <= x <= box[2] and box[1] <= y <= box[3] and winds(point, number):
                return True
        return False

    kept: dict[tuple[int, int], list[tuple[int, int]]] = {}
    seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for (p, pe), along in zip(edges, cuts):
        keys = [_key((p[0] + t * (pe[0] - p[0]), p[1] + t * (pe[1] - p[1]))) for t in sorted(set(along))]
        for a, b in zip(keys, keys[1:]):
            if a == b or (a, b) in seen or (b, a) in seen:
                continue
            seen.add((a, b))
            ax, ay, bx, by = a[0] * _SNAP, a[1] * _SNAP, b[0] * _SNAP, b[1] * _SNAP
            length = math.hypot(bx - ax, by - ay)
            nx, ny = -(by - ay) / length * _PROBE, (bx - ax) / length * _PROBE
            mx, my = (ax + bx) / 2, (ay + by) / 2
            on_left, on_right = covered((mx + nx, my + ny)), covered((mx - nx, my - ny))
            if on_left and not on_right:
                kept.setdefault(a, []).append(b)
            elif on_right and not on_left:
                kept.setdefault(b, []).append(a)

    def point_of(key: tuple[int, int]) -> XY:
        return key[0] * _SNAP, key[1] * _SNAP

    rings: list[list[XY]] = []
    while kept:
        start = next(iter(kept))
        ring_keys = [start]
        previous, current = start, kept[start].pop()
        if not kept[start]:
            del kept[start]
        while current != start:
            choices = kept.get(current)
            if not choices:
                break
            # Where rings touch at a point, turn as far right as the edges allow: each ring stays its own.
            heading = atan2(current[1] - previous[1], current[0] - previous[0])
            index = min(range(len(choices)), key=lambda k: (atan2(choices[k][1] - current[1], choices[k][0] - current[0]) - heading + math.pi) % (2 * math.pi))
            ring_keys.append(current)
            previous, current = current, choices.pop(index)
            if not choices:
                del kept[previous]
        if current == start and len(ring_keys) >= 3:
            ring = [point_of(key) for key in ring_keys]
            # Points along a straight run are not corners.
            simple = [ring[k] for k in range(len(ring))
                      if abs(_orientation(ring[k - 1], ring[k], ring[(k + 1) % len(ring)])) > _SNAP * _SNAP]
            if len(simple) >= 3:
                rings.append(simple)
    outers = sorted((ring for ring in rings if area(ring) > 0), key=lambda ring: -area(ring))
    pieces: list[tuple[list[XY], list[list[XY]]]] = [(ring, []) for ring in outers]
    for hole in (ring for ring in rings if area(ring) < 0):
        (ax, ay), (bx, by) = hole[0], hole[1]
        length = math.hypot(bx - ax, by - ay) or 1.0
        probe = ((ax + bx) / 2 - (by - ay) / length * _PROBE, (ay + by) / 2 + (bx - ax) / length * _PROBE)
        holders = [piece for piece in pieces if inside(probe, piece[0])]
        if holders:
            min(holders, key=lambda piece: area(piece[0]))[1].append(hole)
    return pieces
