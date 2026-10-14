"""``pencil`` (lite): one pass along each inside crease and corner, where the tool touches two surfaces at once.

Keys: ``crease_deg`` (how sharply the drop-cutter surface must bend for a crease, default 30); and the shared
``stock_to_leave_mm``, ``faces`` (only over those faces' footprint) or ``region`` (``{"polygon": [[x, y], ...]}``,
WCS). Without faces or a region it looks over the part's whole silhouette.

How it plans: the drop-cutter height over a grid (spacing a sixth of the tool's radius, between 0.05 and 0.25 mm;
coarser only for a part too big for the point budget, said as an ``adapted`` step). Where the tool touches two
surfaces at once, its height bends sharply upward in some direction (a valley in the drop-cutter surface): a grid
point whose slope turns upward by more than ``crease_deg`` across it, and more than at its neighbours that way, is on
a crease. Crease points are joined into polylines, smoothed, dropped onto the part again (refined like ``parallel``)
and cut one after another, nearest first.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["PencilOp"]


class PencilOp(Operation):
    name = "pencil"
    plain = "Pencil"
    family = "3D milling"
    machines = MILLS
    status = "lite"
    limits = (
        "Creases are found on a sampling grid: each pass lies within one grid spacing of the true corner, on the "
        "side away from the part, so up to that much can stay in a corner.",
        "One pass per crease at the tool's own radius; a corner much tighter than the tool needs a smaller tool "
        "(rest machining), not more pencil passes.",
        "Creases shorter than four grid points, or bending less than crease_deg, are not traced.",
    )
    keys = ("crease_deg",)
    common_keys = ("feed", "speed", "stock_to_leave_mm")
    tool_types = ("ball", "bull", "flat")
    takes_faces = True
    takes_region = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if spec.faces and spec.region is not None:
            raise CamJobError(f"{spec.where}: give a pencil faces or a region, not both")
        return {
            "crease_deg": read_number(spec.extra, "crease_deg", spec.where, default=30.0, maximum=170.0),
            "region": region_polygon(spec, where=spec.where)[0] if spec.region is not None else None,
        }

    def plan(self, ctx, params):
        import numpy as np
        import shapely

        from cadgen._internal.cam import fit
        from cadgen._internal.cam.dropcutter import zmap
        from cadgen._internal.cam.milling3d import Linker, StockNow, boundary, drape, drop_mesh, simplify
        from cadgen._internal.cam.operations.parallel import densify

        tool = ctx.tool
        r = tool.radius
        leave = ctx.spec.stock_to_leave_mm
        tol = max(0.002, ctx.tolerance_mm)
        heights = ctx.heights
        floor = heights.part_bottom
        feeds = ctx.feeds("finish", stepover_mm=r)
        area = boundary(ctx, params["region"])
        b = ctx.builder()
        if area.is_empty or area.area < 1e-6:
            ctx.meta["note"] = "nothing to cut: the boundary is empty"
            return b.build()
        x0, y0, x1, y1 = area.bounds
        spacing, steps = fit.sample_spacing((x1 - x0 + 2) * (y1 - y0 + 2), min(0.25, max(0.05, r / 6.0)), fit.Budget(),
                                            dims=2, what="pencil grid")
        ctx.meta["adapted"] = steps
        mesh = drop_mesh(ctx)
        gx0, gy0 = x0 - spacing, y0 - spacing
        nx = int(math.ceil((x1 - x0) / spacing)) + 3
        ny = int(math.ceil((y1 - y0) / spacing)) + 3
        grid = zmap(mesh, tool, gx0, gy0, spacing, nx, ny, leave=leave, floor=floor)
        xs, ys = gx0 + np.arange(nx) * spacing, gy0 + np.arange(ny) * spacing
        inside = shapely.contains_xy(area, *np.meshgrid(xs, ys, indexing="ij"))
        on_floor = grid <= floor + 1e-9
        threshold = math.radians(params["crease_deg"])
        crease = np.zeros_like(inside)
        for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
            step = spacing * math.hypot(di, dj)
            plus = _shift(grid, di, dj)
            minus = _shift(grid, -di, -dj)
            bend = np.arctan((plus - grid) / step) - np.arctan((grid - minus) / step)
            bend = np.nan_to_num(bend, nan=0.0, neginf=0.0, posinf=0.0)
            valid = ~on_floor & ~(_shift(on_floor.astype(float), di, dj) > 0.5) & \
                ~(_shift(on_floor.astype(float), -di, -dj) > 0.5)
            peak = (bend >= _shift(bend, di, dj)) & (bend >= _shift(bend, -di, -dj))
            crease |= valid & (bend > threshold) & peak
        crease &= inside
        chains = _chains(crease)
        lines = []
        for chain in chains:
            if len(chain) < 4:
                continue
            xy = np.column_stack([xs[chain[:, 0]], ys[chain[:, 1]]])
            closed = len(chain) > 4 and np.abs(chain[0] - chain[-1]).max() <= 1
            if closed:
                xy = np.vstack([xy, xy[:1]])
            lines.append(_smooth(xy, closed))
        draped = drape([densify(line, max(spacing, 0.05)) for line in lines], tool, mesh, leave=leave, floor=floor,
                       tolerance=tol / 2.0)
        link = Linker(ctx, b, mesh, leave=leave, floor=floor, feeds=feeds, hop=tool.diameter_mm,
                      stock_now=StockNow(ctx))
        remaining = [simplify(points, tol / 2.0) for points in draped]
        while remaining:
            here = np.asarray(b.pos[:2])
            k = min(range(len(remaining)), key=lambda i: min(np.hypot(*(remaining[i][0, :2] - here)),
                                                             np.hypot(*(remaining[i][-1, :2] - here))))
            points = remaining.pop(k)
            if np.hypot(*(points[-1, :2] - here)) < np.hypot(*(points[0, :2] - here)):
                points = points[::-1]
            link.to(points[0])
            b.polyline(points[1:], f=feeds.feed_mm_min)
        link.finish()
        ctx.meta.update({"passes": len(draped), "stock_to_leave": leave, "grid_mm": round(spacing, 4),
                         "links": {"hops": link.hops, "retracts": link.retracts}})
        return b.build()


def _shift(grid, di: int, dj: int):
    """``grid`` read at ``(i + di, j + dj)``; NaN off the edge."""
    import numpy as np

    out = np.full(grid.shape, np.nan)
    nx, ny = grid.shape
    out[max(0, -di):nx - max(0, di), max(0, -dj):ny - max(0, dj)] = \
        grid[max(0, di):nx - max(0, -di), max(0, dj):ny - max(0, -dj)]
    return out


def _chains(mask):
    """The marked grid points joined into chains of 8-neighbours: a list of (N, 2) index arrays, each walked from an
    end (or anywhere round a loop), going straight on where it can."""
    import numpy as np

    points = {tuple(p) for p in np.argwhere(mask).tolist()}
    around = [(di, dj) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]

    def neighbours(p):
        return [(p[0] + di, p[1] + dj) for di, dj in around if (p[0] + di, p[1] + dj) in points]

    chains = []
    while points:
        ends = [p for p in points if len(neighbours(p)) <= 1]
        start = min(ends) if ends else min(points)
        chain = [start]
        points.discard(start)
        heading = None
        while True:
            options = neighbours(chain[-1])
            if not options:
                break
            if heading is not None:
                options.sort(key=lambda q: -((q[0] - chain[-1][0]) * heading[0] + (q[1] - chain[-1][1]) * heading[1]))
            nxt = options[0]
            heading = (nxt[0] - chain[-1][0], nxt[1] - chain[-1][1])
            chain.append(nxt)
            points.discard(nxt)
        chains.append(np.asarray(chain))
    return chains


def _smooth(xy, closed: bool, passes: int = 3):
    """A grid staircase eased by a few rounds of neighbour averaging (the ends of an open line held)."""
    import numpy as np

    xy = np.asarray(xy, dtype=float)
    if len(xy) < 3:
        return xy
    for _ in range(passes):
        if closed:
            body = xy[:-1]
            body = 0.25 * np.roll(body, 1, axis=0) + 0.5 * body + 0.25 * np.roll(body, -1, axis=0)
            xy = np.vstack([body, body[:1]])
        else:
            inner = 0.25 * xy[:-2] + 0.5 * xy[1:-1] + 0.25 * xy[2:]
            xy = np.vstack([xy[:1], inner, xy[-1:]])
    return xy
