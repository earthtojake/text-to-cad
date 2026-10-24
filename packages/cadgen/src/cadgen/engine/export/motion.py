"""A configuration sequence (a motion, as the structure says) baked into a glTF clip: keys where
forward kinematics needs them, no more.

Each configuration sequence of the document (``mechanism.Timeline``) is one clip of the same
name. Its keys start at the sequence's waypoints (each one a key: there the speed may jump) and the halfway point between each two; at each key every moving placement's
translation and rotation is the true forward kinematics through the mechanism (couplings
included), and its in- and out-tangents the one-sided derivatives of that FK there. Between
two keys glTF's CUBICSPLINE (a cubic Hermite, the rotation normalized after) stands for the
sequence; a step is halved while, at any eighth of it, a placement's interpolated origin strays
from the true FK by more than ``LINEAR_TOLERANCE`` of the model's size (the diagonal of what
the view places) or its rotation by more than ``ANGULAR_TOLERANCE`` radians. Few keys where
the sequence is smooth, more where it is not. A placement the sequence does not move has no
channel. The GLB writes each placement's tracks as LINEAR keys within a tenth of a millimetre and
of a degree of this bake (``keys.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = ["Clip", "clips", "quaternion", "quaternions"]

# The checked fractions of a step between two keys.
CHECKS = tuple(step / 8 for step in range(1, 8))


@dataclass
class Clip:
    """One motion baked: its name, duration, key times, and per moving instance (``instances``,
    by instance index) its keys' translations and rotations, each ``(in-tangent, value,
    out-tangent)`` rows (k x 3 x 3 and k x 3 x 4); the worst deviation found at the checks."""

    name: str
    duration: float
    times: np.ndarray
    instances: list[int]
    translations: list[np.ndarray] = field(default_factory=list)
    rotations: list[np.ndarray] = field(default_factory=list)
    deviation: tuple[float, float] = (0.0, 0.0)  # mm, radians


def quaternion(matrix: np.ndarray) -> np.ndarray:
    """A rotation matrix's unit quaternion, glTF's order (x, y, z, w), w >= 0."""
    return quaternions(np.asarray(matrix, dtype=float)[None])[0]


def quaternions(matrices: np.ndarray) -> np.ndarray:
    """Each of a stack of rotation matrices (n x 4 x 4 or n x 3 x 3) as its unit quaternion, glTF's
    order (x, y, z, w), w >= 0: Shepperd's method, the branch of the largest of the trace and the
    diagonal, every row at once. A motion's keys take one per moving placement at every sample, so
    this is the export's inner loop."""
    m = np.asarray(matrices, dtype=float)[:, :3, :3]
    d0, d1, d2 = m[:, 0, 0], m[:, 1, 1], m[:, 2, 2]
    trace = d0 + d1 + d2
    first = trace > 0
    second = ~first & (d0 > d1) & (d0 > d2)
    third = ~first & ~second & (d1 > d2)
    with np.errstate(invalid="ignore", divide="ignore"):  # the branches not taken are discarded
        s = np.sqrt(trace + 1.0) * 2
        q0 = np.stack([(m[:, 2, 1] - m[:, 1, 2]) / s, (m[:, 0, 2] - m[:, 2, 0]) / s, (m[:, 1, 0] - m[:, 0, 1]) / s,
                       0.25 * s], axis=1)
        s = np.sqrt(1.0 + d0 - d1 - d2) * 2
        q1 = np.stack([0.25 * s, (m[:, 0, 1] + m[:, 1, 0]) / s, (m[:, 0, 2] + m[:, 2, 0]) / s,
                       (m[:, 2, 1] - m[:, 1, 2]) / s], axis=1)
        s = np.sqrt(1.0 + d1 - d0 - d2) * 2
        q2 = np.stack([(m[:, 0, 1] + m[:, 1, 0]) / s, 0.25 * s, (m[:, 1, 2] + m[:, 2, 1]) / s,
                       (m[:, 0, 2] - m[:, 2, 0]) / s], axis=1)
        s = np.sqrt(1.0 + d2 - d0 - d1) * 2
        q3 = np.stack([(m[:, 0, 2] + m[:, 2, 0]) / s, (m[:, 1, 2] + m[:, 2, 1]) / s, 0.25 * s,
                       (m[:, 1, 0] - m[:, 0, 1]) / s], axis=1)
    q = np.where(first[:, None], q0, np.where(second[:, None], q1, np.where(third[:, None], q2, q3)))
    # Each row's length as a dot product, as ``np.linalg.norm`` takes a vector's.
    q = q / np.sqrt(q[:, None, :] @ q[:, :, None])[:, 0]
    return np.where(q[:, 3:] < 0, -q, q)


