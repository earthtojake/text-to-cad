"""How much of an operation's path cuts nothing: the share of its cutting moves (feeds, plunges, arcs) along which
the tool removes no material.

The material is the stock as it stood before the operation (:class:`~cadgen._internal.cam.milling3d.StockNow`, every
earlier operation replayed) and as the operation's own earlier moves leave it. It is held as a grid of the stock's top
in the setup's WCS, cells a twelfth of the tool's radius; the tool's lower surface
(:meth:`~cadgen._internal.cam.tools.Tool.height_at`) is stamped on the grid each time the path has gone a cell further
(a stretch of finely pointed path is one stamp, so a step too short to reach a new cell is not taken for air). A
stretch whose stamp lowers no cell by more than a hair (the tolerance, at least 0.01 mm) cut air. The part's own
material is not the operation's to cut: a tool brushing a wall the grid rounds into it is not cutting.

:func:`air_report` gives ``{"air_fraction", "air_mm", "cut_mm"}``: the adaptive clears record it in their ``meta`` (it
is the number adaptive clearing is built to keep low), and the tests read it.
"""

from __future__ import annotations

import math

__all__ = ["air_report"]

#: The finest grid the report builds: a path over a larger area takes coarser cells.
MAX_CELLS = 4_000_000
#: The most stamps it makes: a longer path is stamped further apart (the report is coarser, never slow).
MAX_STAMPS = 400_000


def air_report(ctx, toolpath, *, stock_now=None) -> dict:
    """``{"air_fraction", "air_mm", "cut_mm"}`` of ``toolpath`` (WCS, ``ctx.tool``'s): the cutting length that removed
    nothing over all the cutting length, both in mm."""
    import numpy as np

    from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED, PLUNGE
    from cadgen._internal.cam.milling3d import StockNow

    empty = {"air_fraction": 0.0, "air_mm": 0.0, "cut_mm": 0.0}
    kinds = toolpath.moves["kind"]
    cutting_moves = np.isin(kinds, (FEED, PLUNGE, ARC_CW, ARC_CCW))
    total = float(toolpath.lengths()[cutting_moves].sum()) if len(kinds) else 0.0
    if total <= 0.0:
        return empty
    tool = ctx.tool
    r = tool.radius
    tol = max(0.01, ctx.tolerance_mm)
    ends = toolpath.positions()[1:][cutting_moves]
    span = ends[:, :2].max(axis=0) - ends[:, :2].min(axis=0) + 4 * r
    cell = max(r / 12.0, math.sqrt(float(np.prod(span)) / MAX_CELLS), 1e-3)
    spacing = max(cell, total / MAX_STAMPS)
    samples = toolpath.sample(chord_mm=tol, max_step_mm=spacing)
    points = samples.points
    cutting = np.isin(samples.kind, (FEED, PLUNGE, ARC_CW, ARC_CCW)) & (samples.move >= 0)
    index = np.nonzero(cutting)[0]
    if not len(index):
        return empty
    lengths = np.linalg.norm(points[index] - points[index - 1], axis=1)
    low, high = points[index, :2].min(axis=0) - r, points[index, :2].max(axis=0) + r

    # The grid: the stock as it stands under it, and the part's own material.
    k = int(math.ceil(r / cell))
    nx = int(math.ceil((high[0] - low[0]) / cell)) + 2 * k + 1
    ny = int(math.ceil((high[1] - low[1]) / cell)) + 2 * k + 1
    x0, y0 = low[0] - k * cell, low[1] - k * cell
    gx, gy = np.meshgrid(x0 + (np.arange(nx) + 0.5) * cell, y0 + (np.arange(ny) + 0.5) * cell, indexing="ij")
    xy = np.column_stack([gx.ravel(), gy.ravel()])
    stock = stock_now if stock_now is not None else StockNow(ctx)
    tops = np.asarray(stock.surface_at(xy), dtype=float)
    part_face = np.asarray(stock.part_surface_at(xy), dtype=float)
    # The tool's footprint as flat offsets into the grid, each with the height of the tool's lower surface there.
    di, dj = np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1), indexing="ij")
    distance = np.hypot(di, dj) * cell
    footprint = distance <= r
    offsets = (di[footprint] * ny + dj[footprint]).astype(np.int64)
    lift = np.asarray(tool.height_at(distance[footprint]), dtype=float)

    # A stamp each time the path has gone ``spacing`` since the last one, and at the end of each run of consecutive
    # cutting samples; each stamp stands for the stretch since the one before.
    travelled = np.cumsum(lengths)
    breaks = np.nonzero(np.diff(index) != 1)[0]
    stamps, stretch = [], []
    for first, end in zip(np.r_[0, breaks + 1], np.r_[breaks, len(index) - 1]):
        since = travelled[first] - lengths[first]
        while True:
            n = min(first + int(np.searchsorted(travelled[first:end + 1], since + spacing)), end)
            stamps.append(n)
            stretch.append(travelled[n] - since)
            if n == end:
                break
            since, first = travelled[n], n + 1
    air = cut = 0.0
    for n, length in zip(stamps, stretch):
        x, y, z = points[index[n]]
        cells = int((x - x0) // cell) * ny + int((y - y0) // cell) + offsets
        floor = z + lift
        over = (tops[cells] > floor + tol) & (part_face[cells] <= floor + tol)
        if over.any():
            tops[cells[over]] = floor[over]
            cut += length
        else:
            air += length
    if air + cut <= 0.0:
        return empty
    return {"air_fraction": round(float(air / (air + cut)), 4), "air_mm": round(float(air), 1),
            "cut_mm": round(float(cut), 1)}
