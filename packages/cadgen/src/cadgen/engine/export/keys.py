"""A baked track written as glTF LINEAR keys: the fewest the GLB needs to stay within
``KEY_MM`` and ``KEY_DEGREES`` of the bake.

The bakes key a track where its curve needs them (``motion.py``: every track of a clip on the
keys its hardest track needs; ``animation.py``: CUBICSPLINE where a channel eases), so a track
holds many more keys than straight lines between them would need, and a CUBICSPLINE key three
values. Before the GLB writes a track that is not STEP, it becomes LINEAR keys -- lerped, a
rotation slerped, as glTF interpolates LINEAR -- chosen against the bake's own curve (its
Hermite, or its lines) sampled densely: at ``1/m`` of each of its steps, the bake's keys among
the samples. A CUBICSPLINE step takes as many as keep its curve within ``SLACK`` of the
tolerance of the line between any two neighbouring samples (a Hermite bends most at an end of
its step, and its chord between two samples ``1/m`` of the step apart strays from it by at most
that bend over ``8 m^2``), and every sample is held to the tolerance less that slack, so a kept
line that holds the samples holds the curve between them too. A LINEAR rotation's step takes
``SAMPLES``; a LINEAR translation or scale is held at its keys alone, since a line strays
furthest from a polyline at the polyline's corners.

- **Candidates**: the bake's keys, and every sample of a step that a straight line between its
  own two keys does not hold (an eased step keyed sparsely), so a key may fall between two of the
  bake's.
- **Kept**: the first and the last key, both keys of every jump (two keys closer than ``JUMP``
  of the clip: how a bake that is not STEP writes one), and, from each kept key, the farthest
  candidate whose straight segment stays within the tolerance at every sample it spans and, for
  a rotation, turns at most ``MOST_TURN_DEGREES``.
- **Distance**: a translation's in the node's millimetres; a rotation's the angle between the
  two; a uniform scale's change times the part's ``reach``, its farthest point from its origin,
  so a scale is held to the millimetres its part moves.

STEP tracks (a hide) are written as baked, key for key. The choice is numpy arithmetic in a
fixed order over the bake's float64 keys, so a document gives the same keys, and the GLB the
same bytes, every time.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = ["KEY_DEGREES", "KEY_MM", "linear"]

KEY_MM = 0.1  # under a pixel: a 1 m model filling a 4K screen draws 0.26 mm a pixel.
KEY_DEGREES = 0.1  # a point 57 mm from its pivot moves 0.1 mm.
SAMPLES = 8  # samples a LINEAR rotation's step, as the bakes check their own steps at eighths.
JUMP = 1e-6  # of the clip: two keys this close are a jump, which no line between them draws.
MOST_TURN_DEGREES = 120.0  # two kept rotation keys, as the bake's own: well short of a half turn.
SLACK = 0.05  # of the tolerance, left for the curve between two samples.
MOST_SAMPLES = 4096  # a bake step's samples at most, however sharply it bends.
_WINDOW = 16  # candidate ends tried at once from a kept key, before galloping further.


def _slerp(a: np.ndarray, b: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Rows of quaternions slerped from ``a`` to ``b`` (rows, or one) by fractions ``s``, the
    short way, as glTF's LINEAR rotation (three.js: ``Quaternion.slerpFlat``)."""
    dot = np.sum(a * b, axis=-1, keepdims=True)
    b = np.where(dot < 0, -b, b)
    theta = np.arccos(np.clip(np.abs(dot), 0.0, 1.0))
    sin = np.sin(theta)
    near = sin < 1e-6
    safe = np.where(near, 1.0, sin)
    first = np.where(near, 1.0 - s, np.sin((1.0 - s) * theta) / safe)
    second = np.where(near, s, np.sin(s * theta) / safe)
    found = first * a + second * b
    return found / np.linalg.norm(found, axis=-1, keepdims=True)


def _apart(path: str, got: np.ndarray, truth: np.ndarray) -> np.ndarray:
    """How far each row of ``got`` is from ``truth``: radians for a rotation, else the distance."""
    if path == "rotation":
        dot = np.abs(np.sum(got * truth, axis=-1))
        return 2.0 * np.arccos(np.clip(dot, 0.0, 1.0))
    if path == "scale":
        return np.max(np.abs(got - truth), axis=-1)
    return np.linalg.norm(got - truth, axis=-1)


