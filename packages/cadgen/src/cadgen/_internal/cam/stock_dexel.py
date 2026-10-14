"""The multi-axis stock simulator: a tri-dexel (three orthogonal grids of rays, each ray holding its material as
intervals), so a tool at any angle cuts it: 4th-axis wraps, 3+2 setups, swarf and 5-axis finishing.

**What it holds.** Three grids over the stock's bounds, one per part axis: rays along X on a YZ grid, along Y on an
XZ grid, along Z on an XY grid, one ray through each cell's centre (nudged off the cell lines by a hair so a ray never
runs along a mesh edge). Each ray carries sorted, disjoint intervals ``[lo, hi]`` (mm along the ray) where there is
material. They start as the stock mesh ray-cast (box, cylinder or a STEP blank alike) and lose what every tool
placement sweeps.

**How it cuts.** :meth:`DexelSim.cut` walks one setup's toolpath in program order, in part coordinates: each move is
sampled no further apart than :attr:`step` (and no more than :data:`DEG_STEP` of any rotary axis), its tool axis from
the move's A/B/C (``multiaxis.tool_axes``). At each sample the tool is a convex solid, the cutter's profile swept up
its axis to beyond the stock (as the heightfield's column, everything above the tip goes too): a flat end is one
cylinder, a ball end a sphere and a cylinder, a bull nose or a cone a stack of cylinders inscribed in the profile
(never more than the real cutter, at most a sixth of the profile's rise short). Each ray through the solid loses the
one interval where it is inside (the hull of the pieces' intervals, exact for a convex solid). Rapids are tested,
never cut: a rapid whose tool overlaps material by more than :data:`RAPID_TOLERANCE` (or half a cell) along a ray is
a hit, and so is any move made with the spindle stopped (:func:`~cadgen._internal.cam.stock.move_modes`): a tool that
is not turning cuts nothing. A back bore's stopped moves are its bar's neck through the hole, tested as a cylinder of
the neck's radius (``shank_diameter_mm`` / 2) from the tip up; its head feeding up from under the part cuts only what
the head sweeps (a cylinder ``flute_length_mm`` tall over the tip), never the material over it, and is left out of
the reach depth (the reach check judges the bar from the plan). Before each run of cutting samples it measures how
far the material along the tool's axis stands over the tip within reach of the tool's side (the reach check), on the
grid most in line with the tool.

**What it reports.** :meth:`volume` sums the Z rays' intervals (cell area x length: good to about half a cell on
walls, exact in Z). :meth:`material_left` compares each ray's stock with the part's own intervals (the part mesh
ray-cast the same way): a piece of stock outside the part and over its footprint (a vertical column through the part,
as the heightfield judges) counts by its thickness, the least of its lengths along the three rays through it, so a
thin skin left on a wall reads thin. :meth:`mesh` draws the Z dexels as boxes merged into
one surface (each column's material as boxes one cell square, shared walls dropped, and faces at one height or one
span merged into rectangles, so a flat top is a few quads): closed, exact in height, blocky by a cell sideways
(watertight up to T-junctions). Stdlib at import; numpy inside.
"""

from __future__ import annotations

import math

import numpy as np

from cadgen._internal.cam.fit import op_step
from cadgen._internal.cam.ir import ARC_CCW, ARC_CW
from cadgen._internal.cam.stock import BACK_CUT, CUT, IDLE, NECK, PASS, MaterialLeft, SimReport, move_modes

__all__ = ["DexelSim", "ray_intervals"]

#: How far a rapid may run into material (along a ray) before it is a hit (mm).
RAPID_TOLERANCE = 0.05
#: The most any rotary axis turns between two samples (degrees).
DEG_STEP = 1.0
#: The most rays the three grids hold together (the cell grows to fit).
MAX_RAYS = 450_000
#: (placement, ray) pairs handled per numpy chunk.
_CHUNK = 1_500_000
#: A ray's nudge off the cell centre, in cells (so it never runs exactly along a mesh edge).
_NUDGE = (1.234567e-4, 2.718281e-4)
_EMPTY_LO, _EMPTY_HI = np.inf, -np.inf


def _merge(ray, lo, hi):
    """Disjoint intervals per ray from overlapping ones: ``(ray, lo, hi)`` sorted, merged."""
    if not len(ray):
        return ray, lo, hi
    order = np.lexsort((lo, ray))
    ray, lo, hi = ray[order], lo[order], hi[order]
    big = 1e7
    end = np.maximum.accumulate(ray * big + hi)
    start = ray * big + lo
    new = np.ones(len(ray), dtype=bool)
    new[1:] = (start[1:] > end[:-1]) | (ray[1:] != ray[:-1])
    groups = np.nonzero(new)[0]
    merged_hi = np.maximum.reduceat(hi, groups)
    return ray[groups], lo[groups], merged_hi


def _compact(lo, hi):
    """Rows of intervals with empties dropped and the rest sorted, columns trimmed to the longest row."""
    empty = hi - lo <= 1e-6
    lo = np.where(empty, _EMPTY_LO, lo)
    hi = np.where(empty, _EMPTY_HI, hi)
    order = np.argsort(lo, axis=1, kind="stable")
    lo = np.take_along_axis(lo, order, axis=1)
    hi = np.take_along_axis(hi, order, axis=1)
    width = max(1, int((~empty).sum(axis=1).max())) if len(lo) else 1
    return lo[:, :width], hi[:, :width]


