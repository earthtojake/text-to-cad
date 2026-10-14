"""``parallel``: finish a 3D surface in parallel passes, each dropped onto the part (drop-cutter).

Keys: ``angle_deg`` (the passes' direction in the WCS XY plane; 0 runs along X), ``pattern`` (``zigzag``, the
default, or ``one_way``), ``min_slope_deg`` / ``max_slope_deg`` (cut only where the surface's slope lies between
them: ``"max_slope_deg": 45`` keeps to the shallow areas and leaves steep walls to ``waterline``); and the shared
``stepover`` (default 0.1 of the diameter: the distance between passes), ``stock_to_leave_mm``, ``faces`` (the tool
centre stays over those faces' footprint) or ``region`` (``{"polygon": [[x, y], ...]}``, WCS). Without faces or a
region the passes cover the part's whole silhouette.

How it plans: passes at the stepover across the boundary, sampled along their length (every half radius, up to a
millimetre; coarser only when the point count would explode, said as an ``adapted`` step) and dropped onto the part
with the stock to leave; wherever the drop-cutter surface strays from the straight move between two samples by more
than half the tolerance, the move is halved (up to ten times), so a vertical step becomes a near-vertical move. Points
then come out again within half the tolerance. Passes are joined zig-zag by short feeds along the surface; a longer
link goes up, across over the stock as it stands (the previous operations simulated) and back down.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["ParallelOp", "parse_parallel", "plan_parallel"]


class ParallelOp(Operation):
    name = "parallel"
    plain = "Parallel finish"
    family = "3D milling"
    machines = MILLS
    status = "full"
    keys = ("angle_deg", "pattern", "min_slope_deg", "max_slope_deg")
    common_keys = ("feed", "speed", "stepover", "stepover_mm", "stock_to_leave_mm")
    tool_types = ("ball", "bull", "flat")
    takes_faces = True
    takes_region = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        return parse_parallel(spec, spec.extra)

    def plan(self, ctx, params):
        return plan_parallel(ctx, params)


def parse_slopes(spec, extra) -> tuple[float, float]:
    low = read_number(extra, "min_slope_deg", spec.where, default=0.0, minimum=0.0, maximum=90.0)
    high = read_number(extra, "max_slope_deg", spec.where, default=90.0, minimum=0.0, maximum=90.0)
    if low >= high:
        raise CamJobError(f"{spec.where}: min_slope_deg ({low:g}) must be less than max_slope_deg ({high:g})")
    return low, high


def parse_parallel(spec, extra) -> dict:
    if spec.faces and spec.region is not None:
        raise CamJobError(f"{spec.where}: give a {spec.op} faces or a region, not both")
    low, high = parse_slopes(spec, extra)
    return {
        "angle_deg": read_number(extra, "angle_deg", spec.where, default=0.0, minimum=-360.0, maximum=360.0),
        "pattern": choice(extra.get("pattern", "zigzag"), ("zigzag", "one_way"), f"{spec.where}.pattern"),
        "min_slope_deg": low, "max_slope_deg": high,
        "region": region_polygon(spec, where=spec.where)[0] if spec.region is not None else None,
    }


def raster_lines(area, stepover: float, angle_deg: float):
    """Passes across ``area`` at ``stepover`` apart along ``angle_deg``: a list of (passes on one line) lists of
    (N, 2) arrays, each running in +direction, lines in order across."""
    import numpy as np
    import shapely
    from shapely import affinity

    turned = affinity.rotate(area, -angle_deg, origin=(0.0, 0.0))
    x0, y0, x1, y1 = turned.bounds
    count = max(1, int(math.ceil((y1 - y0) / stepover - 1e-9)) + 1)
    ys = [0.5 * (y0 + y1)] if y1 - y0 < 1e-9 else list(np.linspace(y0, y1, count))
    c, s = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    rows = []
    for k, y in enumerate(ys):
        # The edge lines sit a hair inside the boundary so they meet it.
        yy = min(max(y, y0 + 1e-7), y1 - 1e-7)
        cut = shapely.LineString([(x0 - 1.0, yy), (x1 + 1.0, yy)]).intersection(turned)
        pieces = []
        for part in shapely.get_parts(cut):
            if part.geom_type != "LineString" or part.length < 1e-6:
                continue
            coords = np.asarray(part.coords)[:, :2]
            if coords[0, 0] > coords[-1, 0]:
                coords = coords[::-1]
            pieces.append(coords)
        pieces.sort(key=lambda p: p[0, 0])
        rows.append([np.column_stack([p[:, 0] * c - p[:, 1] * s, p[:, 0] * s + p[:, 1] * c]) for p in pieces])
    return rows


def densify(coords, spacing: float):
    """A polyline with points no more than ``spacing`` apart (its own points kept)."""
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    out = [coords[:1]]
    for a, b in zip(coords[:-1], coords[1:]):
        n = max(1, int(math.ceil(math.hypot(*(b - a)) / spacing)))
        t = np.arange(1, n + 1)[:, None] / n
        out.append(a + (b - a) * t)
    return np.vstack(out)


def keep_runs(points, keep):
    """The runs of consecutive kept points (at least two each)."""
    import numpy as np

    runs = []
    edges = np.diff(np.concatenate([[0], keep.astype(np.int8), [0]]))
    for a, b in zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]):
        if b - a >= 2:
            runs.append(points[a:b])
    return runs


def plan_parallel(ctx, params, *, limit=None):
    """The parallel toolpath; ``limit`` (a shapely area, WCS) keeps the tool centre inside it (rest machining)."""
    import numpy as np

    from cadgen._internal.cam import fit
    from cadgen._internal.cam.milling3d import Linker, StockNow, boundary, drape, drop_mesh, simplify, slopes

    tool = ctx.tool
    r = tool.radius
    leave = ctx.spec.stock_to_leave_mm
    tol = max(0.002, ctx.tolerance_mm)
    heights = ctx.heights
    floor = heights.part_bottom
    stepover = ctx.stepover(0.1)
    feeds = ctx.feeds("finish", stepover_mm=stepover)
    area = boundary(ctx, params["region"])
    if limit is not None:
        area = area.intersection(limit)
    b = ctx.builder()
    if area.is_empty or area.area < 1e-6:
        ctx.meta["note"] = "nothing to cut: the boundary is empty"
        return b.build()
    mesh = drop_mesh(ctx)
    rows = raster_lines(area, stepover, params["angle_deg"])
    length = sum(float(np.hypot(*np.diff(p, axis=0).T).sum()) for row in rows for p in row)
    spacing, steps = fit.sample_spacing(length, min(1.0, max(0.05, r / 2.0)), fit.Budget(), dims=1,
                                        what="parallel passes")
    ctx.meta["adapted"] = steps
    flat = [(k, densify(p, spacing)) for k, row in enumerate(rows) for p in row]
    draped = drape([p for _, p in flat], tool, mesh, leave=leave, floor=floor, tolerance=tol / 2.0)
    limited = params["min_slope_deg"] > 0 or params["max_slope_deg"] < 90
    passes = []
    for (k, _), points in zip(flat, draped):
        runs = [points]
        if limited:
            slope = slopes(points[:, :2], tool, mesh, leave=leave, floor=floor, step=min(0.25, stepover / 2))
            runs = keep_runs(points, (slope >= params["min_slope_deg"] - 1e-9)
                             & (slope <= params["max_slope_deg"] + 1e-9))
        for run in runs:
            passes.append((k, simplify(run, tol / 2.0)))
    ordered = []
    for k in sorted({k for k, _ in passes}):
        row = [p for kk, p in passes if kk == k]
        if params["pattern"] == "zigzag" and k % 2 == 1:
            row = [p[::-1] for p in reversed(row)]
        ordered.extend(row)
    stock_now = StockNow(ctx)
    link = Linker(ctx, b, mesh, leave=leave, floor=floor, feeds=feeds, hop=max(2.5 * stepover, tool.diameter_mm),
                  stock_now=stock_now)
    if params["pattern"] == "one_way":
        link.hop = 2.5 * stepover
    for points in ordered:
        link.to(points[0])
        b.polyline(points[1:], f=feeds.feed_mm_min)
    link.finish()
    ctx.meta.update({"passes": len(ordered), "stock_to_leave": leave, "links": {"hops": link.hops,
                                                                             "retracts": link.retracts}})
    return b.build()
