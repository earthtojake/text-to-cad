"""Bake a model's clips (``cadgen.animation``) into sidecar keyframes.

A clip runs ONCE, here, when its model builds: ``update(t, m)`` at every sample
time, against the built tree's occurrence table. What ships is data — the
``animation`` section of the model's sidecar. Its keys are glTF's: every renderer
and the animated GLB export play them as glTF's samplers do, so nothing downstream
works out a motion of its own::

    {"clips": [{"id", "label", "duration", "loop", "tracks": [<track>, ...]}, ...]}

The clips keep the order ``animation=`` declares them in; the first is the one
a viewer opens on.

A track drives one CHANNEL of a set of leaf occurrences (document ids) that it
moves alike, to far finer than a key is written at. ``times`` start at 0, rise
strictly, and end at or before ``duration``; each channel carries one value per
time:

    transform  [d, q, d', q']: 14 numbers      the track's "pivot" moves by d while
                                              the part turns by q about it: the
                                              matrix is T(pivot + d) R(q) T(-pivot),
                                              a glTF node at pivot + d turned by q
                                              over a child at -pivot. Between keys
                                              they follow glTF's CUBICSPLINE
                                              sampler: each component a cubic
                                              Hermite curve through the keys' values
                                              and their rates d' (mm/s) and q' (per
                                              s), q normalized. The pivot is the
                                              point whose path accelerates least:
                                              on a spinning part's axis. The rest
                                              pose is the identity, and a rigid move
                                              premultiplies whatever the kinematics
                                              put there
    opacity    0..1 | null                     lerp between numbers; null is the
                                              material's own, held
    visible    true | false | null             held; null is the rest state
    tube       {"path", "twistDeg"} | null     the path is {"normal", "segments"}, or
                                              {"normal", "map"}: the track's rest
                                              under the affine map p -> A p + b, its
                                              rows [a, a, a, b] in turn (a centerline
                                              that is one, as a spring compressing
                                              along its axis; never over arcs); null
                                              is the rest. A key poses the tube's
                                              glTF skin (``tube_skin``): joints along
                                              the centerline, which lerp and slerp
                                              between keys. The track also carries
                                              "rest", "maxSegmentLength" (the most
                                              rest arc length between two joints)
                                              and, for a braided finish, "braid",
                                              constant through a clip

A key interpolation rebuilds within tolerance is dropped (Ramer-Douglas-Peucker
over each track, under the interpolation a player does), and a track whose keys
are all one value keeps one key. A
transform's tolerance is a fraction of the model's diagonal, measured at the
corners of the box of the parts the track moves (the model's box where the
store remembers none for one of them): two rigid transforms differ by an affine
map, whose largest displacement over a box is at a corner, so the corners bound
the error over every point of those parts. A part turns at most 120 degrees between
two kept keys, and each key's quaternion is on the side of the one before, so the
curve between them never takes the long way round. A hold -- one value at two
samples running, on any channel -- keeps its first and last samples as keys and
nothing between them, its keys' rates zero, so a renderer has nothing to redraw
through it. A tube's
tolerance is measured on points along its centerline and on how far its
cross-sections turn, and then on its skin's joints: an interval whose middle sample
the joints' interpolation misses gets a key there (:func:`_refine_tube_keys`).
"""

from __future__ import annotations

import bisect
import contextlib
import hashlib
import json
import math
import struct
from typing import Any, Iterable, Mapping, Sequence

CHANNELS = ("transform", "opacity", "visible", "tube")

# Transform error, as a fraction of the model's bounding-box diagonal, under which
# a key is dropped: a tenth of a pixel with the whole model in view, and a pixel
# zoomed in tenfold -- measured at the corners of the moving parts' own box, the
# worst lever arm they have. The floor is the rounding the keys are written at.
TRANSFORM_TOLERANCE = 1e-4
LENGTH_FLOOR = 1e-4
OPACITY_TOLERANCE = 1.0 / 512.0
# How far a tube's cross-sections may turn from where the clip put them: its
# twist, and its path's normal (the seed of its frame).
TUBE_TURN_TOLERANCE_DEG = 0.1
# A quaternion's sign is chosen to continue the one before it: a part that turns
# further than this between two samples could be turning either way, and its
# keys would not say which.
MAX_SAMPLE_TURN_DEG = 90.0
# Two kept keys turn less than this apart, well short of the half turn at which
# "the turn from one key to the next" stops being one rotation.
MAX_KEY_TURN_DEG = 120.0

_LENGTH_DIGITS = 4
_QUATERNION_DIGITS = 7
_MAP_DIGITS = 9  # a tube map's linear part, applied about the centerline's middle
_TIME_DIGITS = 6
_OPACITY_DIGITS = 4

_SEGMENT_FIELDS = {
    "line": ("start", "end"),
    "arc": ("center", "axis", "start", "sweepDeg"),
    "bezier": ("points",),
}


class AnimationError(ValueError):
    """A clip that cannot be baked: a bad target, effect or value."""


# --- Rigid transforms ----------------------------------------------------------
#
# A transform is a 12-tuple: the rotation row-major, then the translation. Every
# effect a clip can apply is rigid, which is what lets a key be written as a
# translation and a quaternion and interpolated without shearing.

_IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


def _is_identity(t: tuple) -> bool:
    return max(abs(a - b) for a, b in zip(t, _IDENTITY)) < 1e-12


def _compose(a: tuple, b: tuple) -> tuple:
    """``a`` after ``b``."""
    a0, a1, a2, a3, a4, a5, a6, a7, a8, ax, ay, az = a
    b0, b1, b2, b3, b4, b5, b6, b7, b8, bx, by, bz = b
    return (
        a0 * b0 + a1 * b3 + a2 * b6, a0 * b1 + a1 * b4 + a2 * b7, a0 * b2 + a1 * b5 + a2 * b8,
        a3 * b0 + a4 * b3 + a5 * b6, a3 * b1 + a4 * b4 + a5 * b7, a3 * b2 + a4 * b5 + a5 * b8,
        a6 * b0 + a7 * b3 + a8 * b6, a6 * b1 + a7 * b4 + a8 * b7, a6 * b2 + a7 * b5 + a8 * b8,
        a0 * bx + a1 * by + a2 * bz + ax, a3 * bx + a4 * by + a5 * bz + ay, a6 * bx + a7 * by + a8 * bz + az,
    )


def _rotation(axis: tuple, degrees: float, origin: tuple) -> tuple:
    x, y, z = axis
    angle = math.radians(degrees)
    c, s = math.cos(angle), math.sin(angle)
    k = 1.0 - c
    r = (
        c + x * x * k, x * y * k - z * s, x * z * k + y * s,
        y * x * k + z * s, c + y * y * k, y * z * k - x * s,
        z * x * k - y * s, z * y * k + x * s, c + z * z * k,
    )
    ox, oy, oz = origin
    return r + (
        ox - (r[0] * ox + r[1] * oy + r[2] * oz),
        oy - (r[3] * ox + r[4] * oy + r[5] * oz),
        oz - (r[6] * ox + r[7] * oy + r[8] * oz),
    )


