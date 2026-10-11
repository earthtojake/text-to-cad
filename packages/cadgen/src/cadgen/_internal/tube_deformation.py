"""Tube deformation: cadgen's one tube engine.

A tube track (``animation_bake``) keys a tube's centerline. Nothing else in the
product works out where a tube is: this compiles a key's centerline, and
``tube_skin`` turns it into the joints of a glTF skin that every CAD view, every
snapshot and the animated GLB export play as glTF plays a skin. What lives here:

- the path compiler: line, arc and cubic Bezier segments, Bezier arc length by
  adaptive five-point Gauss-Legendre quadrature, normals carried by parallel
  transport, a key that maps its rest compiled on the rest's own parameters;
- the projection of every rest vertex onto the rest centerline;
- the refinement that splits the rest mesh into bands of at most
  ``maxSegmentLength`` of rest arc length.

Everything works on numpy arrays over all vertices, frames, table entries or
segments at once; a normal is carried down a path by composing its turns (a prefix
scan of their quaternions, or Rodrigues' formula read off two tangents). Pinned by
``test_tube_deformation.py``.

Coordinates are the document's millimetres before occurrence animation; the
caller places the rest mesh in the space the paths are authored in.
"""

from __future__ import annotations

import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

EPS = 1e-7
MAX_REFINED_TRIANGLES = 700_000
COMPILED_PATH_CACHE_SIZE = 128
# Every Bezier table is split at least this finely before quadrature decides.
_FORCED_INTERVALS = 128
_MAX_DEPTH = 20
_GAUSS_NODES = (0.0, 0.5384693101056831, -0.5384693101056831, 0.906179845938664, -0.906179845938664)
_GAUSS_WEIGHTS = (0.5688888888888889, 0.4786286704993665, 0.4786286704993665, 0.2369268850561891, 0.2369268850561891)
# How many (point, table entry) distances one projection step holds at once.
_PROJECTION_CHUNK = 1 << 19
_SEGMENT_KEYS = {
    "line": ("kind", "start", "end"),
    "arc": ("kind", "center", "axis", "start", "sweepDeg"),
    "bezier": ("kind", "points"),
}
_DEFORMATION_KEYS = ("rest", "path", "twistDeg", "maxSegmentLength", "braid", "mapsRest")


class TubeDeformationError(ValueError):
    """A path or deformation cadgen refuses, and why."""


def _fail(message: str):
    raise TubeDeformationError(f"tube deformation: {message}")


# --- three-vectors -------------------------------------------------------------
#
# Scalars as tuples for what a path compiles once, numpy (n, 3) arrays for what it
# does per vertex or per sample. A dot starts from 0, so -0 never leaks out of one.


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return 0.0 + a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _length(a):
    return math.sqrt(0.0 + a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(v, name: str):
    size = _length(v)
    if size < EPS:
        _fail(f"{name} must be nonzero")
    return _mul(v, 1 / size)


def _rotate(v, axis, angle: float):
    c = math.cos(angle)
    s = math.sin(angle)
    return _add(_add(_mul(v, c), _mul(_cross(axis, v), s)), _mul(axis, _dot(axis, v) * (1 - c)))


def _vdot(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a[..., 0] * b[..., 0] + a[..., 1] * b[..., 1] + a[..., 2] * b[..., 2]


def _vcross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.broadcast_arrays(a, b)
    return np.stack([
        a[..., 1] * b[..., 2] - a[..., 2] * b[..., 1],
        a[..., 2] * b[..., 0] - a[..., 0] * b[..., 2],
        a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0],
    ], axis=-1)


def _vlength(a: np.ndarray) -> np.ndarray:
    return np.sqrt(a[..., 0] * a[..., 0] + a[..., 1] * a[..., 1] + a[..., 2] * a[..., 2])


def _vrotate(v: np.ndarray, axis: np.ndarray, angle: np.ndarray) -> np.ndarray:
    c = np.cos(angle)[..., None]
    s = np.sin(angle)[..., None]
    return (v * c + _vcross(axis, v) * s) + axis * (_vdot(axis, v)[..., None] * (1 - c))


def _vtransport(normal: np.ndarray, frm: np.ndarray, to: np.ndarray) -> np.ndarray:
    """Parallel transport of transverse normals from unit tangents ``frm`` to ``to``."""
    axis = _vcross(frm, to)
    sine = _vlength(axis)
    cosine = _vdot(frm, to)
    small = sine < EPS
    if np.any(small & (cosine < 0)):
        _fail("path tangent reverses")
    out = np.array(normal, dtype=np.float64, copy=True)
    turn = ~small
    if np.any(turn):
        out[turn] = _vrotate(out[turn], axis[turn] * (1 / sine[turn])[:, None], np.arctan2(sine[turn], cosine[turn]))
    return out


def _carry(normal: np.ndarray, frm: np.ndarray, to: np.ndarray) -> np.ndarray:
    """Parallel transport for a batch, without trigonometry: the turn from unit ``frm``
    to unit ``to`` about ``a = frm x to`` takes ``n`` to
    ``n c + a x n + a (a . n) / (1 + c)`` with ``c = frm . to`` -- Rodrigues' formula
    with the sine and cosine of the turn read off the two tangents. A turn below EPS
    leaves the normal as it is."""
    axis = _vcross(frm, to)
    sine = _vlength(axis)
    cosine = _vdot(frm, to)
    small = sine < EPS
    if np.any(small & (cosine < 0)):
        _fail("path tangent reverses")
    out = (normal * cosine[:, None] + _vcross(axis, normal)
           + axis * (_vdot(axis, normal) / (1 + cosine))[:, None])
    if np.any(small):
        out[small] = normal[small]
    return out


def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ], axis=-1)


# --- cubic Bezier --------------------------------------------------------------
#
# ``points`` is one curve's (4, 3) control net, or (n, 4, 3): one net per parameter,
# for a batch over many segments at once.


def _bezier_at(points: np.ndarray, t: np.ndarray) -> np.ndarray:
    q = 1 - t
    return ((q * q * q)[:, None] * points[..., 0, :] + (3 * q * q * t)[:, None] * points[..., 1, :]
            + (3 * q * t * t)[:, None] * points[..., 2, :] + (t * t * t)[:, None] * points[..., 3, :])


def _bezier_derivative(points: np.ndarray, t: np.ndarray) -> np.ndarray:
    q = 1 - t
    return ((3 * q * q)[:, None] * (points[..., 1, :] - points[..., 0, :])
            + (6 * q * t)[:, None] * (points[..., 2, :] - points[..., 1, :])
            + (3 * t * t)[:, None] * (points[..., 3, :] - points[..., 2, :]))


def _bezier_second(points: np.ndarray, t: np.ndarray) -> np.ndarray:
    return ((6 * (1 - t))[:, None] * (points[..., 2, :] - 2 * points[..., 1, :] + points[..., 0, :])
            + (6 * t)[:, None] * (points[..., 3, :] - 2 * points[..., 2, :] + points[..., 1, :]))


