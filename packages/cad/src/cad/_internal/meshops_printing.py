"""3D printing's measures of a triangle mesh that both integrations share, numpy alone.

The build123d integration triangulates a B-rep (``_dfm_brep.triangles``: each triangle naming its face)
and hands the arrays here; the trimesh integration hands its mesh's. Every function takes ``V`` (n, 3)
vertices in millimetres, Z up, and ``F`` (m, 3) vertex indices of outward-wound triangles, and answers
plain arrays and numbers:

- ``crossings``: every crossing of a grid of lines parallel to one axis with the surface (where, which
  triangle, which way) -- a raster of the mesh, exact on each line;
- ``support``: the column fill under every down-facing surface steeper than a limit: support volume,
  the part's surface the supports touch (per triangle owner: a face ordinal), from a raster along Z;
- ``voxels``: the material (by the winding of each Z line's crossings) and the surface (every voxel a
  crossing along X, Y or Z passes through), so a wall thinner than a voxel still closes a cavity;
- ``cavities``: air the outside cannot reach -- sealed, or reachable only through openings narrower
  than a ball (a hollow part's drain holes) -- with each cavity's volume and openings;
- ``span``: a flat overhang's span between the walls that carry it (a bridge) or its reach beyond the
  one wall that does (a cantilever);
- ``orientation_rows`` and ``ranked``: each candidate rotation's support volume and contact, build height,
  bed contact, overhang and shallow-slope area, and their weighted ranking (``WEIGHTS``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

__all__ = ["ANGLE_EPS", "OVERHANG_AREA_MM2", "OVERHANG_REACH_MM", "KNIFE_DEG", "POCKET_MIN_CELLS", "rot_text", "thin_depth", "Cavity", "Crossings", "Grid", "ROTATIONS", "WEIGHTS", "angles", "ball_pad", "build_fit", "field_pitch", "fit", "in_triangles_xy", "inscribed", "raster_pitch", "sections", "spread_points", "cavities", "crossings", "down_to",
           "frame", "near_segments", "orientation_rows", "ranked", "rotation", "span", "support", "voxels"]

# Lines of a raster are offset by these irrational fractions of the pitch, so no line runs exactly
# through a vertex or along an edge of a mesh built on round numbers (each crossing counted once).
_JITTER = (0.0763932 * (math.sqrt(5) - 1), 0.0447214 * (math.sqrt(3) - 1))


#: A convex edge whose material angle is under this many degrees is a **knife edge**, not a corner. The
#: material at distance ``d`` from an edge of angle ``a`` is ``2 d tan(a / 2)`` thick, so it is thinner than a
#: minimum wall ``t`` for ``t / (2 tan(a / 2))`` from the edge: half a wall at a box's 90 deg corner (the one
#: bead every corner is), 1.2 walls at 45 deg, 1.9 at 30, 5.7 at 10 -- past 45 deg the sliver under the
#: minimum is deeper than a whole wall, which a printer cannot lay. 45 deg is also the slope the guides
#: (Hubs FDM) hold self-supporting: a chamfer of 45 deg or more leaves no knife edge.
KNIFE_DEG = 45.0

#: An angle within this many degrees of a limit is at the limit, not under it: a 45 deg chamfer the kernel
#: makes reads 44.999999999999936 on one axis and 45.000000000000014 on the other, and both are 45 (Hubs FDM:
#: "up to 45°" self-supports). Every comparison of a surface's angle with a limit subtracts it.
ANGLE_EPS = 1e-6
#: Overhangs too small to need support (the owner's figures, both paths): a slope, ceiling or cantilever with
#: less than OVERHANG_AREA_MM2 under the angle limit, or a cantilever reaching less than the nozzle's width
#: (``--nozzle``, else OVERHANG_REACH_MM: one extrusion width lays it), is listed with ``counted`` false and
#: judged by no rule -- a 0.01 mm flat a chamfer leaves short of its corner is no overhang.
OVERHANG_AREA_MM2 = 1.0
OVERHANG_REACH_MM = 0.4


def thin_depth(minimum: float | None, angle_deg: float) -> float | None:
    """How far from an edge of material angle ``angle_deg`` the material stays thinner than ``minimum``."""
    if minimum is None or not angle_deg > 0:
        return None
    return float(minimum) / (2.0 * math.tan(math.radians(angle_deg) / 2.0))


def frame(V: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each triangle's unit outward normal and area."""
    tri = V[F]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    normals = np.divide(cross, length[:, None], out=np.zeros_like(cross), where=length[:, None] > 0)
    return normals, 0.5 * length


def angles(normals: np.ndarray) -> np.ndarray:
    """Each surface's angle from horizontal, in degrees: 0 a flat floor or ceiling, 90 a wall."""
    return np.degrees(np.arccos(np.clip(np.abs(normals[..., 2]), 0.0, 1.0)))


# --- the raster -------------------------------------------------------------------------------------------