def _quaternion(t: tuple) -> tuple[float, float, float, float]:
    """(x, y, z, w) of a transform's rotation."""
    r00, r01, r02, r10, r11, r12, r20, r21, r22 = t[:9]
    trace = r00 + r11 + r22
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        q = ((r21 - r12) * s, (r02 - r20) * s, (r10 - r01) * s, 0.25 / s)
    elif r00 > r11 and r00 > r22:
        s = 2.0 * math.sqrt(1.0 + r00 - r11 - r22)
        q = (0.25 * s, (r01 + r10) / s, (r02 + r20) / s, (r21 - r12) / s)
    elif r11 > r22:
        s = 2.0 * math.sqrt(1.0 + r11 - r00 - r22)
        q = ((r01 + r10) / s, 0.25 * s, (r12 + r21) / s, (r02 - r20) / s)
    else:
        s = 2.0 * math.sqrt(1.0 + r22 - r00 - r11)
        q = ((r02 + r20) / s, (r12 + r21) / s, 0.25 * s, (r10 - r01) / s)
    n = math.sqrt(sum(c * c for c in q))
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def _rotation_of(q: Sequence[float]) -> tuple:
    x, y, z, w = q
    return (
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
    )


def _pose_at(a: Sequence[float], b: Sequence[float], span: float, u: float) -> tuple[list[float], tuple]:
    """(d, rotation) a fraction ``u`` of the way between two transform keys ``span``
    seconds apart, as glTF's CUBICSPLINE sampler draws it: each component a cubic
    Hermite curve through the keys' values and tangents, the quaternion normalized."""
    u2 = u * u
    u3 = u2 * u
    h00, h10, h01, h11 = 2 * u3 - 3 * u2 + 1, u3 - 2 * u2 + u, 3 * u2 - 2 * u3, u3 - u2
    c = [h00 * a[n] + h10 * span * a[7 + n] + h01 * b[n] + h11 * span * b[7 + n] for n in range(7)]
    size = math.sqrt(c[3] * c[3] + c[4] * c[4] + c[5] * c[5] + c[6] * c[6])
    return c[:3], _rotation_of([c[3] / size, c[4] / size, c[5] / size, c[6] / size])


def _turn_deg(a: Sequence[float], b: Sequence[float]) -> float:
    dot = abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3])
    return math.degrees(2.0 * math.acos(min(1.0, dot)))


# --- Values a clip passes ------------------------------------------------------


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        try:
            value = float(value)  # numpy scalars and the like
        except (TypeError, ValueError):
            raise AnimationError(f"{name} must be a finite number, got {value!r}") from None
        if not math.isfinite(value):
            raise AnimationError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _vec3(value: object, name: str) -> tuple[float, float, float]:
    try:
        items = list(value)  # type: ignore[arg-type]
    except TypeError:
        raise AnimationError(f"{name} must be three numbers, got {value!r}") from None
    if len(items) != 3:
        raise AnimationError(f"{name} must be three numbers, got {value!r}")
    return tuple(_number(item, name) for item in items)  # type: ignore[return-value]


def _unit(value: object, name: str) -> tuple[float, float, float]:
    x, y, z = _vec3(value, name)
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-12:
        raise AnimationError(f"{name} must be a nonzero vector, got {value!r}")
    return (x / n, y / n, z / n)


def _rigid(matrix: object) -> tuple:
    try:
        rows = [list(row) for row in matrix]  # type: ignore[union-attr]
    except TypeError:
        raise AnimationError(f"transform needs a 4x4 matrix, got {matrix!r}") from None
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        raise AnimationError("transform needs a 4x4 matrix (four rows of four)")
    m = [[_number(value, "transform matrix entry") for value in row] for row in rows]
    if max(abs(m[3][0]), abs(m[3][1]), abs(m[3][2]), abs(m[3][3] - 1.0)) > 1e-9:
        raise AnimationError("transform matrix's last row must be 0, 0, 0, 1")
    r = (m[0][0], m[0][1], m[0][2], m[1][0], m[1][1], m[1][2], m[2][0], m[2][1], m[2][2])
    for i in range(3):
        for j in range(3):
            dot = r[i * 3] * r[j * 3] + r[i * 3 + 1] * r[j * 3 + 1] + r[i * 3 + 2] * r[j * 3 + 2]
            if abs(dot - (1.0 if i == j else 0.0)) > 1e-6:
                raise AnimationError("transform matrix must be rigid: its rotation is not orthonormal (no scale or shear)")
    det = r[0] * (r[4] * r[8] - r[5] * r[7]) - r[1] * (r[3] * r[8] - r[5] * r[6]) + r[2] * (r[3] * r[7] - r[4] * r[6])
    if det < 0.0:
        raise AnimationError("transform matrix must be rigid: it mirrors")
    return r + (m[0][3], m[1][3], m[2][3])


def _tube_path(value: object, name: str) -> dict[str, Any]:
    """The shape of a tube centerline, checked and copied; its geometry (segments
    meeting with matching tangents) is the renderer's tube runtime's to judge."""
    if not isinstance(value, Mapping) or set(value) != {"normal", "segments"}:
        raise AnimationError(f"{name} must be {{'normal': [x, y, z], 'segments': [...]}}")
    segments = value["segments"]
    if not isinstance(segments, (list, tuple)) or not segments:
        raise AnimationError(f"{name}['segments'] must be a nonempty list")
    out = []
    for index, segment in enumerate(segments):
        where = f"{name}['segments'][{index}]"
        kind = segment.get("kind") if isinstance(segment, Mapping) else None
        fields = _SEGMENT_FIELDS.get(kind)  # type: ignore[arg-type]
        if fields is None:
            raise AnimationError(f"{where} kind must be one of {', '.join(_SEGMENT_FIELDS)}")
        if set(segment) != {"kind", *fields}:
            raise AnimationError(f"{where} ({kind}) takes exactly: {', '.join(fields)}")
        entry: dict[str, Any] = {"kind": kind}
        for field in fields:
            if field == "sweepDeg":
                entry[field] = _number(segment[field], f"{where} sweepDeg")
            elif field == "points":
                points = list(segment[field])
                if len(points) != 4:
                    raise AnimationError(f"{where} points must be four control points")
                entry[field] = [list(_vec3(point, f"{where} point")) for point in points]
            else:
                entry[field] = list(_vec3(segment[field], f"{where} {field}"))
        out.append(entry)
    return {"normal": list(_unit(value["normal"], f"{name}['normal']")), "segments": out}


