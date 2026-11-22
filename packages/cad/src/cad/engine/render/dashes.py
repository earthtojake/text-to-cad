"""A stroke's line style, as the viewer draws it (``@cad/core`` ``common/annotation.js``'s ``dashPattern``):
a mark's ``dash`` -- ``"dashed"`` or ``"dotted"``, absent for solid -- is a pattern in screen pixels scaled with
its width, and a dashed stroke is drawn as its runs of ink along its line, the pattern running on unbroken
from segment to segment. A dot is a run of no length, drawn by its round caps alone."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:  # numpy is the stills' alone: the snapshot's checks read DASHES with nothing installed
    import numpy as np

DASHES = ("solid", "dashed", "dotted")


def dash_pattern(dash: Any, width: float) -> tuple[float, float] | None:
    """``(on, off)`` in screen pixels for a stroke ``width`` pixels wide, or None for a solid one."""
    w = max(1.0, float(width or 1))
    if dash == "dashed":
        return max(6.0, 4 * w), max(4.0, 3 * w)
    if dash == "dotted":
        return 0.001, max(3.0, 2 * w)
    return None


def dash_runs(points: np.ndarray, lengths_px: Sequence[float], pattern: tuple[float, float],
              shares: np.ndarray | None = None) -> list[tuple[np.ndarray, np.ndarray | None]]:
    """The runs of ink of a polyline (``points``, N x D; ``lengths_px`` each of its N-1 segments' length on screen)
    dashed by ``pattern``: each run its points (the line's own, cut where a dash starts and ends) and, with
    ``shares`` (the pen's width at each point), its shares at them."""
    import numpy as np

    on, off = pattern
    period = on + off
    runs: list[tuple[list[np.ndarray], list[float]]] = []
    current: tuple[list[np.ndarray], list[float]] | None = None
    travelled = 0.0

    def at(index: int, t: float) -> tuple[np.ndarray, float]:
        point = points[index] + (points[index + 1] - points[index]) * t
        share = 1.0 if shares is None else float(shares[index] + (shares[index + 1] - shares[index]) * t)
        return point, share

    for index, length in enumerate(lengths_px):
        length = float(length)
        start = travelled
        end = travelled + length
        # Dots: a run of no length at each period's start, drawn by its round caps.
        if on < 0.01:
            edge = start - (start % period)
            while edge < end or (edge == end and index == len(lengths_px) - 1):
                if edge >= start and length > 0:
                    point, share = at(index, (edge - start) / length)
                    runs.append(([point, point], [share, share]))
                edge += period
            travelled = end
            continue
        cuts = [0.0]
        phase = start % period
        edge = start - phase
        while edge < end:
            for boundary in (edge, edge + on):
                if start < boundary < end:
                    cuts.append((boundary - start) / length)
            edge += period
        cuts.append(1.0)
        for a, b in zip(cuts, cuts[1:]):
            middle = start + (a + b) / 2 * length
            inked = (middle % period) < on if b > a else False
            first, first_share = at(index, a)
            last, last_share = at(index, b)
            if inked:
                if current is None:
                    current = ([first], [first_share])
                    runs.append(current)
                current[0].append(last)
                current[1].append(last_share)
            else:
                current = None
        travelled = end
    return [(np.array(run_points), None if shares is None else np.array(run_shares)) for run_points, run_shares in runs
            if len(run_points) >= 2]


def segment_lengths(points: np.ndarray) -> list[float]:
    """Each segment's length, for points already on the screen."""
    return [float(math.dist(a, b)) for a, b in zip(points[:-1], points[1:])]