def _rectangles(keys: list, u, v):
    """Unit cells ``(u, v)`` (integers) merged into rectangles of cells that share every key: runs along ``v``,
    then runs that match along ``u``. ``(keys of each rectangle, u0, u1, v0, v1)``, ends exclusive. Keys are
    compared to a nanometre (ray casts put one face's height a few ulps apart)."""
    u = np.asarray(u, dtype=np.int64)
    v = np.asarray(v, dtype=np.int64)
    keys = [np.round(np.asarray(k, dtype=float), 6) for k in keys]
    if not len(u):
        empty = np.zeros(0, dtype=np.int64)
        return [k[:0] for k in keys], empty, empty, empty, empty
    order = np.lexsort((v, u, *reversed(keys)))
    u, v, keys = u[order], v[order], [k[order] for k in keys]
    same = np.ones(len(u), dtype=bool)
    same[0] = False
    for k in keys:
        same[1:] &= k[1:] == k[:-1]
    same[1:] &= (u[1:] == u[:-1]) & (v[1:] == v[:-1] + 1)
    first = np.nonzero(~same)[0]
    last = np.append(first[1:], len(u)) - 1
    keys, u, v0, v1 = [k[first] for k in keys], u[first], v[first], v[last] + 1
    order = np.lexsort((u, v1, v0, *reversed(keys)))
    keys, u, v0, v1 = [k[order] for k in keys], u[order], v0[order], v1[order]
    same = np.ones(len(u), dtype=bool)
    same[0] = False
    for k in keys:
        same[1:] &= k[1:] == k[:-1]
    same[1:] &= (v0[1:] == v0[:-1]) & (v1[1:] == v1[:-1]) & (u[1:] == u[:-1] + 1)
    first = np.nonzero(~same)[0]
    last = np.append(first[1:], len(u)) - 1
    return [k[first] for k in keys], u[first], u[last] + 1, v0[first], v1[first]


def _subtract(lo, hi, a, b):
    """Interval rows (M, K) minus one interval ``[a, b]`` per row (M,); an empty ``[a, b]`` (b <= a) takes nothing."""
    empty = b <= a
    a = np.where(empty, np.inf, a)[:, None]
    b = np.where(empty, np.inf, b)[:, None]
    new_lo = np.concatenate([lo, np.maximum(lo, b)], axis=1)
    new_hi = np.concatenate([np.minimum(hi, a), hi], axis=1)
    return _compact(new_lo, new_hi)


def _overlap(lo, hi, a, b):
    """The longest overlap of each row's intervals (M, K) with ``[a, b]`` (M,): (length, start, end)."""
    start = np.maximum(lo, a[:, None])
    end = np.minimum(hi, b[:, None])
    length = end - start
    k = np.argmax(length, axis=1)
    rows = np.arange(len(lo))
    return length[rows, k], start[rows, k], end[rows, k]


