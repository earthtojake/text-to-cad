"""What the 3D milling operations share (``rough``, ``parallel``, ``waterline``, ``scallop``, ``pencil``, ``rest``).

* :func:`silhouette` / :class:`Silhouettes`: the part seen from the tool, as a shapely polygon: the projection of all
  the material above a height (upward-facing triangles clipped to it, plus the section there), cumulative from the
  top down for z-level roughing.
* :func:`boundary`: where an operation's tool centre may go: its ``region``, the footprint of its ``faces``, or the
  part's silhouette, grown as the operation asks.
* :func:`drape`: polylines in XY dropped onto the part (drop-cutter), with midpoints added wherever the straight
  move between two points would stray from the drop-cutter surface by more than the tolerance; :func:`simplify`
  removes points again within the tolerance (Douglas-Peucker in 3D).
* :class:`StockNow`: the stock as it stands before this operation (the heightfield simulator replaying
  ``ctx.history``), for safe link heights, rest machining (:meth:`StockNow.rest_area`), and adaptive clearing and the
  air report (:meth:`StockNow.standing`, :meth:`StockNow.surface_at`, :meth:`StockNow.part_surface_at`).
* :class:`Linker`: moves between passes: a short hop feeds along the drop-cutter surface; anything longer goes
  straight up, across at a safe height over the stock as it stands, down to just above the stock and feeds in.

numpy and shapely at import (the engine imports this only when it plans in 3D).
"""

from __future__ import annotations

import math

import numpy as np
import shapely

from cadgen._internal.cam import geom2d
from cadgen._internal.cam.dropcutter import DropMesh, drop

__all__ = ["Linker", "Silhouettes", "StockNow", "boundary", "drape", "drop_mesh", "mask_polygons",
           "reference_rest_area", "simplify", "silhouette", "slopes"]

#: How far above the stock as it stands a long link travels, and the tool comes down to before it feeds in (mm).
LINK_CLEARANCE = 1.0


def drop_mesh(ctx) -> DropMesh:
    vertices, triangles = ctx.mesh
    return DropMesh.of(vertices, triangles)


# --- silhouettes and boundaries ------------------------------------------------------------------------------

def _clip_up(corners, z):
    """Triangles (N, 3, 3) clipped to ``z' >= z`` and projected: a list of (M, 2) polygons."""
    out = []
    above = corners[:, :, 2] >= z
    full = above.all(axis=1)
    out.extend(corners[full][:, :, :2])
    for tri in corners[~full & above.any(axis=1)]:
        ring = []
        for k in range(3):
            a, b = tri[k], tri[(k + 1) % 3]
            if a[2] >= z:
                ring.append(a[:2])
            if (a[2] >= z) != (b[2] >= z):
                t = (z - a[2]) / (b[2] - a[2])
                ring.append(a[:2] + (b[:2] - a[:2]) * t)
        if len(ring) >= 3:
            out.append(np.asarray(ring))
    return out


def _union(polygons, extra=None):
    shapes = [shapely.Polygon(p) for p in polygons if len(p) >= 3]
    shapes = [s for s in shapes if s.area > 1e-12]
    if extra is not None and not extra.is_empty:
        shapes.append(extra)
    if not shapes:
        return shapely.Polygon()
    return _without_slivers(shapely.union_all(shapes, grid_size=1e-5))


def _without_slivers(shape, area: float = 1e-3):
    """``shape`` without the pinholes and specks a union of many triangles leaves (less than ``area`` mm²)."""
    out = []
    for polygon in geom2d.polygons_of(shape):
        if polygon.area < area:
            continue
        holes = [ring for ring in polygon.interiors if shapely.Polygon(ring).area >= area]
        out.append(shapely.Polygon(polygon.exterior, holes))
    return shapely.union_all(out) if out else shapely.Polygon()


class Silhouettes:
    """The part's silhouette above heights asked for from the top down (each answer is cumulative)."""

    def __init__(self, vertices, triangles, sections=None):
        corners = np.asarray(vertices, dtype=float)[np.asarray(triangles)]
        normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        up = normal[:, 2] > 1e-12
        self.corners = corners[up]
        self.zmin = self.corners[:, :, 2].min(axis=1)
        self.zmax = self.corners[:, :, 2].max(axis=1)
        self.sections = sections
        self.shape = shapely.Polygon()
        self._z = math.inf

    def above(self, z: float):
        """The projection of every bit of the part above ``z`` (call with ``z`` falling)."""
        if z > self._z:
            raise ValueError("silhouettes are asked for from the top down")
        pick = (self.zmax > z) & (self.zmin < self._z)
        polygons = _clip_up(self.corners[pick], z)
        section = self.sections.at(z) if self.sections is not None else shapely.Polygon()
        self.shape = _union(polygons, extra=shapely.union(self.shape, section))
        self._z = z
        return self.shape


