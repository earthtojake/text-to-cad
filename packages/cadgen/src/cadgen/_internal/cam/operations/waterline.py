"""``waterline``: finish steep walls in constant-height loops, each the line where the tool touches the part at its
level.

Keys: ``min_slope_deg`` / ``max_slope_deg`` (keep to where the surface's slope lies between them, e.g.
``"min_slope_deg": 40`` for steep walls only), ``direction`` (``climb``, the default, or ``conventional``); and the
shared ``stepdown_mm`` (the height between levels; default the stepover, 0.1 of the diameter), ``stock_to_leave_mm``,
``faces`` (the tool centre stays over those faces' footprint, grown by the tool's radius) or ``region``
(``{"polygon": [[x, y], ...]}``, WCS). Without faces or a region it runs round the whole part.

How it plans: the drop-cutter height over a grid covering the boundary (spacing a quarter of the radius, between
0.1 and 0.5 mm; coarser only for a part too big for the point budget, said as an ``adapted`` step), once. At each
level from the top down, marching squares finds where the grid crosses the level; each crossing is then bisected
along its grid edge with the drop-cutter until it sits on the free side within a quarter of the tolerance, so the loop
is where the tool touches, not an interpolation. Wherever the straight move between two loop points would cut more
than half the tolerance into the part, a point pushed out onto the contact is added between them. Loops run with
the part on the right (climb) and come out again within half the tolerance; from one level to the next the tool
steps down where the way is clear, else it lifts and comes down over the stock as it stands.

A feature narrower than the grid can fall between its points and be missed (the gouge check still judges every
move against the part).
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon
from cadgen._internal.cam.operations.parallel import keep_runs, parse_slopes

__all__ = ["WaterlineOp", "parse_waterline", "plan_waterline"]


class WaterlineOp(Operation):
    name = "waterline"
    plain = "Waterline"
    family = "3D milling"
    machines = MILLS
    status = "full"
    keys = ("min_slope_deg", "max_slope_deg", "direction")
    tool_types = ("ball", "bull", "flat")
    takes_faces = True
    takes_region = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        return parse_waterline(spec, spec.extra)

    def plan(self, ctx, params):
        return plan_waterline(ctx, params)


def parse_waterline(spec, extra) -> dict:
    if spec.faces and spec.region is not None:
        raise CamJobError(f"{spec.where}: give a {spec.op} faces or a region, not both")
    low, high = parse_slopes(spec, extra)
    return {
        "min_slope_deg": low, "max_slope_deg": high,
        "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{spec.where}.direction")
        == "climb",
        "region": region_polygon(spec, where=spec.where)[0] if spec.region is not None else None,
    }


def plan_waterline(ctx, params, *, limit=None):
    """The waterline toolpath; ``limit`` (a shapely area, WCS) keeps the tool centre inside it (rest machining)."""
    import numpy as np
    import shapely

    from cadgen._internal.cam import fit
    from cadgen._internal.cam.dropcutter import contours, drop, push, zmap
    from cadgen._internal.cam.milling3d import Linker, StockNow, boundary, drop_mesh, simplify

    tool = ctx.tool
    r = tool.radius
    leave = ctx.spec.stock_to_leave_mm
    tol = max(0.002, ctx.tolerance_mm)
    heights = ctx.heights
    floor = heights.part_bottom
    stepdown = ctx.spec.stepdown_mm if ctx.spec.stepdown_mm is not None else ctx.stepover(0.1)
    feeds = ctx.feeds("finish", stepover_mm=stepdown)
    area = boundary(ctx, params["region"], grow=r + leave + 0.5)
    if limit is not None:
        area = area.intersection(limit)
    b = ctx.builder()
    if area.is_empty or area.area < 1e-6:
        ctx.meta["note"] = "nothing to cut: the boundary is empty"
        return b.build()
    mesh = drop_mesh(ctx)
    x0, y0, x1, y1 = area.bounds
    spacing, steps = fit.sample_spacing((x1 - x0 + 2) * (y1 - y0 + 2), min(0.5, max(0.1, r / 4.0)), fit.Budget(),
                                        dims=2, what="waterline grid")
    ctx.meta["adapted"] = steps
    gx0, gy0 = x0 - spacing, y0 - spacing
    nx = int(math.ceil((x1 - x0) / spacing)) + 3
    ny = int(math.ceil((y1 - y0) / spacing)) + 3
    grid = zmap(mesh, tool, gx0, gy0, spacing, nx, ny, leave=leave, floor=floor)
    inside = shapely.contains_xy(area, *np.meshgrid(gx0 + np.arange(nx) * spacing, gy0 + np.arange(ny) * spacing,
                                                    indexing="ij"))
    if not inside.any():
        ctx.meta["note"] = "nothing to cut: the boundary holds no grid point"
        return b.build()
    gz = np.gradient(grid, spacing)
    slope_grid = np.degrees(np.arctan(np.hypot(gz[0], gz[1])))
    top = float(grid[inside].max())
    low = float(grid[inside].min())
    if top - low < 1e-6:
        ctx.meta["note"] = "nothing to cut: the part is flat inside the boundary"
        return b.build()
    from cadgen._internal.cam.job_errors import level_count

    count = level_count(top, low, stepdown)
    levels = [top - (top - low) * (k + 0.5) / count for k in range(count)]
    # Never exactly on a flat: a level a hair above one finds its walls.
    flats = np.unique(np.round(grid[inside], 4))
    levels = [z + 2e-4 if np.any(np.abs(flats - z) < 1e-4) else z for z in levels]
    fine = max(tol / 4.0, 1e-4)

    def refine(free_xy, blocked_xy, level):
        """Each crossing moved from its free node toward its blocked one onto the contact, ending on the free side
        within ``fine``: false position and bisection by turns, each point dropped only until it converges."""
        lo, hi = free_xy.copy(), blocked_xy.copy()
        z_lo = drop(lo, tool, mesh, leave=leave, floor=floor)
        z_hi = drop(hi, tool, mesh, leave=leave, floor=floor)
        active = np.nonzero(np.hypot(*(hi - lo).T) > fine)[0]
        for step in range(64):
            if not len(active):
                break
            a, c = lo[active], hi[active]
            za, zc = z_lo[active], z_hi[active]
            t = np.full(len(active), 0.5)
            if step % 2 == 0:
                # False position where the surface is smooth; a jump (a vertical wall) is only ever halved.
                with np.errstate(invalid="ignore", divide="ignore"):
                    guess = (level[active] - za) / (zc - za)
                smooth = np.isfinite(guess) & (np.abs(zc - za) < 4.0 * np.hypot(*(c - a).T))
                t = np.where(smooth, np.clip(np.nan_to_num(guess, nan=0.5), 0.02, 0.98), 0.5)
            mid = a + (c - a) * t[:, None]
            zm = drop(mid, tool, mesh, leave=leave, floor=floor)
            ok = zm <= level[active]
            lo[active] = np.where(ok[:, None], mid, a)
            z_lo[active] = np.where(ok, zm, za)
            hi[active] = np.where(ok[:, None], c, mid)
            z_hi[active] = np.where(ok, zc, zm)
            active = active[np.hypot(*(hi[active] - lo[active]).T) > fine]
        return lo

    def slope_at(xy):
        i = np.clip(np.rint((xy[:, 0] - gx0) / spacing).astype(int), 0, nx - 1)
        j = np.clip(np.rint((xy[:, 1] - gy0) / spacing).astype(int), 0, ny - 1)
        return slope_grid[i, j]

    limited = params["min_slope_deg"] > 0 or params["max_slope_deg"] < 90
    pieces = []
    for level, lines in zip(levels, contours(grid, levels, gx0, gy0, spacing, refine=refine)):
        for line in lines:
            closed = len(line) > 3 and bool(np.allclose(line[0], line[-1]))
            whole = shapely.LineString(line)
            if whole.within(area.buffer(1e-9)):
                pieces.append((level, line, closed))
                continue
            clipped = whole.intersection(area)
            parts = shapely.get_parts(shapely.line_merge(clipped) if clipped.geom_type == "MultiLineString" else clipped)
            pieces += [(level, np.asarray(p.coords)[:, :2], False) for p in parts
                       if p.geom_type == "LineString" and p.length > 1e-3]
    fixed = _fix_chords([p for _, p, _ in pieces], np.array([z for z, _, _ in pieces]), tool, mesh, leave, floor,
                        spacing, tol, push, drop)
    loops = []
    for (level, _, closed), piece in zip(pieces, fixed):
        runs = [piece]
        if limited:
            slope = slope_at(piece)
            keep = (slope >= params["min_slope_deg"] - 1e-9) & (slope <= params["max_slope_deg"] + 1e-9)
            if not keep.all():
                runs = keep_runs(piece, keep)
                closed = False
        for run in runs:
            loops.append((level, run, closed and len(runs) == 1))
    climbs = _orient([run for _, run, _ in loops], np.array([z for z, _, _ in loops]), tool, mesh, leave, floor,
                     params["climb"], drop)
    loops = [(level, simplify(np.column_stack([run, np.full(len(run), level)]), tol / 2.0), closed)
             for (level, _, closed), run in zip(loops, climbs)]
    stock_now = StockNow(ctx)
    link = Linker(ctx, b, mesh, leave=leave, floor=floor, feeds=feeds, hop=max(2.5 * stepdown, 0.5 * tool.diameter_mm),
                  stock_now=stock_now)
    remaining = list(loops)
    while remaining:
        level = remaining[0][0]
        here = np.asarray(b.pos[:2])
        same = [k for k, item in enumerate(remaining) if abs(item[0] - level) < 1e-9]
        best, start = None, 0
        for k in same:
            pts = remaining[k][1]
            d = np.hypot(pts[:, 0] - here[0], pts[:, 1] - here[1])
            j = int(np.argmin(d)) if remaining[k][2] else (0 if d[0] <= d[-1] or True else len(d) - 1)
            if best is None or d[j] < best[0]:
                best, start = (d[j], k), j
        _, k = best
        _, points, closed = remaining.pop(k)
        if closed and start:
            points = np.vstack([points[start:-1], points[:start + 1]])
        # Step down from the last loop: only when the straight way is clear of the part.
        if link.cutting:
            hop = np.linspace(np.asarray(b.pos), points[0], 8)
            clear = drop(hop[:, :2], tool, mesh, leave=leave, floor=floor) <= hop[:, 2] + 1e-6
            if not clear.all():
                link.cutting = False
                link.retracts += 1
        _to_level(link, b, points[0], tool, mesh, leave, floor, drop)
        b.polyline(points[1:], f=feeds.feed_mm_min)
    link.finish()
    ctx.meta.update({"levels": len(levels), "passes": len(loops), "stock_to_leave": leave,
                     "grid_mm": round(spacing, 4), "links": {"hops": link.hops, "retracts": link.retracts}})
    return b.build()


def _to_level(link, b, start, tool, mesh, leave, floor, drop) -> None:
    """To the start of a loop: a straight feed when the linker is cutting and it is close, else the linker's way
    round (up, over, down)."""
    import numpy as np

    here = np.asarray(b.pos)
    distance = math.hypot(start[0] - here[0], start[1] - here[1])
    if link.cutting and distance <= link.hop:
        b.feed(x=start[0], y=start[1], z=start[2], f=link.feeds.feed_mm_min)
        link.hops += 1
        return
    if link.cutting:
        link.retracts += 1
        link.cutting = False
    link.to(start)


def _fix_chords(lines, levels, tool, mesh, leave, floor, spacing, tol, push, drop):
    """Add, between loop points whose straight move would cut more than half the tolerance into the part, a point
    pushed out onto the contact (up to three rounds, every loop at once)."""
    import numpy as np

    lines = [np.asarray(line, dtype=float) for line in lines]
    for _ in range(3):
        mids, owners, after, normals = [], [], [], []
        for k, line in enumerate(lines):
            if len(line) >= 2:
                mids.append(0.5 * (line[1:] + line[:-1]))
                owners.append(np.full(len(line) - 1, k))
                after.append(np.arange(1, len(line)))
                seg = line[1:] - line[:-1]
                length = np.maximum(np.hypot(seg[:, 0], seg[:, 1]), 1e-12)
                normals.append(np.column_stack([-seg[:, 1], seg[:, 0]]) / length[:, None])
        if not mids:
            return lines
        mid, owner, at, normal = (np.concatenate(x) for x in (mids, owners, after, normals))
        level = levels[owner]
        # Judged as the gouge check judges: the cutter inset by half the tolerance must not reach the level.
        bad = np.nonzero(drop(mid, tool, mesh, leave=leave - tol / 2.0, floor=floor) > level + 1e-9)[0]
        if not len(bad):
            return lines
        # Push away from the material: toward the side where the cutter sits lower.
        probe = drop(np.vstack([mid[bad] + normal[bad] * spacing, mid[bad] - normal[bad] * spacing]), tool, mesh,
                     leave=leave, floor=floor).reshape(2, -1)
        direction = np.where((probe[0] <= probe[1])[:, None], normal[bad], -normal[bad])
        moved, ok = push(mid[bad], direction, level[bad], tool, mesh, distance=2 * spacing, tolerance=tol / 10.0,
                         leave=leave)
        if not ok.any():
            return lines
        for k in np.unique(owner[bad][ok]):
            pick = (owner[bad] == k) & ok
            lines[k] = np.insert(lines[k], at[bad][pick], moved[pick], axis=0)
    return lines


def _orient(lines, levels, tool, mesh, leave, floor, climb: bool, drop):
    """Each loop turned so the part is on its right (climb) or left (conventional): one probe pair per loop."""
    import numpy as np

    probes, ks = [], []
    for k, points in enumerate(lines):
        if len(points) < 2:
            continue
        seg = points[1:] - points[:-1]
        length = np.hypot(seg[:, 0], seg[:, 1])
        j = int(np.argmax(length))
        if length[j] < 1e-9:
            continue
        normal_left = np.array([-seg[j, 1], seg[j, 0]]) / length[j]
        mid = 0.5 * (points[j] + points[j + 1])
        step = min(0.2, max(1e-3, length[j]))
        probes += [mid + normal_left * step, mid - normal_left * step]
        ks.append(k)
    out = list(lines)
    if not ks:
        return out
    z = drop(np.asarray(probes), tool, mesh, leave=leave, floor=floor).reshape(-1, 2)
    for k, (left, right) in zip(ks, z):
        if (right > left) != climb:
            out[k] = lines[k][::-1]
    return out