def hermite(first: np.ndarray, second: np.ndarray, span: float, s: float) -> np.ndarray:
    """glTF's CUBICSPLINE between two keys, each ``(in-tangent, value, out-tangent)``."""
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * first[1] + span * (s ** 3 - 2 * s ** 2 + s) * first[2]
            + (-2 * s ** 3 + 3 * s ** 2) * second[1] + span * (s ** 3 - s ** 2) * second[0])


class _Motion:
    """One motion's true placements over its clip: every moving instance's world matrix in
    the document's frame at ``t``."""

    def __init__(self, view: Any, name: str, candidates: list[int]) -> None:
        from cadgen.engine import mechanism

        structure = view.source.structure
        self.kinematics = kinematics = structure["kinematics"]
        self.timeline = mechanism.Timeline(kinematics, name)
        self.worlds = mechanism.LinkWorlds(kinematics)
        rest = mechanism.link_worlds(kinematics, {label: mechanism._as_tuple(value)
                                                  for label, value in kinematics["asBuilt"].items()})
        self.unrest = [np.linalg.inv(matrix) for matrix in rest]
        owner = {index: link for link, entry in enumerate(kinematics["links"]) for index in entry["instances"]}
        self.base = {index: np.array(structure["instances"][index]["matrix"], dtype=float).reshape(4, 4).T
                     for index in candidates if index in owner}
        self.owner = owner
        # The instances whose link stands anywhere else than as built, at a key or between keys.
        moved_links: set[int] = set()
        breaks = self.timeline.breaks
        times = list(breaks) + [a + (b - a) * s for a, b in zip(breaks, breaks[1:]) for s in (0.25, 0.5, 0.75)]
        for t in times:
            worlds = self.links(t)
            for link, (now, unrest) in enumerate(zip(worlds, self.unrest)):
                if link not in moved_links and not np.allclose(now @ unrest, np.eye(4), rtol=0, atol=1e-9):
                    moved_links.add(link)
        self.instances = [index for index in candidates if self.owner.get(index) in moved_links]
        self._links = sorted({owner[index] for index in self.instances})
        self._bases = np.array([self.base[index] for index in self.instances]).reshape(-1, 4, 4)

    def links(self, t: float) -> list[np.ndarray]:
        return self.worlds(self.timeline.values(t))

    def at(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Every moving instance's translation (n x 3) and rotation (n x 4) at ``t``: each link's
        motion from as built once, then every instance's world matrix and quaternion as one stack."""
        if not self.instances:
            return np.zeros((0, 3)), np.zeros((0, 4))
        worlds = self.links(t)
        moved = {link: worlds[link] @ self.unrest[link] for link in self._links}
        matrices = np.matmul(np.array([moved[self.owner[index]] for index in self.instances]), self._bases)
        return matrices[:, :3, 3].copy(), quaternions(matrices)


def _aligned(rotations: np.ndarray, to: np.ndarray) -> np.ndarray:
    """Each quaternion of ``rotations`` signed to lie on ``to``'s side, row by row."""
    signs = np.where(np.sum(rotations * to, axis=1) < 0, -1.0, 1.0)
    return rotations * signs[:, None]


class _Keys:
    """The keys of one clip, made as they are asked for: at each, every moving instance's
    ``(in-tangent, value, out-tangent)`` for its translation and its rotation."""

    def __init__(self, motion: _Motion) -> None:
        self.motion = motion
        self.period = motion.timeline.period
        self.step = 1e-5 * self.period
        self.held: dict[float, tuple[np.ndarray, np.ndarray]] = {}

    def key(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        found = self.held.get(t)
        if found is None:
            at = self.motion.at
            translation, rotation = at(t)
            h = self.step

            def left() -> tuple[np.ndarray, np.ndarray]:
                (t1, r1), (t2, r2) = at(t - h), at(t - 2 * h)
                r1, r2 = _aligned(r1, rotation), _aligned(r2, rotation)
                return (3 * translation - 4 * t1 + t2) / (2 * h), (3 * rotation - 4 * r1 + r2) / (2 * h)

            def right() -> tuple[np.ndarray, np.ndarray]:
                (t1, r1), (t2, r2) = at(t + h), at(t + 2 * h)
                r1, r2 = _aligned(r1, rotation), _aligned(r2, rotation)
                return (-3 * translation + 4 * t1 - t2) / (2 * h), (-3 * rotation + 4 * r1 - r2) / (2 * h)

            before = left() if t - 2 * h >= 0 else None
            after = right() if t + 2 * h <= self.period else None
            before = before if before is not None else after
            after = after if after is not None else before
            found = self.held[t] = (np.stack([before[0], translation, after[0]], axis=1),
                                    np.stack([before[1], rotation, after[1]], axis=1))
        return found


def _deviation(keys: _Keys, a: float, b: float) -> tuple[float, float]:
    """The worst origin (mm) and rotation (radians) deviation of the step from ``a`` to ``b``
    at its checks: the Hermite of the two keys against the true FK."""
    (ta, ra), (tb, rb) = keys.key(a), keys.key(b)
    signs = np.where(np.sum(ra[:, 1] * rb[:, 1], axis=1) < 0, -1.0, 1.0)
    rb = rb * signs[:, None, None]
    span = b - a
    worst = [0.0, 0.0]
    for s in CHECKS:
        translation, rotation = keys.motion.at(a + span * s)
        got_t = hermite(ta.transpose(1, 0, 2), tb.transpose(1, 0, 2), span, s)
        got_r = hermite(ra.transpose(1, 0, 2), rb.transpose(1, 0, 2), span, s)
        got_r = got_r / np.linalg.norm(got_r, axis=1, keepdims=True)
        worst[0] = max(worst[0], float(np.max(np.linalg.norm(got_t - translation, axis=1), initial=0.0)))
        dots = np.clip(np.abs(np.sum(got_r * rotation, axis=1)), 0.0, 1.0)
        worst[1] = max(worst[1], float(np.max(2 * np.arccos(dots), initial=0.0)))
    return worst[0], worst[1]


def clips(view: Any, candidates: list[int], size: float) -> list[Clip]:
    """Every motion of the view's document baked (see the module docstring): ``candidates``
    the instances the GLB has a node for, ``size`` the model's (mm)."""
    from cadgen.engine import mechanism
    from cadgen.engine.export import ExportRefused

    kinematics = view.source.structure.get("kinematics") or {}
    found = []
    linear, angular = mechanism.LINEAR_TOLERANCE * max(1.0, size), mechanism.ANGULAR_TOLERANCE
    for name in kinematics.get("motions") or {}:
        try:
            motion = _Motion(view, name, candidates)
        except mechanism.KinematicsError as error:
            raise ExportRefused(f"motion {name!r}: {error}") from None
        keys = _Keys(motion)
        times = sorted(set(motion.timeline.breaks))
        times = sorted(set(times) | {(a + b) / 2 for a, b in zip(times, times[1:])})
        worst = (0.0, 0.0)
        if motion.instances:
            while True:
                split, worst = [], (0.0, 0.0)
                for a, b in zip(times, times[1:]):
                    deviation = _deviation(keys, a, b)
                    worst = (max(worst[0], deviation[0]), max(worst[1], deviation[1]))
                    if deviation[0] > linear or deviation[1] > angular:
                        split.append((a + b) / 2)
                if not split:
                    break
                grown = sorted(set(times) | set(split))
                # A split that rounds onto existing keys adds no time, so the key count never reaches
                # MOST_KEYS and the loop would not end: refuse a pass that does not grow the keys.
                if len(grown) == len(times) or len(grown) > mechanism.MOST_KEYS:
                    raise ExportRefused(f"motion {name!r}: its clip does not settle within the tolerance in "
                                        f"{mechanism.MOST_KEYS} keys")
                times = grown
        clip = Clip(name, motion.timeline.duration, np.array(times), motion.instances,
                    deviation=worst)
        rows = [keys.key(t) for t in times] if motion.instances else []
        for at in range(len(motion.instances)):
            translations = np.array([row[0][at] for row in rows])
            rotations = np.array([row[1][at] for row in rows])
            for key in range(1, len(rotations)):  # each key's sign on its predecessor's side
                if np.dot(rotations[key, 1], rotations[key - 1, 1]) < 0:
                    rotations[key] = -rotations[key]
            clip.translations.append(translations)
            clip.rotations.append(rotations)
        found.append(clip)
    return found