def linear(times: np.ndarray, rows: np.ndarray, interpolation: str, path: str, duration: float,
           reach: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """A baked track's LINEAR keys (see the module): its ``times`` and ``rows`` as the bake wrote
    them (``CUBICSPLINE`` rows in-tangent, value, out-tangent: k x 3 x width; ``LINEAR`` k x
    width), its ``path``, the clip's ``duration`` and, for a scale, its part's ``reach`` (mm).
    Returns the kept times and values."""
    times = np.asarray(times, dtype=float)
    rows = np.asarray(rows, dtype=float)
    values = rows[:, 1] if interpolation == "CUBICSPLINE" else rows
    count = len(times)
    if count < 2:
        return times.copy(), values.copy()
    rotation = path == "rotation"
    if rotation:
        limit = math.radians(KEY_DEGREES)
    elif path == "scale":
        limit = KEY_MM / reach if reach > 0 else math.inf
    else:
        limit = KEY_MM
    most_turn = math.radians(MOST_TURN_DEGREES)

    # The bake sampled: each step at 1/m of it, the bake's keys exact among the samples.
    spans = np.diff(times)
    each = np.full(count - 1, SAMPLES if rotation and interpolation == "LINEAR" else 1, dtype=float)
    if interpolation == "CUBICSPLINE" and math.isfinite(limit):
        p0, m0 = values[:-1], rows[:-1, 2] * spans[:, None]
        p1, m1 = values[1:], rows[1:, 0] * spans[:, None]
        bend = np.maximum(np.linalg.norm(-6 * p0 - 4 * m0 + 6 * p1 - 2 * m1, axis=1),
                          np.linalg.norm(6 * p0 + 2 * m0 - 6 * p1 + 4 * m1, axis=1))
        bend = bend * (2.0 if rotation else 1.0)  # a unit quaternion's angle is twice its chord
        each = np.maximum(each, np.ceil(np.sqrt(bend / (8 * SLACK * limit))))
    jumps = np.flatnonzero(spans < JUMP * duration)
    each[jumps] = 1  # a jump is its two keys, both kept: nothing between them is drawn
    each = np.minimum(each, MOST_SAMPLES).astype(int)
    held = limit * (1 - SLACK)
    starts = np.concatenate([[0], np.cumsum(each)])  # the sample of each key
    step = np.concatenate([np.repeat(np.arange(count - 1), each), [count - 2]])
    fraction = np.concatenate([(np.arange(starts[-1]) - starts[step[:-1]]) / each[step[:-1]], [1.0]])
    at = times[step] + fraction * spans[step]
    at[starts] = times
    s = fraction[:, None]
    if interpolation == "CUBICSPLINE":
        span = spans[step][:, None]
        truth = ((2 * s ** 3 - 3 * s ** 2 + 1) * rows[step, 1] + span * (s ** 3 - 2 * s ** 2 + s) * rows[step, 2]
                 + (-2 * s ** 3 + 3 * s ** 2) * rows[step + 1, 1] + span * (s ** 3 - s ** 2) * rows[step + 1, 0])
        if rotation:
            truth = truth / np.linalg.norm(truth, axis=1, keepdims=True)
    elif rotation:
        truth = _slerp(values[step], values[step + 1], s)
    else:
        truth = values[step] + s * (values[step + 1] - values[step])
    truth[starts] = values

    # The candidates: every key, and every sample of a step its own two keys' line does not hold.
    if interpolation == "CUBICSPLINE":
        straight = _slerp(values[step], values[step + 1], s) if rotation else \
            values[step] + s * (values[step + 1] - values[step])
        loose = np.maximum.reduceat(_apart(path, straight, truth)[:-1], starts[:-1]) > held
    else:
        loose = np.zeros(count - 1, dtype=bool)
    if rotation:
        turn = 2.0 * np.arccos(np.clip(np.abs(np.sum(values[:-1] * values[1:], axis=1)), 0.0, 1.0))
        loose |= turn > most_turn
    loose[jumps] = False
    whole = np.concatenate([np.repeat(loose, each), [False]])
    whole[starts] = True
    # A sample becomes a key only where its time, as the GLB writes it (float32), is after the one before.
    written = at.astype(np.float32)
    inner = np.flatnonzero(whole & ~np.isin(np.arange(len(at)), starts))
    whole[inner[(written[inner] <= written[inner - 1]) | (written[inner] >= written[np.minimum(inner + 1, len(at) - 1)])]] = False
    candidates = np.flatnonzero(whole)
    place = np.full(len(at), -1)
    place[candidates] = np.arange(len(candidates))
    forced = np.zeros(len(candidates), dtype=bool)
    forced[[0, -1]] = True
    forced[place[starts[jumps]]] = True
    forced[place[starts[jumps + 1]]] = True
    pinned = np.flatnonzero(forced)

    def holds(first: int, ends: np.ndarray) -> np.ndarray:
        """Whether the line from candidate ``first`` to each of ``ends`` holds every sample it spans."""
        a = candidates[first]
        bs = candidates[ends]
        ok = np.ones(len(ends), dtype=bool)
        if rotation:
            ok &= 2.0 * np.arccos(np.clip(np.abs(truth[bs] @ truth[a]), 0.0, 1.0)) <= most_turn
        inside = np.arange(a + 1, bs[-1])
        if not len(inside):
            return ok
        f = (at[inside][None, :] - at[a]) / (at[bs] - at[a])[:, None]
        if rotation:
            got = _slerp(truth[a][None, None, :], truth[bs][:, None, :], f[:, :, None])
        else:
            got = truth[a] + f[:, :, None] * (truth[bs] - truth[a])[:, None, :]
        off = _apart(path, got, truth[inside][None, :, :])
        off[inside[None, :] >= bs[:, None]] = 0.0
        return ok & (off.max(axis=1) <= held)

    kept = [0]
    first, last = 0, len(candidates) - 1
    while first < last:
        bound = int(pinned[np.searchsorted(pinned, first, side="right")])
        top = min(first + _WINDOW, bound)
        ends = np.arange(first + 1, top + 1)
        ok = holds(first, ends)
        best = int(ends[ok][-1]) if ok.any() else first + 1
        if best == top < bound:
            # The whole window holds: gallop on, then halve back to the farthest end that holds.
            good, bad, width = top, None, _WINDOW
            while bad is None and good < bound:
                width *= 2
                probe = min(first + width, bound)
                if holds(first, np.array([probe]))[0]:
                    good = probe
                else:
                    bad = probe
            while bad is not None and bad - good > 1:
                middle = (good + bad) // 2
                if holds(first, np.array([middle]))[0]:
                    good = middle
                else:
                    bad = middle
            best = good
        kept.append(best)
        first = best
    chosen = candidates[kept]
    out = truth[chosen].copy()
    if rotation:  # each key on its predecessor's side, so the way between two is the short one
        for at_key in range(1, len(out)):
            if float(np.dot(out[at_key], out[at_key - 1])) < 0:
                out[at_key] = -out[at_key]
    return at[chosen].copy(), out
