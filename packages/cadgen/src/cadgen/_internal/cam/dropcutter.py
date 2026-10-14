"""Drop-cutter: how low a cutter can sit over each XY point without cutting into the part's triangle mesh.

:func:`drop` is the batch API every 3D planner and the 3D checks share::

    z = drop(points_xy, tool, mesh, leave=0.0, floor=None)

``points_xy`` is (N, 2) in the mesh's frame (a setup's WCS: the tool comes down from +Z), ``tool`` a
:class:`~cadgen._internal.cam.tools.Tool` (or a :class:`Cutter`), ``mesh`` a ``(vertices, triangles)`` pair or a
:class:`DropMesh`. The answer is the lowest tool-tip height at each point such that the cutter touches the mesh and
cuts nothing; ``-inf`` where no triangle is within the cutter's reach, or ``floor`` when one is given (and the answer
is below it). ``leave`` holds the cutter ``leave`` mm off the surface everywhere (the cutter is replaced by its
offset: a flat by a bull of radius ``R + leave`` with corner ``leave``, a ball and a bull grown by ``leave``, a cone
moved down its axis by ``leave / sin(half angle)``, which keeps at least ``leave`` and a little more at its tip); a
negative ``leave`` insets the cutter, so the answer is how low the real cutter may go while cutting no more than
``-leave`` into the part (what the gouge check asks).

Cutters (:class:`Cutter`, from a tool's type): ``flat`` (flat, and every square-ended tool: reamer, boring, tap,
thread mill, slot), ``ball``, ``bull`` (a torus: flat to ``R - rc``, then a corner of radius ``rc``) and ``cone``
(vee, chamfer, engraver, spot, drill: a tip radius, a half angle, up to the radius ``R``). The lower surface is
``h(rho)``, its height above the tip at radial distance ``rho``, convex and non-decreasing for all four.

The three contact tests, each exact for its primitive, vectorised over (point, primitive) pairs:

* **vertex**: ``z = v_z - h(|v - q|)``;
* **facet**: the cutter touches a plane (normal ``n`` turned up) at radius ``rho_c`` on the uphill side
  (flat ``R``; ball ``R |n_xy|``; bull ``R - rc + rc |n_xy|``; cone both its tip circle and its rim); the contact
  counts when it lies inside the triangle: ``z = plane(q - rho_c u) - h(rho_c)``;
* **edge**: in the edge's vertical plane the cutter's section is ``h(sqrt(d^2 + s^2))``, so the highest the edge
  holds it is the maximum of the concave ``g(s) = z(s) - h(...)`` over the part of the edge within reach: an end of
  that interval for a flat, closed forms for a ball and a cone, a bisection on ``g'`` for a bull.

Primitives are bucketed once per mesh and cutter radius on a hierarchy of XY grids (each vertex, edge and facet in
the finest grid where its box touches a few cells, listed in each; a point gathers the cells within the radius of
its own), so a point is tested only against what is near it, and a big flat triangle only once or twice; facets and edges are tested
only where their highest corner, less the cutter's height at their box's distance, could beat the best answer so
far (vertices first, so the bound bites). Everything after the bucketing is numpy over chunks
of pairs.

Also here: :func:`zmap` (drop over a grid), :func:`contours` (marching squares on a grid at a level, as polylines)
and :func:`push` (bisect each point along a direction to where the cutter at height ``z`` just touches), the
helpers waterline and the checks use. numpy at import (the engine imports this only when it plans in 3D).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["Cutter", "DropMesh", "contours", "cutter_for", "drop", "push", "zmap"]

#: (point, primitive) pairs evaluated per numpy chunk.
_PAIRS = 1_500_000
#: A primitive whose box covers more grid cells than this is tested against every point once (big flat triangles).
_LARGE_CELLS = 16
_EPS = 1e-12


@dataclass(frozen=True)
class Cutter:
    """A cutter's lower surface about its axis, from the tip: ``kind`` flat, ball, bull or cone."""

    kind: str
    radius: float
    corner: float = 0.0             # bull: the corner radius (ball: = radius)
    tip: float = 0.0                # cone: the tip radius
    half_angle: float = 0.0         # cone: radians from the axis
    #: Added to every answer: an offset cutter's tip sits this far above the cutter it stands for.
    shift: float = 0.0

    @property
    def flat_radius(self) -> float:
        """The radius of the flat bottom: ``R - rc`` for a bull, ``R`` for a flat, the tip for a cone, 0 for a ball."""
        if self.kind == "flat":
            return self.radius
        if self.kind in ("ball", "bull"):
            return self.radius - self.corner
        return self.tip

    def h(self, rho):
        """Height of the lower surface above the tip at radial distance ``rho`` (array), ``inf`` beyond the radius."""
        rho = np.abs(np.asarray(rho, dtype=float))
        out = np.full(rho.shape, np.inf)
        inside = rho <= self.radius + 1e-12
        r = np.minimum(rho[inside], self.radius)
        if self.kind == "flat":
            out[inside] = 0.0
        elif self.kind in ("ball", "bull"):
            a, rc = self.radius - self.corner, self.corner
            dd = np.maximum(0.0, r - a)
            out[inside] = rc - np.sqrt(np.maximum(0.0, rc * rc - dd * dd))
        else:
            out[inside] = np.maximum(0.0, r - self.tip) / math.tan(self.half_angle)
        return out

    def offset(self, leave: float) -> "Cutter":
        """The cutter grown by ``leave`` all round (see the module docstring), with ``shift`` raised to match; a
        negative ``leave`` insets it instead (a cutter that reaches only what the real one would cut more than
        ``-leave`` into: the gouge check's cutter)."""
        if leave < 0:
            t = min(-leave, 0.5 * self.radius)
            if self.kind == "cone":
                return Cutter("cone", self.radius - t, tip=max(0.0, self.tip - t), half_angle=self.half_angle,
                              shift=self.shift - t / math.sin(self.half_angle))
            corner = max(0.0, self.corner - t)
            kind = self.kind if self.kind == "flat" else ("ball" if self.kind == "ball" else
                                                          ("bull" if corner > 0 else "flat"))
            return Cutter(kind, self.radius - t, corner=corner if kind != "flat" else 0.0, shift=self.shift - t)
        if leave == 0:
            return self
        if self.kind == "flat":
            return Cutter("bull", self.radius + leave, corner=leave, shift=self.shift + leave)
        if self.kind in ("ball", "bull"):
            kind = "ball" if self.kind == "ball" else "bull"
            return Cutter(kind, self.radius + leave, corner=self.corner + leave, shift=self.shift + leave)
        drop_by = leave / math.sin(self.half_angle)
        return Cutter("cone", self.radius + leave, tip=self.tip, half_angle=self.half_angle,
                      shift=self.shift + drop_by)