def silhouette(vertices, triangles, z: float | None = None, sections=None):
    """The part's projection onto XY (of the material above ``z`` when given)."""
    corners = np.asarray(vertices, dtype=float)[np.asarray(triangles)]
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    corners = corners[normal[:, 2] > 1e-12]
    if z is None:
        return _union(list(corners[:, :, :2]))
    section = sections.at(z) if sections is not None else None
    return _union(_clip_up(corners[corners[:, :, 2].max(axis=1) > z], z), extra=section)


def boundary(ctx, region, *, grow: float = 0.0):
    """Where the tool centre may go: the op's ``region`` polygon, else its faces' footprint, else the part's
    silhouette; the last two grown by ``grow``."""
    if region is not None:
        return region
    vertices, triangles = ctx.mesh
    if ctx.spec.faces:
        shapes = [ctx.footprint(ctx.face_triangles(ref)) for ref in ctx.spec.faces]
        shape = shapely.union_all(shapes).buffer(0)
    else:
        shape = silhouette(vertices, triangles)
    return geom2d.offset(shape, grow, tolerance=ctx.tolerance_mm) if grow > 0 else shape


# --- draping and simplifying ---------------------------------------------------------------------------------

def drape(paths, tool, mesh, *, leave: float, floor: float, tolerance: float, rounds: int = 10):
    """Each (N, 2) polyline dropped onto the part: (M, 3) arrays with midpoints added (up to ``rounds`` halvings)
    wherever the drop-cutter height at a segment's middle is more than ``tolerance`` from the straight line."""
    paths = [np.asarray(p, dtype=float).reshape(-1, 2) for p in paths]
    if not paths:
        return []
    ids = np.concatenate([np.full(len(p), k) for k, p in enumerate(paths)])
    xy = np.vstack(paths)
    z = drop(xy, tool, mesh, leave=leave, floor=floor)
    for _ in range(rounds):
        same = ids[1:] == ids[:-1]
        mid = 0.5 * (xy[1:] + xy[:-1])
        length = np.hypot(*(xy[1:] - xy[:-1]).T)
        candidates = np.nonzero(same & (length > max(tolerance, 1e-3)))[0]
        if not len(candidates):
            break
        zm = drop(mid[candidates], tool, mesh, leave=leave, floor=floor)
        off = np.abs(zm - 0.5 * (z[candidates] + z[candidates + 1])) > tolerance
        if not off.any():
            break
        where = candidates[off] + 1
        xy = np.insert(xy, where, mid[candidates[off]], axis=0)
        z = np.insert(z, where, zm[off])
        ids = np.insert(ids, where, ids[where - 1])
    out = []
    bounds = np.concatenate([[0], np.nonzero(ids[1:] != ids[:-1])[0] + 1, [len(ids)]])
    for a, b in zip(bounds[:-1], bounds[1:]):
        out.append(np.column_stack([xy[a:b], z[a:b]]))
    return out


def simplify(points, tolerance: float):
    """Douglas-Peucker in 3D: the points of (N, 3) ``points`` needed to stay within ``tolerance`` of all of them."""
    points = np.asarray(points, dtype=float)
    n = len(points)
    if n <= 2:
        return points
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        p, q = points[a], points[b]
        seg = q - p
        inner = points[a + 1:b]
        length2 = float(seg @ seg)
        if length2 < 1e-24:
            dist = np.linalg.norm(inner - p, axis=1)
        else:
            t = np.clip((inner - p) @ seg / length2, 0.0, 1.0)
            dist = np.linalg.norm(inner - (p + t[:, None] * seg), axis=1)
        k = int(np.argmax(dist))
        if dist[k] > tolerance:
            m = a + 1 + k
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return points[keep]


def slopes(points_xy, tool, mesh, *, leave: float, floor: float, step: float):
    """The drop-cutter surface's slope (degrees) at each point, from central differences ``step`` apart in x and
    y."""
    p = np.asarray(points_xy, dtype=float).reshape(-1, 2)
    offsets = np.array([[step, 0.0], [-step, 0.0], [0.0, step], [0.0, -step]])
    z = drop(np.vstack([p + o for o in offsets]), tool, mesh, leave=leave, floor=floor).reshape(4, -1)
    gx = (z[0] - z[1]) / (2 * step)
    gy = (z[2] - z[3]) / (2 * step)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


