"""An animation (``engine/animations.py``) baked into glTF channels: keys where its curves need them.

Each animation of a built source is one glTF animation of its name, its duration in its
``extras``, as a motion's is. Every part the animation moves has a channel per path it changes
(``translation``, ``rotation``, ``scale``), its true place at time ``t`` worked out as
``engine/animations.py`` says the channels compose: the references holding it, outermost the
largest, each its translations after its rotations about their pivots, after the mechanism's
forward kinematics at the ``pose`` channel's keys; its scale the product of its references'.

A path's interpolation is its channels': all ``STEP``, STEP keys at each jump (the value after
it); all ``LINEAR``, LINEAR keys; otherwise CUBICSPLINE, from the channels' own key times and the
middle of each two. A LINEAR or CUBICSPLINE step is halved while, at any eighth of it, glTF's
interpolation of its two keys strays from the true place by more than ``LINEAR_TOLERANCE`` of the
model's size in an origin, ``ANGULAR_TOLERANCE`` radians in a rotation or 1e-3 in a scale, or its
two keys turn more than ``MOST_TURN_DEGREES`` apart: a straight move keeps its two keys, a turn
about a pivot off the part's origin gets as many as its arc needs. A CUBICSPLINE key's in- and
out-tangents are the one-sided derivatives of the true curve there -- the old clip baker's rates,
central differences of its samples, in the limit, and zero where a channel starts or stops eased
-- so a speed may jump where one channel hands over to the next. Every sampler runs from 0 to the
duration, so a player's clip is the animation once. The GLB writes every channel but a STEP one
as LINEAR keys within a tenth of a millimetre and of a degree of this bake (``keys.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cadgen.engine.export.motion import CHECKS, hermite, quaternion

__all__ = ["Baked", "Channel", "bake"]

SCALE_TOLERANCE = 1e-3
MOST_TURN_DEGREES = 120.0
_INTERPOLATION = {"step": "STEP", "linear": "LINEAR", "cubic": "CUBICSPLINE"}


@dataclass
class Channel:
    """One glTF channel: its instance, its path, its interpolation, its key times and its outputs
    (a row per key; three per key, in-tangent, value, out-tangent, for CUBICSPLINE)."""

    instance: int
    path: str
    interpolation: str
    times: np.ndarray
    values: np.ndarray


@dataclass
class Baked:
    name: str
    duration: float
    channels: list[Channel] = field(default_factory=list)
    deviation: tuple[float, float] = (0.0, 0.0)  # mm, radians: the worst at the checks


def _turn(axis: np.ndarray, radians: float, pivot: np.ndarray) -> np.ndarray:
    """The rigid turn by ``radians`` about the line through ``pivot`` along unit ``axis``."""
    x, y, z = axis
    c, s, k = math.cos(radians), math.sin(radians), 1.0 - math.cos(radians)
    rotation = np.array([[c + x * x * k, x * y * k - z * s, x * z * k + y * s],
                         [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
                         [z * x * k - y * s, z * y * k + x * s, c + z * z * k]])
    return _about(rotation, pivot)


def _about(rotation: np.ndarray, pivot: np.ndarray) -> np.ndarray:
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = pivot - rotation @ pivot
    return matrix


def _rotation(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _slerp(a: np.ndarray, b: np.ndarray, s: float) -> np.ndarray:
    dot = float(np.dot(a, b))
    if dot < 0:
        b, dot = -b, -dot
    if dot > 0.9995:
        found = a + s * (b - a)
        return found / np.linalg.norm(found)
    theta = math.acos(min(1.0, dot))
    return (math.sin((1 - s) * theta) * a + math.sin(s * theta) * b) / math.sin(theta)


class _Keyed:
    """One authored channel's curve (see ``engine/animations.py``): None before its first key, its
    last key's value after its last; between two keys ``STEP`` holds, ``LINEAR`` runs at constant
    speed (a quaternion slerped), ``CUBICSPLINE`` eases in and out (zero tangents: a Hermite of
    zero rates, a quaternion normalized after, as glTF's own CUBICSPLINE is)."""

    def __init__(self, keys: Any, interpolation: str, quaternion: bool = False) -> None:
        self.times = np.array([float(t) for t, _value in keys])
        self.values = np.array([np.atleast_1d(np.asarray(value, dtype=float)) for _t, value in keys])
        self.interpolation, self.quaternion = interpolation, quaternion
        if quaternion:
            for at in range(1, len(self.values)):
                if float(np.dot(self.values[at], self.values[at - 1])) < 0:
                    self.values[at] = -self.values[at]

    @property
    def start(self) -> float:
        return float(self.times[0])

    @property
    def last(self) -> np.ndarray:
        return self.values[-1]

    def at(self, t: float) -> np.ndarray | None:
        times, values = self.times, self.values
        if t < times[0]:
            return None
        if t >= times[-1]:
            return values[-1]
        k = int(np.searchsorted(times, t, side="right")) - 1
        if self.interpolation == "STEP":
            return values[k]
        s = (t - times[k]) / (times[k + 1] - times[k])
        if self.interpolation == "LINEAR":
            return _slerp(values[k], values[k + 1], s) if self.quaternion else values[k] + s * (values[k + 1] - values[k])
        w = s * s * (3.0 - 2.0 * s)
        found = values[k] + w * (values[k + 1] - values[k])
        return found / np.linalg.norm(found) if self.quaternion else found


class _Group:
    """One reference's channels, ready to place it at any time (see the module)."""

    def __init__(self, leaves: tuple, first: int) -> None:
        self.leaves, self.size, self.first = leaves, len(leaves), first
        self.translations: list[_Keyed] = []
        # Per rotation: its curve, and the axis (a curve of degrees) or None (a curve of quaternions), its pivot.
        self.rotations: list[tuple[_Keyed, np.ndarray | None, np.ndarray]] = []
        self.scales: list[_Keyed] = []
        self.centre = np.zeros(3)

    def matrix(self, t: float) -> np.ndarray:
        found = np.eye(4)
        for curve, axis, pivot in self.rotations:
            value = curve.at(t)
            if value is None:
                continue
            turn = _turn(axis, math.radians(float(value[0])), pivot) if axis is not None else \
                _about(_rotation(value), pivot)
            found = turn @ found
        for curve in self.translations:
            value = curve.at(t)
            if value is not None:
                found[:3, 3] += value
        return found

    def factor(self, t: float) -> float:
        value = 1.0
        for curve in self.scales:
            found = curve.at(t)
            if found is None:
                break
            value = float(found[0])
        return value


_EASE = {"CUBICSPLINE": "cubic", "LINEAR": "linear"}


class _Pose:
    """The mechanism over the animation: each link's motion from as built at ``t``."""

    def __init__(self, kinematics: dict[str, Any], tracks: list[Any]) -> None:
        from cadgen.engine import mechanism

        self.kinematics = kinematics
        self.tracks = sorted(tracks, key=lambda track: track.start)
        self.labels = sorted(kinematics["asBuilt"])
        rest = {label: mechanism._as_tuple(value) for label, value in kinematics["asBuilt"].items()}
        self.sizes = [len(rest[label]) for label in self.labels]
        self.unrest = [np.linalg.inv(matrix) for matrix in mechanism.link_worlds(kinematics, rest)]
        self.tables = []
        for track in self.tracks:
            times = np.array([when for when, _values in track.keys], dtype=float)
            rows = [[value for label in self.labels for value in dict(values).get(label, rest[label])]
                    for _when, values in track.keys]
            self.tables.append((times, np.array(rows, dtype=float)))
        self.held: dict[float, list[np.ndarray]] = {}

    def values(self, t: float) -> dict[str, tuple[float, ...]]:
        at = 0
        for index, track in enumerate(self.tracks):
            if track.start <= t:
                at = index
        times, table = self.tables[at]
        interpolation = self.tracks[at].interpolation
        if interpolation == "STEP" or len(times) == 1:
            row = table[max(0, int(np.searchsorted(times, t, side="right")) - 1)]
        else:
            from cadgen.engine.mechanism import _interpolated

            row = _interpolated(times, table, _EASE[interpolation], t)
        found, offset = {}, 0
        for label, size in zip(self.labels, self.sizes):
            found[label] = tuple(float(value) for value in row[offset:offset + size])
            offset += size
        return found

    def deltas(self, t: float) -> list[np.ndarray]:
        found = self.held.get(t)
        if found is None:
            from cadgen.engine import mechanism

            worlds = mechanism.link_worlds(self.kinematics, self.values(t))
            found = self.held[t] = [now @ unrest for now, unrest in zip(worlds, self.unrest)]
        return found

    @property
    def times(self) -> list[float]:
        return sorted({float(when) for times, _table in self.tables for when in times})


def _occurrences(structure: dict[str, Any]) -> dict[tuple[int, ...], int]:
    """Each part's occurrence path (component indices from the root) to its instance index."""
    found: dict[tuple[int, ...], int] = {}

    def visit(node: dict[str, Any], path: tuple[int, ...]) -> None:
        if "children" in node:
            for at, child in enumerate(node["children"]):
                visit(child, path + (at,))
        else:
            found[path] = node["instance"]

    visit(structure["tree"], ())
    return found


def _ramp(keys: tuple, first: Any, last: Any) -> tuple:
    """A start-to-end channel's keys with its two values given now."""
    return ((keys[0][0], last),) if len(keys) == 1 else ((keys[0][0], first), (keys[-1][0], last))


class _Animation:
    """One resolved animation over the view's nodes: each one's true translation, rotation and
    scale at any time."""

    def __init__(self, view: Any, resolved: Any, held: dict[int, Any], shown: list[Any]) -> None:
        from cadgen.engine.export.mesh import placed_points

        structure = view.source.structure
        self.duration = resolved.duration
        placed = {item.instance: item for item in shown}
        index_of = _occurrences(structure)
        corners: dict[int, np.ndarray] = {}

        def box(instances: list[int]) -> np.ndarray | None:
            low, high = np.full(3, np.inf), np.full(3, -np.inf)
            for index in instances:
                item = placed[index]
                found = corners.get(item.prototype)
                if found is None:
                    points = np.asarray(held[item.prototype].positions, dtype=np.float32).reshape(-1, 3)
                    least, most = points.min(axis=0), points.max(axis=0)
                    found = corners[item.prototype] = np.array(
                        [[(least, most)[i][0], (least, most)[j][1], (least, most)[k][2]]
                         for i in (0, 1) for j in (0, 1) for k in (0, 1)], dtype=np.float32)
                moved = placed_points(found, item.matrix)
                low, high = np.minimum(low, moved.min(axis=0)), np.maximum(high, moved.max(axis=0))
            return (low + high) / 2 if np.all(np.isfinite(low)) else None

        def point(value: Any) -> np.ndarray:
            return np.asarray(value, dtype=float)

        def vector(value: Any) -> np.ndarray:
            return np.asarray(value, dtype=float)

        groups: dict[tuple, _Group] = {}
        members: dict[tuple, list[int]] = {}

        def group(leaves: tuple, order: int) -> _Group:
            found = groups.get(leaves)
            if found is None:
                instances = [index_of[leaf] for leaf in leaves if leaf in index_of and index_of[leaf] in placed]
                found = groups[leaves] = _Group(leaves, order)
                members[leaves] = instances
                centre = box(instances)
                found.centre = centre if centre is not None else np.zeros(3)
            return found

        pose_tracks = []
        for track in sorted(resolved.tracks, key=lambda track: (track.start, track.end, track.order)):
            if track.path == "pose":
                pose_tracks.append(track)
                continue
            extra = track.extra
            if track.path == "translation" and extra is not None and extra[0] == "explode":
                _kind, how, given, distance = extra
                held_groups = [group(leaves, track.order) for leaves in track.groups]
                if how == "direction":
                    axis = vector(given)
                    ranked = sorted(range(len(held_groups)), key=lambda at: (float(held_groups[at].centre @ axis), at))
                    moves = {at: axis * distance * rank for rank, at in enumerate(ranked)}
                else:
                    middle = point(given) if given is not None else \
                        np.mean([item.centre for item in held_groups], axis=0)
                    moves = {}
                    for at, item in enumerate(held_groups):
                        away = item.centre - middle
                        length = float(np.linalg.norm(away))
                        moves[at] = away / length * distance if length > 1e-9 else np.zeros(3)
                for at, item in enumerate(held_groups):
                    item.translations.append(_Keyed(_ramp(track.keys, np.zeros(3), moves[at]), track.interpolation))
                continue
            for leaves in track.groups:
                item = group(leaves, track.order)
                if track.path == "translation":
                    if extra is None:
                        keys = tuple((t, vector(value)) for t, value in track.keys)
                    else:
                        before = sum((curve.last for curve in item.translations), np.zeros(3))
                        keys = _ramp(track.keys, np.zeros(3), point(extra[1]) - item.centre - before)
                    item.translations.append(_Keyed(keys, track.interpolation))
                elif track.path == "rotation":
                    if extra[0] == "quaternion":
                        keys = tuple((t, quaternion(_about(_rotation(np.asarray(value)), np.zeros(3))))
                                     for t, value in track.keys)
                        pivot = point(extra[1]) if extra[1] is not None else item.centre
                        item.rotations.append((_Keyed(keys, track.interpolation, quaternion=True), None, pivot))
                    else:
                        _kind, axis, given, absolute = extra
                        turned = vector(axis)
                        keys = track.keys
                        if absolute:
                            before = sum(float(curve.last[0]) * float(np.dot(other, turned))
                                         for curve, other, _pivot in item.rotations if other is not None)
                            keys = _ramp(keys, 0.0, keys[-1][1] - before)
                        item.rotations.append((_Keyed(keys, track.interpolation), turned,
                                               point(given) if given is not None else item.centre))
                else:
                    if track.keys[0][1] is None:
                        now = item.scales[-1].last[0] if item.scales else 1.0
                        keys = ((track.keys[0][0], now), *track.keys[1:])
                    else:
                        keys = track.keys
                    item.scales.append(_Keyed(keys, track.interpolation))
        # Outermost first: the largest reference, then the first named.
        ordered = sorted(groups.values(), key=lambda item: (-item.size, item.first))
        self.held_at: dict[float, dict[int, np.ndarray]] = {}
        self.of: dict[int, list[_Group]] = {}
        for item in ordered:
            for index in members[item.leaves]:
                self.of.setdefault(index, []).append(item)
        self.base = {index: np.asarray(item.matrix, dtype=float) for index, item in placed.items()}
        self.pose: _Pose | None = None
        self.link: dict[int, int] = {}
        if pose_tracks:
            kinematics = structure["kinematics"]
            self.pose = _Pose(kinematics, pose_tracks)
            owner = {index: link for link, entry in enumerate(kinematics["links"]) for index in entry["instances"]}
            times = self.pose.times
            checks = sorted(set(times) | {(a + b) / 2 for a, b in zip(times, times[1:])})
            moved = {link for t in checks for link, delta in enumerate(self.pose.deltas(t))
                     if not np.allclose(delta, np.eye(4), rtol=0, atol=1e-9)}
            for index in placed:
                if owner.get(index) in moved:
                    self.link[index] = owner[index]

    def paths(self, index: int) -> dict[str, tuple[set[str], set[float]]]:
        """The paths the animation changes on an instance: per path, its channels' interpolations
        and their key times."""
        found: dict[str, tuple[set[str], set[float]]] = {}

        def add(path: str, curve: Any, times: Any) -> None:
            kinds, breaks = found.setdefault(path, (set(), set()))
            kinds.add(curve)
            breaks.update(float(t) for t in times)

        for item in self.of.get(index, ()):
            for curve in item.translations:
                add("translation", curve.interpolation, curve.times)
            for curve, _axis, _pivot in item.rotations:
                add("translation", curve.interpolation, curve.times)
                add("rotation", curve.interpolation, curve.times)
            for curve in item.scales:
                add("scale", curve.interpolation, curve.times)
        if index in self.link:
            for track in self.pose.tracks:
                for path in ("translation", "rotation"):
                    add(path, track.interpolation, [when for when, _values in track.keys])
        return found

    def matrix(self, index: int, t: float) -> np.ndarray:
        held = self.held_at.setdefault(t, {})
        found = self.base[index]
        if index in self.link:
            found = self.pose.deltas(t)[self.link[index]] @ found
        for item in reversed(self.of.get(index, ())):
            key = id(item)
            moved = held.get(key)
            if moved is None:
                moved = held[key] = item.matrix(t)
            found = moved @ found
        return found

    def value(self, index: int, path: str, t: float) -> np.ndarray:
        if path == "scale":
            factor = 1.0
            for item in self.of.get(index, ()):
                factor *= item.factor(t)
            return np.full(3, factor)
        matrix = self.matrix(index, t)
        return matrix[:3, 3].copy() if path == "translation" else quaternion(matrix)


def _distance(path: str, got: np.ndarray, truth: np.ndarray) -> float:
    if path == "rotation":
        got = got / np.linalg.norm(got)
        return 2 * math.acos(min(1.0, abs(float(np.dot(got, truth)))))
    return float(np.max(np.abs(got - truth))) if path == "scale" else float(np.linalg.norm(got - truth))


def _channel(motion: _Animation, index: int, path: str, kinds: set[str], breaks: set[float],
             tolerance: dict[str, float]) -> tuple[Channel, float]:
    from cadgen.engine import mechanism
    from cadgen.engine.export import ExportRefused

    duration = motion.duration
    ease = {"STEP": "step", "LINEAR": "linear"}.get(next(iter(kinds)), "cubic") if len(kinds) == 1 else "cubic"
    at = lambda t: motion.value(index, path, t)  # noqa: E731
    limit = tolerance[path]
    if ease == "step":
        times = sorted({0.0, duration} | breaks)
        rows = [at(t) for t in times]
        return Channel(index, path, "STEP", np.array(times), _signed(path, np.array(rows))), 0.0
    times = sorted({0.0, duration} | {t for t in breaks if 0.0 <= t <= duration})
    if ease == "cubic":
        times = sorted(set(times) | {(a + b) / 2 for a, b in zip(times, times[1:])})
    h = 1e-5 * duration
    keys: dict[float, np.ndarray] = {}

    def key(t: float) -> np.ndarray:
        found = keys.get(t)
        if found is None:
            value = at(t)
            if ease == "linear":
                found = keys[t] = value
                return found

            def near(u: float) -> np.ndarray:
                other = at(u)
                return -other if path == "rotation" and float(np.dot(other, value)) < 0 else other

            before = (3 * value - 4 * near(t - h) + near(t - 2 * h)) / (2 * h) if t - 2 * h >= 0 else None
            after = (-3 * value + 4 * near(t + h) - near(t + 2 * h)) / (2 * h) if t + 2 * h <= duration else None
            before = before if before is not None else after
            after = after if after is not None else before
            found = keys[t] = np.stack([before, value, after])
        return found

    def deviation(a: float, b: float) -> float:
        first, second = key(a), key(b)
        worst = 0.0
        if path == "rotation":
            dot = float(np.dot(first[1] if ease == "cubic" else first, second[1] if ease == "cubic" else second))
            if dot < 0:
                second, dot = -second, -dot
            # Two keys turn less than this apart, well short of the half turn where the way between them
            # stops being one rotation (the old clip baker's bound).
            if 2 * math.acos(min(1.0, dot)) > math.radians(MOST_TURN_DEGREES):
                return math.inf
        for s in CHECKS:
            t = a + (b - a) * s
            if ease == "cubic":
                got = hermite(first, second, b - a, s)
            elif path == "rotation":
                got = _slerp(first, second, s)
            else:
                got = first + s * (second - first)
            worst = max(worst, _distance(path, got, at(t)))
        return worst

    while True:
        split, worst = [], 0.0
        for a, b in zip(times, times[1:]):
            found = deviation(a, b)
            worst = max(worst, found)
            if found > limit:
                split.append((a + b) / 2)
        if not split:
            break
        grown = sorted(set(times) | set(split))
        # A split whose midpoints round onto existing keys adds no time (two key times one ulp
        # apart): the key count then never reaches MOST_KEYS and the loop would not end, so a pass
        # that does not grow the keys is refused, as too many keys already is.
        if len(grown) == len(times) or len(grown) > mechanism.MOST_KEYS:
            raise ExportRefused(f"the {path} of instance {index} does not settle within the tolerance in "
                                f"{mechanism.MOST_KEYS} keys")
        times = grown
    rows = np.array([key(t) for t in times])
    return Channel(index, path, _INTERPOLATION[ease], np.array(times), _signed(path, rows)), worst


def _signed(path: str, rows: np.ndarray) -> np.ndarray:
    """Each rotation key on its predecessor's side, so the curve between two never takes the long way."""
    if path != "rotation":
        return rows
    rows = rows.copy()
    middle = (lambda row: row[1]) if rows.ndim == 3 else (lambda row: row)
    for at in range(1, len(rows)):
        if float(np.dot(middle(rows[at]), middle(rows[at - 1]))) < 0:
            rows[at] = -rows[at]
    return rows


def bake(view: Any, held: dict[int, Any], shown: list[Any], node_of: dict[int, int], size: float) -> list[Baked]:
    """Every animation of the view's source baked (see the module): ``shown`` the placements the
    GLB draws, ``node_of`` their nodes, ``size`` the model's (mm)."""
    from cadgen.engine import mechanism

    found: list[Baked] = []
    tolerance = {"translation": mechanism.LINEAR_TOLERANCE * max(1.0, size),
                 "rotation": mechanism.ANGULAR_TOLERANCE, "scale": SCALE_TOLERANCE}
    drawn = [item for item in shown if item.instance in node_of]
    for resolved in (view.source.animations or {}).values():
        motion = _Animation(view, resolved, held, drawn)
        baked = Baked(resolved.name, resolved.duration)
        worst = [0.0, 0.0]
        for item in drawn:
            for path, (eases, breaks) in sorted(motion.paths(item.instance).items()):
                channel, deviation = _channel(motion, item.instance, path, eases, breaks, tolerance)
                matrix = np.asarray(item.matrix, dtype=float)
                rest = {"translation": matrix[:3, 3], "rotation": quaternion(matrix), "scale": np.ones(3)}[path]
                if not _moves(channel, rest):
                    continue
                baked.channels.append(channel)
                if path == "translation":
                    worst[0] = max(worst[0], deviation)
                elif path == "rotation":
                    worst[1] = max(worst[1], deviation)
        baked.deviation = (worst[0], worst[1])
        found.append(baked)
    return found


def _moves(channel: Channel, rest: np.ndarray) -> bool:
    """Whether a channel puts its node anywhere but where it stands at rest: a path a channel
    names but never changes (the translation of a part turned about its own origin) has none."""
    values = channel.values if channel.values.ndim == 2 else channel.values[:, 1]
    if channel.path == "rotation":
        return bool(np.any(np.abs(np.abs(values @ rest) - 1.0) > 1e-9))
    return bool(np.any(np.abs(values - rest) > 1e-9))