def cutter_for(tool) -> Cutter:
    """The drop-cutter profile of a job's tool (a :class:`Cutter` passes through)."""
    if isinstance(tool, Cutter):
        return tool
    r = float(tool.radius)
    kind = tool.type
    if kind == "ball":
        return Cutter("ball", r, corner=r)
    if kind == "bull":
        rc = min(float(tool.corner_radius_mm), r)
        if rc <= 1e-9:
            return Cutter("flat", r)
        if rc >= r - 1e-9:
            return Cutter("ball", r, corner=r)
        return Cutter("bull", r, corner=rc)
    if kind in ("vee", "chamfer", "engraver", "spot", "drill"):
        angle = tool.angle_deg or (tool.point_angle if kind == "drill" else 90.0)
        return Cutter("cone", r, tip=min(r, float(tool.tip_diameter_mm) / 2.0), half_angle=math.radians(angle / 2.0))
    return Cutter("flat", r)


# --- the mesh, its primitives and their buckets -------------------------------------------------------------

class DropMesh:
    """A triangle mesh prepared for drop-cutter: unique vertices and edges, non-vertical facets with their planes,
    and per cutter radius an XY bucket grid of each. Build it once per mesh (:meth:`of` caches by array)."""

    _cache: dict = {}

    def __init__(self, vertices, triangles):
        v = np.ascontiguousarray(vertices, dtype=float)
        t = np.ascontiguousarray(triangles, dtype=np.int64)
        self.vertices = v
        self.triangles = t
        used = np.unique(t)
        self.v = v[used]
        edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
        keys = np.unique(edges[:, 0] * (len(v) + 1) + edges[:, 1])
        self.e0 = v[keys // (len(v) + 1)]
        self.e1 = v[keys % (len(v) + 1)]
        self.e_lo = np.minimum(self.e0[:, :2], self.e1[:, :2])
        self.e_hi = np.maximum(self.e0[:, :2], self.e1[:, :2])
        self.e_top = np.maximum(self.e0[:, 2], self.e1[:, 2])
        corners = v[t]
        normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        length = np.linalg.norm(normal, axis=1)
        keep = length > 1e-14
        normal = normal[keep] / length[keep, None]
        corners = corners[keep]
        # Turned up: a plane is the same plane either way, and the cutter comes from above.
        normal = np.where(normal[:, 2:3] < 0, -normal, normal)
        facets = normal[:, 2] > 1e-9
        self.f_corners = corners[facets]
        self.f_normal = normal[facets]
        # Boxes and tops, for the cheap bound that skips what cannot beat the best answer so far.
        self.f_lo = self.f_corners[:, :, :2].min(axis=1)
        self.f_hi = self.f_corners[:, :, :2].max(axis=1)
        self.f_top = self.f_corners[:, :, 2].max(axis=1)
        self.f_d = np.einsum("ij,ij->i", self.f_normal, self.f_corners[:, 0])
        # 2D barycentric inverse for the point-in-triangle test.
        a = self.f_corners[:, 0, :2]
        e1 = self.f_corners[:, 1, :2] - a
        e2 = self.f_corners[:, 2, :2] - a
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        ok = np.abs(det) > 1e-18
        det = np.where(ok, det, 1.0)
        self.f_inv = np.stack([np.stack([e2[:, 1], -e2[:, 0]], axis=1),
                               np.stack([-e1[:, 1], e1[:, 0]], axis=1)], axis=1) / det[:, None, None]
        self.f_inv[~ok] = 0.0
        self.f_ok = ok
        self.lo = v[used].min(axis=0) if len(used) else np.zeros(3)
        self.hi = v[used].max(axis=0) if len(used) else np.zeros(3)
        self._buckets: dict = {}

    @classmethod
    def of(cls, vertices, triangles) -> "DropMesh":
        if isinstance(vertices, DropMesh):
            return vertices
        key = (id(vertices), id(triangles))
        hit = cls._cache.get(key)
        if hit is not None and hit[0] is vertices and hit[1] is triangles:
            return hit[2]
        mesh = cls(vertices, triangles)
        if len(cls._cache) >= 6:
            cls._cache.pop(next(iter(cls._cache)))
        cls._cache[key] = (vertices, triangles, mesh)
        return mesh

    def buckets(self, reach: float) -> "_Buckets":
        key = round(float(reach), 9)
        if key not in self._buckets:
            if len(self._buckets) >= 8:
                self._buckets.pop(next(iter(self._buckets)))
            self._buckets[key] = _Buckets(self, float(reach))
        return self._buckets[key]


class _Grid:
    """One XY grid of a bucket hierarchy: cells of ``cell`` mm from ``(x0, y0)``, and the neighbour offsets a point
    within its own cell must gather to see everything within ``reach``."""

    def __init__(self, x0: float, y0: float, cell: float, nx: int, ny: int, reach: float):
        self.x0, self.y0, self.cell, self.nx, self.ny = x0, y0, cell, nx, ny
        k = int(math.ceil(reach / cell))
        offsets = [(di, dj) for di in range(-k, k + 1) for dj in range(-k, k + 1)
                   if math.hypot(max(0, abs(di) - 1), max(0, abs(dj) - 1)) * cell <= reach + 1e-9]
        self.di = np.array([o[0] for o in offsets], dtype=np.int64)
        self.dj = np.array([o[1] for o in offsets], dtype=np.int64)

    def span(self, lo, hi):
        """(i0, i1, j0, j1) cell ranges of boxes."""
        i0 = np.clip(np.floor((lo[:, 0] - self.x0) / self.cell).astype(np.int64), 0, self.nx - 1)
        i1 = np.clip(np.floor((hi[:, 0] - self.x0) / self.cell).astype(np.int64), 0, self.nx - 1)
        j0 = np.clip(np.floor((lo[:, 1] - self.y0) / self.cell).astype(np.int64), 0, self.ny - 1)
        j1 = np.clip(np.floor((hi[:, 1] - self.y0) / self.cell).astype(np.int64), 0, self.ny - 1)
        return i0, i1, j0, j1

    def index(self, lo, hi, top, ids):
        """CSR (starts (cells + 1,), primitive ids, each cell's highest primitive top) of primitives ``ids`` (their
        boxes ``lo``/``hi`` and ``top``s given for those ids only) in the cells their boxes touch."""
        cells = self.nx * self.ny
        starts = np.zeros(cells + 1, dtype=np.int64)
        cell_top = np.full(cells, -np.inf)
        if not len(ids):
            return (np.cumsum(starts), np.zeros(0, dtype=np.int64), cell_top, np.zeros((0, 2)), np.zeros((0, 2)),
                    np.zeros(0))
        i0, i1, j0, j1 = self.span(lo, hi)
        wi, wj = i1 - i0 + 1, j1 - j0 + 1
        counts = wi * wj
        which = np.repeat(np.arange(len(ids), dtype=np.int64), counts)
        within = np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(np.cumsum(counts) - counts, counts)
        rw = np.repeat(wj, counts)
        flat = (np.repeat(i0, counts) + within // rw) * self.ny + np.repeat(j0, counts) + within % rw
        order = np.argsort(flat, kind="stable")
        np.add.at(starts, flat + 1, 1)
        np.maximum.at(cell_top, flat, top[which])
        listed = which[order]
        # The boxes and tops again in listing order, so the bound reads them close together.
        return np.cumsum(starts), ids[listed], cell_top, lo[listed], hi[listed], top[listed]

    def slots(self, points):
        """(point index, cell, the cell's distance from the point) for every cell within reach of each point
        (cells off the grid left out)."""
        i = np.floor((points[:, 0] - self.x0) / self.cell).astype(np.int64)
        j = np.floor((points[:, 1] - self.y0) / self.cell).astype(np.int64)
        ii = i[:, None] + self.di[None, :]
        jj = j[:, None] + self.dj[None, :]
        valid = (ii >= 0) & (ii < self.nx) & (jj >= 0) & (jj < self.ny)
        cx0 = self.x0 + ii * self.cell
        cy0 = self.y0 + jj * self.cell
        px, py = points[:, 0:1], points[:, 1:2]
        dx = np.maximum(0.0, np.maximum(cx0 - px, px - (cx0 + self.cell)))
        dy = np.maximum(0.0, np.maximum(cy0 - py, py - (cy0 + self.cell)))
        point = np.broadcast_to(np.arange(len(points))[:, None], ii.shape)[valid]
        return point, (ii * self.ny + jj)[valid], np.hypot(dx, dy)[valid]


class _Buckets:
    """A hierarchy of XY grids over the mesh for one cutter reach. Each vertex, edge and facet sits in the finest
    grid where its box touches at most :data:`_LARGE_CELLS` cells (each grid's cell is four times the last), listed in
    every cell its box touches; a point gathers, per grid, the cells within ``reach`` of its own."""

    def __init__(self, mesh: DropMesh, reach: float):
        span = np.maximum(mesh.hi[:2] - mesh.lo[:2], 1e-6)
        edge_len = np.hypot(*(mesh.e1[:, :2] - mesh.e0[:, :2]).T) if len(mesh.e0) else np.ones(1)
        typical = float(np.median(edge_len)) if len(edge_len) else 1.0
        cell = max(0.25 * reach, typical, 0.05)
        while span[0] * span[1] / (cell * cell) > 4e6:
            cell *= 1.5
        boxes = {"vertex": (mesh.v[:, :2], mesh.v[:, :2], mesh.v[:, 2]),
                 "facet": (mesh.f_lo, mesh.f_hi, mesh.f_top),
                 "edge": (mesh.e_lo, mesh.e_hi, mesh.e_top)}
        left = {kind: np.arange(len(box[0]), dtype=np.int64) for kind, box in boxes.items()}
        self.levels = []
        while any(len(ids) for ids in left.values()):
            x0, y0 = float(mesh.lo[0] - cell), float(mesh.lo[1] - cell)
            grid = _Grid(x0, y0, cell, int(math.ceil(span[0] / cell)) + 3, int(math.ceil(span[1] / cell)) + 3, reach)
            last = grid.nx * grid.ny <= 4
            entry = {}
            for kind, (lo, hi, top) in boxes.items():
                ids = left[kind]
                i0, i1, j0, j1 = grid.span(lo[ids], hi[ids])
                fits = ((i1 - i0 + 1) * (j1 - j0 + 1) <= _LARGE_CELLS) | last
                here = ids[fits]
                entry[kind] = grid.index(lo[here], hi[here], top[here], here)
                left[kind] = ids[~fits]
            self.levels.append((grid, entry))
            cell *= 4.0


def _pairs(slot_points, slot_cells, csr):
    """(point, listing position) pairs for the slots, in chunks of about :data:`_PAIRS` (``csr[1][position]`` is the
    primitive)."""
    starts, ids = csr[0], csr[1]
    counts = starts[slot_cells + 1] - starts[slot_cells]
    keep = counts > 0
    slot_points, slot_cells, counts = slot_points[keep], slot_cells[keep], counts[keep]
    total = np.cumsum(counts)
    begin = 0
    while begin < len(counts):
        base = total[begin - 1] if begin else 0
        end = max(int(np.searchsorted(total, base + _PAIRS, side="right")), begin + 1)
        c = counts[begin:end]
        n = int(c.sum())
        p = np.repeat(slot_points[begin:end], c)
        within = np.arange(n, dtype=np.int64) - np.repeat(np.cumsum(c) - c, c)
        yield p, np.repeat(starts[slot_cells[begin:end]], c) + within
        begin = end


def _could_raise(points, pairs, position, csr, best, cutter):
    """The pairs whose primitive could still raise the point's answer: its highest corner, less the cutter's height
    at the primitive's nearest box distance, stands over the best so far (out of reach: never). Returns the pairs'
    points and primitives."""
    q = points[pairs]
    box_lo, box_hi = csr[3][position], csr[4][position]
    dx = np.maximum(0.0, np.maximum(box_lo[:, 0] - q[:, 0], q[:, 0] - box_hi[:, 0]))
    dy = np.maximum(0.0, np.maximum(box_lo[:, 1] - q[:, 1], q[:, 1] - box_hi[:, 1]))
    keep = csr[5][position] - cutter.h(np.hypot(dx, dy)) > best[pairs] + 1e-12
    return pairs[keep], csr[1][position[keep]]


def _vertex(q, v, cutter):
    d = np.hypot(v[:, 0] - q[:, 0], v[:, 1] - q[:, 1])
    return v[:, 2] - cutter.h(d)


def _facet(q, mesh, f, cutter):
    """The facet test's answer per pair (``-inf`` where the contact falls outside its triangle)."""
    n = mesh.f_normal[f]
    nxy = np.hypot(n[:, 0], n[:, 1])
    flatish = nxy < 1e-12
    ux = np.where(flatish, 0.0, n[:, 0] / np.where(flatish, 1.0, nxy))
    uy = np.where(flatish, 0.0, n[:, 1] / np.where(flatish, 1.0, nxy))
    if cutter.kind == "flat":
        radii = [np.where(flatish, 0.0, cutter.radius)]
    elif cutter.kind in ("ball", "bull"):
        radii = [np.where(flatish, 0.0, cutter.radius - cutter.corner + cutter.corner * nxy)]
    else:
        radii = [np.where(flatish, 0.0, cutter.tip), np.where(flatish, 0.0, cutter.radius)]
    a = mesh.f_corners[f, 0, :2]
    inv = mesh.f_inv[f]
    best = np.full(len(f), -np.inf)
    for rho in radii:
        cx = q[:, 0] - rho * ux
        cy = q[:, 1] - rho * uy
        dx, dy = cx - a[:, 0], cy - a[:, 1]
        w1 = inv[:, 0, 0] * dx + inv[:, 0, 1] * dy
        w2 = inv[:, 1, 0] * dx + inv[:, 1, 1] * dy
        inside = (w1 >= -1e-9) & (w2 >= -1e-9) & (w1 + w2 <= 1 + 1e-9) & mesh.f_ok[f]
        z = (mesh.f_d[f] - n[:, 0] * cx - n[:, 1] * cy) / n[:, 2] - cutter.h(rho)
        best = np.maximum(best, np.where(inside, z, -np.inf))
    return best


def _edge(q, p0, p1, cutter):
    """The edge test's answer per pair (``-inf`` where the edge is out of reach)."""
    ex, ey = p1[:, 0] - p0[:, 0], p1[:, 1] - p0[:, 1]
    length = np.hypot(ex, ey)
    good = length > 1e-12
    length = np.where(good, length, 1.0)
    wx, wy = ex / length, ey / length
    rx, ry = q[:, 0] - p0[:, 0], q[:, 1] - p0[:, 1]
    l0 = rx * wx + ry * wy                      # the foot of q along the edge, from p0
    d = np.abs(rx * wy - ry * wx)               # q's distance from the edge's line
    R = cutter.radius
    good &= d <= R
    reach = np.sqrt(np.maximum(0.0, R * R - d * d))
    m = (p1[:, 2] - p0[:, 2]) / length          # the edge's slope along its length
    lo = np.maximum(-l0, -reach)
    hi = np.minimum(length - l0, reach)
    good &= hi >= lo - 1e-12
    kind = cutter.kind
    if kind == "flat":
        candidates = [lo, hi]
    elif kind == "ball":
        candidates = [np.clip(m * reach / np.sqrt(1.0 + m * m), lo, hi)]
    elif kind == "cone":
        k = m * math.tan(cutter.half_angle)
        steep = np.abs(k) >= 1.0
        s_k = np.where(steep, 0.0, k * d / np.sqrt(np.maximum(1e-300, 1.0 - k * k)))
        s_flat = np.sqrt(np.maximum(0.0, cutter.tip * cutter.tip - d * d))
        best_s = np.sign(m) * np.maximum(np.abs(s_k), s_flat)
        best_s = np.where(steep, np.sign(m) * reach, best_s)
        candidates = [np.clip(best_s, lo, hi)]
    else:
        candidates = [_bull_edge(m, d, lo, hi, cutter)]
    best = np.full(len(q), -np.inf)
    for s in candidates:
        rho = np.sqrt(d * d + s * s)
        z = p0[:, 2] + m * (l0 + s) - cutter.h(np.minimum(rho, R))
        best = np.maximum(best, np.where(good, z, -np.inf))
    return best


def _bull_edge(m, d, lo, hi, cutter, iterations: int = 40):
    """Where ``g(s) = m s - h(sqrt(d^2 + s^2))`` peaks on ``[lo, hi]`` for a torus: bisection on the decreasing
    ``g'``."""
    a, rc = cutter.radius - cutter.corner, cutter.corner

    def slope(s):
        rho = np.sqrt(d * d + s * s)
        dd = np.clip(rho - a, 0.0, rc * (1 - 1e-12))
        dh = dd / np.sqrt(np.maximum(1e-300, rc * rc - dd * dd))
        return m - dh * np.where(rho > 1e-15, s / np.maximum(rho, 1e-15), 0.0)

    low, high = lo.copy(), np.maximum(hi, lo)
    g_low, g_high = slope(low), slope(high)
    out = np.where(g_low <= 0, low, np.where(g_high >= 0, high, np.nan))
    todo = np.isnan(out)
    if todo.any():
        a_, b_ = low[todo], high[todo]
        mm, dd_ = m[todo], d[todo]
        for _ in range(iterations):
            mid = 0.5 * (a_ + b_)
            rho = np.sqrt(dd_ * dd_ + mid * mid)
            ddd = np.clip(rho - a, 0.0, rc * (1 - 1e-12))
            dh = ddd / np.sqrt(np.maximum(1e-300, rc * rc - ddd * ddd))
            g = mm - dh * np.where(rho > 1e-15, mid / np.maximum(rho, 1e-15), 0.0)
            up = g > 0
            a_ = np.where(up, mid, a_)
            b_ = np.where(up, b_, mid)
        out[todo] = 0.5 * (a_ + b_)
    return out


def drop(points_xy, tool, mesh, *, leave: float = 0.0, floor: float | None = None):
    """The lowest tool-tip height over each point that cuts nothing (see the module docstring)."""
    points = np.asarray(points_xy, dtype=float).reshape(-1, 2)
    if not isinstance(mesh, DropMesh):
        mesh = DropMesh.of(*mesh)
    cutter = cutter_for(tool).offset(leave)
    best = np.full(len(points), -np.inf)
    if len(points) and len(mesh.v):
        buckets = mesh.buckets(cutter.radius)
        # Blocks of points keep the slot arrays small.
        widest = max(len(grid.di) for grid, _ in buckets.levels)
        block = max(1, 2_000_000 // widest)
        for b0 in range(0, len(points), block):
            sub = points[b0:b0 + block]
            levels = []
            for grid, entry in buckets.levels:
                sp, sc, sd = grid.slots(sub)
                levels.append((sp + b0, sc, cutter.h(sd), sd <= 0.0, entry))
            # Vertices in the point's own cell first, so the bounds after have a best answer to beat.
            for first in (True, False):
                for sp, sc, heights, own, entry in levels:
                    csr = entry["vertex"]
                    live = (own if first else ~own) & (csr[2][sc] - heights > best[sp] + 1e-12)
                    for pairs, position in _pairs(sp[live], sc[live], csr):
                        np.maximum.at(best, pairs, _vertex(points[pairs], mesh.v[csr[1][position]], cutter))
            for sp, sc, heights, own, entry in levels:
                csr = entry["facet"]
                live = csr[2][sc] - heights > best[sp] + 1e-12
                for pairs, position in _pairs(sp[live], sc[live], csr):
                    pairs, primitive = _could_raise(points, pairs, position, csr, best, cutter)
                    if len(pairs):
                        np.maximum.at(best, pairs, _facet(points[pairs], mesh, primitive, cutter))
            for sp, sc, heights, own, entry in levels:
                csr = entry["edge"]
                live = csr[2][sc] - heights > best[sp] + 1e-12
                for pairs, position in _pairs(sp[live], sc[live], csr):
                    pairs, primitive = _could_raise(points, pairs, position, csr, best, cutter)
                    if len(pairs):
                        np.maximum.at(best, pairs, _edge(points[pairs], mesh.e0[primitive], mesh.e1[primitive],
                                                         cutter))
    best = best + cutter.shift
    if floor is not None:
        best = np.maximum(best, floor)
    return best


# --- grids, contours and pushing ------------------------------------------------------------------------------

def zmap(mesh, tool, x0: float, y0: float, spacing: float, nx: int, ny: int, *, leave: float = 0.0,
         floor: float | None = None):
    """Drop over the grid ``x0 + i * spacing, y0 + j * spacing`` (``i < nx``, ``j < ny``): an (nx, ny) array."""
    xs = x0 + np.arange(nx) * spacing
    ys = y0 + np.arange(ny) * spacing
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    z = drop(np.column_stack([gx.ravel(), gy.ravel()]), tool, mesh, leave=leave, floor=floor)
    return z.reshape(nx, ny)


def contours(grid, levels, x0: float, y0: float, spacing: float, *, refine=None):
    """Marching squares: the curves where ``grid`` crosses each of ``levels`` (a number, or a list: then a list of
    answers), each a list of (N, 2) polylines (closed ones repeat their first point). A node is "free" at a level when
    its value is at most the level.

    ``refine(free_xy, blocked_xy, level_z) -> xy`` (optional) places every crossing of every level on its grid edge
    (from the free node toward the blocked one), in one call; by default they are interpolated linearly. Saddle cells
    are split by the mean of their corners."""
    single = np.isscalar(levels)
    levels = [float(levels)] if single else [float(z) for z in levels]
    grid = np.asarray(grid, dtype=float)
    nx, ny = grid.shape
    if nx < 2 or ny < 2:
        return [] if single else [[] for _ in levels]
    xs = x0 + np.arange(nx) * spacing
    ys = y0 + np.arange(ny) * spacing
    work = []
    free_pts, blocked_pts, zs, linear = [], [], [], []
    for level in levels:
        free = grid <= level
        xi, xj = np.nonzero(free[:-1, :] != free[1:, :])
        yi, yj = np.nonzero(free[:, :-1] != free[:, 1:])
        ends = []
        for ai, aj, bi, bj in ((xi, xj, xi + 1, xj), (yi, yj, yi, yj + 1)):
            a_free = free[ai, aj]
            a_xy = np.column_stack([xs[ai], ys[aj]])
            b_xy = np.column_stack([xs[bi], ys[bj]])
            fa = np.where(a_free[:, None], a_xy, b_xy)
            fb = np.where(a_free[:, None], b_xy, a_xy)
            va = np.where(a_free, grid[ai, aj], grid[bi, bj])
            vb = np.where(a_free, grid[bi, bj], grid[ai, aj])
            with np.errstate(invalid="ignore", divide="ignore"):
                t = np.where(np.isfinite(vb) & np.isfinite(va) & (vb != va), (level - va) / (vb - va), 0.5)
            t = np.clip(np.nan_to_num(t, nan=0.5), 0.0, 1.0)
            free_pts.append(fa)
            blocked_pts.append(fb)
            zs.append(np.full(len(fa), level))
            linear.append(fa + (fb - fa) * t[:, None])
            ends.append(len(fa))
        work.append((free, xi, xj, yi, yj, ends))
    counts = [sum(item[5]) for item in work]
    if refine is not None and sum(counts):
        placed = refine(np.vstack(free_pts), np.vstack(blocked_pts), np.concatenate(zs))
    else:
        placed = np.vstack(linear) if linear else np.zeros((0, 2))
    out = []
    offset = 0
    for level, (free, xi, xj, yi, yj, _), count in zip(levels, work, counts):
        points = placed[offset:offset + count]
        offset += count
        out.append(_link_crossings(grid, level, free, xi, xj, yi, yj, points))
    return out[0] if single else out


def _link_crossings(grid, level, free, xi, xj, yi, yj, points):
    """The polylines of one level's crossings (x-edge crossings first in ``points``, then y-edge ones)."""
    import shapely

    nx, ny = grid.shape
    if not len(points):
        return []
    index_x = np.full((nx - 1, ny), -1, dtype=np.int64)
    index_x[xi, xj] = np.arange(len(xi))
    index_y = np.full((nx, ny - 1), -1, dtype=np.int64)
    index_y[yi, yj] = len(xi) + np.arange(len(yi))
    # Each cell's four edges: bottom (x-edge j), right (y-edge i+1), top (x-edge j+1), left (y-edge i).
    edges = np.stack([index_x[:, :-1], index_y[1:, :], index_x[:, 1:], index_y[:-1, :]], axis=-1)
    count = (edges >= 0).sum(axis=-1)
    two = count == 2
    pairs = np.sort(edges[two], axis=-1)[:, 2:]
    segments = [pairs]
    ci, cj = np.nonzero(count == 4)
    saddles = []
    for i, j in zip(ci.tolist(), cj.tolist()):
        bottom, right, top, left = (int(e) for e in edges[i, j])
        corners = grid[i:i + 2, j:j + 2]
        mean = float(np.mean(np.where(np.isfinite(corners), corners, level)))
        if bool(free[i, j]) == (mean <= level):
            saddles += [[bottom, right], [top, left]]
        else:
            saddles += [[left, bottom], [right, top]]
    if saddles:
        segments.append(np.asarray(saddles, dtype=np.int64))
    seg = np.vstack(segments)
    lines = points[seg]
    lines = lines[np.hypot(*(lines[:, 1] - lines[:, 0]).T) > 1e-12]
    if not len(lines):
        return []
    merged = shapely.line_merge(shapely.multilinestrings(lines))
    return [shapely.get_coordinates(part) for part in shapely.get_parts(merged)
            if len(shapely.get_coordinates(part)) >= 2]


def push(points_xy, directions, z, tool, mesh, *, distance: float, tolerance: float, leave: float = 0.0):
    """Each point moved along its unit ``direction`` to where a cutter with its tip at ``z`` (a number or one per
    point) just stops cutting: bisection between the point and ``distance`` along, ending on the free side within
    ``tolerance``. Returns (moved points, ok); ``ok`` is False where even ``distance`` along is not free (the point
    is returned as given)."""
    points = np.asarray(points_xy, dtype=float).reshape(-1, 2)
    directions = np.asarray(directions, dtype=float).reshape(-1, 2)
    z = np.broadcast_to(np.asarray(z, dtype=float), (len(points),))
    if not len(points):
        return points, np.zeros(0, dtype=bool)
    lo = np.zeros(len(points))
    hi = np.full(len(points), float(distance))
    here = drop(points, tool, mesh, leave=leave)
    free_now = here <= z + 1e-9
    far = drop(points + directions * distance, tool, mesh, leave=leave)
    ok = free_now | (far <= z + 1e-9)
    work = ~free_now & ok
    hi = np.where(free_now, 0.0, hi)
    steps = max(1, int(math.ceil(math.log2(max(distance, tolerance) / max(tolerance, 1e-6)))) + 1)
    for _ in range(steps):
        if not work.any():
            break
        mid = 0.5 * (lo + hi)
        idx = np.nonzero(work)[0]
        zz = drop(points[idx] + directions[idx] * mid[idx, None], tool, mesh, leave=leave)
        is_free = zz <= z[idx] + 1e-9
        hi[idx] = np.where(is_free, mid[idx], hi[idx])
        lo[idx] = np.where(is_free, lo[idx], mid[idx])
    moved = points + directions * np.where(ok, hi, 0.0)[:, None]
    return moved, ok