# --- the stock as it stands ----------------------------------------------------------------------------------

#: The last replays, so the next operation of the same job cuts only what was planned since: (stock, part, cell) ->
#: (stock, simulator, the toolpaths it has cut).
_REPLAYS: dict = {}
#: How many replays are kept: a job's clearing grids, its default one and a second tool's do not evict each other.
REPLAYS_KEPT = 4


def fine_cell(radius: float) -> float:
    """The stock grid an adaptive clear reads the stock as it stands on: a tenth of the tool's radius, 0.2 to 0.5 mm
    (finer costs the replay of every earlier operation far more than it gains)."""
    return min(0.5, max(0.2, radius / 10.0))


class StockNow:
    """The stock before this operation: a heightfield simulation of every toolpath planned before it."""

    def __init__(self, ctx, *, cell: float | None = None):
        from cadgen._internal.cam.stock_heightfield import HeightfieldSim

        self.wcs = ctx.wcs
        self.ctx = ctx
        axis = ctx.wcs.tool_axis
        self.available = abs(abs(axis[2]) - 1.0) < 1e-9
        self.direction = 1 if axis[2] > 0 else -1
        radius = ctx.tool.radius if ctx.tool is not None else 1.0
        self.cell = float(cell or min(1.0, max(0.2, radius / 3.0)))
        self.sim = None
        self._dilated: dict = {}
        self._ends = None
        self._part_face = None
        self._standing: dict = {}
        if not self.available:
            return
        history = list(getattr(ctx, "history", ()) or ())
        key = (id(ctx.stock), id(ctx.part), round(self.cell, 6))
        cached = _REPLAYS.get(key)
        done = 0
        if cached is not None and cached[0] is ctx.stock and len(cached[2]) <= len(history) and all(
                a is b for a, b in zip(cached[2], (path for _, path in history))):
            sim, done = cached[1], len(cached[2])
        else:
            sim = HeightfieldSim(ctx.stock, ctx.part, cell_mm=self.cell, tolerance_mm=max(0.01, ctx.tolerance_mm))
        tools = {tool.id: tool for tool in ctx.job.tools}
        # Operations replayed for an earlier one are not replayed again: only what is new is cut.
        for wcs, path in history[done:]:
            sim.cut(path, tools, wcs)
        if len(_REPLAYS) >= REPLAYS_KEPT and key not in _REPLAYS:
            _REPLAYS.pop(next(iter(_REPLAYS)))
        _REPLAYS[key] = (ctx.stock, sim, [path for _, path in history])
        self.sim = sim

    def _surface(self):
        """The material's face toward the tool, as heights in part z: the tops (tool from +Z) or the bottoms."""
        sim = self.sim
        exists = sim.top > sim.bottom + 1e-9
        if self.direction > 0:
            return np.where(exists, sim.top, -np.inf)
        return np.where(exists, sim.bottom, np.inf)

    def _grid_dilated(self, radius: float):
        """The surface, each cell the extreme within ``radius`` of it."""
        key = round(radius, 6)
        if key not in self._dilated:
            surface = self._surface()
            k = int(math.ceil(radius / self.cell))
            out = surface.copy()
            pick = np.maximum if self.direction > 0 else np.minimum
            nx, ny = surface.shape
            for di in range(-k, k + 1):
                for dj in range(-k, k + 1):
                    if math.hypot(max(0, abs(di) - 1), max(0, abs(dj) - 1)) * self.cell > radius:
                        continue
                    src = surface[max(0, di):nx + min(0, di), max(0, dj):ny + min(0, dj)]
                    view = out[max(0, -di):nx + min(0, -di), max(0, -dj):ny + min(0, -dj)]
                    view[...] = pick(view, src)
            self._dilated[key] = out
        return self._dilated[key]

    def top_near(self, points_xy, radius: float):
        """The highest stock (WCS z) within ``radius`` of each WCS point; ``-inf`` off the stock."""
        points = np.asarray(points_xy, dtype=float).reshape(-1, 2)
        if self.sim is None:
            return np.full(len(points), np.inf)
        sim = self.sim
        part, i, j = self._cell_index(points)
        grid = self._grid_dilated(radius + sim.cell)
        # Off the grid (it ends at the stock's edge): a point within ``radius`` of the grid still has stock within
        # ``radius`` of it, and the nearest cell's dilation holds it; only a point farther out sees none. (A point a
        # tool radius past the stock's side, a finishing pass's start beside a wall, is near the stock.)
        x1, y1 = sim.x0 + sim.nx * sim.cell, sim.y0 + sim.ny * sim.cell
        gap_x = np.maximum(np.maximum(sim.x0 - part[:, 0], part[:, 0] - x1), 0.0)
        gap_y = np.maximum(np.maximum(sim.y0 - part[:, 1], part[:, 1] - y1), 0.0)
        inside = np.hypot(gap_x, gap_y) <= radius + sim.cell
        ii, jj = np.clip(i, 0, sim.nx - 1), np.clip(j, 0, sim.ny - 1)
        height = np.where(inside, grid[ii, jj], -np.inf if self.direction > 0 else np.inf)
        far = ~inside | ~np.isfinite(height)
        part_z = np.where(far, 0.0, height)
        wcs_z = self.wcs.to_wcs(np.column_stack([part[:, :2], part_z]))[:, 2]
        return np.where(far, -np.inf, wcs_z)

    def _cell_index(self, points):
        """WCS points (N, 2) as part coordinates and the indices of the cells they fall in."""
        sim = self.sim
        part = self.wcs.from_wcs(np.column_stack([points, np.zeros(len(points))]))
        i = np.floor((part[:, 0] - sim.x0) / sim.cell).astype(np.int64)
        j = np.floor((part[:, 1] - sim.y0) / sim.cell).astype(np.int64)
        return part, i, j

    def _wcs_heights(self, heights):
        """A grid of part heights as WCS z (``nan`` kept)."""
        sim = self.sim
        i, j = np.meshgrid(np.arange(sim.nx), np.arange(sim.ny), indexing="ij")
        x, y = (sim.x0 + (i + 0.5) * sim.cell).ravel(), (sim.y0 + (j + 0.5) * sim.cell).ravel()
        z = self.wcs.to_wcs(np.column_stack([x, y, np.nan_to_num(heights.ravel())]))[:, 2]
        return np.where(np.isnan(heights.ravel()), np.nan, z).reshape(heights.shape)

    def _wcs_ends(self):
        """Each cell's material toward the tool and away from it, as WCS z (the surface, then the far end); ``nan``
        where the stock is cut through."""
        if self._ends is None:
            sim = self.sim
            exists = sim.top > sim.bottom + 1e-9
            near, far = (sim.top, sim.bottom) if self.direction > 0 else (sim.bottom, sim.top)
            self._ends = tuple(self._wcs_heights(np.where(exists, heights, np.nan)) for heights in (near, far))
        return self._ends

    def _at(self, grid, points_xy):
        """``grid``'s value in the cell under each WCS point; ``-inf`` off the grid, where it is ``nan``, or outside
        the stock's outline (a cell along the stock's edge reaches past it)."""
        sim = self.sim
        points = np.asarray(points_xy, dtype=float).reshape(-1, 2)
        _, i, j = self._cell_index(points)
        on = (i >= 0) & (i < sim.nx) & (j >= 0) & (j < sim.ny)
        on &= shapely.contains_xy(self.ctx.stock_outline, points[:, 0], points[:, 1])
        out = np.full(len(points), -np.inf)
        values = grid[i[on], j[on]]
        out[on] = np.where(np.isnan(values), -np.inf, values)
        return out

    def surface_at(self, points_xy):
        """The stock's face toward the tool (WCS z) under each WCS point; ``-inf`` off the stock or where it is cut
        through. Where this setup is not simulated, the stock's top over its outline."""
        if self.sim is None:
            points = np.asarray(points_xy, dtype=float).reshape(-1, 2)
            inside = shapely.contains_xy(self.ctx.stock_outline, points[:, 0], points[:, 1])
            return np.where(inside, self.ctx.heights.stock_top, -np.inf)
        return self._at(self._wcs_ends()[0], points_xy)

    def part_surface_at(self, points_xy):
        """The part's face toward the tool (WCS z) under each WCS point; ``-inf`` where the part has no material, and
        everywhere where this setup is not simulated."""
        if self.sim is None:
            return np.full(len(np.asarray(points_xy, dtype=float).reshape(-1, 2)), -np.inf)
        if self._part_face is None:
            part_top, part_bottom = self.sim._part(self.ctx.part)
            self._part_face = self._wcs_heights(part_top if self.direction > 0 else part_bottom)
        return self._at(self._part_face, points_xy)

    def standing(self, z: float, *, part=None, leave: float = 0.0, hair: float = 0.01):
        """Where stock stands across the WCS level ``z`` (more than ``hair`` over it, its far end under it) that an
        operation may cut, as WCS XY polygons: every cell that holds material counts whole and is grown by a cell, so
        a thin wall left by an earlier cut is never taken for air, and none reaches past the stock's outline. ``part``
        (its section at the level, WCS) and the stock to leave on it are taken out. Where this setup is not simulated,
        the whole stock's outline."""
        if self.sim is None:
            shape = self.ctx.stock_outline
        else:
            near, far = self._wcs_ends()
            with np.errstate(invalid="ignore"):
                mask = (near > z + hair) & (far < z)
            key = mask.tobytes()
            if key not in self._standing:
                shape = shapely.Polygon()
                if mask.any():
                    shape = mask_polygons(mask, self.sim.x0, self.sim.y0, self.sim.cell, transform=self._to_wcs_xy,
                                          clean=False).buffer(self.sim.cell, quad_segs=2)
                    shape = shape.intersection(self.ctx.stock_outline)
                self._standing[key] = shape
            shape = self._standing[key]
        if part is not None and not part.is_empty and not shape.is_empty:
            shape = shape.difference(geom2d.offset(part, leave + self.cell, tolerance=self.ctx.tolerance_mm))
        return shape

    def rest_area(self, *, threshold: float):
        """Where the stock stands more than ``threshold`` over the part (WCS XY polygons), or None when this setup is
        not simulated."""
        if self.sim is None:
            return None
        sim = self.sim
        part_top, part_bottom = sim._part(self.ctx.part)
        if self.direction > 0:
            excess = sim.top - part_top
        else:
            excess = part_bottom - sim.bottom
        exists = sim.top > sim.bottom + 1e-9
        mask = np.nan_to_num(excess, nan=0.0) > threshold
        mask &= exists & ~np.isnan(part_top)
        return mask_polygons(mask, sim.x0, sim.y0, sim.cell, transform=self._to_wcs_xy)

    def _to_wcs_xy(self, xy):
        xy = np.asarray(xy, dtype=float)
        return self.wcs.to_wcs(np.column_stack([xy, np.zeros(len(xy))]))[:, :2]