def _braid(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"pitch", "depth", "strands"}:
        raise AnimationError("braid must be {'pitch', 'depth', 'strands'}")
    pitch, depth, strands = _number(value["pitch"], "braid pitch"), _number(value["depth"], "braid depth"), value["strands"]
    if pitch <= 0 or depth < 0 or isinstance(strands, bool) or not isinstance(strands, int) or not 2 <= strands <= 64 or strands % 2:
        raise AnimationError("braid needs a positive pitch, a nonnegative depth and an even strand count from 2 to 64")
    return {"pitch": pitch, "depth": depth, "strands": strands}


# --- What a clip targets ---------------------------------------------------------


def _natural(occurrence_id: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in occurrence_id.lstrip("o").split("."))


class AnimationTargets:
    """The names and ids a clip's ``m.get`` resolves, each to document leaves."""

    def __init__(self, by_id: Mapping[str, Sequence[str]], by_name: Mapping[str, Sequence[str]]):
        self._by_id = {key: tuple(value) for key, value in by_id.items()}
        self._by_name = {key: tuple(value) for key, value in by_name.items()}
        self._resolved: dict[str, tuple[str, ...]] = {}

    def labels(self) -> list[str]:
        return sorted(self._by_name)

    def resolve(self, target: object) -> tuple[str, ...]:
        key = target if isinstance(target, str) else None
        cached = self._resolved.get(key) if key is not None else None
        if cached is not None:
            return cached
        if not isinstance(target, str) or not target.startswith("#") or not target[1:].strip():
            raise AnimationError(f"animation target {target!r} must be a #name or an #o1.2 occurrence id")
        selector = target[1:].strip()
        if selector in self._by_id:
            leaves = self._by_id[selector]
        else:
            leaves = tuple(dict.fromkeys(
                leaf for node in self._by_name.get(selector, ()) for leaf in self._by_id.get(node, ())
            ))
        if not leaves:
            known = ", ".join(f"#{name}" for name in self.labels()[:20]) or "(none)"
            more = " ..." if len(self._by_name) > 20 else ""
            raise AnimationError(f"animation target {target!r} names no part or group; names: {known}{more}")
        self._resolved[target] = leaves
        return leaves


def animation_targets(descriptor: Mapping[str, Any]) -> AnimationTargets:
    """Targets over a descriptor (an ``assembly.json``): its node names and ids,
    each resolving to the leaf occurrences beneath it."""
    from cadgen._internal.source_sidecar import _descriptor_nodes

    by_id, by_name = _descriptor_nodes(descriptor)
    return AnimationTargets(by_id, by_name)


# --- One sample ----------------------------------------------------------------


class _Frame:
    __slots__ = ("transform", "opacity", "visible", "tube")

    def __init__(self) -> None:
        self.transform: dict[str, tuple] = {}
        self.opacity: dict[str, float] = {}
        self.visible: dict[str, bool] = {}
        self.tube: dict[str, dict[str, Any]] = {}


class Handle:
    """The parts one ``m.get`` names. Every method returns the handle."""

    __slots__ = ("_frame", "_leaves")

    def __init__(self, frame: _Frame, leaves: tuple[str, ...]) -> None:
        self._frame = frame
        self._leaves = leaves

    def _apply(self, op: tuple) -> "Handle":
        transforms = self._frame.transform
        for leaf in self._leaves:
            current = transforms.get(leaf)
            transforms[leaf] = op if current is None else _compose(op, current)
        return self

    def rotate(self, axis: object, degrees: object, origin: object = (0.0, 0.0, 0.0)) -> "Handle":
        return self._apply(_rotation(_unit(axis, "rotate axis"), _number(degrees, "rotate degrees"), _vec3(origin, "rotate origin")))

    def translate(self, vector: object) -> "Handle":
        return self._apply(_IDENTITY[:9] + _vec3(vector, "translate vector"))

    def transform(self, matrix: object) -> "Handle":
        return self._apply(_rigid(matrix))

    def opacity(self, value: object) -> "Handle":
        value = min(1.0, max(0.0, _number(value, "opacity")))
        for leaf in self._leaves:
            self._frame.opacity[leaf] = value
        return self

    def visible(self, flag: object) -> "Handle":
        for leaf in self._leaves:
            self._frame.visible[leaf] = bool(flag)
        return self

    def deform_tube(
        self,
        *,
        rest: object,
        path: object,
        twist_deg: object = 0.0,
        max_segment_length: object = 1.0,
        braid: object = None,
    ) -> "Handle":
        segment = _number(max_segment_length, "deform_tube max_segment_length")
        if segment < 0.05:
            raise AnimationError("deform_tube max_segment_length must be at least 0.05 mm")
        spec = {
            "rest": _tube_path(rest, "deform_tube rest"),
            "path": _tube_path(path, "deform_tube path"),
            "twistDeg": _number(twist_deg, "deform_tube twist_deg"),
            "maxSegmentLength": segment,
            "braid": _braid(braid),
        }
        for leaf in self._leaves:
            self._frame.tube[leaf] = spec
        return self


class Model:
    """The ``m`` a clip's ``update(t, m)`` receives."""

    __slots__ = ("_frame", "_targets")

    def __init__(self, frame: _Frame, targets: AnimationTargets) -> None:
        self._frame = frame
        self._targets = targets

    def get(self, *targets: str) -> Handle:
        if not targets:
            raise AnimationError("m.get needs at least one #name or #occurrence id")
        if len(targets) == 1:
            return Handle(self._frame, self._targets.resolve(targets[0]))
        leaves = dict.fromkeys(leaf for target in targets for leaf in self._targets.resolve(target))
        return Handle(self._frame, tuple(leaves))

    def labels(self) -> list[str]:
        return self._targets.labels()


# --- Keyframe reduction --------------------------------------------------------


def _keep(count: int, error, tolerance: float, forced: Iterable[int] = (), reach=None) -> list[int]:
    """The sample indices to keep: both ends, every forced index, and enough
    between them that interpolating the kept samples rebuilds each dropped one
    within ``tolerance`` (``error(i, j, k)``: sample k's error between keys i, j).
    ``reach(i, j)``, when given, is the farthest sample before ``j`` that key
    ``i`` may span to, or None when it may span to ``j`` itself."""
    if count <= 2:
        return list(range(count))
    keep = {0, count - 1, *forced}
    anchors = sorted(keep)
    stack = list(zip(anchors, anchors[1:]))
    while stack:
        i, j = stack.pop()
        split = reach(i, j) if reach is not None else None
        if split is None:
            worst, split = tolerance, None
            for k in range(i + 1, j):
                e = error(i, j, k)
                if e > worst:
                    worst, split = e, k
        if split is not None:
            keep.add(split)
            stack += [(i, split), (split, j)]
    return sorted(keep)


