"""FreeCAD's path commands, read as moves: what the checks test against the part and the viewer draws.

An operation's commands (``[name, {word: value}]``, as ``freecad_job.py`` hands them back) are FreeCAD's own: ``G0``
rapids, ``G1`` feeds, ``G2``/``G3`` arcs in the XY plane (``I J`` the centre from the start, a helix with ``Z``),
and the drilling cycles ``G81``/``G82``/``G83`` (to ``Z`` from ``R``, back to ``R`` under ``G99`` or to where the cycle
began under ``G98``). Coordinates are absolute (``G90``); FreeCAD's feeds are mm/s, as its posts read them. Anything
else (``G91``, another plane) is an error: a move cadgen cannot read is a move it cannot check.

:func:`read` turns them into :class:`Moves`: sample points (arcs within :data:`CHORD_MM`), each with whether the move
ending there is a rapid, its operation and its time. Stdlib at import; numpy inside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

__all__ = ["CHORD_MM", "Moves", "read"]

#: How far an arc's samples may stray from the arc (mm).
CHORD_MM = 0.02
_IGNORED = {"G17", "G21", "G40", "G49", "G54", "G80", "G90", "G94", "M3", "M4", "M5", "M6", "M7", "M8",
            "M9"}
_CYCLES = {"G81", "G82", "G83", "G73"}


@dataclass
class Moves:
    """Samples in setup coordinates: ``points`` (N, 3); ``rapid`` (N,) whether the move ending at each sample is a
    rapid (the first sample's is its own); ``op`` (N,) the operation's index; ``t`` (N,) seconds from the setup's
    start."""

    points: Any
    rapid: Any
    op: Any
    t: Any


def _arc(start, end, centre, clockwise: bool):
    """Points along an XY arc from ``start`` to ``end`` about ``centre`` (z rising linearly), ``start`` excluded."""
    r = math.hypot(start[0] - centre[0], start[1] - centre[1])
    a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
    a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
    sweep = a1 - a0
    if clockwise and sweep >= -1e-12:
        sweep -= 2 * math.pi
    elif not clockwise and sweep <= 1e-12:
        sweep += 2 * math.pi
    step = 2 * math.acos(max(-1.0, 1 - CHORD_MM / r)) if r > CHORD_MM else math.pi / 2
    count = max(2, int(math.ceil(abs(sweep) / max(step, 1e-3))))
    out = []
    for k in range(1, count + 1):
        f = k / count
        a = a0 + sweep * f
        out.append((centre[0] + r * math.cos(a), centre[1] + r * math.sin(a), start[2] + (end[2] - start[2]) * f))
    out[-1] = tuple(end)
    return out


def read(operations: list[tuple[int, list]], start: tuple[float, float, float], rapid_mm_min: float) -> Moves:
    """The moves of a setup's operations (``(index, commands)`` in program order), the tool starting at ``start``."""
    import numpy as np

    position = list(start)
    points, rapid, ops, times = [tuple(start)], [True], [operations[0][0] if operations else 0], [0.0]
    clock = 0.0
    feed = None
    back_to_start = True                        # G98: a drilling cycle returns to where it began

    def go(target, is_rapid: bool, op: int, rate):
        nonlocal clock
        last = points[-1]
        length = math.dist(last, target)
        speed = rapid_mm_min / 60.0 if is_rapid else rate
        clock += length / speed if speed else 0.0
        points.append(tuple(target))
        rapid.append(is_rapid)
        ops.append(op)
        times.append(clock)

    for op, commands in operations:
        for name, words in commands:
            if name.startswith("(") or name in _IGNORED:
                continue
            if name in ("G98", "G99"):
                back_to_start = name == "G98"
                continue
            if "F" in words and words["F"] > 0:
                feed = words["F"]
            target = [words.get(axis, position[k]) for k, axis in enumerate("XYZ")]
            if name in ("G0", "G00"):
                go(target, True, op, None)
            elif name in ("G1", "G01"):
                if not feed and target != position:
                    raise ValueError(f"operation {op}: FreeCAD fed a move with no feed rate")
                go(target, False, op, feed)
            elif name in ("G2", "G02", "G3", "G03"):
                if "K" in words and abs(words["K"]) > 1e-9 and ("I" not in words and "J" not in words):
                    raise ValueError(f"operation {op}: an arc outside the XY plane, which cadgen does not read")
                centre = (position[0] + words.get("I", 0.0), position[1] + words.get("J", 0.0))
                arc_start = tuple(position)
                for point in _arc(arc_start, target, centre, name in ("G2", "G02")):
                    go(point, False, op, feed)
            elif name in _CYCLES:
                initial = position[2]
                retract = words.get("R", initial)
                x, y = words.get("X", position[0]), words.get("Y", position[1])
                go([x, y, initial], True, op, None)
                go([x, y, retract], True, op, None)
                go([x, y, words["Z"]], False, op, feed)
                target = [x, y, initial if back_to_start else retract]
                go(target, True, op, None)
            else:
                raise ValueError(f"operation {op}: FreeCAD wrote {name}, which cadgen does not read")
            position = list(points[-1]) if name not in _CYCLES else target
    return Moves(points=np.asarray(points, dtype=float), rapid=np.asarray(rapid, dtype=bool),
                 op=np.asarray(ops, dtype=np.int64), t=np.asarray(times, dtype=float))
