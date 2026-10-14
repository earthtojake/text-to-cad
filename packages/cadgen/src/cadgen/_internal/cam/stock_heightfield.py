"""The 3-axis stock simulator: a two-sided heightfield (a top and a bottom height per XY cell, part coordinates).

Each cell of a grid over the stock's footprint holds one column of material, ``[bottom, top]``; an empty column has
``top <= bottom``. A setup whose tool comes from +Z cuts tops down, one from -Z cuts bottoms up, so a part flipped
for its second side is simulated exactly; side and tilted setups are not (:meth:`HeightfieldSim.supports` says so,
and the run reports it as adapted).

:meth:`HeightfieldSim.cut` walks one setup's toolpath in program order, sampled no coarser than a cell. Before each
run of cutting moves it measures how deep the tool sits below the material within reach of its side (the reach
check), then stamps the cutter's profile at every sample (``tool.height_at`` at each cell centre's distance from
the tool axis). Rapids are tested, never stamped: a rapid whose cutter dips more than 0.05 mm into material is a
hit. So is any move made with the spindle stopped (:func:`~cadgen._internal.cam.stock.move_modes`): a tool that is
not turning cuts nothing. A back bore's stopped moves are its bar's neck through the hole, tested with the neck's
radius (``shank_diameter_mm`` / 2) from the tip up. Its head feeding up from under the part cuts the column's far
side (a top setup's bottoms up to the head's top, ``flute_length_mm`` over the tip), never the column above it: one
column of material per cell holds a counterbore cut into the part's back face exactly (its bottom rises), and the
reach check judges the bar from the plan, not from a depth measured here. Each cell remembers the last operation
whose cutter passed over it (``last_op``), so material left is judged against that operation's stock to leave. The
grid's cell is chosen by the fit ladder; its error is about half a cell sideways and nothing vertically.

numpy at import (the engine imports this only when it simulates).
"""

from __future__ import annotations

import math

import numpy as np

from cadgen._internal.cam.fit import op_step
from cadgen._internal.cam.stock import BACK_CUT, CUT, IDLE, NECK, PASS, MaterialLeft, SimReport, move_modes

__all__ = ["HeightfieldSim", "raster_heights"]

#: Cells x kernel cells handled per numpy chunk.
_CHUNK = 4_000_000
#: How far a rapid may dip into material before it is a hit (mm).
RAPID_TOLERANCE = 0.05


def raster_heights(vertices, triangles, x0: float, y0: float, cell: float, nx: int, ny: int):
    """The highest and lowest point of a mesh over each cell centre, ``(top, bottom)`` (nx, ny), NaN where the
    mesh does not cover the cell."""
    top = np.full((nx, ny), -np.inf)
    bottom = np.full((nx, ny), np.inf)
    tri = np.asarray(vertices, dtype=float)[np.asarray(triangles)]
    e1 = tri[:, 1, :2] - tri[:, 0, :2]
    e2 = tri[:, 2, :2] - tri[:, 0, :2]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    keep = np.abs(det) > 1e-12
    tri, det = tri[keep], det[keep]
    lo = np.floor((tri[:, :, :2].min(axis=1) - [x0, y0]) / cell - 0.5).astype(int)
    hi = np.ceil((tri[:, :, :2].max(axis=1) - [x0, y0]) / cell - 0.5).astype(int)
    lo = np.maximum(lo, 0)
    hi = np.minimum(hi, [nx - 1, ny - 1])
    for t in range(len(tri)):
        i0, j0 = lo[t]
        i1, j1 = hi[t]
        if i1 < i0 or j1 < j0:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
        px = x0 + (ii + 0.5) * cell
        py = y0 + (jj + 0.5) * cell
        a, b, c = tri[t]
        # Barycentric coordinates of the cell centres.
        w1 = ((px - a[0]) * (c[1] - a[1]) - (py - a[1]) * (c[0] - a[0])) / det[t]
        w2 = ((b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])) / det[t]
        w0 = 1.0 - w1 - w2
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        ti, tj = ii[inside], jj[inside]
        np.maximum.at(top, (ti, tj), z[inside])
        np.minimum.at(bottom, (ti, tj), z[inside])
    top[np.isinf(top)] = np.nan
    bottom[np.isinf(bottom)] = np.nan
    return top, bottom