def _corners(bounds: Sequence[Sequence[float]]) -> list[tuple[float, float, float]]:
    (x0, y0, z0), (x1, y1, z1) = bounds
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def _apply_point(r: Sequence[float], t: Sequence[float], p: Sequence[float]) -> tuple[float, float, float]:
    return (
        r[0] * p[0] + r[1] * p[1] + r[2] * p[2] + t[0],
        r[3] * p[0] + r[4] * p[1] + r[5] * p[2] + t[1],
        r[6] * p[0] + r[7] * p[1] + r[8] * p[2] + t[2],
    )


def _solve3(a: list[list[float]], b: list[float]) -> list[float]:
    """``a x = b`` by Gaussian elimination with partial pivoting."""
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, 3):
            f = m[r][col] / m[col][col]
            for c in range(col, 4):
                m[r][c] -= f * m[col][c]
    x = [0.0, 0.0, 0.0]
    for r in (2, 1, 0):
        x[r] = (m[r][3] - sum(m[r][c] * x[c] for c in range(r + 1, 3))) / m[r][r]
    return x


def _pivot(values: list[tuple], center: Sequence[float], reach: float) -> tuple[float, float, float]:
    """The point whose path accelerates least: argmin over c of the sum of
    |M_{k+1}(c) - 2 M_k(c) + M_{k-1}(c)|^2.

    A part spinning about an axis, still or carried along, accelerates least on
    that axis, so its keys need only the spin and the carry, each smooth. Where
    the minimum is not one point -- along a still axis, or anywhere for a pure
    translation -- the tie goes to the point nearest ``center``, the middle of
    the parts the track moves. A minimum farther than ``reach`` from it comes of
    a turn too slight to place an axis by (a solver's rounding, say): its key's
    quaternion would be written as no turn at all while d kept the turn's lever
    arm, so ``center`` is the pivot."""
    a = [[0.0] * 3 for _ in range(3)]
    b = [0.0] * 3
    for before, at, after in zip(values, values[1:], values[2:]):
        m = [after[n] - 2.0 * at[n] + before[n] for n in range(12)]
        rows = (m[0:3], m[3:6], m[6:9])
        for i in range(3):
            for j in range(3):
                a[i][j] += rows[0][i] * rows[0][j] + rows[1][i] * rows[1][j] + rows[2][i] * rows[2][j]
            b[i] -= rows[0][i] * m[9] + rows[1][i] * m[10] + rows[2][i] * m[11]
    tie = 1e-9 * (a[0][0] + a[1][1] + a[2][2]) + 1e-30
    for i in range(3):
        a[i][i] += tie
        b[i] += tie * center[i]
    pivot = _solve3(a, b)
    return tuple(pivot) if math.dist(pivot, center) <= reach else tuple(center)  # type: ignore[return-value]


def _transform_keys(
    times: list[float], values: list[tuple], corners: list[tuple], center: Sequence[float], reach: float,
    tolerance: float, where: str,
) -> tuple[list[int], tuple[float, float, float], list[list[float]]]:
    quats: list[tuple] = []
    swept = [0.0]  # degrees turned from the first sample, summed sample by sample
    for index, value in enumerate(values):
        q = _quaternion(value)
        if quats:
            previous = quats[-1]
            if previous[0] * q[0] + previous[1] * q[1] + previous[2] * q[2] + previous[3] * q[3] < 0.0:
                q = (-q[0], -q[1], -q[2], -q[3])  # the same rotation, on the near side
            turn = _turn_deg(previous, q)
            if turn > MAX_SAMPLE_TURN_DEG + 1e-6:
                raise AnimationError(
                    f"{where} turns {turn:.0f} degrees between the samples at "
                    f"{times[index - 1]:g} s and {times[index]:g} s: raise the clip's fps"
                )
            swept.append(swept[-1] + turn)
        quats.append(q)
    pivot = tuple(_length(c) for c in _pivot(values, center, reach))
    # Each sample's key: d (where the pivot goes: M(pivot) - pivot) and q.
    # Each sample's key: d (where the pivot goes: M(pivot) - pivot), q, and their
    # rates -- central differences, one-sided at the ends, and none beside a HOLD
    # (the same pose two samples running): a part enters and leaves a hold at rest,
    # and a central difference straddling one would carry half the move's speed into
    # it.
    moves = [[m - p for m, p in zip(_apply_point(v, v[9:], pivot), pivot)] for v in values]
    last = len(values) - 1
    still = [k > 0 and values[k - 1] == values[k] for k in range(len(values))] + [False]
    keys = []
    for k in range(len(values)):
        if still[k] or still[k + 1]:
            tangent = [0.0] * 7
        else:
            i, j = max(0, k - 1), min(last, k + 1)
            span = times[j] - times[i]
            ends = (moves[i] + list(quats[i]), moves[j] + list(quats[j]))
            tangent = [(ends[1][n] - ends[0][n]) / span for n in range(7)]
        keys.append([*moves[k], *quats[k], *tangent])
    truth = [[_apply_point(value, value[9:], corner) for corner in corners] for value in values]
    arms = [tuple(c - p for c, p in zip(corner, pivot)) for corner in corners]

    def error(i: int, j: int, k: int) -> float:
        span = times[j] - times[i]
        d, r = _pose_at(keys[i], keys[j], span, (times[k] - times[i]) / span)
        at = (pivot[0] + d[0], pivot[1] + d[1], pivot[2] + d[2])
        return max(math.dist(_apply_point(r, at, arm), true) for arm, true in zip(arms, truth[k]))

    def reach(i: int, j: int) -> int | None:
        # The SWEPT turn, not the net one: a whole revolution between two keys
        # nets nothing and must still be split.
        if swept[j] - swept[i] <= MAX_KEY_TURN_DEG:
            return None
        return bisect.bisect_right(swept, swept[i] + MAX_KEY_TURN_DEG, i + 1, j) - 1

    keep = _keep(len(values), error, tolerance, forced=_holds(values), reach=reach)
    digits = ((_LENGTH_DIGITS,) * 3 + (_QUATERNION_DIGITS,) * 4) * 2
    return keep, pivot, [[_round(c, digits[n]) for n, c in enumerate(keys[k])] for k in keep]


def _lerp_path(a: Mapping[str, Any], b: Mapping[str, Any], u: float) -> dict[str, Any]:
    """Every number of two same-shaped centerlines, lerped: what every renderer does."""

    def lerp3(p: Sequence[float], q: Sequence[float]) -> list[float]:
        return [p[n] + (q[n] - p[n]) * u for n in range(3)]

    segments = []
    for one, other in zip(a["segments"], b["segments"]):
        segment: dict[str, Any] = {"kind": one["kind"]}
        for field in _SEGMENT_FIELDS[one["kind"]]:
            if field == "sweepDeg":
                segment[field] = one[field] + (other[field] - one[field]) * u
            elif field == "points":
                segment[field] = [lerp3(p, q) for p, q in zip(one[field], other[field])]
            else:
                segment[field] = lerp3(one[field], other[field])
        segments.append(segment)
    return {"normal": lerp3(a["normal"], b["normal"]), "segments": segments}