def ray_intervals(vertices, triangles, axis: int, u0: float, v0: float, cell: float, nu: int, nv: int):
    """A closed mesh ray-cast along part axis ``axis`` through the centres of an ``nu`` x ``nv`` grid (origin
    ``(u0, v0)`` on the other two axes, in order): ``(lo, hi)`` (nu * nv, K) inside intervals, empty slots
    ``(inf, -inf)``."""
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64)
    u_axis, v_axis = [i for i in range(3) if i != axis]
    count = nu * nv
    if not len(triangles):
        return np.full((count, 1), _EMPTY_LO), np.full((count, 1), _EMPTY_HI)
    tri = vertices[triangles]
    p = tri[:, :, [u_axis, v_axis]]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    keep = np.abs(det) > 1e-14
    tri, p, e1, e2, det = tri[keep], p[keep], e1[keep], e2[keep], det[keep]
    nudge_u, nudge_v = _NUDGE[0] * cell, _NUDGE[1] * cell
    lo_i = np.maximum(np.ceil((p[:, :, 0].min(axis=1) - u0 - nudge_u) / cell - 0.5).astype(np.int64), 0)
    hi_i = np.minimum(np.floor((p[:, :, 0].max(axis=1) - u0 - nudge_u) / cell - 0.5).astype(np.int64), nu - 1)
    lo_j = np.maximum(np.ceil((p[:, :, 1].min(axis=1) - v0 - nudge_v) / cell - 0.5).astype(np.int64), 0)
    hi_j = np.minimum(np.floor((p[:, :, 1].max(axis=1) - v0 - nudge_v) / cell - 0.5).astype(np.int64), nv - 1)
    ni = np.maximum(hi_i - lo_i + 1, 0)
    nj = np.maximum(hi_j - lo_j + 1, 0)
    sizes = ni * nj
    rays, depths = [], []
    order = np.nonzero(sizes)[0]
    start = 0
    while start < len(order):
        # Chunks of triangles whose candidate cells fit the budget.
        cum = np.cumsum(sizes[order[start:]])
        stop = start + max(1, int(np.searchsorted(cum, _CHUNK)))
        idx = order[start:stop]
        start = stop
        n = sizes[idx]
        owner = np.repeat(idx, n)
        within = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
        ii = lo_i[owner] + within // nj[owner]
        jj = lo_j[owner] + within % nj[owner]
        pu = u0 + (ii + 0.5) * cell + nudge_u
        pv = v0 + (jj + 0.5) * cell + nudge_v
        a = p[owner, 0]
        w1 = ((pu - a[:, 0]) * e2[owner, 1] - (pv - a[:, 1]) * e2[owner, 0]) / det[owner]
        w2 = (e1[owner, 0] * (pv - a[:, 1]) - e1[owner, 1] * (pu - a[:, 0])) / det[owner]
        w0 = 1.0 - w1 - w2
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        t = tri[owner]
        depth = w0 * t[:, 0, axis] + w1 * t[:, 1, axis] + w2 * t[:, 2, axis]
        rays.append((ii * nv + jj)[inside])
        depths.append(depth[inside])
    lo = np.full((count, 1), _EMPTY_LO)
    hi = np.full((count, 1), _EMPTY_HI)
    if not rays:
        return lo, hi
    ray = np.concatenate(rays)
    depth = np.concatenate(depths)
    if not len(ray):
        return lo, hi
    order = np.lexsort((depth, ray))
    ray, depth = ray[order], depth[order]
    # Crossings a hair apart on one ray are one crossing (a ray through a shared edge).
    keep = np.ones(len(ray), dtype=bool)
    keep[1:] = (ray[1:] != ray[:-1]) | (depth[1:] - depth[:-1] > 1e-9)
    ray, depth = ray[keep], depth[keep]
    first = np.searchsorted(ray, ray, side="left")
    rank = np.arange(len(ray)) - first
    counts = np.bincount(ray, minlength=count)
    usable = rank < (counts[ray] // 2) * 2          # an odd crossing count drops its last crossing
    ray, depth, rank = ray[usable], depth[usable], rank[usable]
    starts = rank % 2 == 0
    width = max(1, int((counts // 2).max()))
    lo = np.full((count, width), _EMPTY_LO)
    hi = np.full((count, width), _EMPTY_HI)
    lo[ray[starts], rank[starts] // 2] = depth[starts]
    hi[ray[~starts], rank[~starts] // 2] = depth[~starts]
    return lo, hi


class _Grid:
    """Rays along part axis ``axis`` through the centres of a grid on the other two axes."""

    def __init__(self, axis: int, low, high, cell: float):
        self.axis = axis
        self.u_axis, self.v_axis = [i for i in range(3) if i != axis]
        self.cell = cell
        self.u0, self.v0 = float(low[self.u_axis]), float(low[self.v_axis])
        self.nu = max(1, int(math.ceil((high[self.u_axis] - low[self.u_axis]) / cell)))
        self.nv = max(1, int(math.ceil((high[self.v_axis] - low[self.v_axis]) / cell)))
        self.lo = np.full((self.count, 1), _EMPTY_LO)
        self.hi = np.full((self.count, 1), _EMPTY_HI)

    @property
    def count(self) -> int:
        return self.nu * self.nv

    def load(self, vertices, triangles):
        self.lo, self.hi = ray_intervals(vertices, triangles, self.axis, self.u0, self.v0, self.cell, self.nu, self.nv)

    def centres(self, rays):
        """(u, v) of rays (flat indices)."""
        i, j = np.divmod(rays, self.nv)
        return (self.u0 + (i + 0.5) * self.cell + _NUDGE[0] * self.cell,
                self.v0 + (j + 0.5) * self.cell + _NUDGE[1] * self.cell)

    def ray_at(self, u, v):
        """The ray nearest each (u, v), or -1 outside the grid."""
        i = np.floor((u - self.u0) / self.cell).astype(np.int64)
        j = np.floor((v - self.v0) / self.cell).astype(np.int64)
        ok = (i >= 0) & (i < self.nu) & (j >= 0) & (j < self.nv)
        return np.where(ok, i * self.nv + j, -1)

    def length(self) -> float:
        return float(np.clip(self.hi - self.lo, 0.0, None).sum())

    def remove(self, rays, a, b) -> None:
        """Take ``[a, b]`` out of each ray in ``rays`` (repeats allowed)."""
        if not len(rays):
            return
        rays, a, b = _merge(rays, a, b)
        rank = np.arange(len(rays)) - np.searchsorted(rays, rays, side="left")
        for r in range(int(rank.max()) + 1):
            pick = rank == r
            rows = rays[pick]
            lo, hi = _subtract(self.lo[rows], self.hi[rows], a[pick], b[pick])
            width = lo.shape[1]
            if width > self.lo.shape[1]:
                pad = width - self.lo.shape[1]
                self.lo = np.hstack([self.lo, np.full((self.count, pad), _EMPTY_LO)])
                self.hi = np.hstack([self.hi, np.full((self.count, pad), _EMPTY_HI)])
            self.lo[rows, :width], self.hi[rows, :width] = lo, hi
            self.lo[rows, width:], self.hi[rows, width:] = _EMPTY_LO, _EMPTY_HI


def _primitives(tool, length: float):
    """The cutter as convex pieces ``(kind, radius, h0, h1)``: ``"cyl"`` a cylinder of ``radius`` from ``h0`` to
    ``h1`` over the tip, ``"sph"`` a sphere of ``radius`` centred ``h0`` over the tip; each inscribed in the cutter."""
    r = tool.radius
    kind = tool.type
    if kind == "ball":
        return [("sph", r, r, 0.0), ("cyl", r, r, length)]
    if kind == "bull" and tool.corner_radius_mm > 0:
        rc = min(tool.corner_radius_mm, r)
        pieces = [("cyl", r - rc, 0.0, length)] if r - rc > 1e-9 else []
        for k in range(1, 5):
            rho = (r - rc) + rc * k / 4.0
            pieces.append(("cyl", rho, float(tool.height_at(rho)), length))
        return pieces
    if kind in ("vee", "chamfer", "engraver", "spot", "drill"):
        tip = tool.tip_diameter_mm / 2.0
        pieces = []
        for k in range(0, 7):
            rho = tip + (r - tip) * k / 6.0
            if rho > 1e-9:
                pieces.append(("cyl", rho, float(tool.height_at(rho)), length))
        return pieces
    return [("cyl", r, 0.0, length)]


def _cylinder_interval(w, axis_u, k: int, radius: float, h0: float, h1: float):
    """t-interval of each ray (origin offset ``w`` = O - tip (P, 3), along part axis ``k``) inside a cylinder of the
    tool axis ``axis_u`` (P, 3)."""
    uk = axis_u[:, k]
    wu = np.einsum("ij,ij->i", w, axis_u)
    a = w - wu[:, None] * axis_u
    ab = a[:, k]
    aa = np.einsum("ij,ij->i", a, a)
    bb = 1.0 - uk * uk
    t0 = np.full(len(w), -np.inf)
    t1 = np.full(len(w), np.inf)
    slanted = bb > 1e-12
    disc = ab * ab - bb * (aa - radius * radius)
    root = np.sqrt(np.maximum(disc, 0.0))
    safe = np.where(slanted, bb, 1.0)
    t0 = np.where(slanted, (-ab - root) / safe, t0)
    t1 = np.where(slanted, (-ab + root) / safe, t1)
    miss = (slanted & (disc < 0)) | (~slanted & (aa > radius * radius))
    along = np.abs(uk) > 1e-12
    safe_u = np.where(along, uk, 1.0)
    ha = (h0 - wu) / safe_u
    hb = (h1 - wu) / safe_u
    lo_h = np.where(along, np.minimum(ha, hb), -np.inf)
    hi_h = np.where(along, np.maximum(ha, hb), np.inf)
    miss |= ~along & ((wu < h0) | (wu > h1))
    t0 = np.maximum(t0, lo_h)
    t1 = np.minimum(t1, hi_h)
    miss |= t1 <= t0
    return np.where(miss, np.inf, t0), np.where(miss, -np.inf, t1)


def _sphere_interval(w, axis_u, k: int, radius: float, h: float):
    oc = w - h * axis_u
    b = oc[:, k]
    c = np.einsum("ij,ij->i", oc, oc) - radius * radius
    disc = b * b - c
    root = np.sqrt(np.maximum(disc, 0.0))
    miss = disc < 0
    return np.where(miss, np.inf, -b - root), np.where(miss, -np.inf, -b + root)


class DexelSim:
    kind = "dexel"

    def __init__(self, stock, part=None, *, cell_mm: float, tolerance_mm: float = 0.01, max_rays: int = MAX_RAYS):
        low = np.asarray(stock.bounds_min, dtype=float)
        high = np.asarray(stock.bounds_max, dtype=float)
        size = np.maximum(high - low, 1e-6)
        cell = float(cell_mm)
        first = cell
        while (size[0] * size[1] + size[1] * size[2] + size[0] * size[2]) / (cell * cell) > max_rays:
            cell *= 1.25
        self.adapted: list[dict] = []
        if cell > first:
            self.adapted.append({"step": "stock_grid",
                                 "words": f"tri-dexel stock grid {first:.3g} mm -> {cell:.3g} mm so its three ray grids "
                                          f"fit {max_rays:,} rays",
                                 "accuracy": f"material left and removed volume are good to about {cell / 2:.3g} mm"})
        self.cell = cell
        self.low, self.high = low, high
        self.tolerance = float(tolerance_mm)
        #: Sample spacing along the path (the fit ladder may raise it).
        self.step = cell
        self.grids = [_Grid(axis, low, high, cell) for axis in range(3)]
        for grid in self.grids:
            grid.load(stock.vertices, stock.triangles)
        self._length = float(np.linalg.norm(size)) + 1.0
        self._part_grids = None

    @property
    def cells(self) -> int:
        return sum(grid.count for grid in self.grids)

    def supports(self, wcs) -> str | None:
        return None

    def volume(self) -> float:
        return self.grids[2].length() * self.cell * self.cell

    # --- placements -----------------------------------------------------------------------------------

    def _pairs(self, grid: _Grid, tips, axes, radius: float):
        """(placement, ray) candidates: rays crossing the box round each placed tool, clipped to the stock."""
        span = np.empty(len(tips))
        start = np.zeros(len(tips))
        reach = radius + self.cell
        low, high = self.low - reach, self.high + reach
        # The tool's axis segment clipped to the stock box (slab method).
        s0 = np.zeros(len(tips))
        s1 = np.full(len(tips), self._length)
        for k in range(3):
            d = axes[:, k]
            o = tips[:, k]
            flat = np.abs(d) < 1e-12
            safe = np.where(flat, 1.0, d)
            ta = (low[k] - o) / safe
            tb = (high[k] - o) / safe
            s0 = np.where(flat, np.where((o < low[k]) | (o > high[k]), np.inf, s0), np.maximum(s0, np.minimum(ta, tb)))
            s1 = np.where(flat, s1, np.minimum(s1, np.maximum(ta, tb)))
        live = s1 > s0
        start, span = np.where(live, s0, 0.0), np.where(live, s1, 0.0)
        a = tips + start[:, None] * axes
        b = tips + span[:, None] * axes
        u, v = grid.u_axis, grid.v_axis
        lo_i = np.floor((np.minimum(a[:, u], b[:, u]) - reach - grid.u0) / grid.cell).astype(np.int64)
        hi_i = np.floor((np.maximum(a[:, u], b[:, u]) + reach - grid.u0) / grid.cell).astype(np.int64)
        lo_j = np.floor((np.minimum(a[:, v], b[:, v]) - reach - grid.v0) / grid.cell).astype(np.int64)
        hi_j = np.floor((np.maximum(a[:, v], b[:, v]) + reach - grid.v0) / grid.cell).astype(np.int64)
        lo_i, lo_j = np.maximum(lo_i, 0), np.maximum(lo_j, 0)
        hi_i, hi_j = np.minimum(hi_i, grid.nu - 1), np.minimum(hi_j, grid.nv - 1)
        ni = np.where(live, np.maximum(hi_i - lo_i + 1, 0), 0)
        nj = np.where(live, np.maximum(hi_j - lo_j + 1, 0), 0)
        n = ni * nj
        owner = np.repeat(np.arange(len(tips)), n)
        within = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
        nj_o = np.maximum(nj[owner], 1)
        ii = lo_i[owner] + within // nj_o
        jj = lo_j[owner] + within % nj_o
        return owner, ii * grid.nv + jj

    def _intervals(self, grid: _Grid, owner, rays, tips, axes, pieces):
        """The t-interval of each (placement, ray) pair inside the placed tool (hull of its pieces)."""
        cu, cv = grid.centres(rays)
        origin = np.zeros((len(rays), 3))
        origin[:, grid.u_axis], origin[:, grid.v_axis] = cu, cv
        w = origin - tips[owner]
        axis_u = axes[owner]
        t0 = np.full(len(rays), np.inf)
        t1 = np.full(len(rays), -np.inf)
        for kind, radius, h0, h1 in pieces:
            if kind == "sph":
                a, b = _sphere_interval(w, axis_u, grid.axis, radius, h0)
            else:
                a, b = _cylinder_interval(w, axis_u, grid.axis, radius, h0, h1)
            t0 = np.minimum(t0, a)
            t1 = np.maximum(t1, b)
        return t0, t1

    def _chunks(self, grid, tips, axes, radius):
        """(placement, ray) pairs in chunks of at most :data:`_CHUNK`."""
        step = max(1, int(_CHUNK // max(1, self._pairs_per(grid, radius, tips, axes))))
        for s in range(0, len(tips), step):
            owner, rays = self._pairs(grid, tips[s:s + step], axes[s:s + step], radius)
            yield s, owner, rays

    def _pairs_per(self, grid, radius, tips, axes) -> float:
        side = 2 * (radius + self.cell) / grid.cell + 1
        return side * (side + self._length / grid.cell * 0.25)

    def _stamp(self, tips, axes, tool, pieces=None) -> None:
        """Remove what the placed tool sweeps: its cutter swept up its axis, or ``pieces`` when given."""
        pieces = pieces or _primitives(tool, self._length)
        radius = max(piece[1] for piece in pieces)
        for grid in self.grids:
            for s, owner, rays in self._chunks(grid, tips, axes, radius):
                if not len(rays):
                    continue
                t0, t1 = self._intervals(grid, owner, rays, tips[s:], axes[s:], pieces)
                hit = t1 > t0
                grid.remove(rays[hit], t0[hit], t1[hit])

    def _rapid_hit(self, tips, axes, tool, pieces=None):
        """(worst overlap, placement index) of rapid placements with the material, along any ray: the cutter swept
        up its axis, or ``pieces`` when given (a back-boring bar's neck)."""
        pieces = pieces or _primitives(tool, self._length)
        radius = max(piece[1] for piece in pieces)
        worst, where = 0.0, -1
        threshold = max(RAPID_TOLERANCE, self.cell / 2.0)
        for grid in self.grids:
            for s, owner, rays in self._chunks(grid, tips, axes, radius):
                if not len(rays):
                    continue
                t0, t1 = self._intervals(grid, owner, rays, tips[s:], axes[s:], pieces)
                hit = t1 > t0
                if not hit.any():
                    continue
                length, _, _ = _overlap(grid.lo[rays[hit]], grid.hi[rays[hit]], t0[hit], t1[hit])
                k = int(np.argmax(length))
                if length[k] > max(worst, threshold):
                    worst, where = float(length[k]), s + int(owner[hit][k])
        return worst, where

    def _depth(self, tips, axes, tool):
        """The furthest material stands over the tip along the tool's axis within reach of its side: (depth,
        placement index)."""
        reach = tool.radius + max(self.cell, 0.2)
        dominant = np.abs(axes).sum(axis=0).argmax()
        grid = self.grids[int(dominant)]
        pieces = [("cyl", reach, 0.0, self._length)]
        best, where = -np.inf, -1
        for s, owner, rays in self._chunks(grid, tips, axes, reach):
            if not len(rays):
                continue
            t0, t1 = self._intervals(grid, owner, rays, tips[s:], axes[s:], pieces)
            hit = t1 > t0
            if not hit.any():
                continue
            owner, rays, t0, t1 = owner[hit], rays[hit], t0[hit], t1[hit]
            lo, hi = grid.lo[rays], grid.hi[rays]
            start = np.maximum(lo, t0[:, None])
            end = np.minimum(hi, t1[:, None])
            real = end > start + 1e-9
            if not real.any():
                continue
            cu, cv = grid.centres(rays)
            origin = np.zeros((len(rays), 3))
            origin[:, grid.u_axis], origin[:, grid.v_axis] = cu, cv
            local = s + owner
            wu = np.einsum("ij,ij->i", origin - tips[local], axes[local])
            uk = axes[local, grid.axis]
            h = np.maximum(wu[:, None] + start * uk[:, None], wu[:, None] + end * uk[:, None])
            h = np.where(real, h, -np.inf).max(axis=1)
            k = int(np.argmax(h))
            if h[k] > best:
                best, where = float(h[k]), int(local[k])
        return best, where

    # --- cutting ---------------------------------------------------------------------------------------

    def _sample(self, path, abc_before, step: float | None = None):
        """Placements along ``path`` (WCS): ``(points (M, 3), abc (M, 3), kind (M,), move (M,))``, each move split so
        no piece is longer than ``step`` (:attr:`step` when none is given) or turns any rotary axis more than
        :data:`DEG_STEP`."""
        step = self.step if step is None else step
        moves = path.moves
        if not len(moves):
            return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=np.uint8), np.zeros(0, dtype=np.int64)
        abc = np.column_stack([moves["a"], moves["b"], moves["c"]])
        kinds = moves["kind"]
        if np.isin(kinds, (ARC_CW, ARC_CCW)).any():
            samples = path.sample(self.tolerance, max_step_mm=step)
            rows = np.maximum(samples.move, 0)
            points_abc = np.where(samples.move[:, None] >= 0, abc[rows], abc_before[None, :])
            return samples.points[1:], points_abc[1:], samples.kind[1:], samples.move[1:]
        pos = path.positions()
        before = np.vstack([abc_before[None, :], abc[:-1]])
        lengths = np.linalg.norm(np.diff(pos, axis=0), axis=1)
        turns = np.abs(abc - before).max(axis=1)
        pieces = np.maximum(1, np.maximum(np.ceil(lengths / max(step, 1e-6)), np.ceil(turns / DEG_STEP)))
        pieces = pieces.astype(np.int64)
        move = np.repeat(np.arange(len(moves)), pieces)
        within = np.arange(int(pieces.sum())) - np.repeat(np.cumsum(pieces) - pieces, pieces)
        fraction = ((within + 1) / pieces[move])[:, None]
        points = pos[move] + (pos[move + 1] - pos[move]) * fraction
        angles = before[move] + (abc[move] - before[move]) * fraction
        return points, angles, kinds[move], move

    def cut(self, toolpath, tools: dict, wcs) -> SimReport:
        from cadgen._internal.cam.multiaxis import tool_axes

        report = SimReport(setup=wcs.setup_id)
        rotary = bool(toolpath.rotary) or bool(wcs.rotary_deg)
        modes = move_modes(toolpath)
        setup_abc = dict(wcs.rotary_deg)
        for op in toolpath.ops:
            tool = tools.get(op.tool) if op.tool else None
            if tool is None or tool.family != "mill" or op.end <= op.start:
                continue
            piece = toolpath.slice(op.start, op.end)
            if op.start > 0:
                row = toolpath.moves[op.start - 1]
                abc_before = np.array([row["a"], row["b"], row["c"]], dtype=float)
            else:
                abc_before = np.array([setup_abc.get(axis, 0.0) for axis in "abc"])
            points_w, abc, kinds, moves = self._sample(piece, abc_before, op_step(self.step, self.cell, tool))
            if not len(points_w):
                continue
            # The run's first sample is where the operation starts.
            points = wcs.from_wcs(np.vstack([piece.positions()[:1], points_w]))
            axes = tool_axes(np.vstack([abc_before[None, :], abc]), wcs, rotary=rotary)
            moves = np.concatenate([[-1], moves])
            # Each placement's move's mode; the first (where the op starts) neither cuts nor moves.
            classes = np.where(moves >= 0, modes[op.start + np.maximum(moves, 0)], IDLE)
            neck = [("cyl", tool.holder.shank_diameter_mm / 2.0, 0.0, self._length)]
            head = [("cyl", tool.radius, 0.0, tool.flute_length_mm)]
            before = self.volume()
            breaks = np.nonzero(np.diff(classes))[0] + 1
            starts = np.concatenate([[0], breaks])
            ends = np.concatenate([breaks, [len(classes)]])
            deepest = {"depth_mm": -np.inf, "at": None}
            worst = {mode: {"depth_mm": 0.0, "at": None, "move": None, "count": 0} for mode in (PASS, NECK)}
            for a, b in zip(starts, ends):
                kind = classes[a]
                if kind in (CUT, BACK_CUT):
                    lo = max(0, a - 1)
                    run_p, run_a = points[lo:b], axes[lo:b]
                    if kind == BACK_CUT:
                        # The head alone, feeding up from under the part: what it sweeps goes, never the material
                        # over it (its neck runs in the hole). Its reach is judged by ``reach`` from the plan.
                        self._stamp(run_p, run_a, tool, head)
                        continue
                    depth, k = self._depth(run_p, run_a, tool)
                    if depth > deepest["depth_mm"]:
                        deepest = {"depth_mm": depth, "at": run_p[k]}
                    self._stamp(run_p, run_a, tool)
                elif kind in (PASS, NECK):
                    dip, k = self._rapid_hit(points[a:b], axes[a:b], tool, neck if kind == NECK else None)
                    if dip > 0:
                        hit = worst[kind]
                        hit["count"] += 1
                        if dip > hit["depth_mm"]:
                            hit.update(depth_mm=dip, at=points[a + k], move=int(op.start + moves[a + k]))
            report.removed_mm3_by_op[op.index] = before - self.volume()
            if deepest["at"] is not None:
                report.depth_by_op[op.index] = {"depth_mm": round(float(deepest["depth_mm"]), 4),
                                                "at": [round(float(v), 4) for v in deepest["at"]]}
            for mode, hit in worst.items():
                if hit["count"]:
                    report.rapid_hits.append({"op": op.index, "move": hit["move"], "count": hit["count"],
                                              "depth_mm": round(hit["depth_mm"], 4),
                                              "at": [round(float(v), 4) for v in hit["at"]],
                                              **({"neck_diameter_mm": round(2 * neck[0][1], 4)}
                                                 if mode == NECK else {})})
        return report

    # --- results -------------------------------------------------------------------------------------------

    def _part(self, part):
        if self._part_grids is None:
            grids = []
            for grid in self.grids:
                copy = _Grid(grid.axis, self.low, self.high, self.cell)
                copy.load(part.vertices, part.triangles)
                grids.append(copy)
            self._part_grids = grids
        return self._part_grids

    @staticmethod
    def _excess(stock: _Grid, part: _Grid):
        """Stock outside the part, per ray: ``(ray, lo, hi)`` pieces."""
        lo, hi = stock.lo.copy(), stock.hi.copy()
        for k in range(part.lo.shape[1]):
            a = part.lo[:, k]
            b = part.hi[:, k]
            live = b > a
            if not live.any():
                continue
            rows = np.nonzero(live)[0]
            sub_lo, sub_hi = _subtract(lo[rows], hi[rows], a[rows], b[rows])
            width = max(lo.shape[1], sub_lo.shape[1])
            if width > lo.shape[1]:
                pad = width - lo.shape[1]
                lo = np.hstack([lo, np.full((len(lo), pad), _EMPTY_LO)])
                hi = np.hstack([hi, np.full((len(hi), pad), _EMPTY_HI)])
            if sub_lo.shape[1] < width:
                pad = width - sub_lo.shape[1]
                sub_lo = np.hstack([sub_lo, np.full((len(sub_lo), pad), _EMPTY_LO)])
                sub_hi = np.hstack([sub_hi, np.full((len(sub_hi), pad), _EMPTY_HI)])
            lo[rows], hi[rows] = sub_lo, sub_hi
        rays, cols = np.nonzero(hi - lo > 1e-6)
        return rays, lo[rays, cols], hi[rays, cols]

    def material_left(self, part, *, stock_to_leave_mm: float, tolerance_mm: float) -> MaterialLeft:
        """Stock standing outside the part thicker than the stock to leave plus a tolerance (and a cell's noise)."""
        part_grids = self._part(part)
        pieces = [self._excess(stock, own) for stock, own in zip(self.grids, part_grids)]
        threshold = stock_to_leave_mm + max(0.05, tolerance_mm, self.cell * 0.25)
        best = None
        volume = area = 0.0
        low = np.full(3, np.inf)
        high = np.full(3, -np.inf)
        for k, (rays, lo, hi) in enumerate(pieces):
            if not len(rays):
                continue
            grid = self.grids[k]
            cu, cv = grid.centres(rays)
            mid = np.zeros((len(rays), 3))
            mid[:, grid.u_axis], mid[:, grid.v_axis], mid[:, grid.axis] = cu, cv, (lo + hi) / 2.0
            thickness = hi - lo
            for j, (o_rays, o_lo, o_hi) in enumerate(pieces):
                if j == k:
                    continue
                other = self.grids[j]
                ray = other.ray_at(mid[:, other.u_axis], mid[:, other.v_axis])
                found = np.zeros(len(rays))
                if len(o_rays):
                    at = mid[:, other.axis]
                    first = np.searchsorted(o_rays, ray, side="left")
                    last = np.searchsorted(o_rays, ray, side="right")
                    for q in range(int((last - first).max()) if len(first) else 0):
                        idx = np.minimum(first + q, len(o_rays) - 1)
                        ok = (first + q < last) & (o_lo[idx] - self.cell / 2 <= at) & (at <= o_hi[idx] + self.cell / 2)
                        found = np.where(ok, np.maximum(found, o_hi[idx] - o_lo[idx]), found)
                thickness = np.minimum(thickness, found)
            # Judged only over the part's footprint (a column through the part), as the heightfield judges.
            column = part_grids[2].ray_at(mid[:, 0], mid[:, 1])
            footprint = (column >= 0) & (part_grids[2].hi[np.maximum(column, 0)] >
                                         part_grids[2].lo[np.maximum(column, 0)]).any(axis=1)
            over = (thickness > threshold) & footprint
            if not over.any():
                continue
            if k == 2:
                volume = float((hi - lo)[over].sum() * self.cell * self.cell)
                area = float(over.sum() * self.cell * self.cell)
            low = np.minimum(low, mid[over].min(axis=0))
            high = np.maximum(high, mid[over].max(axis=0))
            i = int(np.argmax(np.where(over, thickness, -np.inf)))
            if best is None or thickness[i] > best[0]:
                best = (float(thickness[i]), mid[i])
        if best is None:
            return MaterialLeft(0.0, 0.0, 0.0, None)
        if volume == 0.0:
            volume = best[0] * self.cell * self.cell
            area = self.cell * self.cell
        return MaterialLeft(volume_mm3=volume, area_mm2=area, max_mm=best[0],
                            at=tuple(float(v) for v in best[1]), bounds_min=tuple(float(v) for v in low),
                            bounds_max=tuple(float(v) for v in high))

    def mesh(self, max_columns: int = 300):
        """The Z dexels as boxes merged into one closed surface (see the module docstring); a grid larger than
        ``max_columns`` a side is drawn from every n-th column."""
        grid = self.grids[2]
        factor = max(1, int(math.ceil(max(grid.nu, grid.nv) / max_columns)))
        nu, nv = int(math.ceil(grid.nu / factor)), int(math.ceil(grid.nv / factor))
        rows = (np.arange(nu)[:, None] * factor * grid.nv + np.arange(nv)[None, :] * factor).ravel()
        lo = grid.lo[rows].reshape(nu, nv, -1)
        hi = grid.hi[rows].reshape(nu, nv, -1)
        cell = grid.cell * factor
        x0, y0 = grid.u0, grid.v0
        quads = []          # (4, 3) corner arrays, counter-clockwise seen from outside

        def emit(corners):
            if len(corners):
                quads.append(corners)

        # Tops and bottoms: one rectangle per run of cells at one height (merged along y, then equal runs along x).
        live = hi > lo
        ii, jj, kk = np.nonzero(live)
        for z, up in ((hi[ii, jj, kk], True), (lo[ii, jj, kk], False)):
            (z,), u0, u1, v0, v1 = _rectangles([z], ii, jj)
            xa, xb = x0 + u0 * cell, x0 + u1 * cell
            ya, yb = y0 + v0 * cell, y0 + v1 * cell
            corners = [np.column_stack([xa, ya, z]), np.column_stack([xb, ya, z]),
                       np.column_stack([xb, yb, z]), np.column_stack([xa, yb, z])]
            emit(np.stack(corners if up else [corners[0], corners[3], corners[2], corners[1]], axis=1))
        # Side walls: each column's material not in its neighbour's, on the shared face, merged along the wall where
        # neighbouring columns show the same span.
        for axis in (0, 1):
            pad_lo = np.full((nu + 2, nv + 2, lo.shape[2]), _EMPTY_LO)
            pad_hi = np.full((nu + 2, nv + 2, lo.shape[2]), _EMPTY_HI)
            pad_lo[1:-1, 1:-1], pad_hi[1:-1, 1:-1] = lo, hi
            for sign in (1, -1):
                if axis == 0:
                    own_lo, own_hi = pad_lo[1:-1, 1:-1], pad_hi[1:-1, 1:-1]
                    nb_lo, nb_hi = pad_lo[1 + sign:nu + 1 + sign, 1:-1], pad_hi[1 + sign:nu + 1 + sign, 1:-1]
                else:
                    own_lo, own_hi = pad_lo[1:-1, 1:-1], pad_hi[1:-1, 1:-1]
                    nb_lo, nb_hi = pad_lo[1:-1, 1 + sign:nv + 1 + sign], pad_hi[1:-1, 1 + sign:nv + 1 + sign]
                a_lo = own_lo.reshape(nu * nv, -1)
                a_hi = own_hi.reshape(nu * nv, -1)
                b_lo = nb_lo.reshape(nu * nv, -1)
                b_hi = nb_hi.reshape(nu * nv, -1)
                for k in range(b_lo.shape[1]):
                    a_lo, a_hi = _subtract(a_lo, a_hi, b_lo[:, k], b_hi[:, k])
                index, col = np.nonzero(a_hi > a_lo)
                if not len(index):
                    continue
                i, j = np.divmod(index, nv)
                z0, z1 = a_lo[index, col], a_hi[index, col]
                # The wall's plane is fixed by i (x walls) or j (y walls); runs go along the other index.
                plane, along = (i, j) if axis == 0 else (j, i)
                (plane, z0, z1), _, _, w0, w1 = _rectangles([plane.astype(float), z0, z1], np.zeros_like(along),
                                                            along)
                plane = plane.astype(np.int64)
                if axis == 0:
                    x = x0 + (plane + (1 if sign > 0 else 0)) * cell
                    ya_, yb_ = y0 + w0 * cell, y0 + w1 * cell
                    p = [np.column_stack([x, ya_, z0]), np.column_stack([x, yb_, z0]),
                         np.column_stack([x, yb_, z1]), np.column_stack([x, ya_, z1])]
                else:
                    y = y0 + (plane + (1 if sign > 0 else 0)) * cell
                    xa_, xb_ = x0 + w0 * cell, x0 + w1 * cell
                    p = [np.column_stack([xa_, y, z0]), np.column_stack([xa_, y, z1]),
                         np.column_stack([xb_, y, z1]), np.column_stack([xb_, y, z0])]
                if sign < 0:
                    p = p[::-1]
                emit(np.stack(p, axis=1))
        if not quads:
            return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
        corners = np.concatenate(quads)
        vertices = corners.reshape(-1, 3)
        base = np.arange(len(corners)) * 4
        triangles = np.vstack([np.column_stack([base, base + 1, base + 2]),
                               np.column_stack([base, base + 2, base + 3])]).astype(np.int64)
        return vertices, triangles