def _bezier_length(points: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Arc length over [lo, hi] by five-point Gauss-Legendre quadrature."""
    mid = (lo + hi) / 2
    half = (hi - lo) / 2
    d10 = points[..., 1, :] - points[..., 0, :]
    d21 = points[..., 2, :] - points[..., 1, :]
    d32 = points[..., 3, :] - points[..., 2, :]
    total = np.zeros(np.shape(lo))
    for node, weight in zip(_GAUSS_NODES, _GAUSS_WEIGHTS):
        t = mid + half * node
        q = 1 - t
        a = 3 * q * q
        b = 6 * q * t
        c = 3 * t * t
        dx = a * d10[..., 0] + b * d21[..., 0] + c * d32[..., 0]
        dy = a * d10[..., 1] + b * d21[..., 1] + c * d32[..., 1]
        dz = a * d10[..., 2] + b * d21[..., 2] + c * d32[..., 2]
        total = total + weight * np.sqrt(dx * dx + dy * dy + dz * dz)
    return half * total


def _units(vectors: np.ndarray, name: str) -> np.ndarray:
    sizes = _vlength(vectors)
    if np.any(sizes < EPS):
        _fail(f"{name} must be nonzero")
    return vectors * (1 / sizes)[:, None]


# --- segments and paths ----------------------------------------------------------


class Segment:
    """One compiled segment of a centerline."""

    __slots__ = (
        "kind", "start", "end", "tangent", "length", "normal", "offset", "bounds_min", "bounds_max",
        "center", "axis", "radial", "radius", "sign", "points",
        "table_t", "table_s", "table_tangent", "table_normal", "table_points",
    )

    def __init__(self, kind: str):
        self.kind = kind
        self.normal = None
        self.offset = 0.0
        self.radius = math.inf
        self.table_points = None


_KINDS = {"line": 0, "arc": 1, "bezier": 2}


class _PathArrays:
    """Every segment's numbers as arrays, and every Bezier table end to end, so a
    batch of arc lengths samples across all the segments at once."""

    def __init__(self, segments: list) -> None:
        count = len(segments)
        self.kind = np.array([_KINDS[segment.kind] for segment in segments], dtype=np.int8)
        self.start = np.array([segment.start for segment in segments], dtype=np.float64).reshape(count, 3)
        self.tangent = np.array([segment.tangent for segment in segments], dtype=np.float64).reshape(count, 3)
        self.normal = np.array([segment.normal for segment in segments], dtype=np.float64).reshape(count, 3)
        self.center = np.zeros((count, 3))
        self.axis = np.zeros((count, 3))
        self.radial = np.zeros((count, 3))
        self.radius = np.ones(count)
        self.sign = np.ones(count)
        self.points = np.zeros((count, 4, 3))
        self.table_start = np.zeros(count, dtype=np.int64)
        self.table_count = np.zeros(count, dtype=np.int64)
        tables: list[tuple] = []
        filled = 0
        for index, segment in enumerate(segments):
            if segment.kind == "arc":
                self.center[index] = segment.center
                self.axis[index] = segment.axis
                self.radial[index] = segment.radial
                self.radius[index] = segment.radius
                self.sign[index] = segment.sign
            elif segment.kind == "bezier":
                self.points[index] = segment.points
                self.table_start[index] = filled
                self.table_count[index] = len(segment.table_t)
                filled += len(segment.table_t)
                tables.append((segment.table_t, segment.table_s, segment.table_tangent, segment.table_normal))
        self.table_t = np.concatenate([table[0] for table in tables]) if tables else np.zeros(0)
        self.table_s = np.concatenate([table[1] for table in tables]) if tables else np.zeros(0)
        # Each entry's arc length along the whole path, for ONE search across segments.
        owners = np.repeat(np.nonzero(self.kind == 2)[0], self.table_count[self.kind == 2])
        self.table_along = self.table_s + np.array([segment.offset for segment in segments])[owners]
        self.nets = _Nets(self.points)
        self.table_tangent = np.concatenate([table[2] for table in tables]) if tables else np.zeros((0, 3))
        self.table_normal = np.concatenate([table[3] for table in tables]) if tables else np.zeros((0, 3))


@dataclass
class Path:
    """A compiled centerline: its segments, and its length."""

    segments: list
    length: float

    def __post_init__(self) -> None:
        self.offsets = np.array([segment.offset for segment in self.segments])
        self.lengths = np.array([segment.length for segment in self.segments])
        # Each segment's end as every lookup compares it: offset + length.
        self.ends = np.array([segment.offset + segment.length for segment in self.segments])
        self._arrays: _PathArrays | None = None

    @property
    def arrays(self) -> _PathArrays:
        if self._arrays is None:
            self._arrays = _PathArrays(self.segments)
        return self._arrays


def _keys(value: object, allowed: Sequence[str], name: str) -> None:
    if not isinstance(value, Mapping):
        _fail(f"{name} must be an object")
    for key in value:
        if key not in allowed:
            _fail(f"unknown {name} key {json.dumps(key)}; expected {', '.join(allowed)}")


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _vector(value: object, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3 or not all(_number(item) for item in value):
        _fail(f"{name} must be a finite vec3")
    return [float(item) for item in value]  # type: ignore[union-attr]


def _path_spec_normal(raw: object) -> list[float]:
    """The ONE shape check for a path envelope, returning its seed normal."""
    _keys(raw, ("segments", "normal"), "path")
    segments = raw.get("segments")  # type: ignore[union-attr]
    if not isinstance(segments, (list, tuple)) or not segments:
        _fail("path needs at least one segment")
    # No default seed: a guessed transverse normal would flip as the first tangent
    # turns during an animation, twisting the tube a quarter turn in one frame.
    if "normal" not in raw:  # type: ignore[operator]
        _fail("path normal is required: give both the rest and the posed path an explicit transverse normal seed")
    return _vector(raw["normal"], "normal")  # type: ignore[index]


def canonical_segment(spec: object, index: int) -> dict:
    """The ONE shape check for a segment, returning an owned plain-number copy."""
    if not isinstance(spec, Mapping):
        _fail(f"segment {index} must be an object")
    kind = spec.get("kind")  # type: ignore[union-attr]
    _keys(spec, _SEGMENT_KEYS.get(kind, _SEGMENT_KEYS["arc"]), f"segment {index}")  # type: ignore[arg-type]
    if kind == "line":
        return {"kind": "line", "start": _vector(spec.get("start"), "start"), "end": _vector(spec.get("end"), "end")}
    if kind == "arc":
        return {
            "kind": "arc", "center": _vector(spec.get("center"), "center"), "axis": _vector(spec.get("axis"), "axis"),
            "start": _vector(spec.get("start"), "start"), "sweepDeg": spec.get("sweepDeg"),
        }
    if kind == "bezier":
        points = spec.get("points")
        if not isinstance(points, (list, tuple)) or len(points) != 4:
            _fail("Bezier points must contain four vec3 control points")
        return {"kind": "bezier", "points": [_vector(point, "Bezier point") for point in points]}  # type: ignore[union-attr]
    _fail(f"unknown segment kind {json.dumps(kind)}; expected line, arc, bezier")
    raise AssertionError  # unreachable


def canonical_path_spec(raw: object) -> dict:
    """A validated, OWNED copy of a path spec: plain numbers, no compiled table."""
    normal = _path_spec_normal(raw)
    return {"normal": normal, "segments": [canonical_segment(spec, index) for index, spec in enumerate(raw["segments"])]}  # type: ignore[index]


def _segment_point(segment: Segment, distance: float):
    if segment.kind == "line":
        return _add(segment.start, _mul(segment.tangent, distance))
    if segment.kind == "bezier":
        t, _lower = _bezier_parameter(segment, np.array([distance]))
        return tuple(_bezier_at(segment.points, t)[0])
    return _add(segment.center, _rotate(segment.radial, segment.axis, distance / segment.radius * segment.sign))


def _compile_segment(raw: object, index: int, canonical: bool = False) -> Segment:
    """One segment's exact numbers. ``canonical`` says ``raw`` already came out of
    ``canonical_segment`` (a normalized deformation's spec), so it is not checked twice."""
    spec = raw if canonical else canonical_segment(raw, index)
    if spec["kind"] == "line":
        segment = Segment("line")
        segment.start = tuple(spec["start"])
        segment.end = tuple(spec["end"])
        delta = _sub(segment.end, segment.start)
        segment.tangent = _unit(delta, "line")
        segment.length = _length(delta)
        return segment
    if spec["kind"] == "arc":
        segment = Segment("arc")
        center = tuple(spec["center"])
        start = tuple(spec["start"])
        axis = _unit(spec["axis"], "axis")
        radial = _sub(start, center)
        radius = _length(radial)
        sweep = spec["sweepDeg"]
        angle = sweep * math.pi / 180 if _number(sweep) else math.nan
        if not math.isfinite(angle) or abs(angle) < EPS or abs(angle) > 2 * math.pi + EPS:
            _fail("arc sweepDeg must be nonzero and at most 360 degrees")
        if radius < EPS or abs(_dot(radial, axis)) > EPS * max(1.0, radius):
            _fail("arc start must be in its normal plane with nonzero radius")
        sign = 1.0 if angle > 0 else -1.0
        segment.center, segment.start, segment.axis, segment.radial = center, start, axis, radial
        segment.radius, segment.sign = radius, sign
        segment.tangent = _mul(_cross(axis, radial), sign / radius)
        segment.length = radius * abs(angle)
        segment.end = _segment_point(segment, segment.length)
        return segment
    segment = Segment("bezier")
    segment.points = np.array(spec["points"], dtype=np.float64)
    segment.start = tuple(spec["points"][0])
    segment.end = tuple(spec["points"][3])
    segment.tangent = tuple(_units(_bezier_derivative(segment.points, np.zeros(1)), "Bezier tangent")[0])
    return segment


def _segment_bounds(segment: Segment) -> None:
    """A Bezier lies inside its control hull; an arc's box covers its whole circle,
    so pruning never discards the closest segment."""
    if segment.kind == "arc":
        segment.bounds_min = np.array([value - segment.radius for value in segment.center])
        segment.bounds_max = np.array([value + segment.radius for value in segment.center])
        return
    points = segment.points if segment.kind == "bezier" else np.array([segment.start, segment.end])
    segment.bounds_min = points.min(axis=0)
    segment.bounds_max = points.max(axis=0)


def _set_table(segment: Segment, t: np.ndarray, s: np.ndarray, tangents: np.ndarray, normals: np.ndarray) -> None:
    segment.table_t = t
    segment.table_s = s
    segment.table_tangent = tangents
    segment.table_normal = normals
    segment.table_points = None
    segment.length = float(s[-1])


def _adaptive_tables(nets: np.ndarray) -> list:
    """The adaptive table of each net: split until a piece's quadrature agrees with
    its halves' and its tangent turns by less than 0.0081 degrees.

    Every curve splits a whole level at a time; the pieces kept are those a depth-
    first recursion would keep, in its order, and a curve's first failure is its
    one with the least parameter. Each entry is ``(t, s, tangents)`` without the
    first row, or the failure's message."""
    count = len(nets)
    k = np.arange(_FORCED_INTERVALS, dtype=np.float64)
    owner = np.repeat(np.arange(count), _FORCED_INTERVALS)
    lo = np.tile(k / _FORCED_INTERVALS, count)
    hi = np.tile((k + 1) / _FORCED_INTERVALS, count)
    depth = 7  # 1/128 is 2^-7: the forced split is exact
    kept = []
    failures: dict[int, tuple[float, str]] = {}
    while lo.size:
        points = nets[owner]
        mid = (lo + hi) / 2
        whole = _bezier_length(points, lo, hi)
        left = _bezier_length(points, lo, mid)
        right = _bezier_length(points, mid, hi)
        da = _bezier_derivative(points, lo)
        db = _bezier_derivative(points, hi)
        la = _vlength(da)
        lb = _vlength(db)
        zero = (la < EPS) | (lb < EPS)
        with np.errstate(divide="ignore", invalid="ignore"):
            b = db * (1 / lb)[:, None]
            turn = _vdot(da * (1 / la)[:, None], b)
        split = ~zero & (depth < _MAX_DEPTH) & ((np.abs(whole - left - right) > 1e-9) | (turn < 0.9999))
        final = ~zero & ~split
        cusp = final & (turn < 0.99)
        for rows, message in ((zero, "Bezier tangent must be nonzero"), (cusp, "Bezier has a cusp or unresolved tangent")):
            for curve, at in zip(owner[rows].tolist(), lo[rows].tolist()):
                if curve not in failures or at < failures[curve][0]:
                    failures[curve] = (at, message)
        keep = final & ~cusp
        if np.any(keep):
            kept.append((owner[keep], lo[keep], hi[keep], left[keep], right[keep], b[keep]))
        owner = np.concatenate([owner[split], owner[split]])
        lo, hi = np.concatenate([lo[split], mid[split]]), np.concatenate([mid[split], hi[split]])
        depth += 1
    if not kept:
        return [failures[curve][1] for curve in range(count)]
    owners, starts, ends, lefts, rights, tangents = (np.concatenate([entry[n] for entry in kept]) for n in range(6))
    order = np.lexsort((starts, owners))
    owners, ends, lefts, rights, tangents = owners[order], ends[order], lefts[order], rights[order], tangents[order]
    bounds = np.searchsorted(owners, np.arange(count + 1))
    out: list = []
    for curve in range(count):
        if curve in failures:
            out.append(failures[curve][1])
            continue
        rows = slice(bounds[curve], bounds[curve + 1])
        # s[i] = (s[i-1] + left) + right: each piece's halves added in turn.
        halves = np.empty(2 * (bounds[curve + 1] - bounds[curve]))
        halves[0::2] = lefts[rows]
        halves[1::2] = rights[rows]
        out.append((ends[rows], np.add.accumulate(halves)[1::2], tangents[rows]))
    return out


def _image_tables(nets: np.ndarray, parameters: list, first_tangents: np.ndarray) -> list:
    """The table of each net that is an affine image of a tabulated curve, on that
    curve's parameters: an affine image is the same polynomial in the same
    parameter, so the pieces chosen for the original serve it, each integrated
    once. Each entry is ``(t, s, tangents)`` without the first row, or the message
    of the first failure a walk over the entries meets."""
    counts = [len(table) - 1 for table in parameters]
    owner = np.repeat(np.arange(len(nets)), counts)
    t = np.concatenate([table[1:] for table in parameters])
    before = np.concatenate([table[:-1] for table in parameters])
    points = nets[owner]
    derivative = _bezier_derivative(points, t)
    sizes = _vlength(derivative)
    with np.errstate(divide="ignore", invalid="ignore"):
        tangents = derivative * (1 / sizes)[:, None]
    lengths = _bezier_length(points, before, t)
    bounds = np.concatenate([[0], np.cumsum(counts)])
    out: list = []
    for curve in range(len(nets)):
        rows = slice(bounds[curve], bounds[curve + 1])
        zero = np.nonzero(sizes[rows] < EPS)[0]
        if zero.size:
            walked = np.vstack([first_tangents[curve], tangents[rows][:int(zero[0])]])
            _turned, reverses = _turns(walked[:-1], walked[1:])
            out.append("path tangent reverses" if np.any(reverses) else "Bezier tangent must be nonzero")
            continue
        out.append((t[rows], np.add.accumulate(lengths[rows]), tangents[rows]))
    return out


def _turns(frm: np.ndarray, to: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(quaternion of the minimal turn from each unit ``frm`` to ``to``, whether it
    reverses). A turn below EPS is none, as transport has it (:func:`_carry`)."""
    axis = _vcross(frm, to)
    sine = _vlength(axis)
    cosine = _vdot(frm, to)
    small = sine < EPS
    half = np.arctan2(sine, cosine) / 2
    with np.errstate(divide="ignore", invalid="ignore"):
        scale = np.where(small, 0.0, np.sin(half) / sine)
    out = np.empty((len(frm), 4))
    out[:, :3] = axis * scale[:, None]
    out[:, 3] = np.where(small, 1.0, np.cos(half))
    return out, small & (cosine < 0)


def _rotate_by(normal: np.ndarray, turns: np.ndarray) -> np.ndarray:
    """Each unit quaternion of ``turns`` applied to ``normal`` (one vector, or one per turn)."""
    u = turns[:, :3]
    v = np.broadcast_to(normal, u.shape)
    twice = 2 * _vcross(u, v)
    return v + turns[:, 3:4] * twice + _vcross(u, twice)


def _carried(seed, steps: np.ndarray) -> np.ndarray:
    """The normal at every node of a chain of turns from ``seed``: a prefix scan of
    the turns' quaternions forms every partial product in log2(n) array steps
    instead of carrying it one turn at a time."""
    nodes = np.empty((len(steps) + 1, 3))
    nodes[0] = seed
    if not len(steps):
        return nodes
    product = np.array(steps, copy=True)
    reach = 1
    while reach < len(product):
        product[reach:] = _qmul(product[reach:], product[:-reach])
        reach *= 2
    product /= np.sqrt(np.sum(product * product, axis=1))[:, None]
    nodes[1:] = _rotate_by(np.asarray(seed, dtype=np.float64), product)
    return nodes


def _parameter_at(points: np.ndarray, table_t: np.ndarray, table_s: np.ndarray, lower: np.ndarray,
                  distance: np.ndarray) -> np.ndarray:
    """The Bezier parameter at each arc length, from the table entry ``lower`` below
    it: interpolated between the entries, then three Newton steps on the length."""
    lower_t = table_t[lower]
    upper_t = table_t[lower + 1]
    lower_s = table_s[lower]
    upper_s = table_s[lower + 1]
    t = lower_t + (upper_t - lower_t) * (distance - lower_s) / (upper_s - lower_s)
    batch = points.ndim == 3
    active = np.arange(len(distance))
    for _ in range(3):
        if not active.size:
            break
        net = points[active] if batch else points
        error = lower_s[active] + _bezier_length(net, lower_t[active], t[active]) - distance[active]
        moving = np.abs(error) >= 1e-11
        active = active[moving]
        if not active.size:
            break
        net = points[active] if batch else points
        speed = _vlength(_bezier_derivative(net, t[active]))
        t[active] = np.maximum(lower_t[active], np.minimum(upper_t[active], t[active] - error[moving] / speed))
    return t


class _Nets:
    """A batch of control nets as contiguous component rows, (3, n) each: the base
    point and the three differences every derivative is made of."""

    __slots__ = ("p0", "d10", "d21", "d32")

    def __init__(self, nets: np.ndarray) -> None:
        self.p0 = np.ascontiguousarray(nets[:, 0, :].T)
        self.d10 = np.ascontiguousarray((nets[:, 1, :] - nets[:, 0, :]).T)
        self.d21 = np.ascontiguousarray((nets[:, 2, :] - nets[:, 1, :]).T)
        self.d32 = np.ascontiguousarray((nets[:, 3, :] - nets[:, 2, :]).T)

    def take(self, rows: np.ndarray) -> "_Nets":
        out = _Nets.__new__(_Nets)
        out.p0, out.d10, out.d21, out.d32 = self.p0[:, rows], self.d10[:, rows], self.d21[:, rows], self.d32[:, rows]
        return out

    def derivative(self, t: np.ndarray) -> np.ndarray:
        q = 1 - t
        out = (3 * q * q) * self.d10
        out += (6 * q * t) * self.d21
        out += (3 * t * t) * self.d32
        return out

    def second(self, t: np.ndarray) -> np.ndarray:
        # p2 - 2 p1 + p0 is d21 - d10, and p3 - 2 p2 + p1 is d32 - d21.
        return (6 * (1 - t)) * (self.d21 - self.d10) + (6 * t) * (self.d32 - self.d21)

    def point(self, t: np.ndarray) -> np.ndarray:
        # p0 + 3 q^2 t d10... in Bernstein form about p0: B(t) - p0 = 3qt^2... folded as
        # the cumulative differences, B(t) = p0 + (1 - q^3) d10 + (3 q t^2 + t^3) d21 + t^3 d32.
        q = 1 - t
        t3 = t * t * t
        return self.p0 + (1 - q * q * q) * self.d10 + (3 * q * t * t + t3) * self.d21 + t3 * self.d32

    def length(self, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        mid = (lo + hi) / 2
        half = (hi - lo) / 2
        total = np.zeros(len(lo))
        for node, weight in zip(_GAUSS_NODES, _GAUSS_WEIGHTS):
            d = self.derivative(mid + half * node)
            total += weight * np.sqrt(np.einsum("ij,ij->j", d, d))
        return half * total


def _frames_on_nets(soa: "_Nets", table_t: np.ndarray, table_s: np.ndarray, table_tangent: np.ndarray,
                    table_normal: np.ndarray, lower: np.ndarray, distance: np.ndarray) -> Frames:
    """The frames at arc lengths along a batch of Beziers, each with its own net and
    its table entry ``lower`` below it: the parameter by interpolation and three
    Newton steps on the length, then the frame there, its normal carried from that
    entry."""
    lower_t = table_t[lower]
    upper_t = table_t[lower + 1]
    lower_s = table_s[lower]
    t = lower_t + (upper_t - lower_t) * (distance - lower_s) / (table_s[lower + 1] - lower_s)
    active = None  # every sample, until some converge
    part = soa
    for _ in range(3):
        if active is None:
            error = lower_s + part.length(lower_t, t) - distance
        else:
            error = lower_s[active] + part.length(lower_t[active], t[active]) - distance[active]
        moving = np.abs(error) >= 1e-11
        if not np.any(moving):
            break
        if active is None and np.all(moving):
            d = part.derivative(t)
            speed = np.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
            t = np.maximum(lower_t, np.minimum(upper_t, t - error / speed))
            continue
        active = np.nonzero(moving)[0] if active is None else active[moving]
        part = soa.take(active)
        d = part.derivative(t[active])
        speed = np.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        t[active] = np.maximum(lower_t[active], np.minimum(upper_t[active], t[active] - error[moving] / speed))
    first = soa.derivative(t)
    speed = np.sqrt(first[0] * first[0] + first[1] * first[1] + first[2] * first[2])
    tangent = (first * (1 / speed)).T
    normal = _carry(table_normal[lower], table_tangent[lower], tangent)
    second = soa.second(t).T
    curvature = (second - tangent * _vdot(second, tangent)[:, None]) * (1 / (speed * speed))[:, None]
    return Frames(soa.point(t).T, tangent, normal, _vcross(tangent, normal), curvature)


def _bezier_parameter(segment: Segment, distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(parameter, index of the table entry below it) at each arc length."""
    s = segment.table_s
    lower = np.clip(np.searchsorted(s, distance, side="left") - 1, 0, len(s) - 2)
    return _parameter_at(segment.points, segment.table_t, s, lower, distance), lower


@dataclass
class Frames:
    """The centerline's frames at a batch of arc lengths: (n, 3) each."""

    point: np.ndarray
    tangent: np.ndarray
    normal: np.ndarray
    binormal: np.ndarray
    curvature: np.ndarray


_FRAME_FIELDS = ("point", "tangent", "normal", "binormal", "curvature")


def _empty_frames(count: int) -> Frames:
    return Frames(*(np.empty((count, 3)) for _ in _FRAME_FIELDS))


def _put(frames: Frames, rows: np.ndarray, part: Frames) -> None:
    for name in _FRAME_FIELDS:
        getattr(frames, name)[rows] = getattr(part, name)


def _bezier_frames_at(points: np.ndarray, t: np.ndarray, lower_tangent: np.ndarray, lower_normal: np.ndarray) -> Frames:
    """The frames at Bezier parameters ``t``, the normal carried from the table entry
    below each (whose tangent and normal are given)."""
    first = _bezier_derivative(points, t)
    speed = _vlength(first)
    tangent = first * (1 / speed)[:, None]
    normal = _vtransport(lower_normal, lower_tangent, tangent)
    second = _bezier_second(points, t)
    curvature = (second - tangent * _vdot(second, tangent)[:, None]) * (1 / (speed * speed))[:, None]
    return Frames(_bezier_at(points, t), tangent, normal, _vcross(tangent, normal), curvature)


def _bezier_frames(segment: Segment, t: np.ndarray, lower: np.ndarray) -> Frames:
    return _bezier_frames_at(segment.points, t, segment.table_tangent[lower], segment.table_normal[lower])


def _segment_frames(segment: Segment, distance: np.ndarray) -> Frames:
    if segment.kind == "bezier":
        t, lower = _bezier_parameter(segment, distance)
        return _bezier_frames(segment, t, lower)
    count = len(distance)
    if segment.kind == "line":
        tangent = np.broadcast_to(np.asarray(segment.tangent), (count, 3))
        normal = np.broadcast_to(np.asarray(segment.normal), (count, 3))
        point = np.asarray(segment.start) + tangent * distance[:, None]
        return Frames(point, np.array(tangent), np.array(normal), _vcross(tangent, normal), np.zeros((count, 3)))
    angle = distance / segment.radius * segment.sign
    axis = np.broadcast_to(np.asarray(segment.axis), (count, 3))
    tangent = _vrotate(np.broadcast_to(np.asarray(segment.tangent), (count, 3)), axis, angle)
    normal = _vrotate(np.broadcast_to(np.asarray(segment.normal), (count, 3)), axis, angle)
    point = np.asarray(segment.center) + _vrotate(np.broadcast_to(np.asarray(segment.radial), (count, 3)), axis, angle)
    curvature = (np.asarray(segment.center) - point) * (1 / (segment.radius * segment.radius))
    return Frames(point, tangent, normal, _vcross(tangent, normal), curvature)


def compile_tube_path(raw: object, image: Path | None = None, *, canonical: bool = False) -> Path:
    """Validate a tangent-continuous path and tabulate it.

    ``image`` is a compiled path this one is an affine image of, segment for
    segment (a key that maps its rest): its Bezier tables are built on that path's
    parameters rather than split adaptively again. ``canonical`` says ``raw`` is a
    normalized deformation's spec, already checked.

    Every segment tabulates as one batch and the normal is carried down the whole
    path in one chain of turns. Failures are collected in the path's order -- by
    segment, and within one: its own numbers, the gap before it, the frame at the
    end of the one before, the corner there, the seed normal, its table -- and the
    first is the one raised."""
    seed = list(raw["normal"]) if canonical else _path_spec_normal(raw)  # type: ignore[index]
    errors: list[tuple[int, int, str]] = []
    segments: list[Segment] = []
    for index, spec in enumerate(raw["segments"]):  # type: ignore[index]
        try:
            segments.append(_compile_segment(spec, index, canonical))
        except TubeDeformationError as error:
            errors.append((index, 0, str(error)))
            break
    count = len(segments)
    for index in range(1, count):
        if _length(_sub(segments[index - 1].end, segments[index].start)) > 1e-5:
            errors.append((index, 1, f"tube deformation: path discontinuity before segment {index}"))

    # Every Bezier's table, without its normals.
    curves = [index for index, segment in enumerate(segments) if segment.kind == "bezier"]
    imaged = [index for index in curves if image is not None and index < len(image.segments)
              and image.segments[index].kind == "bezier"]
    tables: dict[int, tuple] = {}
    adaptive = [index for index in curves if index not in imaged]
    built = []
    if adaptive:
        built += zip(adaptive, _adaptive_tables(np.stack([segments[index].points for index in adaptive])))
    if imaged:
        built += zip(imaged, _image_tables(
            np.stack([segments[index].points for index in imaged]),
            [image.segments[index].table_t for index in imaged],  # type: ignore[union-attr]
            np.array([segments[index].tangent for index in imaged]),
        ))
    for index, table in built:
        if isinstance(table, str):
            errors.append((index, 5, f"tube deformation: {table}"))
        else:
            tables[index] = table
    table_tangents = {index: np.vstack([np.asarray(segments[index].tangent), table[2]])
                      for index, table in tables.items()}

    # The frame at each segment's end, where the next one must continue it.
    ends: dict[int, tuple] = {}
    ended = [index for index in range(count - 1) if segments[index].kind != "bezier" or index in tables]
    tabled = [index for index in ended if segments[index].kind == "bezier"]
    if tabled:
        sizes = [len(tables[index][0]) + 1 for index in tabled]
        starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
        table_t = np.concatenate([np.concatenate([[0.0], tables[index][0]]) for index in tabled])
        table_s = np.concatenate([np.concatenate([[0.0], tables[index][1]]) for index in tabled])
        lower = starts + np.array(sizes) - 2
        nets = np.stack([segments[index].points for index in tabled])
        lengths = np.array([tables[index][1][-1] for index in tabled])
        t_end = _parameter_at(nets, table_t, table_s, lower, lengths)
        first = _bezier_derivative(nets, t_end)
        directions = first * (1 / _vlength(first))[:, None]
        for index, direction in zip(tabled, directions):
            ends[index] = tuple(direction)
    for index in ended:
        segment = segments[index]
        if segment.kind == "line":
            ends[index] = segment.tangent
        elif segment.kind == "arc":
            ends[index] = _rotate(segment.tangent, segment.axis, segment.length / segment.radius * segment.sign)

    # The chain of turns the normal rides: inside each Bezier's table, then over
    # each joint to the next segment's start.
    steps: list[np.ndarray] = []
    starts_at: list[int] = []
    last_turns: dict[int, np.ndarray] = {}
    node = 0
    for index, segment in enumerate(segments):
        starts_at.append(node)
        last = index == count - 1
        if segment.kind == "bezier":
            if index not in tables:
                break
            tangents = table_tangents[index]
            turns, reverses = _turns(tangents[:-1], tangents[1:])
            if np.any(reverses):
                errors.append((index, 5, "tube deformation: path tangent reverses"))
            # The table's last entry branches off the chain: the joint to the next
            # segment leaves from the entry before it, where the end frame is read.
            steps.append(turns[:-1])
            last_turns[index] = turns[-1:]
            node += len(turns) - 1
            if not last:
                joint, reverses = _turns(tangents[-2:-1], np.array([ends[index]]))
                if reverses[0]:
                    errors.append((index + 1, 2, "tube deformation: path tangent reverses"))
                steps.append(joint)
                node += 1
        elif not last:
            if segment.kind == "arc":
                angle = segment.length / segment.radius * segment.sign
                joint = np.array([[*(np.asarray(segment.axis) * math.sin(angle / 2)), math.cos(angle / 2)]])
            else:
                joint = np.array([[0.0, 0.0, 0.0, 1.0]])
            steps.append(joint)
            node += 1
    for index in range(1, count):
        previous = index - 1
        if previous in ends and _dot(ends[previous], segments[index].tangent) < 1 - 1e-7:
            errors.append((index, 3, f"tube deformation: path is not tangent-continuous before segment {index}"))
    if count:
        tangent = segments[0].tangent
        projected = _sub(seed, _mul(tangent, _dot(seed, tangent)))
        if _length(projected) < EPS:
            errors.append((0, 4, "tube deformation: path normal transverse to first tangent must be nonzero"))
    if errors:
        raise TubeDeformationError(min(errors)[2])

    normal0 = _unit(projected, "path normal transverse to first tangent")
    nodes = _carried(normal0, np.concatenate(steps) if steps else np.zeros((0, 4)))
    total = 0.0
    for index, segment in enumerate(segments):
        segment.normal = tuple(nodes[starts_at[index]])
        if segment.kind == "bezier":
            t, s, _tangents = tables[index]
            tangents = table_tangents[index]
            m = len(tangents)
            normals = np.empty((m, 3))
            normals[:m - 1] = nodes[starts_at[index]:starts_at[index] + m - 1]
            normals[m - 1] = _rotate_by(normals[m - 2], last_turns[index])[0]
            _set_table(segment, np.concatenate([[0.0], t]), np.concatenate([[0.0], s]), tangents, normals)
        segment.offset = total
        _segment_bounds(segment)
        total += segment.length
    return Path(segments, total)


def sample_frames(path: Path, distances: np.ndarray) -> Frames:
    """Exact frames at arc lengths along ``path``; past either end the end frame
    extrapolates along its tangent. One batch across every
    segment: each sample gathers its own segment's numbers."""
    distance = np.asarray(distances, dtype=np.float64).reshape(-1)
    if not np.all(np.isfinite(distance)):
        _fail("path distance must be finite")
    arrays = path.arrays
    count = len(distance)
    index = np.minimum(np.searchsorted(path.ends, distance, side="left"), len(path.segments) - 1)
    index[distance <= 0] = 0
    local = distance - path.offsets[index]
    clamped = np.maximum(0.0, np.minimum(path.lengths[index], local))
    frames = _empty_frames(count)
    kinds = arrays.kind[index]
    rows = np.nonzero(kinds == 0)[0]
    if rows.size:
        k = index[rows]
        tangent = arrays.tangent[k]
        normal = arrays.normal[k]
        _put(frames, rows, Frames(arrays.start[k] + tangent * clamped[rows][:, None], tangent, normal,
                                  _vcross(tangent, normal), np.zeros((rows.size, 3))))
    rows = np.nonzero(kinds == 1)[0]
    if rows.size:
        k = index[rows]
        angle = clamped[rows] / arrays.radius[k] * arrays.sign[k]
        axis = arrays.axis[k]
        tangent = _vrotate(arrays.tangent[k], axis, angle)
        normal = _vrotate(arrays.normal[k], axis, angle)
        point = arrays.center[k] + _vrotate(arrays.radial[k], axis, angle)
        curvature = (arrays.center[k] - point) * (1 / (arrays.radius[k] * arrays.radius[k]))[:, None]
        _put(frames, rows, Frames(point, tangent, normal, _vcross(tangent, normal), curvature))
    rows = np.nonzero(kinds == 2)[0]
    if rows.size:
        k = index[rows]
        d = clamped[rows]
        # Each sample's table entry below it, kept inside its own segment's table.
        first = arrays.table_start[k]
        found = np.searchsorted(arrays.table_along, path.offsets[k] + d, side="left") - 1
        lower = np.clip(found, first, first + arrays.table_count[k] - 2)
        part = _frames_on_nets(arrays.nets.take(k), arrays.table_t, arrays.table_s, arrays.table_tangent,
                               arrays.table_normal, lower, d)
        if rows.size == count:
            frames = part
        else:
            _put(frames, rows, part)
    beyond = local != clamped
    if np.any(beyond):
        frames.point[beyond] = frames.point[beyond] + frames.tangent[beyond] * (local - clamped)[beyond][:, None]
    return frames


# --- projection onto the rest centerline ------------------------------------------


def _table_points(segment: Segment) -> np.ndarray:
    if segment.table_points is None:
        segment.table_points = _bezier_at(segment.points, segment.table_t)
    return segment.table_points


def _newton_closest(points: np.ndarray, p: np.ndarray, t0: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Newton on g(t) = (B(t) - p) . B'(t) from the nearest table sample, kept in its
    bracket. NaN where g is not increasing there or it does not converge: the
    bracketing search below then decides."""
    a, b, c, d = points
    t = np.array(t0, dtype=np.float64, copy=True)
    result = np.full(len(t), np.nan)
    active = np.arange(len(t))
    for _ in range(24):
        if not active.size:
            break
        tt = t[active]
        q = 1 - tt
        w0, w1, w2, w3 = q * q * q, 3 * q * q * tt, 3 * q * tt * tt, tt * tt * tt
        u0, u1, u2 = 3 * q * q, 6 * q * tt, 3 * tt * tt
        g = np.zeros(len(tt))
        dg = np.zeros(len(tt))
        for k in range(3):
            offset = w0 * a[k] + w1 * b[k] + w2 * c[k] + w3 * d[k] - p[active, k]
            first = u0 * (b[k] - a[k]) + u1 * (c[k] - b[k]) + u2 * (d[k] - c[k])
            second = 6 * q * (c[k] - 2 * b[k] + a[k]) + 6 * tt * (d[k] - 2 * c[k] + b[k])
            g = g + offset * first
            dg = dg + (first * first + offset * second)
        rising = dg > 0
        with np.errstate(divide="ignore", invalid="ignore"):
            following = np.minimum(hi[active], np.maximum(lo[active], tt - g / dg))
        settled = rising & (np.abs(following - tt) <= 1e-14)
        result[active[settled]] = following[settled]
        going = rising & ~settled
        t[active[going]] = following[going]
        active = active[going]
    return result


def _ternary_closest(points: np.ndarray, p: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    lo = np.array(lo, dtype=np.float64, copy=True)
    hi = np.array(hi, dtype=np.float64, copy=True)
    for _ in range(35):
        a = lo + (hi - lo) / 3
        b = hi - (hi - lo) / 3
        pa = p - _bezier_at(points, a)
        pb = p - _bezier_at(points, b)
        nearer = (pa[:, 0] ** 2 + pa[:, 1] ** 2 + pa[:, 2] ** 2) < (pb[:, 0] ** 2 + pb[:, 1] ** 2 + pb[:, 2] ** 2)
        hi = np.where(nearer, b, hi)
        lo = np.where(nearer, lo, a)
    return (lo + hi) / 2


def _closest_bezier(segment: Segment, p: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(parameter, table entry below it, arc length) of each point's closest point."""
    samples = _table_points(segment)
    count = len(samples)
    nearest = np.empty(len(p), dtype=np.int64)
    chunk = max(1, _PROJECTION_CHUNK // count)
    for start in range(0, len(p), chunk):
        block = p[start:start + chunk]
        dx = block[:, 0, None] - samples[None, :, 0]
        dy = block[:, 1, None] - samples[None, :, 1]
        dz = block[:, 2, None] - samples[None, :, 2]
        nearest[start:start + chunk] = np.argmin(dx ** 2 + dy ** 2 + dz ** 2, axis=1)
    table_t = segment.table_t
    lo = table_t[np.maximum(0, nearest - 1)]
    hi = table_t[np.minimum(count - 1, nearest + 1)]
    t = _newton_closest(segment.points, p, table_t[nearest], lo, hi)
    fallback = np.isnan(t)
    if np.any(fallback):
        t[fallback] = _ternary_closest(segment.points, p[fallback], lo[fallback], hi[fallback])
    lower = np.maximum(0, np.searchsorted(table_t, t, side="right") - 1)
    distance = segment.table_s[lower] + _bezier_length(segment.points, table_t[lower], t)
    return t, lower, distance


def _closest_arc(segment: Segment, p: np.ndarray) -> np.ndarray:
    delta = p - np.asarray(segment.center)
    radial = np.asarray(segment.radial)
    angle = np.arctan2(_vdot(_vcross(radial, delta), np.asarray(segment.axis)), _vdot(delta, radial)) * segment.sign
    angle = np.where(angle < 0, angle + 2 * math.pi, angle)
    local = angle * segment.radius
    beyond = local > segment.length
    if np.any(beyond):
        # Outside the sweep the nearest point is an end; distance to a circle grows
        # with angular offset, so comparing the two ends decides.
        to_start = _vlength(p[beyond] - np.asarray(segment.start))
        to_end = _vlength(p[beyond] - np.asarray(segment.end))
        local[beyond] = np.where(to_start < to_end, 0.0, segment.length)
    return local


def _arc_points(segment: Segment, local: np.ndarray) -> np.ndarray:
    count = len(local)
    axis = np.broadcast_to(np.asarray(segment.axis), (count, 3))
    angle = local / segment.radius * segment.sign
    return np.asarray(segment.center) + _vrotate(np.broadcast_to(np.asarray(segment.radial), (count, 3)), axis, angle)


@dataclass
class _Closest:
    segment: np.ndarray  # winning segment index per point
    local: np.ndarray  # arc length along it, clamped
    t: np.ndarray  # Bezier parameter (NaN elsewhere)
    lower: np.ndarray  # Bezier table entry below t


def _closest_on_path(path: Path, p: np.ndarray) -> _Closest:
    """Each point's closest segment, visiting segments nearest-bound first and
    stopping where a bound passes the best distance found: a tie keeps the segment
    visited first."""
    count = len(p)
    segments = path.segments
    bounds = np.empty((count, len(segments)))
    for index, segment in enumerate(segments):
        gap = np.maximum(np.maximum(segment.bounds_min - p, 0.0), p - segment.bounds_max)
        bounds[:, index] = gap[:, 0] ** 2 + gap[:, 1] ** 2 + gap[:, 2] ** 2
    order = np.argsort(bounds, axis=1, kind="stable")
    ranked = np.take_along_axis(bounds, order, axis=1)
    best = np.full(count, np.inf)
    out = _Closest(np.full(count, -1, dtype=np.int64), np.zeros(count), np.full(count, np.nan),
                   np.zeros(count, dtype=np.int64))
    active = np.ones(count, dtype=bool)
    for rank in range(len(segments)):
        active &= ranked[:, rank] <= best + 1e-12
        rows = np.nonzero(active)[0]
        if not rows.size:
            break
        chosen = order[rows, rank]
        for which in np.unique(chosen):
            sub = rows[chosen == which]
            segment = segments[which]
            q = p[sub]
            t = lower = None
            if segment.kind == "bezier":
                t, lower, distance = _closest_bezier(segment, q)
                local = np.maximum(0.0, np.minimum(segment.length, distance))
                nearest = _bezier_at(segment.points, t)
            elif segment.kind == "line":
                local = np.maximum(0.0, np.minimum(segment.length, _vdot(q - np.asarray(segment.start), np.asarray(segment.tangent))))
                nearest = np.asarray(segment.start) + np.asarray(segment.tangent) * local[:, None]
            else:
                local = np.maximum(0.0, np.minimum(segment.length, _closest_arc(segment, q)))
                nearest = _arc_points(segment, local)
            gap = q - nearest
            d2 = gap[:, 0] ** 2 + gap[:, 1] ** 2 + gap[:, 2] ** 2
            better = d2 < best[sub]
            won = sub[better]
            best[won] = d2[better]
            out.segment[won] = which
            out.local[won] = local[better]
            if t is not None:
                out.t[won] = t[better]
                out.lower[won] = lower[better]
            else:
                out.t[won] = np.nan
    return out


def project_distances(path: Path, points: np.ndarray) -> np.ndarray:
    """Arc length along ``path`` of each point's closest point."""
    closest = _closest_on_path(path, points)
    return path.offsets[closest.segment] + closest.local


@dataclass
class Projection:
    """Each point against the rest centerline."""

    distance: np.ndarray
    transverse: np.ndarray  # (n, 2): along the frame's normal, binormal
    axial: np.ndarray
    frames: Frames


def project_points(path: Path, points: np.ndarray) -> Projection:
    """The closest exact centerline point of each point, and its frame there."""
    closest = _closest_on_path(path, points)
    frames = _empty_frames(len(points))
    for which in np.unique(closest.segment):
        rows = np.nonzero(closest.segment == which)[0]
        segment = path.segments[which]
        if segment.kind == "bezier":
            # Straight from the closest parameter: no round trip through arc length.
            _put(frames, rows, _bezier_frames(segment, closest.t[rows], closest.lower[rows]))
        else:
            _put(frames, rows, _segment_frames(segment, closest.local[rows]))
    delta = points - frames.point
    return Projection(
        distance=path.offsets[closest.segment] + closest.local,
        transverse=np.stack([_vdot(delta, frames.normal), _vdot(delta, frames.binormal)], axis=1),
        axial=_vdot(delta, frames.tangent),
        frames=frames,
    )


# --- deformations ----------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Deformation:
    """A tube's pose as NUMBERS, validated and owned: never a compiled path.

    ``maps_rest`` says the path is the rest under one affine map, segment for
    segment, so it compiles on the rest's parameters."""

    rest_spec: dict
    path_spec: dict
    twist_deg: float
    max_segment_length: float
    braid: dict | None = None
    maps_rest: bool = False


def normalize_tube_deformation(spec: Mapping[str, Any], *, rest_spec: dict | None = None) -> Deformation:
    """A deformation spec, validated: ``{rest, path, twistDeg?, maxSegmentLength?,
    braid?, mapsRest?}``. Compiles nothing.

    ``rest_spec`` is ``spec["rest"]`` already canonical (``canonical_path_spec``),
    for a caller posing one tube many times: every deformation it makes then
    shares that one copy."""
    _keys(spec, _DEFORMATION_KEYS, "deformation")
    twist = spec.get("twistDeg")
    twist = 0.0 if twist is None else twist
    if not _number(twist):
        _fail("twistDeg must be finite")
    step = spec.get("maxSegmentLength")
    step = 1.0 if step is None else step
    if not _number(step) or step < 0.05:
        _fail("maxSegmentLength must be at least 0.05 mm")
    braid = spec.get("braid")
    if braid:
        _keys(braid, ("pitch", "depth", "strands"), "braid")
        pitch, depth, strands = braid.get("pitch"), braid.get("depth"), braid.get("strands")
        valid = (_number(pitch) and pitch > 0 and _number(depth) and depth >= 0
                 and isinstance(strands, int) and not isinstance(strands, bool) and 2 <= strands <= 64 and strands % 2 == 0)
        if not valid:
            _fail("braid needs positive pitch, nonnegative depth, and an even strand count from 2 to 64")
        braid = {"pitch": pitch, "depth": depth, "strands": strands}
    else:
        braid = None
    return Deformation(
        rest_spec=canonical_path_spec(spec.get("rest")) if rest_spec is None else rest_spec,
        path_spec=canonical_path_spec(spec.get("path")),
        twist_deg=float(twist),
        max_segment_length=float(step),
        braid=braid,
        maps_rest=bool(spec.get("mapsRest")),
    )


@dataclass(frozen=True)
class CompiledDeformation:
    """A deformation with its two paths resolved, for as long as a caller poses with it."""

    deformation: Deformation
    rest: Path
    path: Path

    @property
    def twist_deg(self) -> float:
        return self.deformation.twist_deg

    @property
    def max_segment_length(self) -> float:
        return self.deformation.max_segment_length


_compiled_paths: "OrderedDict[tuple, Path]" = OrderedDict()
_compile_lock = threading.Lock()


def _spec_key(spec: Mapping[str, Any]) -> str:
    return json.dumps(spec, separators=(",", ":"))


def _cached_compile(spec: Mapping[str, Any], image: Path | None = None, image_key: str | None = None) -> Path:
    """One compile per spec through a bounded LRU: the rest paths and whichever
    posed ones are in flight. A path compiled on an image's parameters is its own
    entry, keyed by that image too: its table must pair with the image's."""
    key = (_spec_key(spec), image_key if image is not None else None)
    with _compile_lock:
        path = _compiled_paths.pop(key, None)
    if path is None:
        path = compile_tube_path(spec, image, canonical=True)
    with _compile_lock:
        _compiled_paths[key] = path
        while len(_compiled_paths) > COMPILED_PATH_CACHE_SIZE:
            _compiled_paths.popitem(last=False)
    return path


def compile_deformation(deformation: Deformation) -> CompiledDeformation:
    """Resolve a deformation's two paths. Never memoised onto the deformation: a
    bake holds a sample per grid step, and a sample that held its tables would hold
    hundreds of kilobytes."""
    rest = _cached_compile(deformation.rest_spec)
    image = rest if deformation.maps_rest else None
    path = _cached_compile(deformation.path_spec, image, _spec_key(deformation.rest_spec))
    return CompiledDeformation(deformation, rest, path)


# --- the rest mesh: refine, map, pose --------------------------------------------


def _round_half_up(value: float) -> int:
    """The nearest integer, a half going up, so a weight and its negation never
    round apart."""
    floor = math.floor(value)
    return floor + 1 if value - floor >= 0.5 else floor


def _clip_polygon(polygon: list, cut: float, above: bool) -> list:
    """Clip a polygon of [distance, w0, w1, w2] rows against one band boundary,
    dropping a corner that repeats the one before it."""
    result = []
    count = len(polygon)
    for index in range(count):
        a = polygon[index]
        b = polygon[(index + 1) % count]
        in_a = a[0] >= cut if above else a[0] <= cut
        in_b = b[0] >= cut if above else b[0] <= cut
        if in_a:
            result.append(a)
        if in_a != in_b:
            t = (cut - a[0]) / (b[0] - a[0])
            result.append([a[j] + t * (b[j] - a[j]) for j in range(4)])
    return [row for index, row in enumerate(result) if not index or (
        abs(row[1] - result[index - 1][1]) + abs(row[2] - result[index - 1][2])
        + abs(row[3] - result[index - 1][3]) > 1e-10)]


def _vertex_key(ids: tuple, corner: list) -> tuple:
    """A refined vertex's identity, shared by every triangle that cuts it: the source
    vertices it interpolates, in id order (ties in corner order), with their weights."""
    a, b, c = ids
    if a <= b:
        order = (0, 1, 2) if b <= c else (0, 2, 1) if a <= c else (2, 0, 1)
    else:
        order = (1, 0, 2) if a <= c else (1, 2, 0) if b <= c else (2, 1, 0)
    key = []
    for k in order:
        weight = _round_half_up(corner[k + 1] * 1e10)
        if weight:
            key.append((ids[k], weight))
    return tuple(key)


@dataclass
class RestMesh:
    """A triangle mesh in the space the paths are authored in."""

    positions: np.ndarray  # (v, 3) float32
    normals: np.ndarray  # (v, 3) float32
    indices: np.ndarray  # (t * 3,) uint32
    # The source triangle each triangle came from, or None when it IS its source.
    source_triangles: np.ndarray | None = None


def _unique_rows(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(first index of each distinct row, in first-seen order; each row's slot).
    -0 and 0 are one value."""
    flat = np.ascontiguousarray(rows + 0.0)
    _unique, first, inverse = np.unique(flat, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    return first[order], rank[inverse.reshape(-1)]


def refine_rest_mesh(mesh: RestMesh, rest: Path, step: float) -> RestMesh:
    """Split the rest mesh's triangles into bands of at most ``step`` of rest arc
    length, interpolating positions and normals.

    A swept STEP surface need not have intermediate rings on a straight run, and a
    bend over one long triangle is a chord. This changes the tessellation only,
    never the rest surface."""
    if step >= rest.length or len(mesh.indices) % 3:
        return RestMesh(mesh.positions, mesh.normals, mesh.indices, None)
    positions64 = mesh.positions.astype(np.float64)
    first, slot = _unique_rows(positions64)
    distances = project_distances(rest, positions64[first])[slot].tolist()
    position_rows = positions64.tolist()
    normal_rows = mesh.normals.astype(np.float64).tolist()
    triangles = mesh.indices.reshape(-1, 3).tolist()
    source_triangles: list[int] = []
    out_indices: list[int] = []
    vertices: dict[tuple, int] = {}
    out_positions: list[list[float]] = []
    out_normals: list[list[float]] = []

    def vertex(ids: tuple, corner: list) -> int:
        key = _vertex_key(ids, corner)
        index = vertices.get(key)
        if index is None:
            index = vertices[key] = len(out_positions)
            w0, w1, w2 = corner[1], corner[2], corner[3]
            p0, p1, p2 = position_rows[ids[0]], position_rows[ids[1]], position_rows[ids[2]]
            n0, n1, n2 = normal_rows[ids[0]], normal_rows[ids[1]], normal_rows[ids[2]]
            out_positions.append([0.0 + w0 * p0[k] + w1 * p1[k] + w2 * p2[k] for k in range(3)])
            out_normals.append([0.0 + w0 * n0[k] + w1 * n1[k] + w2 * n2[k] for k in range(3)])
        return index

    for triangle, ids in enumerate(triangles):
        ids = tuple(ids)
        d0, d1, d2 = distances[ids[0]], distances[ids[1]], distances[ids[2]]
        low, high = min(d0, d1, d2), max(d0, d1, d2)
        first_band = math.floor(low / step)
        last_band = math.floor(high / step)
        initial = [[d0, 1.0, 0.0, 0.0], [d1, 0.0, 1.0, 0.0], [d2, 0.0, 0.0, 1.0]]
        if first_band == last_band and low >= first_band * step and high <= (first_band + 1) * step:
            # Inside one band: both clips keep it whole, and it is its own triangle.
            polygons = [initial]
        else:
            polygons = [_clip_polygon(_clip_polygon(initial, band * step, True), (band + 1) * step, False)
                        for band in range(first_band, last_band + 1)]
        for polygon in polygons:
            for j in range(1, len(polygon) - 1):
                c0, c1, c2 = polygon[0], polygon[j], polygon[j + 1]
                u = (c1[1] - c0[1], c1[2] - c0[2], c1[3] - c0[3])
                v = (c2[1] - c0[1], c2[2] - c0[2], c2[3] - c0[3])
                # A zero-area sliver at an exact band boundary is no surface triangle.
                if _length(_cross(u, v)) < 1e-12:
                    continue
                source_triangles.append(triangle)
                if len(source_triangles) > MAX_REFINED_TRIANGLES:
                    _fail(f"refined tube exceeds {MAX_REFINED_TRIANGLES} triangles; increase maxSegmentLength")
                out_indices.append(vertex(ids, c0))
                out_indices.append(vertex(ids, c1))
                out_indices.append(vertex(ids, c2))
    return RestMesh(
        positions=np.array(out_positions, dtype=np.float32).reshape(-1, 3),
        normals=np.array(out_normals, dtype=np.float32).reshape(-1, 3),
        indices=np.array(out_indices, dtype=np.uint32),
        source_triangles=np.array(source_triangles, dtype=np.uint32),
    )


@dataclass
class RestMapping:
    """Each distinct rest vertex against the rest centerline -- [arc-length
    fraction, transverse u, transverse v] -- and each vertex's row."""

    values: np.ndarray  # (k, 3) float64
    slots: np.ndarray  # (v,) int64


def mapping_for(mesh: RestMesh, rest: Path) -> RestMapping:
    """Every vertex decomposed against the rest centerline. A vertex past the
    centre of the rest's curvature has no one place on it, and is refused."""
    positions = mesh.positions.astype(np.float64)
    first, slots = _unique_rows(positions)
    projected = project_points(rest, positions[first])
    frames = projected.frames
    offset = frames.normal * projected.transverse[:, 0:1] + frames.binormal * projected.transverse[:, 1:2]
    metric = 1 - (0.0 + frames.curvature[:, 0] * offset[:, 0] + frames.curvature[:, 1] * offset[:, 1]
                  + frames.curvature[:, 2] * offset[:, 2])
    if np.any(metric <= EPS):
        _fail("rest mesh crosses the centerline curvature radius")
    values = np.column_stack([projected.distance / rest.length, projected.transverse[:, 0], projected.transverse[:, 1]])
    return RestMapping(values, slots)