def _path_points(path: Mapping[str, Any]) -> list[tuple[float, float, float]]:
    """Points ON a centerline, at fixed fractions of each segment: what a tube
    error is measured on (an arc's center, say, is not on the tube at all)."""
    points = []
    for segment in path["segments"]:
        kind = segment["kind"]
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            if kind == "line":
                s, e = segment["start"], segment["end"]
                points.append(tuple(s[n] + (e[n] - s[n]) * f for n in range(3)))
            elif kind == "arc":
                turn = _rotation(_unit(segment["axis"], "arc axis"), segment["sweepDeg"] * f, tuple(segment["center"]))
                points.append(_apply_point(turn, turn[9:], segment["start"]))
            else:
                p0, p1, p2, p3 = segment["points"]
                g = 1.0 - f
                points.append(tuple(
                    g * g * g * p0[n] + 3 * g * g * f * p1[n] + 3 * g * f * f * p2[n] + f * f * f * p3[n] for n in range(3)
                ))
    return points


def _angle_deg(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _shape(key: Mapping[str, Any] | None) -> tuple | None:
    return None if key is None else tuple(segment["kind"] for segment in key["path"]["segments"])


def _holds(values: list[Any]) -> list[int]:
    """The first and last sample of every HOLD -- one value at two samples running --
    which stay keys: between two keys of one value nothing moves, so a hold costs its
    two ends and a renderer has nothing to redraw through it. Left to the splitting,
    a segment that runs from a hold into a move strays through the hold, and each
    split lands in it nearer the move."""
    still = [k > 0 and values[k - 1] == values[k] for k in range(len(values))] + [False]
    return [k for k in range(len(values)) if still[k] != still[k + 1]]


def _runs(values: list[Any], kind) -> list[int]:
    """Indices that must stay keys because the value's kind changes there: the
    last sample of one kind and the first of the next."""
    forced: list[int] = []
    for k in range(1, len(values)):
        if kind(values[k]) != kind(values[k - 1]):
            forced += [k - 1, k]
    return forced


def _round(value: float, digits: int) -> float:
    return round(value, digits) + 0.0  # never -0.0


def _length(value: float) -> float:
    return _round(value, _LENGTH_DIGITS)


def _rounded_tube(key: Mapping[str, Any]) -> dict[str, Any]:
    path = key["path"]
    segments = []
    for segment in path["segments"]:
        entry: dict[str, Any] = {"kind": segment["kind"]}
        for field in _SEGMENT_FIELDS[segment["kind"]]:
            value = segment[field]
            if field == "points":
                entry[field] = [[_length(c) for c in point] for point in value]
            elif field == "sweepDeg":
                entry[field] = _length(value)
            else:
                entry[field] = [_length(c) for c in value]
        segments.append(entry)
    return {"path": {"normal": [_round(c, _QUATERNION_DIGITS) for c in path["normal"]], "segments": segments}, "twistDeg": _length(key["twistDeg"])}


def _defining_points(path: Mapping[str, Any]) -> list[Sequence[float]]:
    """Every point a line-and-Bezier centerline is defined by, segment by segment."""
    points: list[Sequence[float]] = []
    for segment in path["segments"]:
        points += [segment["start"], segment["end"]] if segment["kind"] == "line" else segment["points"]
    return points


def _mapped(rest: Mapping[str, Any], normal: Sequence[float], m: Sequence[float]) -> dict[str, Any]:
    """``rest`` under the affine map ``m`` (its three rows, each a, a, a, b). A line or
    a Bezier maps to the line or Bezier through the images of its points."""

    def image(p: Sequence[float]) -> list[float]:
        return [m[4 * i] * p[0] + m[4 * i + 1] * p[1] + m[4 * i + 2] * p[2] + m[4 * i + 3] for i in range(3)]

    segments = [
        {"kind": "line", "start": image(segment["start"]), "end": image(segment["end"])} if segment["kind"] == "line"
        else {"kind": "bezier", "points": [image(point) for point in segment["points"]]}
        for segment in rest["segments"]
    ]
    return {"normal": list(normal), "segments": segments}


def key_path(rest: Mapping[str, Any], path: Mapping[str, Any]) -> Mapping[str, Any]:
    """A tube key's centerline: its own segments, or its track's rest under its map."""
    return _mapped(rest, path["normal"], path["map"]) if "map" in path else path


def _map_onto(rest: Mapping[str, Any], path: Mapping[str, Any]) -> list[float] | None:
    """The affine map that takes ``rest`` onto ``path``, rounded as written, when one
    does to the rounding keys are written at and is shorter than the path's points:
    a coil spring compressing along its axis, a tube carried whole. None otherwise;
    arcs never map, as an arc's affine image is in general no arc. The rest is
    written rounded and the map's offset is rounded again, so a mapped key may sit
    twice a key's rounding from the clip's path."""
    shape = [segment["kind"] for segment in rest["segments"]]
    if "arc" in shape or shape != [segment["kind"] for segment in path["segments"]]:
        return None
    source, target = _defining_points(rest), _defining_points(path)
    if 3 * len(source) <= 12:
        return None
    # Least squares about the two middles, held toward the identity so that a rest in a
    # plane or on a line still has one map: argmin |M (p - c) - (q - d)|^2 + e |M - I|^2.
    count = len(source)
    c = [sum(p[i] for p in source) / count for i in range(3)]
    d = [sum(q[i] for q in target) / count for i in range(3)]
    pp = [[0.0] * 3 for _ in range(3)]
    pq = [[0.0] * 3 for _ in range(3)]
    for p, q in zip(source, target):
        u, v = [p[i] - c[i] for i in range(3)], [q[i] - d[i] for i in range(3)]
        for i in range(3):
            for j in range(3):
                pp[i][j] += u[i] * u[j]
                pq[i][j] += u[i] * v[j]
    e = 1e-12 * (pp[0][0] + pp[1][1] + pp[2][2]) + 1e-30
    for i in range(3):
        pp[i][i] += e
        pq[i][i] += e
    m: list[float] = []
    for i in range(3):
        row = [_round(x, _MAP_DIGITS) for x in _solve3(pp, [pq[k][i] for k in range(3)])]
        m += [*row, _length(d[i] - (row[0] * c[0] + row[1] * c[1] + row[2] * c[2]))]
    mapped = _mapped(rest, path["normal"], m)
    if max(math.dist(p, q) for p, q in zip(_path_points(mapped), _path_points(path))) > 2 * LENGTH_FLOOR:
        return None
    return m


def _tube_key(key: Mapping[str, Any] | None, rest: Mapping[str, Any]) -> dict[str, Any] | None:
    """A tube key as written: its centerline as its track's rest under a map where one
    takes the rest onto it (``_map_onto``), else its own segments."""
    if key is None:
        return None
    written = _rounded_tube(key)
    m = _map_onto(rest, key["path"])
    if m is not None:
        written["path"] = {"normal": written["path"]["normal"], "map": m}
    return written


# --- A clip, end to end ----------------------------------------------------------


def sample_times(duration: float, fps: float) -> list[float]:
    """0, 1/fps, ... and ``duration`` itself: the last pose is always sampled. Times are
    written to :data:`_TIME_DIGITS` places, so a sample that would be written at the time
    of the one before it is not taken, and the last is the duration as written."""
    count = max(1, math.ceil(duration * fps - 1e-9))
    times: list[float] = []
    for t in [index / fps for index in range(count)]:
        if not times or _round(t, _TIME_DIGITS) > _round(times[-1], _TIME_DIGITS):
            times.append(t)
    if times and _round(times[-1], _TIME_DIGITS) >= _round(duration, _TIME_DIGITS):
        times.pop()
    return times + [duration]


def _signature(channel: str, value: Any) -> Any:
    """What two leaves' samples must share for the leaves to share a track: a
    transform's rotation to a billionth and its translation to a millionth of a
    millimetre, an opacity to a millionth -- far finer than a key is written at,
    and coarse enough that a part a clip moves through its parent's numbers and
    one it moves through the same numbers recomputed are one track."""
    if channel == "transform":
        return tuple(round(c, 9) for c in value[:9]) + tuple(round(c, 6) for c in value[9:])
    if channel == "opacity" and value is not None:
        return round(value, 6)
    return value


def bake_clip(
    clip_id: str, clip: Any, targets: AnimationTargets, bounds: Sequence[Sequence[float]], leaf_boxes: Any = None,
) -> dict[str, Any]:
    """Sample one :class:`cadgen.animation.Clip` and reduce it to tracks. ``leaf_boxes``
    (``get(leaf)`` -> (min, max) or None) gives each part's own box, where a track's
    error is measured; without it, or for a part it has no box for, the model's."""
    # The duration as the sidecar writes it, so its last key is its end.
    duration = _round(clip.duration, _TIME_DIGITS)
    if duration <= 0:
        raise AnimationError(f"animation clip {clip_id!r}: its duration {clip.duration:g} s is shorter than "
                             f"the {10.0 ** -_TIME_DIGITS:g} s a key's time is written to; make it longer")
    times = sample_times(duration, clip.fps)
    frames: list[_Frame] = []
    # Each distinct transform and tube centerline once, bit for bit: a clip that poses
    # each part afresh every sample repeats a few thousand values over millions of
    # entries (radial's explode: 1.5 million transforms, 23,000 values), a tube's rest
    # is the same at every sample, and the samples are held whole until every track is
    # reduced -- a large assembly's parent build held a gigabyte of copies.
    poses: dict[bytes, tuple] = {}
    centerlines: dict[bytes, dict[str, Any]] = {}

    def centerline(path: dict[str, Any]) -> dict[str, Any]:
        return centerlines.setdefault(hashlib.sha256(json.dumps(path, sort_keys=True).encode()).digest(), path)

    def shared_tubes(tubes: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        by_spec: dict[int, tuple[dict, dict]] = {}  # one m.get's leaves share a spec: keep sharing it
        for spec in tubes.values():
            if id(spec) not in by_spec:
                by_spec[id(spec)] = (spec, {**spec, "rest": centerline(spec["rest"]), "path": centerline(spec["path"])})
        return {leaf: by_spec[id(spec)][1] for leaf, spec in tubes.items()}
    for t in times:
        frame = _Frame()
        try:
            clip.update(t, Model(frame, targets))
        except AnimationError as exc:
            raise AnimationError(f"animation clip {clip_id!r} at t={t:g} s: {exc}") from None
        except Exception as exc:
            raise AnimationError(f"animation clip {clip_id!r} at t={t:g} s: {type(exc).__name__}: {exc}") from exc
        frame.transform = {leaf: poses.setdefault(struct.pack(f"<{len(value)}d", *value), value)
                           for leaf, value in frame.transform.items()}
        if frame.tube:
            frame.tube = shared_tubes(frame.tube)
        frames.append(frame)

    diagonal = math.dist(bounds[0], bounds[1])
    tolerance = max(LENGTH_FLOOR, TRANSFORM_TOLERANCE * diagonal)
    corners = _corners(bounds)
    center = tuple((lo + hi) / 2.0 for lo, hi in zip(bounds[0], bounds[1]))
    rounded_times = [_round(t, _TIME_DIGITS) for t in times]
    tracks: list[dict[str, Any]] = []

    def channel(name: str, rest: Any) -> dict[tuple, list[str]]:
        """Leaves grouped by their whole sequence on this channel: parts that move
        alike (``_signature``) share a track. A leaf no sample touched is left out."""
        leaves = dict.fromkeys(leaf for frame in frames for leaf in getattr(frame, name))
        exact: dict[tuple, list[str]] = {}
        for leaf in leaves:
            exact.setdefault(tuple(getattr(frame, name).get(leaf, rest) for frame in frames), []).append(leaf)
        # Rounding is the costly part, so only one sequence of each exact group is rounded.
        groups: dict[tuple, tuple[tuple, list[str]]] = {}
        for sequence, members in exact.items():
            groups.setdefault(tuple(_signature(name, value) for value in sequence), (sequence, []))[1].extend(members)
        return dict(groups.values())

    def measured(leaves: list[str]) -> tuple[list[tuple], tuple]:
        """Where a transform track's error is measured: the corners of the box of the
        parts it moves, which bound the error over every point of them (two rigid
        transforms differ by an affine map), and that box's middle."""
        boxes = [leaf_boxes.get(leaf) for leaf in leaves] if leaf_boxes is not None else [None]
        if any(box is None for box in boxes):
            return corners, center
        low = [min(box[0][axis] for box in boxes) for axis in range(3)]
        high = [max(box[1][axis] for box in boxes) for axis in range(3)]
        return _corners((low, high)), tuple((lo + hi) / 2.0 for lo, hi in zip(low, high))

    for sequence, leaves in channel("transform", _IDENTITY).items():
        if all(value == sequence[0] for value in sequence) and _is_identity(sequence[0]):
            continue  # touched, never moved
        where = f"animation clip {clip_id!r} part {sorted(leaves, key=_natural)[0]}"
        track_corners, track_center = measured(leaves)
        keep, pivot, values = _transform_keys(times, list(sequence), track_corners, track_center, diagonal, tolerance, where)
        track = _track(leaves, rounded_times, keep, "transform", values)
        track["pivot"] = list(pivot)
        tracks.append(track)

    for sequence, leaves in channel("opacity", None).items():
        values = list(sequence)

        def opacity_error(i: int, j: int, k: int) -> float:
            if values[i] is None:  # a run of nulls: _runs anchors both ends, so all null, held
                return 0.0
            u = (times[k] - times[i]) / (times[j] - times[i])
            return abs(values[i] + (values[j] - values[i]) * u - values[k])

        keep = _keep(len(values), opacity_error, OPACITY_TOLERANCE, _runs(values, lambda v: v is None) + _holds(values))
        tracks.append(_track(leaves, rounded_times, keep, "opacity", [
            None if values[k] is None else _round(values[k], _OPACITY_DIGITS) for k in keep
        ]))

    for sequence, leaves in channel("visible", None).items():
        values = list(sequence)
        keep = [0] + [k for k in range(1, len(values)) if values[k] != values[k - 1]]
        tracks.append(_track(leaves, rounded_times, keep, "visible", [values[k] for k in keep]))

    tube_sequences: dict[tuple, list[str]] = {}
    tube_specs: dict[tuple, list[dict[str, Any] | None]] = {}
    for leaf in dict.fromkeys(leaf for frame in frames for leaf in frame.tube):
        specs = [frame.tube.get(leaf) for frame in frames]
        constant = {json.dumps([s["rest"], s["maxSegmentLength"], s["braid"]], sort_keys=True) for s in specs if s}
        if len(constant) > 1:
            raise AnimationError(
                f"animation clip {clip_id!r} part {leaf}: a tube's rest path, max_segment_length "
                "and braid must stay the same through a clip; only its path and twist move"
            )
        signature = tuple(None if s is None else json.dumps([s["path"], s["twistDeg"]], sort_keys=True) for s in specs)
        tube_sequences.setdefault(signature, []).append(leaf)
        tube_specs.setdefault(signature, specs)
    for signature, leaves in tube_sequences.items():
        specs = tube_specs[signature]
        keys = [None if s is None else {"path": s["path"], "twistDeg": s["twistDeg"]} for s in specs]
        truth = [None if key is None else _path_points(key["path"]) for key in keys]

        def tube_error(i: int, j: int, k: int) -> float:
            # In tolerances: the centerline's points in mm, and the frame (the
            # path's normal and the twist) in tenths of a degree.
            a, b, c = keys[i], keys[j], keys[k]
            if a is None:  # a run of nulls: _runs anchors both ends, so all null, held
                return 0.0
            u = (times[k] - times[i]) / (times[j] - times[i])
            path = _lerp_path(a["path"], b["path"], u)
            moved = max(math.dist(p, q) for p, q in zip(_path_points(path), truth[k]))
            turned = max(
                abs(a["twistDeg"] + (b["twistDeg"] - a["twistDeg"]) * u - c["twistDeg"]),
                _angle_deg(path["normal"], c["path"]["normal"]),
            )
            return max(moved / tolerance, turned / TUBE_TURN_TOLERANCE_DEG)

        keep = _keep(len(keys), tube_error, 1.0, _runs(keys, _shape) + _holds(keys))
        rest = next(s for s in specs if s)
        rest_path = _rounded_tube({"path": rest["rest"], "twistDeg": 0.0})["path"]
        written = [_tube_key(key, rest_path) for key in keys]
        where = f"animation clip {clip_id!r} part {sorted(leaves, key=_natural)[0]}"
        keep = _refine_tube_keys(keep, written, times, rest_path, rest["maxSegmentLength"], tolerance, where)
        track = _track(leaves, rounded_times, keep, "tube", [written[k] for k in keep])
        track["rest"] = rest_path
        track["maxSegmentLength"] = rest["maxSegmentLength"]
        if rest["braid"] is not None:
            track["braid"] = rest["braid"]
        tracks.append(track)

    tracks.sort(key=lambda track: (CHANNELS.index(_channel_of(track)), _natural(track["targets"][0])))
    return {
        "id": clip_id,
        "label": clip.label or clip_id,
        "duration": duration,
        "loop": clip.loop,
        "tracks": tracks,
    }


def _refine_tube_keys(keep: list[int], written: list[Any], times: list[float], rest_path: Mapping[str, Any],
                      spacing: float, tolerance: float, where: str) -> list[int]:
    """``keep``, with a key added wherever the tube's skin misses: an interval whose
    middle sample the joints' LINEAR interpolation draws further than ``tolerance``
    (mm), or turned further than :data:`TUBE_TURN_TOLERANCE_DEG`, from where that
    sample's own key puts them is split there, and its halves are checked in turn.
    Only middles are compiled, so a clip costs a few paths per kept key. A centerline
    no renderer could draw -- a corner, a gap -- fails here, with the time it is at."""
    from cadgen._internal import tube_deformation, tube_skin

    try:
        rest = tube_skin.compile_rest(rest_path)
    except tube_deformation.TubeDeformationError as error:
        raise AnimationError(f"{where}: its rest path: {error}") from None
    fractions = tube_skin.joint_fractions(rest, spacing)
    cache: dict[int, Any] = {}

    def joints(k: int):
        if k not in cache:
            try:
                cache[k] = tube_skin.key_joints(written[k], rest_path, rest, fractions)
            except tube_deformation.TubeDeformationError as error:
                raise AnimationError(f"{where} at t={times[k]:g} s: {error}") from None
        return cache[k]

    kept = set(keep)
    stack = list(zip(keep, keep[1:]))
    while stack:
        i, j = stack.pop()
        if j - i < 2 or written[i] == written[j] == written[(i + j) // 2]:
            continue
        m = (i + j) // 2
        estimate = tube_skin.between(joints(i), joints(j), (times[m] - times[i]) / (times[j] - times[i]))
        moved, turned = tube_skin.joint_error(estimate, joints(m))
        if moved > tolerance or turned > TUBE_TURN_TOLERANCE_DEG:
            kept.add(m)
            stack += [(i, m), (m, j)]
    # Every path the skin keeps is one a renderer draws, so each is compiled once: a
    # centerline that never moves has no interval above to compile it in, and a corner
    # or gap in it fails here like any other.
    previous = None
    for k in sorted(kept):
        if previous is None or written[k] != written[previous]:
            joints(k)
        previous = k
    return sorted(kept)


def _track(leaves: list[str], times: list[float], keep: list[int], channel: str, values: list[Any]) -> dict[str, Any]:
    # A track whose every key is the same value is that value, held: one key.
    if len(values) > 1 and all(value == values[0] for value in values[1:]):
        keep, values = keep[:1], values[:1]
    return {"targets": sorted(leaves, key=_natural), "times": [times[k] for k in keep], channel: values}


def _channel_of(track: Mapping[str, Any]) -> str:
    return next(name for name in CHANNELS if name in track)


def bake_animation(
    clips: Mapping[str, Any], targets: AnimationTargets, bounds: Sequence[Sequence[float]], leaf_boxes: Any = None,
) -> dict[str, Any]:
    """Every clip of a model, baked: the sidecar's ``animation`` section."""
    return {"clips": [bake_clip(clip_id, clip, targets, bounds, leaf_boxes) for clip_id, clip in clips.items()]}


class _LeafBoxes:
    """Each leaf's box in a written document, from the boxes the store remembered
    when it published it (``composed_bounds``), read when first asked for: a clip
    that moves a few parts of a large model measures only those. None where the
    store remembers no box."""

    def __init__(self, descriptor: Mapping[str, Any]) -> None:
        self._occurrences = {str(occurrence["id"]): occurrence for occurrence in descriptor.get("occurrences") or []}
        self._components = descriptor.get("components") or {}
        self._boxes: dict[str, tuple | None] = {}

    def get(self, leaf: str) -> tuple | None:
        if leaf not in self._boxes:
            from cadgen.store._compose_readback import Ineligible, composed_bounds

            occurrence, box = self._occurrences.get(leaf), None
            if occurrence is not None:
                with contextlib.suppress(Ineligible):
                    found = composed_bounds([occurrence], self._components)
                    box = (found["min"], found["max"])
            self._boxes[leaf] = box
        return self._boxes[leaf]


def bake_document_animation(clips: Mapping[str, Any], document_tree: str) -> dict[str, Any]:
    """Bake against the WRITTEN document's tree: its names, its occurrence ids
    and its bounds are exactly what every renderer of the file holds."""
    from cadgen.store.trees import flatten

    descriptor = flatten(document_tree)
    if descriptor is None:
        raise AnimationError(f"cannot bake animation: document tree {document_tree} is missing")
    bbox = descriptor.get("bbox") or {}
    if not bbox.get("min") or not bbox.get("max"):
        raise AnimationError("cannot bake animation: the model has no geometry to measure")
    return bake_animation(clips, animation_targets(descriptor), (bbox["min"], bbox["max"]), _LeafBoxes(descriptor))


# --- The section, read back ------------------------------------------------------


def _fail(message: str) -> ValueError:
    return ValueError(f"animation: {message}")


def _finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def normalize_baked_animation(block: object) -> dict[str, Any] | None:
    """Check a sidecar's ``animation`` section has the shape the renderers read.
    Returns the block (or ``None`` for an empty one); raises with what is wrong."""
    if block is None:
        return None
    if not isinstance(block, Mapping) or set(block) != {"clips"} or not isinstance(block["clips"], list):
        raise _fail("the section must be {'clips': [...]}")
    if not block["clips"]:
        return None
    seen: set[str] = set()
    for index, clip in enumerate(block["clips"]):
        if not isinstance(clip, Mapping) or set(clip) != {"id", "label", "duration", "loop", "tracks"}:
            raise _fail(f"clip {index} must have exactly id, label, duration, loop and tracks")
        clip_id = clip["id"]
        if not isinstance(clip_id, str) or not clip_id or clip_id in seen:
            raise _fail(f"clip {index} needs an id of its own, got {clip_id!r}")
        seen.add(clip_id)
        where = f"clip {clip_id!r}"
        if not isinstance(clip["label"], str) or not clip["label"] or not _finite(clip["duration"]) or clip["duration"] <= 0 or not isinstance(clip["loop"], bool):
            raise _fail(f"{where} needs a label, a positive duration and a boolean loop")
        if not isinstance(clip["tracks"], list):
            raise _fail(f"{where} tracks must be a list")
        for index, track in enumerate(clip["tracks"]):
            _check_track(track, f"{where} track {index}", clip["duration"])
    return dict(block)


def _written_path(path: object, rest: object) -> bool:
    """A tube key's centerline as written: {normal, segments}, or {normal, map}, twelve
    numbers, over a rest without arcs."""
    if not isinstance(path, Mapping) or set(path) not in ({"normal", "segments"}, {"normal", "map"}):
        return False
    if "segments" in path:
        return True
    segments = rest.get("segments") if isinstance(rest, Mapping) else None
    return (
        isinstance(path["map"], list) and len(path["map"]) == 12 and all(_finite(c) for c in path["map"])
        and not any(isinstance(segment, Mapping) and segment.get("kind") == "arc" for segment in segments or [])
    )


def _check_track(track: object, where: str, duration: float) -> None:
    if not isinstance(track, Mapping):
        raise _fail(f"{where} must be an object")
    channels = [name for name in CHANNELS if name in track]
    extra = {"transform": {"pivot"}, "tube": {"rest", "maxSegmentLength", "braid"}}
    allowed = {"targets", "times", *channels} | (extra.get(channels[0], set()) if len(channels) == 1 else set())
    if len(channels) != 1 or set(track) - allowed:
        raise _fail(f"{where} must carry targets, times and exactly one of {', '.join(CHANNELS)}")
    targets, times, values = track.get("targets"), track.get("times"), track[channels[0]]
    if not isinstance(targets, list) or not targets or not all(isinstance(t, str) and t for t in targets):
        raise _fail(f"{where} targets must be a nonempty list of occurrence ids")
    if (
        not isinstance(times, list) or not times or not all(_finite(t) for t in times)
        or times[0] != 0 or any(b <= a for a, b in zip(times, times[1:])) or times[-1] > duration + 1e-9
    ):
        raise _fail(f"{where} times must rise strictly from 0 to at most the duration")
    if not isinstance(values, list) or len(values) != len(times):
        raise _fail(f"{where} needs one {channels[0]} value per time")
    channel = channels[0]
    for value in values:
        if channel == "transform":
            ok = isinstance(value, list) and len(value) == 14 and all(_finite(c) for c in value)
        elif channel == "opacity":
            ok = value is None or (_finite(value) and 0 <= value <= 1)
        elif channel == "visible":
            ok = value is None or isinstance(value, bool)
        else:
            ok = value is None or (
                isinstance(value, Mapping) and set(value) == {"path", "twistDeg"} and _finite(value["twistDeg"])
                and _written_path(value["path"], track.get("rest"))
            )
        if not ok:
            raise _fail(f"{where} has a malformed {channel} value: {value!r}")
    if channel == "transform":
        pivot = track.get("pivot")
        if not isinstance(pivot, list) or len(pivot) != 3 or not all(_finite(c) for c in pivot):
            raise _fail(f"{where} needs its pivot, three numbers")
    if channel == "tube" and (not isinstance(track.get("rest"), Mapping) or not _finite(track.get("maxSegmentLength"))):
        raise _fail(f"{where} needs its rest path and maxSegmentLength")