def mask_polygons(mask, x0: float, y0: float, cell: float, *, transform=None, clean: bool = True):
    """The cells of an (nx, ny) boolean grid (cell ``(i, j)`` spans ``x0 + i * cell``..) as one shapely shape, opened
    by about a cell so single-cell noise along walls drops out (``clean``; else every cell is kept)."""
    boxes = []
    nx, ny = mask.shape
    for i in range(nx):
        row = mask[i]
        if not row.any():
            continue
        edges = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        starts, ends = np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0]
        for a, b in zip(starts, ends):
            boxes.append(shapely.box(x0 + i * cell, y0 + a * cell, x0 + (i + 1) * cell, y0 + b * cell))
    if not boxes:
        return shapely.Polygon()
    shape = shapely.union_all(boxes, grid_size=cell / 1000.0)
    if clean:
        shape = shape.buffer(-0.6 * cell, join_style="mitre").buffer(0.6 * cell, join_style="mitre")
    if transform is not None and not shape.is_empty:
        shape = shapely.transform(shape, transform)
        shape = shape.buffer(0)
    return shape


# --- linking ---------------------------------------------------------------------------------------------------

class Linker:
    """Moves between passes of a 3D finishing operation, on one builder.

    :meth:`to` takes the tool from where it is to the start of the next pass (x, y, z on the drop-cutter surface):
    within ``hop`` mm it feeds straight there along the drop-cutter surface (the hop is draped, so it never cuts
    the part); otherwise straight up, across at ``LINK_CLEARANCE`` over the highest stock along the way (the stock
    as it stands, :class:`StockNow`; the retract plane when that is not known), down to that clearance over the
    stock at the start, then a plunge-feed onto the pass."""

    def __init__(self, ctx, builder, mesh, *, leave: float, floor: float, feeds, hop: float, stock_now=None):
        self.ctx = ctx
        self.b = builder
        self.mesh = mesh
        self.tool = ctx.tool
        self.leave = leave
        self.floor = floor
        self.feeds = feeds
        self.hop = hop
        self.stock = stock_now
        self.heights = ctx.heights
        self.tolerance = max(0.002, ctx.tolerance_mm / 2.0)
        self.retracts = 0
        self.hops = 0
        self.cutting = False

    def _stock_top(self, xy, *, along=None) -> float:
        if self.stock is None or self.stock.sim is None:
            return math.inf
        if along is not None:
            a, b = np.asarray(along[0], dtype=float), np.asarray(along[1], dtype=float)
            count = max(2, int(math.ceil(np.hypot(*(b - a)) / max(self.stock.cell, 0.25))) + 1)
            xy = a + (b - a) * np.linspace(0.0, 1.0, count)[:, None]
        top = self.stock.top_near(xy, self.tool.radius + 0.25)
        return float(np.max(top)) if len(top) else -math.inf

    def safe_over(self, xy, along=None) -> float:
        """The height to travel at over ``xy`` (or along the segment ``along``): ``LINK_CLEARANCE`` over the stock
        as it stands, never above the retract plane (the retract plane when the stock is not known; ``-inf`` when
        there is no stock there at all)."""
        top = self._stock_top(xy, along=along)
        if top == math.inf:
            return self.heights.retract
        return min(self.heights.retract, top + LINK_CLEARANCE)

    def to(self, start) -> None:
        b = self.b
        x, y, z = (float(v) for v in start)
        here = b.pos
        distance = math.hypot(x - here[0], y - here[1])
        if self.cutting and distance <= self.hop:
            count = max(2, int(math.ceil(distance / max(0.05, min(0.5, self.tool.radius / 2)))) + 1)
            line = np.column_stack([np.linspace(here[0], x, count), np.linspace(here[1], y, count)])
            draped = drape([line], self.tool, self.mesh, leave=self.leave, floor=self.floor,
                           tolerance=self.tolerance)[0]
            draped[0, 2] = max(draped[0, 2], here[2])
            draped[-1] = (x, y, z)
            b.polyline(draped[1:], f=self.feeds.feed_mm_min)
            self.hops += 1
            return
        if self.cutting:
            self.retracts += 1
        travel = max(self.safe_over(None, along=((here[0], here[1]), (x, y))), z + LINK_CLEARANCE, here[2])
        if here[2] < travel:
            b.rapid(z=travel)
        b.rapid(x=x, y=y)
        down = max(z + LINK_CLEARANCE, min(b.pos[2], self.safe_over(np.array([[x, y]]))))
        if b.pos[2] > down:
            b.rapid(z=down)
        b.plunge(z=z, f=self.feeds.plunge_mm_min)
        self.cutting = True

    def finish(self) -> None:
        self.b.rapid(z=self.heights.clearance)
        self.cutting = False