@dataclass
class Crossings:
    """The crossings of a grid of lines along ``axis`` with a mesh: line ``(i, j)`` passes through
    ``origin + ((i + 0.5 + jitter) * pitch, (j + 0.5 + jitter) * pitch)`` in the two other axes."""

    axis: int
    origin: np.ndarray          # the grid's corner in the two other axes
    pitch: float
    shape: tuple[int, int]
    i: np.ndarray
    j: np.ndarray
    t: np.ndarray               # where along the axis
    tri: np.ndarray             # the triangle crossed
    sign: np.ndarray            # +1: the surface faces +axis (leaving material going +axis); -1 entering


def _others(axis: int) -> tuple[int, int]:
    return {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]


def crossings(V: np.ndarray, F: np.ndarray, axis: int, origin: np.ndarray, pitch: float,
              shape: tuple[int, int], chunk: int = 4000) -> Crossings:
    """Every crossing of the grid of lines along ``axis`` with the triangles (see ``Crossings``)."""
    a, b = _others(axis)
    tri = V[F]
    normals, _ = frame(V, F)
    indices = np.nonzero(np.abs(normals[:, axis]) > 1e-12)[0]
    out: dict[str, list[np.ndarray]] = {"i": [], "j": [], "t": [], "tri": [], "sign": []}
    ja, jb = _JITTER
    for start in range(0, len(indices), chunk):
        idx = indices[start:start + chunk]
        p = tri[idx]
        pa, pb = p[:, :, a], p[:, :, b]
        lo_i = np.maximum(np.ceil((pa.min(axis=1) - origin[0]) / pitch - 0.5 - ja).astype(int), 0)
        hi_i = np.minimum(np.floor((pa.max(axis=1) - origin[0]) / pitch - 0.5 - ja).astype(int), shape[0] - 1)
        lo_j = np.maximum(np.ceil((pb.min(axis=1) - origin[1]) / pitch - 0.5 - jb).astype(int), 0)
        hi_j = np.minimum(np.floor((pb.max(axis=1) - origin[1]) / pitch - 0.5 - jb).astype(int), shape[1] - 1)
        ni, nj = hi_i - lo_i + 1, hi_j - lo_j + 1
        counts = np.where((ni > 0) & (nj > 0), ni * nj, 0)
        if not counts.any():
            continue
        owner = np.repeat(np.arange(len(idx)), counts)
        local = np.arange(len(owner)) - np.repeat(np.cumsum(counts) - counts, counts)
        gi = lo_i[owner] + local // nj[owner]
        gj = lo_j[owner] + local % nj[owner]
        qa = origin[0] + (gi + 0.5 + ja) * pitch
        qb = origin[1] + (gj + 0.5 + jb) * pitch
        x0, x1, x2 = pa[owner, 0], pa[owner, 1], pa[owner, 2]
        y0, y1, y2 = pb[owner, 0], pb[owner, 1], pb[owner, 2]
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        good = np.abs(det) > 1e-300
        safe = np.where(good, det, 1.0)
        l0 = ((y1 - y2) * (qa - x2) + (x2 - x1) * (qb - y2)) / safe
        l1 = ((y2 - y0) * (qa - x2) + (x0 - x2) * (qb - y2)) / safe
        l2 = 1.0 - l0 - l1
        hit = good & (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not hit.any():
            continue
        o = owner[hit]
        out["t"].append(l0[hit] * p[o, 0, axis] + l1[hit] * p[o, 1, axis] + l2[hit] * p[o, 2, axis])
        out["i"].append(gi[hit])
        out["j"].append(gj[hit])
        out["tri"].append(idx[o])
        out["sign"].append(np.sign(normals[idx[o], axis]).astype(int))

    def joined(name: str, dtype: Any) -> np.ndarray:
        return np.concatenate(out[name]).astype(dtype) if out[name] else np.zeros(0, dtype=dtype)

    return Crossings(axis, np.asarray(origin, dtype=float), float(pitch), shape, joined("i", int), joined("j", int),
                     joined("t", float), joined("tri", int), joined("sign", int))


def _sorted(c: Crossings) -> tuple[np.ndarray, ...]:
    """The crossings sorted by line, then along it: line, t, triangle, sign, whether it is its line's
    first, and the winding just before it (0 in air, above 0 in material)."""
    line = c.i * c.shape[1] + c.j
    order = np.lexsort((c.t, line))
    line, t, tri, sign = line[order], c.t[order], c.tri[order], c.sign[order]
    first = np.ones(len(line), dtype=bool)
    first[1:] = line[1:] != line[:-1]
    step = -sign  # entering material (a surface facing -axis) raises the winding
    total = np.cumsum(step)
    start = np.maximum.accumulate(np.where(first, np.arange(len(line)), 0))
    base = np.where(start > 0, total[np.maximum(start - 1, 0)], 0)
    before = total - step - base
    return line, t, tri, sign, first, before


# --- support ------------------------------------------------------------------------------------------------


def support(V: np.ndarray, F: np.ndarray, angle_limit: float, pitch: float, plate_z: float | None = None,
            owners: np.ndarray | None = None, band: float | None = None) -> dict[str, Any]:
    """The support a part needs standing on the plate (its lowest point unless ``plate_z``), from a raster
    along Z at ``pitch``: under every crossing of a down-facing surface under ``angle_limit`` degrees from
    horizontal that has air below, a column down to the material below or the plate. Its volume, its
    contact with the part (the tops of the columns, and their feet where they stand on the part rather
    than the plate), and that contact per ``owners`` value (a face ordinal) of the triangles touched.
    ``band``: surfaces this close above the plate stand on it (default a fifth of the pitch)."""
    empty = {"volume_mm3": 0.0, "contact_area_mm2": 0.0, "column_count": 0, "per_owner_mm2": {}, "pitch_mm": pitch}
    if len(F) == 0:
        return empty
    lo, hi = V.min(axis=0), V.max(axis=0)
    plate = float(lo[2] if plate_z is None else plate_z)
    band = 0.2 * pitch if band is None else band
    shape = (max(1, int(math.ceil((hi[0] - lo[0]) / pitch))), max(1, int(math.ceil((hi[1] - lo[1]) / pitch))))
    c = crossings(V, F, 2, lo[:2], pitch, shape)
    if not len(c.t):
        return empty
    line, t, tri, sign, first, before = _sorted(c)
    normals, _ = frame(V, F)
    steep = angles(normals[tri]) < angle_limit - ANGLE_EPS
    starts = (sign < 0) & (before <= 0) & steep & (t > plate + band)
    below = np.where(first, plate, np.roll(t, 1))
    length = np.where(starts, t - below, 0.0)
    columns = starts & (length > 1e-6)
    cell = pitch * pitch
    on_part = columns & ~first
    per_owner: dict[int, float] = {}
    if owners is not None:
        touched = np.concatenate([tri[columns], np.roll(tri, 1)[on_part]])
        values, counts = np.unique(owners[touched], return_counts=True)
        per_owner = {int(v): float(n * cell) for v, n in zip(values, counts)}
    return {"volume_mm3": float(length[columns].sum() * cell),
            "contact_area_mm2": float((columns.sum() + on_part.sum()) * cell), "column_count": int(columns.sum()),
            "per_owner_mm2": per_owner, "pitch_mm": pitch}


# --- voxels and cavities ------------------------------------------------------------------------------------


@dataclass
class Grid:
    """Voxels ``(nx, ny, nz)`` of side ``pitch`` from ``origin``: ``material`` inside the mesh by winding,
    ``surface`` where a crossing passes through (a wall thinner than a voxel still closes)."""

    origin: np.ndarray
    pitch: float
    material: np.ndarray
    surface: np.ndarray

    @property
    def shape(self) -> tuple[int, int, int]:
        return tuple(self.material.shape)  # type: ignore[return-value]

    def index(self, points: np.ndarray) -> np.ndarray:
        """The flat index of the voxel holding each point, clipped into the grid."""
        ijk = np.floor((np.asarray(points, dtype=float).reshape(-1, 3) - self.origin) / self.pitch).astype(int)
        ijk = np.clip(ijk, 0, np.array(self.shape) - 1)
        return np.ravel_multi_index((ijk[:, 0], ijk[:, 1], ijk[:, 2]), self.shape)

    def center(self, ijk: np.ndarray) -> np.ndarray:
        return self.origin + (np.asarray(ijk, dtype=float) + 0.5) * self.pitch


def voxels(V: np.ndarray, F: np.ndarray, pitch: float, pad: int = 2) -> Grid:
    """The mesh voxelized at ``pitch`` with ``pad`` empty voxels around it (see ``Grid``)."""
    lo, hi = V.min(axis=0), V.max(axis=0)
    origin = lo - pad * pitch
    shape = tuple(int(math.ceil((hi[k] - lo[k]) / pitch)) + 2 * pad for k in range(3))
    delta = np.zeros(shape, dtype=np.int32)
    surface = np.zeros(shape, dtype=bool)
    for axis in (0, 1, 2):
        a, b = _others(axis)
        c = crossings(V, F, axis, origin[[a, b]], pitch, (shape[a], shape[b]))
        if not len(c.t):
            continue
        k = np.clip(np.floor((c.t - origin[axis]) / pitch).astype(int), 0, shape[axis] - 1)
        ijk = np.empty((len(k), 3), dtype=int)
        ijk[:, axis], ijk[:, a], ijk[:, b] = k, c.i, c.j
        surface[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
        if axis == 2:
            # the winding changes at the first voxel centre past the crossing
            kz = np.clip(np.ceil((c.t - origin[2]) / pitch - 0.5).astype(int), 0, shape[2] - 1)
            np.add.at(delta, (c.i, c.j, kz), -c.sign)
    material = np.cumsum(delta, axis=2) > 0
    return Grid(origin, float(pitch), material, surface)


def ball_pad(ball_radius: float, pitch: float) -> int:
    """The empty voxels a grid needs around the mesh for ``cavities``' ball to roll round its outside."""
    return int(round(ball_radius / pitch)) + 3


def components(mask: np.ndarray) -> np.ndarray:
    """The 6-connected components of a boolean voxel ``mask``: each cell's component (the smallest flat index
    in it), -1 outside the mask. Labels spread along every run of the mask, axis after axis, until none
    changes: each sweep is a few passes over the grid, and a component needs as many sweeps as its path turns."""
    big = np.iinfo(np.int64).max
    labels = np.where(mask, np.arange(mask.size, dtype=np.int64).reshape(mask.shape), big)
    while True:
        changed = False
        for axis in (2, 1, 0):
            moved = np.moveaxis(labels, axis, -1)
            free = np.moveaxis(mask, axis, -1)
            n = moved.shape[-1]
            lines = moved.reshape(-1, n)
            breaks = ~free.reshape(-1, n)
            starts = breaks.copy()
            starts[:, 0] = True
            # a run is a start (a cell outside the mask, or a line's first) and the mask cells after it
            flat = lines.ravel()
            first = np.flatnonzero(starts.ravel())
            least = np.minimum.reduceat(flat, first)
            spread = np.repeat(least, np.diff(np.append(first, flat.size)))
            spread = np.where(breaks.ravel(), flat, np.minimum(flat, spread))
            # a run that starts at a mask cell (a line's first) includes it; one that starts outside does not
            if not np.array_equal(spread, flat):
                changed = True
                labels = np.moveaxis(spread.reshape(moved.shape), -1, axis).copy()
        if not changed:
            break
    return np.where(mask, labels, -1)


_STEPS6 = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]


def _shift_or(mask: np.ndarray, axis: int) -> np.ndarray:
    """``mask`` or its neighbours either way along ``axis``."""
    out = mask.copy()
    lead = [slice(None)] * 3
    tail = [slice(None)] * 3
    lead[axis], tail[axis] = slice(1, None), slice(None, -1)
    out[tuple(lead)] |= mask[tuple(tail)]
    out[tuple(tail)] |= mask[tuple(lead)]
    return out


def _near(mask: np.ndarray, full: bool) -> np.ndarray:
    """Voxels with a 6- (or 26- where ``full``) neighbour in ``mask`` (the 26: the cube, axis by axis)."""
    if full:
        return _shift_or(_shift_or(_shift_or(mask, 0), 1), 2)
    out = np.zeros_like(mask)
    for axis in range(3):
        out |= _shift_or(mask, axis)
    return out


def _depth(air: np.ndarray, steps: int) -> np.ndarray:
    """Each air voxel's distance in voxels to the nearest voxel that is not air, up to ``steps`` (an
    octagonal chamfer: 6- and 26-neighbour erosions alternated)."""
    depth = np.zeros(air.shape, dtype=np.int16)
    current = air.copy()
    for step in range(1, steps + 1):
        current &= ~_near(~current, full=step % 2 == 0)
        if not current.any():
            break
        depth[current] = step
    return depth


def inscribed(material: np.ndarray, steps: int) -> np.ndarray:
    """Each material voxel's distance in voxels to the nearest voxel outside it, up to ``steps``: twice it
    (plus one) times the pitch is the largest ball the material holds there (a section's thickness)."""
    return _depth(material, steps)


def _dilate(mask: np.ndarray, within: np.ndarray, steps: int) -> np.ndarray:
    grown = mask.copy()
    for step in range(1, steps + 1):
        grown |= _near(grown, full=step % 2 == 0) & within
    return grown


@dataclass
class Cavity:
    """Air the outside cannot reach, or only through openings narrower than the probing ball."""

    voxels: np.ndarray                  # flat indices of its voxels
    volume_mm3: float
    centroid: np.ndarray
    sealed: bool                        # no air path out at all at the grid's resolution
    openings: list[dict[str, Any]] = field(default_factory=list)  # {"diameter_mm", "xyz", "voxels"}


def _neighbour_labels(labels: np.ndarray) -> list[np.ndarray]:
    """For each of the 6 directions, every voxel's neighbour's label (the grid's edge: -2)."""
    padded = np.pad(labels, 1, constant_values=-2)
    nx, ny, nz = labels.shape
    return [padded[1 + dx:1 + dx + nx, 1 + dy:1 + dy + ny, 1 + dz:1 + dz + nz] for dx, dy, dz in _STEPS6]


def cavities(grid: Grid, ball_radius: float, cap: int = 32) -> tuple[list[Cavity], np.ndarray]:
    """The cavities of ``grid``, and a label per voxel (flat): -2 material, -1 outside (the probing ball's
    reach), -3 a passage or crevice the ball does not fill, ``k`` cavity ``k``. A cavity is a region of air a
    ball of ``ball_radius`` fits inside but cannot reach from outside -- sealed (no air path out at all) or
    open through narrower openings, a hollow part's drain holes, each opening's diameter estimated from the
    largest ball that fits through it -- or a sealed pocket of air too small for the ball. The grid's padding
    must hold the ball: ``voxels(..., pad=ball_pad(ball_radius, pitch))``."""
    shape = grid.shape
    air = ~(grid.material | grid.surface)
    border = np.zeros(shape, dtype=bool)
    border[[0, -1], :, :] = True
    border[:, [0, -1], :] = True
    border[:, :, [0, -1]] = True

    def touching_border(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        labelled = components(mask)
        open_ = np.unique(labelled[border & mask])
        return labelled, np.isin(labelled, open_) & mask

    air_labels, outside_all = touching_border(air)
    steps = max(1, int(round(ball_radius / grid.pitch)))
    depth = _depth(air, steps + 1)
    fits = depth >= steps
    fit_labels, reached = touching_border(fits)
    # the union of the balls: grown without regard to walls (a ball wholly in air covers only air), so the
    # outside's reach never seeps through an opening narrower than the ball
    everywhere = np.ones(shape, dtype=bool)
    outside = _dilate(reached, everywhere, steps + 1) & air
    labels = np.full(shape, -3, dtype=np.int32)
    labels[~air] = -2
    labels[outside] = -1
    found: list[Cavity] = []
    cores = np.unique(fit_labels[fits & ~reached])
    inner_air = air & ~outside
    for core in cores[:cap]:
        region = _dilate(fit_labels == core, everywhere, steps + 1) & inner_air & (labels == -3)
        if not region.any():
            continue
        sealed = not bool(outside_all[region].any())
        if sealed:
            # a sealed cavity is all the air of its pocket: the crevices the balls miss too
            region |= np.isin(air_labels, np.unique(air_labels[region])) & (labels == -3)
        labels[region] = len(found)
        cells = np.flatnonzero(region)
        ijk = np.stack(np.unravel_index(cells, shape), axis=1)
        found.append(Cavity(cells, float(len(cells) * grid.pitch ** 3), grid.center(ijk.mean(axis=0)), sealed))
    # sealed pockets too small for the ball -- but not a crumb of a few voxels, which the surface's own
    # voxels close off at an inner corner (an exact inner shell is found apart, by the B-rep)
    for pocket in np.unique(air_labels[air & ~outside_all & (labels == -3)])[:max(0, cap - len(found))]:
        region = (air_labels == pocket) & (labels == -3)
        cells = np.flatnonzero(region)
        if len(cells) < POCKET_MIN_CELLS:
            continue
        labels[region] = len(found)
        ijk = np.stack(np.unravel_index(cells, shape), axis=1)
        found.append(Cavity(cells, float(len(cells) * grid.pitch ** 3), grid.center(ijk.mean(axis=0)), sealed=True))
    # openings: the passages (label -3) that touch a cavity and the outside
    passages = labels == -3
    if found and passages.any():
        pieces = components(passages)
        around = _neighbour_labels(labels)
        to_cavity: dict[int, set[int]] = {}
        to_outside: set[int] = set()
        for neighbour in around:
            at = passages & (neighbour >= 0)
            for piece, k in zip(pieces[at].tolist(), neighbour[at].tolist()):
                to_cavity.setdefault(piece, set()).add(k)
            to_outside.update(np.unique(pieces[passages & (neighbour == -1)]).tolist())
        for piece, ks in to_cavity.items():
            if piece not in to_outside:
                continue
            cells = np.flatnonzero(pieces == piece)
            ijk = np.stack(np.unravel_index(cells, shape), axis=1)
            widest = int(depth.ravel()[cells].max())
            for k in sorted(ks):
                found[k].openings.append({"diameter_mm": float((2 * widest + 3) * grid.pitch),
                                          "xyz": grid.center(ijk.mean(axis=0)), "voxels": cells})
    return found, labels.ravel()


# --- a flat overhang's span ---------------------------------------------------------------------------------


def _nearest(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each point, the distance to every segment ``a[k] -> b[k]`` (p, k) and the nearest points (p, k, 3)."""
    ab = b - a
    length = np.einsum("ij,ij->i", ab, ab)
    rel = points[:, None, :] - a[None, :, :]
    s = np.clip(np.einsum("pkj,kj->pk", rel, ab) / np.where(length > 0, length, 1.0), 0.0, 1.0)
    near = a[None, :, :] + s[:, :, None] * ab[None, :, :]
    return np.linalg.norm(points[:, None, :] - near, axis=2), near


def near_segments(points: np.ndarray, starts: np.ndarray, ends: np.ndarray, chunk: int = 2048) -> np.ndarray:
    """Each point's distance to the nearest of the segments ``starts[k] -> ends[k]``, ``chunk`` points at a
    time (the points-by-segments table is never larger than that)."""
    found = np.empty(len(points))
    for at in range(0, len(points), chunk):
        found[at:at + chunk] = _nearest(points[at:at + chunk], starts, ends)[0].min(axis=1)
    return found


def spread_points(tri: np.ndarray, cap: int = 4000) -> np.ndarray:
    """About ``cap`` points spread over the triangles ``tri`` (k, 3, 3) by area: each triangle cut into a
    barycentric grid fine enough for its share, its vertices and every grid node."""
    edges = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    areas = 0.5 * np.linalg.norm(edges, axis=1)
    total = float(areas.sum())
    if total <= 0:
        return tri.reshape(-1, 3)
    spacing = math.sqrt(total / cap)
    found = []
    for t, area in zip(tri, areas):
        size = max(float(np.linalg.norm(t[1] - t[0])), float(np.linalg.norm(t[2] - t[0])),
                   float(np.linalg.norm(t[2] - t[1])))
        n = int(min(60, max(1, math.ceil(size / spacing))))
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1))
        keep = (i + j) <= n
        wa, wb = i[keep] / n, j[keep] / n
        found.append(t[0] + wa[:, None] * (t[1] - t[0]) + wb[:, None] * (t[2] - t[0]))
    return np.vstack(found)


def in_triangles_xy(tri: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """A test of which points lie, seen from above, within the triangles ``tri`` (k, 3, 3)."""
    a, b, c = tri[:, 0, :2], tri[:, 1, :2], tri[:, 2, :2]
    det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    good = np.abs(det) > 1e-300
    safe = np.where(good, det, 1.0)

    def test(points: np.ndarray) -> np.ndarray:
        x, y = points[:, None, 0], points[:, None, 1]
        l0 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / safe
        l1 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / safe
        l2 = 1.0 - l0 - l1
        eps = -1e-9
        return np.any(good & (l0 >= eps) & (l1 >= eps) & (l2 >= eps), axis=1)

    return test


def span(points: np.ndarray, a: np.ndarray, b: np.ndarray, inside: Callable[[np.ndarray], np.ndarray] | None = None,
         refine: float | None = None) -> dict[str, Any]:
    """The span of a flat overhang whose ``points`` (spread over it) are carried by the support segments
    ``a[k] -> b[k]`` (where walls below meet it): the farthest any point lies from a support, and whether
    that point lies among its supports -- within their convex hull, seen from above: a **bridge**, whose span
    is twice that distance, the gap between the walls -- or beyond them, to one side (a **cantilever**, whose
    reach is that distance). ``inside(points)``
    tells which refining points lie on the overhang; ``refine`` is the step around the farthest point."""
    if not len(a) or not len(points):
        return {"kind": "unsupported", "length_mm": None, "reach_mm": None,
                "xyz": points[0].tolist() if len(points) else None}
    chunks = [_nearest(points[i:i + 2000], a, b)[0].min(axis=1) for i in range(0, len(points), 2000)]
    d = np.concatenate(chunks)
    best = int(d.argmax())
    point, reach = points[best], float(d[best])
    if refine and inside is not None:
        # climb: a 5x5 grid round the best point, recentred while it improves, shrunk when it does not
        scale, rounds = float(refine), 0
        while scale > 1e-5 * float(refine) and rounds < 60:
            rounds += 1
            grid = np.linspace(-scale, scale, 5)
            du, dv = np.meshgrid(grid, grid)
            local = np.column_stack([point[0] + du.ravel(), point[1] + dv.ravel(), np.full(du.size, point[2])])
            local = local[inside(local)]
            better = False
            if len(local):
                dl = _nearest(local, a, b)[0].min(axis=1)
                if dl.max() > reach + 1e-12:
                    point, reach, better = local[int(dl.argmax())], float(dl.max()), True
            if not better:
                scale /= 4.0
    held = _within_hull(point[:2], np.vstack([a[:, :2], b[:, :2]]), tolerance=1e-6 + 1e-6 * reach)
    return {"kind": "bridge" if held else "cantilever", "length_mm": 2.0 * reach if held else reach,
            "reach_mm": reach, "xyz": point.tolist()}


def _turn(o: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))


def _hull(points: np.ndarray) -> np.ndarray:
    """The 2D convex hull of ``points``, counter-clockwise (Andrew's monotone chain)."""
    pts = np.unique(np.round(points, 9), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(sequence: np.ndarray) -> list[np.ndarray]:
        chain: list[np.ndarray] = []
        for p in sequence:
            while len(chain) >= 2 and _turn(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        return chain

    lower, upper = half(pts), half(pts[::-1])
    return np.array(lower[:-1] + upper[:-1])


def _within_hull(point: np.ndarray, supports: np.ndarray, tolerance: float) -> bool:
    """Whether ``point`` lies in (or on) the convex hull of the ``supports`` (2D): supports round it on every
    side, as walls round a bridge -- not all to one side, as the one wall of a cantilever."""
    hull = _hull(supports)
    if len(hull) < 3:
        return False
    edges = np.roll(hull, -1, axis=0) - hull
    rel = point[None, :] - hull
    cross = edges[:, 0] * rel[:, 1] - edges[:, 1] * rel[:, 0]
    scale = np.linalg.norm(edges, axis=1)
    return bool(np.all(cross >= -tolerance * np.maximum(scale, 1e-12)))


# --- the build volume -------------------------------------------------------------------------------------


def fit(box: np.ndarray, volume: np.ndarray) -> tuple[float, tuple[int, int, int]]:
    """The part's box in the build volume in the best of the axis orientations: the largest of its sides
    over the volume's (at most 1 fits), and which of the box's axes lies along the volume's X, Y and Z."""
    from itertools import permutations

    best = (math.inf, (0, 1, 2))
    for order in permutations(range(3)):
        ratio = max(float(box[order[k]]) / float(volume[k]) for k in range(3))
        best = min(best, (ratio, order))
    return best


def build_fit(lo: np.ndarray, hi: np.ndarray, machine: dict[str, Any]) -> dict[str, Any]:
    """The build-volume family of a part whose box is ``lo``..``hi`` in ``machine`` (``volume_mm``, ``origin``)."""
    volume = np.array(machine["volume_mm"], dtype=float)
    box = np.asarray(hi, dtype=float) - np.asarray(lo, dtype=float)
    ratio, order = fit(box, volume)
    placed = max(float(box[k]) / float(volume[k]) for k in range(3))
    return {"volume_mm": [float(v) for v in volume], "volume_origin": machine["origin"],
            "bbox_mm": [round(float(v), 4) for v in box], "fill_ratio": round(ratio, 4),
            "fits": bool(ratio <= 1.0 + 1e-9), "as_placed_fill_ratio": round(placed, 4),
            "best_axes": ",".join("xyz"[k] for k in order), "max_dimension_mm": round(float(box.max()), 4),
            "location": "build_volume", "xyz": [round(float(v), 4) for v in (np.asarray(lo) + np.asarray(hi)) / 2.0]}


def sections(grid: Grid, ceiling: float = 12.0) -> dict[str, Any]:
    """A voxel field's thickest section (the largest ball its material holds, to a voxel, up to ``ceiling``
    mm) and its cross-section layer by layer: the largest, its height above the grid's floor, the largest
    change between layers."""
    steps = int(min(48, math.ceil(ceiling / grid.pitch)))
    depth = inscribed(grid.material, steps)
    deepest = int(depth.max())
    found: dict[str, Any] = {"thickness_mm": None, "center": None, "at_least": False}
    if deepest > 0:
        at = np.unravel_index(int(depth.argmax()), depth.shape)
        found = {"thickness_mm": (2 * deepest + 1) * grid.pitch, "center": grid.center(np.array(at)),
                 "at_least": bool(deepest >= steps)}
    layer_area = grid.material.sum(axis=(0, 1)) * grid.pitch ** 2
    filled = np.flatnonzero(layer_area > 0)
    if len(filled):
        values = layer_area[filled]
        top = int(values.argmax())
        found.update(max_cross_section_mm2=float(values[top]),
                     max_cross_section_z=float(grid.origin[2] + (filled[top] + 0.5) * grid.pitch),
                     largest_section_change_mm2=float(np.abs(np.diff(values)).max()) if len(values) > 1 else 0.0)
    return found


def raster_pitch(size: np.ndarray) -> float:
    """The support raster's pitch for a part of box ``size``: 300 columns along its longer side, at most
    90 000 columns in all."""
    size = np.asarray(size, dtype=float)
    return float(max(size[:2].max() / 300.0, math.sqrt(max(size[0] * size[1], 1e-12) / 90000.0), 1e-3))


def field_pitch(size: np.ndarray, ball: float | None = None) -> tuple[float, float]:
    """The voxel pitch for a part of box ``size`` (at most about 1.5 million voxels, 200 along its longest
    side), and the cavity probe's ball radius (a fifth of its smallest side, 3 voxels to 6 mm)."""
    size = np.maximum(np.asarray(size, dtype=float), 1e-9)
    pitch = max(float(size.max()) / 200.0, float(np.prod(size) / 1.5e6) ** (1.0 / 3.0))
    radius = min(6.0, max(3.0 * pitch, 0.2 * float(size.min()))) if ball is None else ball
    return max(pitch, radius / 12.0), radius


# --- orientations -------------------------------------------------------------------------------------------


#: A sealed pocket of air under this many voxels is the voxelisation's, not the part's: a lone voxel the
#: surface closes off at an inner corner read as a cavity with no escape hole (an error in powder and resin).
POCKET_MIN_CELLS = 8


def rot_text(R: np.ndarray) -> str:
    """``R`` as the build123d rotation that makes it, pasteable: ``bd.Rot(x, y, z)`` (degrees; build123d's
    ``Rot(x, y, z)`` is Rx @ Ry @ Rz)."""
    R = np.asarray(R, dtype=float)
    b = math.asin(max(-1.0, min(1.0, float(R[0, 2]))))
    if abs(math.cos(b)) > 1e-9:
        a, c = math.atan2(-R[1, 2], R[2, 2]), math.atan2(-R[0, 1], R[0, 0])
    else:  # gimbal: fold the turn about z into x
        a, c = math.atan2(R[2, 1], R[1, 1]), 0.0
    values = [round(math.degrees(v), 3) + 0.0 for v in (a, b, c)]
    return "bd.Rot({:g}, {:g}, {:g})".format(*values)


def rotation(axis: str, degrees: float) -> np.ndarray:
    """A 3x3 rotation about ``x``, ``y`` or ``z``."""
    c, s = round(math.cos(math.radians(degrees)), 15), round(math.sin(math.radians(degrees)), 15)
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis].astype(float)


#: The six axis-aligned orientations, by the names the mesh check has always given them.
ROTATIONS: dict[str, np.ndarray] = {
    "current_plus_z": np.eye(3), "flip_180_x": rotation("x", 180), "rot_plus_90_x": rotation("x", 90),
    "rot_minus_90_x": rotation("x", -90), "rot_plus_90_y": rotation("y", 90), "rot_minus_90_y": rotation("y", -90),
}


def down_to(normal: np.ndarray) -> np.ndarray:
    """A rotation turning ``normal`` to -Z (a face laid on the plate)."""
    n = np.asarray(normal, dtype=float) / (np.linalg.norm(normal) or 1.0)
    target = np.array([0.0, 0.0, -1.0])
    v = np.cross(n, target)
    c = float(n @ target)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else rotation("x", 180)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def orientation_rows(V: np.ndarray, F: np.ndarray, candidates: dict[str, np.ndarray], angle_limit: float,
                     pitch: float, shallow_deg: float = 20.0, owners: np.ndarray | None = None,
                     cosmetic: set[int] | None = None) -> list[dict[str, Any]]:
    """Each candidate rotation's facts: support volume and contact area (and the contact on ``cosmetic``
    owners), build height, bed contact area, the down-facing area under ``angle_limit``, the area under
    ``shallow_deg`` from horizontal (not flat) that stair-steps, and the box."""
    rows = []
    for name, R in candidates.items():
        W = V @ R.T
        normals, areas = frame(W, F)
        z = W[F][:, :, 2]
        zmin = float(W[:, 2].min())
        tilt = angles(normals)
        on_plate = z.max(axis=1) <= zmin + 1e-3 * max(1.0, pitch)
        down = normals[:, 2] < -1e-9
        held = support(W, F, angle_limit, pitch, plate_z=zmin, owners=owners)
        on_cosmetic = sum(area for owner, area in held["per_owner_mm2"].items() if cosmetic and owner in cosmetic)
        box = W.max(axis=0) - W.min(axis=0)
        rows.append({"orientation": name, "rotation": np.round(R, 6).tolist(), "rotate": rot_text(R),
                     "support_volume_mm3": round(held["volume_mm3"], 2),
                     "support_contact_mm2": round(held["contact_area_mm2"], 2),
                     "support_contact_cosmetic_mm2": round(float(on_cosmetic), 2),
                     "build_height_mm": round(float(box[2]), 3),
                     "bed_contact_mm2": round(float(areas[down & on_plate & (tilt < 1.0)].sum()), 2),
                     "overhang_area_mm2": round(float(areas[down & ~on_plate & (tilt < angle_limit - ANGLE_EPS)].sum()), 2),
                     "stair_step_area_mm2": round(float(areas[(tilt > 0.5) & (tilt < shallow_deg)].sum()), 2),
                     "bbox_mm": [round(float(v), 3) for v in box]})
    return rows


#: How the orientations are ranked: each figure divided by the largest any candidate has (all zero: 0),
#: weighted and summed; the lowest score first. ``bed_contact_lack`` is one less the candidate's bed contact
#: over the largest. ``support`` for the processes that build supports (FDM, SLA, metal PBF), ``powder``
#: for those whose powder holds the part (SLS, MJF): their cost is the build's height.
WEIGHTS = {
    "support": {"support_volume_mm3": 0.30, "support_contact_mm2": 0.15, "support_contact_cosmetic_mm2": 0.10,
                "build_height_mm": 0.15, "overhang_area_mm2": 0.10, "stair_step_area_mm2": 0.10,
                "bed_contact_lack": 0.10},
    "powder": {"build_height_mm": 0.50, "stair_step_area_mm2": 0.30, "overhang_area_mm2": 0.20},
}


def ranked(rows: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    """``rows`` scored by ``weights`` (see ``WEIGHTS``) and sorted best first, each with ``score`` and ``rank``."""
    top = {key: max((float(row.get(key, 0.0)) for row in rows), default=0.0) for key in weights}
    most_bed = max((float(row["bed_contact_mm2"]) for row in rows), default=0.0)
    for row in rows:
        score = 0.0
        for key, weight in weights.items():
            if key == "bed_contact_lack":
                value = 1.0 - (row["bed_contact_mm2"] / most_bed if most_bed > 0 else 1.0)
            else:
                value = row[key] / top[key] if top[key] > 0 else 0.0
            score += weight * value
        row["score"] = round(float(score), 4)
    rows.sort(key=lambda row: (row["score"], row["build_height_mm"], row["orientation"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
