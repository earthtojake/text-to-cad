"""The adapt ladder: a big part or a long job is never refused; the run coarsens and says so.

Three rungs, each a plain-worded step (``{"step", "words", "accuracy"}``) that the result's ``adapted`` list and
the CLI's ``adapted:`` lines carry:

* ``stock_grid``: the stock simulator's cell. It starts at a quarter of the smallest milling tool's radius (between
  0.05 and 1 mm) and grows until the grid fits :attr:`Budget.max_cells`; the material-left and removed-volume
  figures are good to about half a cell.
* ``sim_step``: the spacing of the simulator's samples along the path. It starts at the cell and grows until the
  whole program fits :attr:`Budget.max_sim_samples`; a sample spacing above the cell can leave a scallop of
  material on curved walls in the simulation only.
* ``display``: the GLB's toolpath lines. Arcs are drawn within ``chord`` (starting at the job's tolerance, at least
  0.02 mm); when the lines exceed :attr:`Budget.max_glb_segments` the chord grows, then the lines are thinned. The
  posted G-code always keeps every move.

Stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["Budget", "display_chord", "op_step", "sample_spacing", "sim_step", "stock_cell"]


@dataclass(frozen=True)
class Budget:
    max_cells: int = 4_000_000
    max_sim_samples: int = 6_000_000
    max_glb_segments: int = 1_500_000
    #: Drop-cutter points one 3D operation samples before it refines (its grid or its passes).
    max_drop_points: int = 1_500_000


def _mm(value: float) -> str:
    return f"{value:.3g} mm"


def stock_cell(stock, tools, budget: Budget) -> tuple[float, list[dict]]:
    """The stock grid's cell (mm), and the step taken when it had to grow."""
    radii = [t.radius for t in tools if t.family == "mill" and t.radius > 0]
    desired = min(1.0, max(0.05, (min(radii) if radii else 2.0) / 4.0))
    low, high = stock.bounds_min, stock.bounds_max
    area = max(1e-6, (high[0] - low[0]) * (high[1] - low[1]))
    cell = desired
    while area / (cell * cell) > budget.max_cells:
        cell *= 1.25
    if cell == desired:
        return cell, []
    cells = int(area / (cell * cell))
    return cell, [{"step": "stock_grid",
                   "words": f"stock grid {_mm(desired)} -> {_mm(cell)} so the simulation fits {cells:,} cells",
                   "accuracy": f"material left and removed volume are good to about {_mm(cell / 2)}"}]


def sim_step(path_length_mm: float, cell: float, budget: Budget) -> tuple[float, list[dict]]:
    """The simulator's sample spacing along the path (mm), and the step taken when it had to grow."""
    step = cell
    if path_length_mm / step <= budget.max_sim_samples:
        return step, []
    step = path_length_mm / budget.max_sim_samples
    return step, [{"step": "sim_step",
                   "words": f"simulation samples every {_mm(step)} along {path_length_mm / 1000:.1f} m of path, "
                            f"not every {_mm(cell)}",
                   "accuracy": f"simulated walls may show scallops up to about {_mm(step * step / 8)} deep"}]


def op_step(step: float, cell: float, tool) -> float:
    """One operation's sample spacing in the stock simulator: the program's ``step``, or wider for a big tool. Stamps
    of a radius-r cutter ``s`` apart leave a scallop of about s²/8r between them; at ``s = sqrt(2 r cell)`` that is a
    quarter of a cell, under the grid's own accuracy, and a 25 mm face mill beside a 0.2 mm engraver (a cell of
    0.05 mm) samples every 1.1 mm, not every 0.05 mm: 22 times less work for the same stock."""
    return max(step, math.sqrt(2.0 * max(tool.radius, 0.0) * cell))


def display_chord(segments_at, tolerance: float, budget: Budget) -> tuple[float, int, list[dict]]:
    """``(chord, stride, steps)`` for the GLB's lines: ``segments_at(chord)`` counts the segments a chord gives;
    the chord grows (to 1 mm at most), then every ``stride``-th point is kept."""
    chord = max(0.02, tolerance)
    first = chord
    count = segments_at(chord)
    while count > budget.max_glb_segments and chord < 1.0:
        chord = min(1.0, chord * 4)
        count = segments_at(chord)
    steps = []
    if chord != first:
        steps.append({"step": "display", "words": f"toolpath lines drawn with arcs to {_mm(chord)}, not {_mm(first)}",
                      "accuracy": "the G-code keeps every arc exact; only the drawing is coarser"})
    stride = max(1, int(math.ceil(count / budget.max_glb_segments)))
    if stride > 1:
        steps.append({"step": "display", "words": f"toolpath lines thinned to every {stride}th point to draw "
                      f"{count:,} segments", "accuracy": "the G-code keeps every move; only the drawing is thinned"})
    return chord, stride, steps


def sample_spacing(measure: float, desired: float, budget: Budget, *, dims: int, what: str) -> tuple[float, list[dict]]:
    """A 3D operation's sampling (mm) over ``measure`` (a path length, ``dims`` 1, or an area, ``dims`` 2), and the
    step taken when ``desired`` would need more than :attr:`Budget.max_drop_points` points. ``what`` names the
    sampling in the step's words ("waterline grid")."""
    spacing = desired
    if measure / spacing ** dims <= budget.max_drop_points:
        return spacing, []
    spacing = (measure / budget.max_drop_points) ** (1.0 / dims)
    return spacing, [{"step": "sampling", "words": f"{what} sampled every {_mm(spacing)}, not every {_mm(desired)}, "
                      f"to keep {budget.max_drop_points:,} drop-cutter points",
                      "accuracy": f"features narrower than about {_mm(spacing)} can be missed; heights between "
                      "samples are still checked against the part"}]