def reference_rest_area(ctx, reference, area, *, leave: float, threshold: float, spacing: float):
    """Where a ``reference`` tool, finishing all over ``area`` to ``leave``, would leave more than ``threshold`` over
    the part (WCS XY), on a grid of ``spacing``: its drop-cutter heights, the surface its cutter sweeps from them
    (each point the lowest any placement's cutter reaches there), less the part's own top."""
    from cadgen._internal.cam.dropcutter import cutter_for, zmap
    from cadgen._internal.cam.stock_heightfield import raster_heights

    x0, y0, x1, y1 = area.bounds
    reach = reference.radius
    gx0, gy0 = x0 - reach - spacing, y0 - reach - spacing
    nx = int(math.ceil((x1 - x0 + 2 * reach) / spacing)) + 3
    ny = int(math.ceil((y1 - y0 + 2 * reach) / spacing)) + 3
    vertices, triangles = ctx.mesh
    floor = ctx.heights.part_bottom
    centres = zmap(drop_mesh(ctx), reference, gx0, gy0, spacing, nx, ny, leave=leave, floor=floor)
    cutter = cutter_for(reference)
    k = int(math.ceil(reach / spacing))
    swept = np.full((nx, ny), np.inf)
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            h = float(cutter.h(np.array([math.hypot(di, dj) * spacing]))[0])
            if not math.isfinite(h):
                continue
            src = centres[max(0, di):nx + min(0, di), max(0, dj):ny + min(0, dj)]
            view = swept[max(0, -di):nx + min(0, -di), max(0, -dj):ny + min(0, -dj)]
            np.minimum(view, src + h, out=view)
    top, _ = raster_heights(vertices, triangles, gx0 - spacing / 2, gy0 - spacing / 2, spacing, nx, ny)
    mask = (np.nan_to_num(swept - top, nan=0.0, posinf=0.0) > threshold) & ~np.isnan(top)
    return mask_polygons(mask, gx0 - spacing / 2, gy0 - spacing / 2, spacing)