class _Neck:
    """A back-boring bar's neck as the rapid test reads a tool: a flat cylinder of its radius from the tip up."""

    def __init__(self, radius: float):
        self.radius = float(radius)

    def height_at(self, d):
        d = np.abs(np.asarray(d, dtype=float))
        return np.where(d <= self.radius + 1e-12, 0.0, np.inf)


class HeightfieldSim:
    kind = "heightfield"
    #: :meth:`material_left` takes ``leave_by_op`` (each cell judged by the last operation that covered it).
    tracks_ops = True

    def __init__(self, stock, part=None, *, cell_mm: float, tolerance_mm: float = 0.01):
        low, high = np.asarray(stock.bounds_min, dtype=float), np.asarray(stock.bounds_max, dtype=float)
        self.cell = float(cell_mm)
        self.x0, self.y0 = float(low[0]), float(low[1])
        self.nx = max(1, int(math.ceil((high[0] - low[0]) / self.cell)))
        self.ny = max(1, int(math.ceil((high[1] - low[1]) / self.cell)))
        top, bottom = raster_heights(stock.vertices, stock.triangles, self.x0, self.y0, self.cell, self.nx, self.ny)
        empty = np.isnan(top)
        self.floor = float(low[2])
        self.top = np.where(empty, self.floor, top)
        self.bottom = np.where(empty, self.floor, bottom)
        self.tolerance = float(tolerance_mm)
        #: Sample spacing along the path (the fit ladder may raise it past the cell).
        self.step = self.cell
        self.cut_from_below = False
        self._part_heights = None
        #: The last operation whose cutter covered each cell (-1: none yet).
        self.last_op = np.full((self.nx, self.ny), -1, dtype=np.int64)
        self._op = -1

    @property
    def cells(self) -> int:
        return self.nx * self.ny

    def supports(self, wcs) -> str | None:
        axis = wcs.tool_axis
        if abs(abs(axis[2]) - 1.0) < 1e-9:
            return None
        return (f"the heightfield stock simulates only top and bottom setups; setup '{wcs.setup_id}' comes from the "
                "side, so its cuts are not simulated")

    def volume(self) -> float:
        return float(np.clip(self.top - self.bottom, 0.0, None).sum() * self.cell * self.cell)

    # --- cutting ---------------------------------------------------------------------------------------

    def _kernel(self, reach: float):
        k = int(math.ceil(reach / self.cell)) + 1
        di, dj = np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1), indexing="ij")
        return di.ravel(), dj.ravel()

    def _cells(self, points, di, dj):
        """Kernel cells round each point: flat indices, validity, distance from the point's axis."""
        ci = np.floor((points[:, 0] - self.x0) / self.cell).astype(np.int64)
        cj = np.floor((points[:, 1] - self.y0) / self.cell).astype(np.int64)
        ii = ci[:, None] + di[None, :]
        jj = cj[:, None] + dj[None, :]
        valid = (ii >= 0) & (ii < self.nx) & (jj >= 0) & (jj < self.ny)
        cx = self.x0 + (ii + 0.5) * self.cell
        cy = self.y0 + (jj + 0.5) * self.cell
        d = np.hypot(cx - points[:, 0:1], cy - points[:, 1:2])
        flat = np.where(valid, ii * self.ny + jj, 0)
        return flat, valid, d

    def _depth(self, points, tool, direction: int, di, dj):
        """The deepest any point sits below material within reach of the tool's side: (depth, point index)."""
        reach = tool.radius + max(self.cell, 0.2)
        best, where = -np.inf, -1
        step = max(1, _CHUNK // max(1, len(di)))
        top, bottom = self.top.ravel(), self.bottom.ravel()
        for s in range(0, len(points), step):
            chunk = points[s:s + step]
            flat, valid, d = self._cells(chunk, di, dj)
            near = valid & (d <= reach) & (top[flat] > bottom[flat] + 1e-9)
            if direction > 0:
                depth = np.where(near, top[flat] - chunk[:, 2:3], -np.inf)
            else:
                depth = np.where(near, chunk[:, 2:3] - bottom[flat], -np.inf)
            per = depth.max(axis=1)
            k = int(np.argmax(per))
            if per[k] > best:
                best, where = float(per[k]), s + k
        return best, where

    def _stamp(self, points, tool, direction: int, di, dj, offset: float = 0.0) -> None:
        """Cut the cutter's profile at every point from ``direction``'s side (+1: tops down, -1: bottoms up),
        ``offset`` mm along part z from the point (a back bore's head top over its tip)."""
        step = max(1, _CHUNK // max(1, len(di)))
        top, bottom = self.top.ravel(), self.bottom.ravel()
        last = self.last_op.reshape(-1)
        for s in range(0, len(points), step):
            chunk = points[s:s + step]
            flat, valid, d = self._cells(chunk, di, dj)
            heights = tool.height_at(d)
            inside = valid & np.isfinite(heights)
            surface = chunk[:, 2:3] + offset + direction * heights
            if direction > 0:
                np.minimum.at(top, flat[inside], surface[inside])
            else:
                np.maximum.at(bottom, flat[inside], surface[inside])
            last[flat[inside]] = self._op
        self.top = top.reshape(self.nx, self.ny)
        self.bottom = bottom.reshape(self.nx, self.ny)

    def _rapid_hit(self, points, tool, direction: int, di, dj):
        """(penetration, point index) of the worst rapid sample, or (0, -1)."""
        step = max(1, _CHUNK // max(1, len(di)))
        top, bottom = self.top.ravel(), self.bottom.ravel()
        worst, where = 0.0, -1
        for s in range(0, len(points), step):
            chunk = points[s:s + step]
            flat, valid, d = self._cells(chunk, di, dj)
            heights = tool.height_at(d)
            inside = valid & np.isfinite(heights) & (top[flat] > bottom[flat] + 1e-9)
            surface = chunk[:, 2:3] + direction * heights
            if direction > 0:
                dip = np.where(inside, top[flat] - surface, 0.0)
            else:
                dip = np.where(inside, surface - bottom[flat], 0.0)
            per = dip.max(axis=1)
            k = int(np.argmax(per))
            if per[k] > worst:
                worst, where = float(per[k]), s + k
        return worst, where

    def cut(self, toolpath, tools: dict, wcs) -> SimReport:
        report = SimReport(setup=wcs.setup_id)
        reason = self.supports(wcs)
        if reason:
            report.skipped = reason
            return report
        direction = 1 if wcs.tool_axis[2] > 0 else -1
        if direction < 0:
            self.cut_from_below = True
        modes = move_modes(toolpath)
        for op in toolpath.ops:
            tool = tools.get(op.tool) if op.tool else None
            if tool is None or tool.family != "mill" or op.end <= op.start:
                continue
            piece = toolpath.slice(op.start, op.end)
            samples = piece.sample(self.tolerance, max_step_mm=op_step(self.step, self.cell, tool))
            points = wcs.from_wcs(samples.points)
            # Each sample's move's mode; the first sample (where the op starts) neither cuts nor moves.
            classes = np.where(samples.move >= 0, modes[op.start + np.maximum(samples.move, 0)], IDLE)
            neck = _Neck(tool.holder.shank_diameter_mm / 2.0) if (classes == NECK).any() else None
            di, dj = self._kernel(tool.radius + max(self.cell, 0.2))
            before = self.volume()
            self._op = int(op.index)
            # Runs of consecutive samples of one class, in program order.
            breaks = np.nonzero(np.diff(classes))[0] + 1
            starts = np.concatenate([[0], breaks])
            ends = np.concatenate([breaks, [len(classes)]])
            deepest = {"depth_mm": -np.inf, "at": None}
            worst = {mode: {"depth_mm": 0.0, "at": None, "move": None, "count": 0} for mode in (PASS, NECK)}
            for a, b in zip(starts, ends):
                kind = classes[a]
                if kind in (CUT, BACK_CUT):
                    # A cutting run starts where the previous sample ended.
                    run = points[max(0, a - 1):b]
                    if kind == BACK_CUT:
                        # The head feeds up from under the part: it cuts the column's far side, never its near one
                        # (the reach of a back bore is judged by ``reach`` from the plan, not measured here).
                        self._stamp(run, tool, -direction, di, dj, offset=direction * tool.flute_length_mm)
                        continue
                    depth, k = self._depth(run, tool, direction, di, dj)
                    if depth > deepest["depth_mm"]:
                        deepest = {"depth_mm": depth, "at": run[k]}
                    self._stamp(run, tool, direction, di, dj)
                elif kind in (PASS, NECK):
                    run = points[a:b]
                    if kind == NECK:
                        dip, k = self._rapid_hit(run, neck, direction, *self._kernel(neck.radius + self.cell))
                    else:
                        dip, k = self._rapid_hit(run, tool, direction, di, dj)
                    if dip > RAPID_TOLERANCE:
                        hit = worst[kind]
                        hit["count"] += 1
                        if dip > hit["depth_mm"]:
                            hit.update(depth_mm=dip, at=run[k], move=int(op.start + samples.move[a + k]))
            report.removed_mm3_by_op[op.index] = before - self.volume()
            if deepest["at"] is not None:
                report.depth_by_op[op.index] = {"depth_mm": round(float(deepest["depth_mm"]), 4),
                                                "at": [round(float(v), 4) for v in deepest["at"]]}
            for mode, hit in worst.items():
                if hit["count"]:
                    report.rapid_hits.append({"op": op.index, "move": hit["move"], "count": hit["count"],
                                              "depth_mm": round(hit["depth_mm"], 4),
                                              "at": [round(float(v), 4) for v in hit["at"]],
                                              **({"neck_diameter_mm": round(2 * neck.radius, 4)}
                                                 if mode == NECK else {})})
        return report

    # --- results -------------------------------------------------------------------------------------------

    def _part(self, part):
        if self._part_heights is None:
            self._part_heights = raster_heights(part.vertices, part.triangles, self.x0, self.y0, self.cell,
                                                self.nx, self.ny)
        return self._part_heights

    def material_left(self, part, *, stock_to_leave_mm: float, tolerance_mm: float,
                      leave_by_op: dict | None = None) -> MaterialLeft:
        """Stock still standing above the part (and below it, when a bottom setup was cut) by more than the stock to
        leave plus a tolerance. Columns where the part has no material are not judged (they are not over the
        part). With ``leave_by_op`` ({operation index: stock to leave}) each cell is judged by the stock to leave
        of the last operation that covered it; ``stock_to_leave_mm`` where none did."""
        part_top, part_bottom = self._part(part)
        has_part = ~np.isnan(part_top)
        exists = self.top > self.bottom + 1e-9
        excess = np.where(has_part & exists, self.top - np.where(has_part, part_top, 0.0), 0.0)
        if self.cut_from_below:
            below = np.where(has_part & exists, np.where(has_part, part_bottom, 0.0) - self.bottom, 0.0)
            excess = np.maximum(excess, below)
        leave = np.full(self.last_op.shape, float(stock_to_leave_mm))
        if leave_by_op:
            ops = np.array(sorted(leave_by_op), dtype=np.int64)
            values = np.array([float(leave_by_op[k]) for k in ops])
            covered = np.isin(self.last_op, ops)
            leave[covered] = values[np.searchsorted(ops, self.last_op[covered])]
        threshold = leave + max(0.05, tolerance_mm)
        over = excess > threshold
        if not over.any():
            return MaterialLeft(0.0, 0.0, 0.0, None)
        i, j = np.unravel_index(int(np.argmax(np.where(over, excess, -np.inf))), excess.shape)
        x = self.x0 + (i + 0.5) * self.cell
        y = self.y0 + (j + 0.5) * self.cell
        ii, jj = np.nonzero(over)
        bounds_min = (float(self.x0 + ii.min() * self.cell), float(self.y0 + jj.min() * self.cell), float(part_top[over].min()))
        bounds_max = (float(self.x0 + (ii.max() + 1) * self.cell), float(self.y0 + (jj.max() + 1) * self.cell),
                      float(self.top[over].max()))
        area = float(over.sum() * self.cell * self.cell)
        return MaterialLeft(volume_mm3=float((excess[over]).sum() * self.cell * self.cell), area_mm2=area,
                            max_mm=float(excess[i, j]), at=(float(x), float(y), float(self.top[i, j])),
                            bounds_min=bounds_min, bounds_max=bounds_max)

    def mesh(self, max_cells: int = 300):
        """The stock now as a closed-ish surface: tops and bottoms at cell centres, skirts round the edges. Grids
        larger than ``max_cells`` a side are shown at a block size (tops by block maximum, bottoms by minimum).
        Square blocks of cells that lie on one plane to :data:`DISPLAY_MM` (the uncut top, a floor, a ramp, a
        finish's fine scallops) are one quad each (:func:`_block_triangles`), so a part's stock is a few hundred
        kilobytes, not megabytes; where a big block meets small ones the gap is at most that much."""
        factor = max(1, int(math.ceil(max(self.nx, self.ny) / max_cells)))
        top, bottom = self.top, self.bottom
        if factor > 1:
            mx, my = int(math.ceil(self.nx / factor)), int(math.ceil(self.ny / factor))
            pad_t = np.full((mx * factor, my * factor), -np.inf)
            pad_b = np.full((mx * factor, my * factor), np.inf)
            exists = self.top > self.bottom + 1e-9
            pad_t[:self.nx, :self.ny] = np.where(exists, self.top, -np.inf)
            pad_b[:self.nx, :self.ny] = np.where(exists, self.bottom, np.inf)
            top = pad_t.reshape(mx, factor, my, factor).max(axis=(1, 3))
            bottom = pad_b.reshape(mx, factor, my, factor).min(axis=(1, 3))
            empty = ~np.isfinite(top)
            top = np.where(empty, self.floor, top)
            bottom = np.where(empty, self.floor, bottom)
        mx, my = top.shape
        cell = self.cell * factor
        exists = top > bottom + 1e-9
        xs = self.x0 + (np.arange(mx) + 0.5) * cell
        ys = self.y0 + (np.arange(my) + 0.5) * cell
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        count = mx * my
        vertices = np.vstack([np.column_stack([gx.ravel(), gy.ravel(), top.ravel()]),
                              np.column_stack([gx.ravel(), gy.ravel(), bottom.ravel()])])
        if mx < 2 or my < 2:
            return vertices, np.zeros((0, 3), dtype=np.int64)
        quad = exists[:-1, :-1] & exists[1:, :-1] & exists[1:, 1:] & exists[:-1, 1:]
        top_tris = _block_triangles(top, quad, my)
        bottom_tris = _block_triangles(bottom, quad, my)[:, [0, 2, 1]] + count
        # Skirts on the cell grid's own boundary (between a cell that exists and one that does not), so the merged
        # blocks' long edges never read as boundary.
        index = np.arange(count).reshape(mx, my)
        padded = np.zeros((mx + 1, my + 1), dtype=bool)
        padded[1:-1, 1:-1] = quad
        inner = padded[1:-1, 1:-1]
        a, b = index[:-1, :-1], index[1:, :-1]
        c, d = index[1:, 1:], index[:-1, 1:]
        sides = []
        for corner_a, corner_b, open_ in ((a, b, ~padded[1:-1, :-2]), (b, c, ~padded[2:, 1:-1]),
                                          (c, d, ~padded[1:-1, 2:]), (d, a, ~padded[:-2, 1:-1])):
            keep = inner & open_
            sides.append(np.column_stack([corner_a[keep], corner_b[keep]]))
        boundary = np.vstack(sides)
        skirt = np.vstack([np.column_stack([boundary[:, 1], boundary[:, 0], boundary[:, 0] + count]),
                           np.column_stack([boundary[:, 1], boundary[:, 0] + count, boundary[:, 1] + count])])
        triangles = np.vstack([top_tris, bottom_tris, skirt]).astype(np.int64)
        # Only the vertices the merged surface uses.
        used, triangles = np.unique(triangles, return_inverse=True)
        return vertices[used], triangles.reshape(-1, 3).astype(np.int64)


#: How far a merged block's own vertices may stand off its plane (mm): far below what the viewer shows of a
#: translucent stock, and the most a block's edge can stand off a smaller neighbour's vertex. The simulation
#: itself, and every check, keep the full grid: only the drawing is merged.
DISPLAY_MM = 0.02


def _block_triangles(height, quad, my: int, tolerance: float = DISPLAY_MM):
    """Triangles (vertex indices into a row-major ``(mx, my)`` grid) covering every cell where ``quad`` is true:
    aligned square blocks of 2^L cells whose every vertex lies within ``tolerance`` of the plane through the block's
    corners are two triangles each (a quadtree, judged bottom up and emitted top down), every other cell two
    triangles of its own. Counter-clockwise seen from +Z."""
    from numpy.lib.stride_tricks import sliding_window_view

    cx, cy = quad.shape
    h = np.asarray(height, dtype=float)
    whole = [quad]                          # every cell of the block exists
    levels = [None]
    size = 1
    while True:
        below = whole[-1]
        nb, mb = below.shape[0] // 2, below.shape[1] // 2
        if not nb or not mb:
            break
        size *= 2
        full = below[0:2 * nb:2, 0:2 * mb:2] & below[1:2 * nb:2, 0:2 * mb:2] & below[0:2 * nb:2, 1:2 * mb:2] \
            & below[1:2 * nb:2, 1:2 * mb:2]
        whole.append(full)
        if not full.any():
            levels.append(full)
            break
        window = sliding_window_view(h[:nb * size + 1, :mb * size + 1], (size + 1, size + 1))[::size, ::size]
        corner = window[:, :, 0, 0][:, :, None, None]
        steps = np.arange(size + 1, dtype=float)
        slope_x = (window[:, :, size, 0] - window[:, :, 0, 0])[:, :, None, None] / size
        slope_y = (window[:, :, 0, size] - window[:, :, 0, 0])[:, :, None, None] / size
        plane = corner + slope_x * steps[:, None] + slope_y * steps[None, :]
        flat = np.abs(window - plane).max(axis=(2, 3)) <= tolerance
        levels.append(full & flat)
    covered = np.zeros((cx, cy), dtype=bool)
    out = []
    for level in range(len(levels) - 1, 0, -1):
        size = 2 ** level
        blocks = levels[level]
        free = ~covered[::size, ::size][:blocks.shape[0], :blocks.shape[1]]
        emit = blocks & free
        if not emit.any():
            continue
        bi, bj = np.nonzero(emit)
        i0, j0 = bi * size, bj * size
        a, b = i0 * my + j0, (i0 + size) * my + j0
        c, d = (i0 + size) * my + j0 + size, i0 * my + j0 + size
        out += [np.column_stack([a, b, c]), np.column_stack([a, c, d])]
        mark = np.zeros_like(blocks)
        mark[bi, bj] = True
        grown = np.kron(mark, np.ones((size, size), dtype=bool))
        covered[:grown.shape[0], :grown.shape[1]] |= grown
    ci, cj = np.nonzero(quad & ~covered)
    a, b = ci * my + cj, (ci + 1) * my + cj
    c, d = (ci + 1) * my + cj + 1, ci * my + cj + 1
    out += [np.column_stack([a, b, c]), np.column_stack([a, c, d])]
    return np.vstack(out).astype(np.int64)
