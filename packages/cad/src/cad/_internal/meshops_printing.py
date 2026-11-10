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
- ``Caster``: rays against the triangles in bounded memory (a linear bounding-volume hierarchy);
- ``cavities``: air wider than its way out -- sealed, or open through a throat narrower than the air behind
  it (a hollow part's drain holes), whatever the cavity's shape -- with each cavity's volume and openings;
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

from cad._internal.dfm import checkpoint

__all__ = ["ANGLE_EPS", "FOLD_DEG", "OVERHANG_AREA_MM2", "OVERHANG_REACH_MM", "KNIFE_DEG",
           "THIN_DEPTH_CAP_MM", "rot_text", "thin_depth", "Caster", "Cavity", "Crossings", "Grid", "SPREADS", "Smooth", "SEALED_EXACT", "TRAPPED_METHOD", "trapped_item", "ROTATIONS", "WEIGHTS", "angles", "ball_pad", "build_fit", "field_pitch", "fit", "in_triangles_xy", "inscribed", "raster_pitch", "sections", "smooth", "spread_points", "cavities", "crossings", "down_to",
           "frame", "near_segments", "nearest_segments", "past_segments", "orientation_rows", "ranked", "rotation", "span", "support",
           "voxels", "wall_support"]

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
#: The digits a figure a rule judges is kept to, both paths: a limit is compared with the measurement, never
#: with a figure rounded for display first (a 0.79996 mm wall is under 0.8 mm).
JUDGED = 9
#: Overhangs too small to need support (the owner's figures, both paths): a slope, ceiling or cantilever with
#: less than OVERHANG_AREA_MM2 under the angle limit, or a cantilever reaching less than the nozzle's width
#: (``--nozzle``, else OVERHANG_REACH_MM: one extrusion width lays it), is listed with ``counted`` false and
#: judged by no rule -- a 0.01 mm flat a chamfer leaves short of its corner is no overhang.
OVERHANG_AREA_MM2 = 1.0
OVERHANG_REACH_MM = 0.4


#: A convex crease under this many degrees of material is no knife edge: on a mesh it is a fold (two triangles
#: doubled back on each other) or a sliver of the tessellation, a defect of the triangles, and its thin depth
#: would reach anywhere (0.8 mm's at 0.1 deg is 458 mm; a 0.227 deg crease on a watertight shin wiped every
#: wall ray within 201 mm of it). Exact geometry has no folds: an edge this sharp is a sliver its walls read.
FOLD_DEG = 2.0
#: A knife's thin depth is at most this many mm: past it the sliver is a fin, which the walls measure (an edge of
#: 4.6 deg stays under FDM's 0.8 mm for 10 mm).
THIN_DEPTH_CAP_MM = 10.0


def thin_depth(minimum: float | None, angle_deg: float) -> float | None:
    """How far from an edge of material angle ``angle_deg`` the material stays thinner than ``minimum``: None
    under ``FOLD_DEG`` (no knife), at most ``THIN_DEPTH_CAP_MM``."""
    if minimum is None or not angle_deg >= FOLD_DEG:
        return None
    return min(float(minimum) / (2.0 * math.tan(math.radians(angle_deg) / 2.0)), THIN_DEPTH_CAP_MM)


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


#: The relative spacing of the numbers a mesh file holds (a binary STL's, a GLB's: 32-bit floats), four of
#: them to a triangle's normal: the floor of every angular tolerance (``Smooth.noise``), so one triangle alone
#: -- no neighbour to scatter against -- still reads a 45 deg face as 45 however the part is turned.
_COORDINATE_NOISE = 4.0 * 2.0 ** -23
#: An angle read off a triangle (its own normal's) stands within this many times the spread between that
#: reading and the same angle read off its corners' smoothed normals of the surface's own (``Smooth``). Measured
#: on cones of 20 to 60 deg, a sphere and a torus meshed at 0.05 to 0.5 rad of angular deflection against their
#: exact normals: the spread itself held 66 to 100 % of the triangles, twice it every one (but the poles of the
#: coarsest sphere). ``tests``: a 45 deg cone's every triangle reads 45 within its tolerance, fine and coarse.
SPREADS = 2.0


@dataclass
class Smooth:
    """The surface a mesh stands for, as the mesh itself knows it (``smooth``): at each corner of each
    triangle the surface's normal there -- the mean, by the angle each takes up at the corner, of the normals of
    the triangles round it that are the triangle's own surface -- and each triangle's ``noise``, degrees: what
    its coordinates' own spacing can turn its normal by (their size over its least height).

    A triangle is a chord of the surface: its normal turns from the surface's by about half the turn to its
    neighbours, so an angle read off it is the surface's only to within that. Every comparison of a triangle's
    angle with a limit reads the same angle off the corners' normals too, and takes ``SPREADS`` times the
    difference (and the noise) as the reading's tolerance (``within``): nothing on a plane, a degree on a
    cone's chords -- whose triangles read 44.3 to 45.4 deg where the cone is 45, every one of them at 45."""

    normals: np.ndarray     # (m, 3) each triangle's own
    corners: np.ndarray     # (m, 3, 3) the surface's at each of its corners
    noise: np.ndarray       # (m,) degrees

    def within(self, read: np.ndarray, smoothed: np.ndarray, triangles: Any) -> np.ndarray:
        """The tolerance, degrees, of the angles ``read`` off ``triangles``' own normals, given the same angles
        ``smoothed`` (read off their corners' normals; (n, k): the most of the k counts): see the class."""
        spread = np.abs(np.asarray(smoothed, dtype=float).reshape(len(read), -1) - np.asarray(read)[:, None]).max(axis=1)
        return SPREADS * spread + self.noise[triangles]

    def slopes(self, turned: np.ndarray | None = None) -> np.ndarray:
        """Each triangle's tolerance on its angle from horizontal (``angles``), the mesh turned by the rotation
        ``turned`` where given."""
        normals, corners = (self.normals, self.corners) if turned is None else \
            (self.normals @ turned.T, self.corners @ turned.T)
        return self.within(angles(normals), angles(corners), slice(None))

    def at(self, triangles: np.ndarray, points: np.ndarray, V: np.ndarray, F: np.ndarray) -> np.ndarray:
        """The surface's normal at ``points`` on ``triangles``: their corners' normals, weighed by where each
        point lies in its triangle."""
        tri = np.asarray(V, dtype=float)[np.asarray(F, dtype=int)[triangles]]
        e0, e1, rel = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0], np.asarray(points, dtype=float) - tri[:, 0]
        d00, d01, d11 = (np.einsum("ij,ij->i", e0, e0), np.einsum("ij,ij->i", e0, e1), np.einsum("ij,ij->i", e1, e1))
        d20, d21 = np.einsum("ij,ij->i", rel, e0), np.einsum("ij,ij->i", rel, e1)
        den = d00 * d11 - d01 * d01
        den = np.where(np.abs(den) > 1e-300, den, 1.0)
        b1 = np.clip((d11 * d20 - d01 * d21) / den, 0.0, 1.0)
        b2 = np.clip((d00 * d21 - d01 * d20) / den, 0.0, 1.0)
        weights = np.stack([np.clip(1.0 - b1 - b2, 0.0, 1.0), b1, b2], axis=1)
        mixed = np.einsum("ik,ikj->ij", weights, self.corners[triangles])
        return mixed / np.maximum(np.linalg.norm(mixed, axis=1, keepdims=True), 1e-300)


#: Triangles round one corner that its smoothed normal is read from, at most (a fan's hub has thousands, all
#: alike), and corner-triangle pairs weighed at once.
_SMOOTH_ROUND = 256
_SMOOTH_PAIRS = 2_000_000


def smooth(V: np.ndarray, F: np.ndarray, within_deg: float = 30.0) -> Smooth:
    """``Smooth`` of a mesh: each triangle's corners' normals the mean of the triangles round the corner whose
    own normals turn from the triangle's by under ``within_deg`` (its surface's, not an edge's other side, nor
    the next face round a mitre), each weighed by the angle it takes up at the corner -- so a surface cut into
    triangles either way reads the same."""
    V, F = np.asarray(V, dtype=float), np.asarray(F, dtype=int)
    tri = V[F]
    normals, areas = frame(V, F)
    if not len(tri):
        return Smooth(normals, np.zeros((0, 3, 3)), np.zeros(0))
    edges = [tri[:, (k + 1) % 3] - tri[:, k] for k in range(3)]
    lengths = [np.linalg.norm(edge, axis=1) for edge in edges]
    corner = np.empty((len(tri), 3))
    for k in range(3):
        cosine = np.einsum("ij,ij->i", edges[k], -edges[(k + 2) % 3]) / \
            np.maximum(lengths[k] * lengths[(k + 2) % 3], 1e-300)
        corner[:, k] = np.arccos(np.clip(cosine, -1.0, 1.0))
    # the triangles round each vertex, and the angle each takes up there
    flat = F.ravel()
    order = np.argsort(flat, kind="stable")
    first = np.searchsorted(flat[order], np.arange(len(V) + 1))
    round_face, round_angle = order // 3, corner.ravel()[order]
    count = np.diff(first)[flat]
    taken = np.minimum(count, _SMOOTH_ROUND)
    summed = np.zeros((len(flat), 3))
    alike = math.cos(math.radians(within_deg))
    ends = np.cumsum(taken)
    begin = 0
    while begin < len(flat):
        checkpoint()
        stop = max(begin + 1, int(np.searchsorted(ends, (ends[begin - 1] if begin else 0) + _SMOOTH_PAIRS)))
        rows = np.repeat(np.arange(begin, stop), taken[begin:stop])
        nth = np.arange(len(rows)) - np.repeat(ends[begin:stop] - taken[begin:stop] - (ends[begin - 1] if begin else 0),
                                               taken[begin:stop])
        # a corner of more triangles than are read: every (count / taken)-th of them
        pick = first[flat[rows]] + (nth * count[rows]) // taken[rows]
        other = round_face[pick]
        keep = np.einsum("ij,ij->i", normals[rows // 3], normals[other]) > alike
        weighed = normals[other[keep]] * round_angle[pick[keep]][:, None]
        for axis in range(3):
            summed[:, axis] += np.bincount(rows[keep], weights=weighed[:, axis], minlength=len(flat))
        begin = stop
    summed /= np.maximum(np.linalg.norm(summed, axis=1, keepdims=True), 1e-300)
    height = 2.0 * areas / np.maximum(np.maximum.reduce(lengths), 1e-300)
    noise = np.degrees(_COORDINATE_NOISE * float(np.abs(tri).max()) / np.maximum(height, 1e-300))
    return Smooth(normals, summed.reshape(-1, 3, 3), np.minimum(noise, 90.0))


# --- rays -------------------------------------------------------------------------------------------------


#: Triangles a leaf of ``Caster`` holds, and boxes a box of the level above.
_LEAF = 16
_FAN = 8
#: Ray-box and ray-triangle pairs tested at once: each block's tables are this many rows, about 100 MB at most,
#: however many triangles the mesh has and however many rays are cast.
RAY_PAIRS = 400_000


class Caster:
    """Rays against triangles, numpy alone, in bounded memory: the triangles in Morton order of their centres,
    every ``_LEAF`` of them in a box, every ``_FAN`` boxes in a box of the level above (a linear bounding-volume
    hierarchy, no pointers). A ray's slab test runs down the levels on the (ray, box) pairs still crossing, and
    the triangles of the leaves it crosses are intersected exactly (Moller-Trumbore, both faces), ``RAY_PAIRS``
    pairs at a time: a ray costs the triangles near its line, never the mesh."""

    def __init__(self, V: np.ndarray, F: np.ndarray) -> None:
        tri = np.asarray(V, dtype=float)[np.asarray(F, dtype=int)]
        centre = tri.mean(axis=1) if len(tri) else np.zeros((0, 3))
        lo = centre.min(axis=0) if len(tri) else np.zeros(3)
        size = float((centre.max(axis=0) - lo).max()) if len(tri) else 1.0
        cell = np.clip(((centre - lo) / (size or 1.0) * 1023.0).astype(np.int64), 0, 1023)
        key = np.zeros(len(tri), dtype=np.int64)
        for bit in range(10):
            for axis in range(3):
                key |= ((cell[:, axis] >> bit) & 1) << (3 * bit + axis)
        self.order = np.argsort(key, kind="stable")
        tri = tri[self.order]
        self.a = tri[:, 0]
        self.e1, self.e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        normal = np.cross(self.e1, self.e2)
        length = np.linalg.norm(normal, axis=1, keepdims=True)
        self.normals = np.divide(normal, length, out=np.zeros_like(normal), where=length > 0)
        self.count = len(tri)
        self._place: np.ndarray | None = None
        # the levels' boxes, leaves first; padded by a hair so a ray along a box's face is in it
        pad = 1e-9 * (float(np.abs(tri).max()) if len(tri) else 1.0) + 1e-12
        starts = np.arange(0, max(self.count, 1), _LEAF)
        lows = np.minimum.reduceat(tri.min(axis=1), starts) - pad if len(tri) else np.zeros((0, 3))
        highs = np.maximum.reduceat(tri.max(axis=1), starts) + pad if len(tri) else np.zeros((0, 3))
        self.levels = [(lows, highs)]
        while len(self.levels[-1][0]) > _FAN:
            lows, highs = self.levels[-1]
            starts = np.arange(0, len(lows), _FAN)
            self.levels.append((np.minimum.reduceat(lows, starts), np.maximum.reduceat(highs, starts)))

    def first(self, origins: np.ndarray, directions: np.ndarray, reach: float | None = None,
              ) -> tuple[np.ndarray, np.ndarray]:
        """Each ray's first crossing: its distance along the (unit) direction (inf where none within ``reach``)
        and the triangle crossed (its index in ``F``; -1 where none)."""
        origins = np.asarray(origins, dtype=float).reshape(-1, 3)
        directions = np.asarray(directions, dtype=float).reshape(-1, 3)
        found = np.full(len(origins), np.inf if reach is None else float(reach))
        which = np.full(len(origins), -1)
        if not self.count or not len(origins):
            return np.where(which >= 0, found, np.inf), which
        flat = np.abs(directions) <= 1e-300
        inverse = np.where(flat, np.inf, 1.0 / np.where(flat, 1.0, directions))
        top = len(self.levels[-1][0])
        block = max(1, RAY_PAIRS // (top * _FAN))
        for at in range(0, len(origins), block):
            checkpoint()
            rays = np.repeat(np.arange(at, min(at + block, len(origins))), top)
            nodes = np.tile(np.arange(top), len(rays) // top)
            for level in range(len(self.levels) - 1, -1, -1):
                rays, nodes = self._crossing(origins, inverse, found, rays, nodes, level)
                if level:
                    below = len(self.levels[level - 1][0])
                    nodes = (nodes[:, None] * _FAN + np.arange(_FAN)[None, :]).ravel()
                    rays = np.repeat(rays, _FAN)[nodes < below]
                    nodes = nodes[nodes < below]
            step = max(1, RAY_PAIRS // _LEAF)
            for begin in range(0, len(rays), step):
                r = np.repeat(rays[begin:begin + step], _LEAF)
                k = (nodes[begin:begin + step, None] * _LEAF + np.arange(_LEAF)[None, :]).ravel()
                r, k = r[k < self.count], k[k < self.count]
                t, hit = self._triangles(origins[r], directions[r], k)
                r, k, t = r[hit], k[hit], t[hit]
                if not len(r):
                    continue
                order = np.lexsort((t, r))
                r, k, t = r[order], k[order], t[order]
                head = np.ones(len(r), dtype=bool)
                head[1:] = r[1:] != r[:-1]
                r, k, t = r[head], k[head], t[head]
                nearer = t < found[r]
                found[r[nearer]] = t[nearer]
                which[r[nearer]] = self.order[k[nearer]]
        return np.where(which >= 0, found, np.inf), which

    def _crossing(self, origins: np.ndarray, inverse: np.ndarray, found: np.ndarray, rays: np.ndarray,
                  nodes: np.ndarray, level: int) -> tuple[np.ndarray, np.ndarray]:
        """The (ray, box) pairs of ``level`` whose ray crosses its box before its nearest crossing so far."""
        lows, highs = self.levels[level]
        if not len(rays):
            return rays, nodes
        kept_r, kept_n = [], []
        for begin in range(0, len(rays), RAY_PAIRS):
            r, n = rays[begin:begin + RAY_PAIRS], nodes[begin:begin + RAY_PAIRS]
            o, inv = origins[r], inverse[r]
            with np.errstate(invalid="ignore", over="ignore"):
                t1, t2 = (lows[n] - o) * inv, (highs[n] - o) * inv
            # a ray parallel to a slab is in it or never: its two times are -inf and inf, or the same infinity
            enter = np.nanmax(np.minimum(t1, t2), axis=1)
            leave = np.nanmin(np.maximum(t1, t2), axis=1)
            keep = (enter <= leave) & (leave >= 0.0) & (enter <= found[r])
            kept_r.append(r[keep])
            kept_n.append(n[keep])
        return np.concatenate(kept_r), np.concatenate(kept_n)

    def _triangles(self, o: np.ndarray, d: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Where each ray ``o + t d`` crosses its triangle ``k`` (Moller-Trumbore, either face): ``t``, and
        whether it does, ahead of the origin. A crossing on an edge counts for both its triangles, so no ray
        slips between two."""
        e1, e2 = self.e1[k], self.e2[k]
        p = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, p)
        scale = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1)
        good = np.abs(det) > 1e-12 * scale
        inv = 1.0 / np.where(good, det, 1.0)
        s = o - self.a[k]
        u = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1)
        v = np.einsum("ij,ij->i", d, q) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        eps = 1e-9
        return t, good & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps) & (t > 0.0)

    def normals_of(self, triangles: np.ndarray) -> np.ndarray:
        """The unit normals of ``triangles`` (their indices in ``F``, as ``first`` answers them)."""
        if self._place is None:
            self._place = np.empty(self.count, dtype=int)
            self._place[self.order] = np.arange(self.count)
        return self.normals[self._place[np.asarray(triangles, dtype=int)]]

    def inside(self, points: np.ndarray) -> np.ndarray:
        """Which points lie in the material of a closed, outward-wound mesh: a ray from each first leaves
        through the back of a triangle (one direction, off every axis, so few rays run along a face)."""
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        way = np.array([0.4395064455, 0.617598629942, 0.652231566745])
        _, hit = self.first(points, np.broadcast_to(way, points.shape))
        back = np.zeros(len(points), dtype=bool)
        met = hit >= 0
        back[met] = self.normals_of(hit[met]) @ way > 0.0
        return back


# --- a wall's support -------------------------------------------------------------------------------------


#: Directions a wall is walked in from its thinnest place (``wall_support``), every 22.5 degrees in its plane.
_WALL_FAN = 16
#: Stretches a walk follows a curved wall for, at most: round a tube in about forty.
_WALL_STEPS = 64
#: A wall has run into the part where the material across it is over this many times its own thickness.
_JOINED = 2.0


def wall_support(cast: Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]], point: np.ndarray,
                 normal: np.ndarray, thickness: float) -> dict[str, Any]:
    """Whether the wall of ``thickness`` under ``point`` (on its face, of outward ``normal``) is **supported**:
    joined to the part on two or more sides (the guides' word: Hubs, "connected to other structures on at least
    two sides"), read off the wall itself, the same on exact geometry and on a mesh. ``cast(origins,
    directions)`` answers each ray's distance to the surface from inside the material (inf where none) and the
    surface's outward normal there.

    From the middle of the wall under the point it is walked in ``_WALL_FAN`` directions in its own plane. Each
    walk ends where the wall does: **joined**, where the material across it grows past ``_JOINED`` times its
    thickness (it runs into a floor, a rib, the body: the place is kept); **free**, where it ends in a face
    across the way with the wall still thin (an edge in the air), or thins away to nothing; or it comes back to
    where it started (a **ring**: a tube's wall, joined all round). A curved wall is followed: where a walk
    leaves through the wall's own face it is put back in the middle and turned along the wall.

    Supported: a ring; two or more separate runs of joined directions (a web between two posts); or one run
    whose joins do not lie along one line (a floor and a side wall: round a corner; a skin over a cavity: all
    round). One run along one line is one side (a fin on its base), none is none: unsupported. A walk that
    reaches no end leaves an unsupported reading unknown (``supported`` None), never supported."""
    n0 = np.asarray(normal, dtype=float) / (np.linalg.norm(normal) or 1.0)
    t0 = float(thickness)
    seed = np.array([1.0, 0.0, 0.0]) if abs(n0[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n0, seed)
    u /= np.linalg.norm(u)
    v = np.cross(n0, u)
    turn = np.linspace(0.0, 2.0 * math.pi, _WALL_FAN, endpoint=False)
    d = np.cos(turn)[:, None] * u[None, :] + np.sin(turn)[:, None] * v[None, :]
    start = np.asarray(point, dtype=float) - n0 * t0 / 2.0
    m, n = np.tile(start, (_WALL_FAN, 1)), np.tile(n0, (_WALL_FAN, 1))
    WALKING, FREE, JOINED, RING, LOST = range(5)
    state = np.full(_WALL_FAN, WALKING)
    joins = np.full((_WALL_FAN, 3), np.nan)
    walked = np.zeros(_WALL_FAN)

    def across(points: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        up, face_up = cast(points, normals)
        down, face_down = cast(points, -normals)
        return up, down, face_up, face_down

    near, far = np.array([1 / 16, 1 / 8, 1 / 4, 1 / 2, 3 / 4]), np.array([1.0, 1 / 2, 1 / 4, 1 / 8, 1 / 16])
    for _step in range(_WALL_STEPS):
        active = np.flatnonzero(state == WALKING)
        if not len(active):
            break
        checkpoint()
        length, ahead = cast(m[active], d[active])
        state[active[~np.isfinite(length)]] = LOST
        keep = np.isfinite(length)
        active, length, ahead = active[keep], length[keep], ahead[keep]
        if not len(active):
            break
        # the material across the wall at places along the walk, the more of them near its end
        x = np.concatenate([length[:, None] * near[None, :], length[:, None] - t0 * far[None, :]], axis=1)
        x = np.sort(np.clip(x, length[:, None] * 1e-3, length[:, None] * (1.0 - 1e-3)), axis=1)
        places = m[active][:, None, :] + x[:, :, None] * d[active][:, None, :]
        up, down, _, _ = across(places.reshape(-1, 3), np.repeat(n[active], x.shape[1], axis=0))
        thick = ((up + down) > _JOINED * t0).reshape(x.shape)
        thick &= np.isfinite(up + down).reshape(x.shape)
        first = thick.argmax(axis=1)
        met = np.flatnonzero(thick.any(axis=1))
        if len(met):
            who = active[met]
            lo = np.where(first[met] > 0, x[met, np.maximum(first[met] - 1, 0)], 0.0)
            hi = x[met, first[met]]
            for _halving in range(6):
                middle = (lo + hi) / 2.0
                a, b, _, _ = across(m[who] + middle[:, None] * d[who], n[who])
                grown = ~np.isfinite(a + b) | ((a + b) > _JOINED * t0)
                lo, hi = np.where(grown, lo, middle), np.where(grown, middle, hi)
            joins[who] = m[who] + hi[:, None] * d[who]
            state[who] = JOINED
        rest = np.flatnonzero(~thick.any(axis=1))
        if not len(rest):
            continue
        # the face the walk left through: across the way (an end: the wall stops in the air), or the wall's own
        # (its normal the wall's: the wall curves away under the walk)
        ends = np.abs(np.einsum("ij,ij->i", ahead[rest], n[active[rest]])) < math.cos(math.radians(45.0))
        state[active[rest[ends]]] = FREE
        rest = rest[~ends]
        if not len(rest):
            continue
        # the walk left through the wall's own face: the wall curves. Back to its middle, turned along it
        who = active[rest]
        half = 0.5 * length[rest]
        at = m[who] + half[:, None] * d[who]
        a, b, face_a, face_b = across(at, n[who])
        found = np.isfinite(a + b)
        state[who[~found]] = LOST
        thinned = found & ((a + b) < 0.25 * t0)
        state[who[thinned]] = FREE
        go = found & ~thinned
        who, at, a, b, half = who[go], at[go], a[go], b[go], half[go]
        if not len(who):
            continue
        centre = at + n[who] * ((a - b) / 2.0)[:, None]
        turned = face_a[go] - face_b[go]
        turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-300)
        way = d[who] - np.einsum("ij,ij->i", d[who], turned)[:, None] * turned
        way /= np.maximum(np.linalg.norm(way, axis=1, keepdims=True), 1e-300)
        walked[who] += np.linalg.norm(centre - m[who], axis=1)
        m[who], n[who], d[who] = centre, turned, way
        reach = np.maximum(half, t0)
        state[who[(np.linalg.norm(centre - start, axis=1) < reach) & (walked[who] > 4.0 * reach)]] = RING
    state[state == WALKING] = LOST
    joined = state == JOINED
    # the runs of joined directions round the circle
    runs = int(np.count_nonzero(joined & ~np.roll(joined, 1))) if not joined.all() else 1
    supported: bool | None
    if (state == RING).any() or runs >= 2 or joined.all():
        supported = True
    elif runs == 1 and int(joined.sum()) >= 3:
        places = joins[joined] - joins[joined].mean(axis=0)
        _, _, axes = np.linalg.svd(places, full_matrices=False)
        along = places @ axes[0]
        off = np.linalg.norm(places - along[:, None] * axes[0][None, :], axis=1)
        # round a corner: the joins stand off their own line by a fifth of its length (a fin's on a round base
        # lie a few hundredths off)
        supported = bool(off.max() > max(0.2 * float(np.ptp(along)), 0.5 * t0))
    else:
        supported = False
    if supported is False and (state == LOST).any():
        supported = None
    # sides as the guides count them: none, one, or two and more (a run round a corner is two)
    return {"supported": supported, "joined_sides": 2 if supported else min(runs, 1),
            "joined_directions": int(joined.sum()), "free_directions": int((state == FREE).sum()),
            "unread_directions": int((state == LOST).sum()), "ring": bool((state == RING).any())}


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
            owners: np.ndarray | None = None, band: float | None = None,
            skip: np.ndarray | None = None) -> dict[str, Any]:
    """The support a part needs standing on the plate (its lowest point unless ``plate_z``), from a raster
    along Z at ``pitch``: under every crossing of a down-facing surface under ``angle_limit`` degrees from
    horizontal that has air below, a column down to the material below or the plate. Its volume, its
    contact with the part (the tops of the columns, and their feet where they stand on the part rather
    than the plate), and that contact per ``owners`` value (a face ordinal) of the triangles touched.
    ``band``: surfaces this close above the plate stand on it (default a fifth of the pitch). ``skip``: the
    triangles (a mask) that read under the limit and are at it -- a 45 deg cone's chords -- and need none."""
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
    if skip is not None:
        steep &= ~skip[tri]
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
        checkpoint()  # a sweep at a time: a maze of air takes many
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
        checkpoint()
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
        checkpoint()
        grown |= _near(grown, full=step % 2 == 0) & within
    return grown


def _flood(seed: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The cells of ``mask`` a ``seed`` cell reaches through it (6-connected). A few steps to the neighbours
    first (a flood that starts from the one before it, a voxel smaller, ends there); then the seeds spread along
    every run of the mask, axis after axis, until none grows."""
    grown = seed & mask
    count, whole = int(np.count_nonzero(grown)), int(np.count_nonzero(mask))
    if not count or count == whole:
        return grown
    for _step in range(8):
        grown = (grown | _near(grown, full=False)) & mask
        before, count = count, int(np.count_nonzero(grown))
        if count == before or count == whole:
            return grown
    runs = []
    for axis in (2, 1, 0):
        moved = np.ascontiguousarray(np.moveaxis(mask, axis, -1))
        starts = moved.copy()
        starts[..., 1:] &= ~moved[..., :-1]
        ids = np.cumsum(starts.ravel(), dtype=np.int32)  # each run of the mask along the axis, numbered from 1
        ids[~moved.ravel()] = 0
        runs.append((axis, ids, moved.shape))
    while True:
        checkpoint()  # a sweep at a time: a maze of air takes many
        before = count
        for axis, ids, shape in runs:
            cells = np.ascontiguousarray(np.moveaxis(grown, axis, -1)).ravel()
            reached = np.zeros(int(ids.max()) + 1, dtype=bool)
            reached[ids[cells]] = True
            reached[0] = False
            grown = np.moveaxis(reached[ids].reshape(shape), -1, axis)
        count = int(np.count_nonzero(grown))
        if count == before:
            return np.ascontiguousarray(grown)


def _box(mask: np.ndarray, margin: int = 0) -> tuple[slice, slice, slice]:
    """The slices of the box that holds ``mask``'s cells, ``margin`` cells wider each way (within the grid)."""
    found = []
    for axis in range(3):
        along = np.flatnonzero(mask.any(axis=tuple(k for k in range(3) if k != axis)))
        found.append(slice(max(int(along[0]) - margin, 0), min(int(along[-1]) + 1 + margin, mask.shape[axis])))
    return tuple(found)  # type: ignore[return-value]


@dataclass
class Cavity:
    """Air the outside reaches only through a way out narrower than the air itself, or not at all."""

    voxels: np.ndarray                  # flat indices of its voxels
    volume_mm3: float
    centroid: np.ndarray
    sealed: bool                        # no air path out at all at the grid's resolution
    openings: list[dict[str, Any]] = field(default_factory=list)  # {"diameter_mm", "uncertainty_mm", "exact", "xyz"}
    inscribed_mm: float = 0.0           # the largest ball it holds, to a voxel


#: Rays of the fan that reads a passage's cross-section (``_section``): the least of them reads the inscribed
#: circle of a slot to 1 / cos(pi / 32), half a percent.
_FAN_RAYS = 32
#: Two facets a throat's rays land on that turn by less than this are one curved wall's chords (a round hole's
#: polygon), whose sag the reading carries as its uncertainty; a sharper turn is the opening's own corner.
_CHORD_DEG = 45.0


def _section(caster: Caster, at: np.ndarray, way: np.ndarray, reach: float,
             ) -> tuple[np.ndarray, float, float, np.ndarray] | None:
    """The cross-section of a passage through ``at`` square to ``way``: a fan of rays in that plane reads the
    walls all round, the point moved to their middle (half the way between each pair of opposite walls, four
    times) -- its middle, the radius of the largest circle about it (the nearest wall), how far a round wall's
    chords (``_CHORD_DEG``) stand inside the circle they stand for, and the walls' normals where the rays
    landed. None where a ray meets no wall within ``reach``: the section is open, no passage's."""
    seed = np.array([1.0, 0.0, 0.0]) if abs(way[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(way, seed)
    u /= np.linalg.norm(u)
    v = np.cross(way, u)
    angles = np.linspace(0.0, 2.0 * math.pi, _FAN_RAYS, endpoint=False)
    fan = np.cos(angles)[:, None] * u[None, :] + np.sin(angles)[:, None] * v[None, :]
    centre = np.asarray(at, dtype=float)
    for _move in range(4):
        distance, hit = caster.first(np.broadcast_to(centre, fan.shape), fan, reach)
        if not np.isfinite(distance).all():
            return None
        shift = ((distance - np.roll(distance, _FAN_RAYS // 2)) / 2.0)[:, None] * fan
        centre = centre + shift.sum(axis=0) / (_FAN_RAYS / 2.0)
    distance, hit = caster.first(np.broadcast_to(centre, fan.shape), fan, reach)
    if not np.isfinite(distance).all():
        return None
    radius = float(distance.min())
    normals = caster.normals_of(hit)
    turn = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", normals, np.roll(normals, 1, axis=0)), -1.0, 1.0)))
    chord = turn[(turn > 1e-6) & (turn < _CHORD_DEG)]
    sag = radius * (1.0 / math.cos(math.radians(float(chord.max())) / 2.0) - 1.0) if len(chord) else 0.0
    return centre, radius, sag, normals


def _throat(caster: Caster, start: np.ndarray, inward: np.ndarray, pitch: float, ceiling: float,
            ) -> dict[str, Any] | None:
    """The narrowest cross-section of the passage that leaves a cavity at ``start`` (a point in its mouth)
    going ``inward`` (from the outside to the cavity): the largest ball that goes through. Stations half a
    voxel apart along it each read their section (``_section``; one wider than ``ceiling`` -- the widest the
    voxels allow -- is in the open, or in the cavity). ``inward`` is only the voxels' guess of the passage's
    line, and a section cut askew through a passage's end reads narrow, so each station takes the line from
    its own walls -- the direction their normals are all square to -- and reads its section square to that.
    The least is the throat: ``diameter_mm``, ``xyz`` and ``uncertainty_mm`` (its chords' sag, and the fan's
    own half a percent). None where no station reads a section."""
    way = inward / (np.linalg.norm(inward) or 1.0)
    at = np.asarray(start, dtype=float) - way * 2.0 * pitch
    best: dict[str, Any] | None = None
    opened = 0
    for _station in range(256):
        checkpoint()
        read = _section(caster, at, way, 4.0 * ceiling)
        if read is not None and read[1] <= ceiling:
            # the walls' own line: the direction their normals are all square to (the least of their spread)
            values, vectors = np.linalg.eigh(read[3].T @ read[3])
            if values[0] < 0.05 * values[1]:
                line = vectors[:, 0] * (1.0 if float(vectors[:, 0] @ way) >= 0.0 else -1.0)
                if float(line @ way) < 1.0 - 1e-9:
                    again = _section(caster, read[0], line, 4.0 * ceiling)
                    if again is not None and again[1] <= ceiling:
                        way, read = line, again
        if read is not None and read[1] <= ceiling:
            opened = 0
            if best is None or 2.0 * read[1] < best["diameter_mm"]:
                best = {"diameter_mm": 2.0 * read[1], "xyz": read[0], "exact": True,
                        "uncertainty_mm": 2.0 * read[2] + 0.01 * read[1]}
            if np.linalg.norm(read[0] - at) < pitch:
                at = read[0]  # the passage's own middle: its bends are followed
        else:
            opened += 1
            if best is not None and opened >= 4:
                break  # through the throat and out into the cavity
        ahead, _ = caster.first(at[None], way[None], pitch)
        if np.isfinite(ahead[0]) and ahead[0] < 0.5 * pitch:
            break  # a wall ahead: the passage ends or turns
        at = at + way * 0.5 * pitch
    return best


def cavities(grid: Grid, ball_radius: float, cap: int = 32, caster: Caster | None = None,
             ) -> tuple[list[Cavity], np.ndarray]:
    """The cavities of ``grid``, and a label per voxel (flat): -2 material, -1 air that is no cavity, ``k``
    cavity ``k``.

    A cavity is air that is wider than its way out: a region holding a ball that cannot leave. For every
    radius ``r`` up to ``ball_radius`` (a voxel at a time), the air a ball of ``r`` fits in is flooded from the
    grid's border; what it fits in and the flood does not reach is enclosed at ``r``, and is a cavity where it
    holds a ball two voxels larger still (the field's resolution: a slot whose voxels read a voxel wider here
    than there is no cavity). Its extent is the air the outside's ball of ``r`` cannot touch, joined to it; it
    is found at the least ``r`` that encloses it, so its way out -- its widest -- is known to a voxel whatever
    the cavity's shape: a flat hollow 10 mm high behind a 2 mm vent is a cavity as a hollow sphere is. Air the
    largest ball leaves by (an opening over ``2 ball_radius`` wide) is a pocket's mouth, no cavity. A cavity
    no ball of any size leaves is ``sealed`` at the grid's resolution.

    Each opening is where the cavity's air meets the outside's; with a ``caster`` (the triangles' rays) its
    throat is measured on the triangles (``_throat``: ``exact``, with its chords' ``uncertainty_mm``), else read
    off the voxels to a voxel. The grid's padding must hold the ball: ``voxels(..., pad=ball_pad(ball_radius,
    pitch))``."""
    shape = grid.shape
    air = ~(grid.material | grid.surface)
    border = np.zeros(shape, dtype=bool)
    border[[0, -1], :, :] = True
    border[:, [0, -1], :] = True
    border[:, :, [0, -1]] = True
    top = max(1, int(round(ball_radius / grid.pitch)))
    depth = _depth(air, top + 2)  # 0: beside a wall; d: a ball of d voxels fits
    # the outside at each radius, the widest first: each flood starts from the one before
    reached: dict[int, np.ndarray] = {}
    last = np.zeros(shape, dtype=bool)
    for level in range(top, -1, -1):
        fits = depth >= level if level else air
        last = _flood(last | (border & fits), fits)
        reached[level] = last
    labels = np.full(shape, -1, dtype=np.int32)
    labels[~air] = -2
    everywhere = np.ones(shape, dtype=bool)
    found: list[Cavity] = []
    for level in range(top + 1):
        fits = (depth >= level if level else air) & (labels == -1)
        cores = fits & ~reached[level]
        if not cores.any() or len(found) >= cap:
            continue
        # the outside as its ball of this radius touches it: grown without regard to walls, a voxel past the
        # ball (into the surface's own voxels, never through them), so it stops at an opening the ball does not fit
        outside = (_dilate(reached[level], everywhere, level + 1) & air) if level else reached[0]
        room = air & ~outside & (labels == -1)
        joined = _flood(cores, room)
        box = _box(joined, 1)
        pieces = components(joined[box])
        for piece in np.unique(pieces[cores[box]]):
            region = np.zeros(shape, dtype=bool)
            region[box] = pieces == piece
            deepest = int(depth[region].max())
            if deepest < level + 1 or len(found) >= cap:
                continue  # no wider than its way out, to the field's resolution
            cells = np.flatnonzero(region)
            ijk = np.stack(np.unravel_index(cells, shape), axis=1)
            # the surface's own voxels round it are half air: counted so, the volume is the cavity's
            skin = int(np.count_nonzero(_near(region[box], full=False) & grid.surface[box]))
            cavity = Cavity(cells, float((len(cells) + 0.5 * skin) * grid.pitch ** 3), grid.center(ijk.mean(axis=0)),
                            sealed=level == 0, inscribed_mm=float((2 * deepest + 1) * grid.pitch))
            if level:
                wide = _box(region, 5)
                origin = np.array([part.start for part in wide])
                cavity.openings = _openings(grid, region[wide], outside[wide], origin, level, caster)
            labels[region] = len(found)
            found.append(cavity)
    return found, labels.ravel()


def _openings(grid: Grid, region: np.ndarray, outside: np.ndarray, origin: np.ndarray, level: int,
              caster: Caster | None) -> list[dict[str, Any]]:
    """The openings of a cavity enclosed at ``level`` (``region`` and the ``outside``, both cut to the box of
    the grid that starts at voxel ``origin``): each patch of its air that touches the outside's, with the
    throat behind it (``_throat``), or the voxels' reading of it -- about ``2 level`` voxels wide, to two voxels
    -- where no ray reads one."""
    mouths = region & _near(outside, full=True)
    if not mouths.any():
        return []
    patches = components(_near(mouths, full=True) & (region | outside))
    ceiling = (level + 1.5) * grid.pitch
    found = []
    for patch in np.unique(patches[mouths]):
        here = (patches == patch) & mouths
        cells = np.stack(np.nonzero(here), axis=1)
        near = _dilate(here, np.ones(here.shape, dtype=bool), 3)
        inner, outer = np.stack(np.nonzero(near & region), axis=1), np.stack(np.nonzero(near & outside), axis=1)
        middle = cells[np.argmin(np.linalg.norm(cells - cells.mean(axis=0), axis=1))]
        opening = {"diameter_mm": float(2 * level * grid.pitch), "uncertainty_mm": float(2.0 * grid.pitch),
                   "exact": False, "xyz": grid.center(origin + cells.mean(axis=0))}
        way = inner.mean(axis=0) - outer.mean(axis=0) if len(inner) and len(outer) else np.zeros(3)
        if caster is not None and np.linalg.norm(way) > 1e-9:
            measured = _throat(caster, grid.center(origin + middle), way, grid.pitch, ceiling)
            if measured is not None:
                opening = measured
        found.append(opening)
    return found


#: How both paths say they found the trapped volumes.
TRAPPED_METHOD = ("sealed voids exactly, from their own shells; from a voxel field, air wider than its way out "
                  "(a ball fits in it that cannot leave), whatever its shape; each opening's throat measured on "
                  "the surface (exact: true), or read off the voxels to two voxels")
#: What a sealed void read from its own shell says of its openings: none.
SEALED_EXACT = {"sealed": True, "exact": True, "escape_holes": 0, "escape_hole_diameters_mm": [],
                "min_escape_hole_mm": None, "escape_hole_uncertainty_mm": None}


def trapped_item(cavity: Cavity, pitch: float, diameters: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    """A voxel cavity as both paths list it: its place, volume and openings -- ``diameters`` (each with its
    uncertainty) where the caller read them (exact geometry's holes), else the cavity's own. A cavity the voxels
    read sealed that is no sealed void's shell (the caller replaces those) has a way out under a voxel wide:
    one opening of at most ``pitch`` (``escape_hole_at_most``), never no opening."""
    found = sorted(diameters if diameters is not None else
                   [(float(opening["diameter_mm"]), float(opening["uncertainty_mm"])) for opening in cavity.openings])
    item = {"xyz": cavity.centroid, "volume_mm3": round(float(cavity.volume_mm3), 2), "sealed": False,
            "exact": False, "escape_holes": len(found),
            "escape_hole_diameters_mm": [round(d, 4) for d, _ in found],
            "min_escape_hole_mm": round(found[0][0], JUDGED) if found else None,
            "escape_hole_uncertainty_mm": round(found[0][1], 4) if found else None,
            "inscribed_mm": round(float(cavity.inscribed_mm), 3)}
    if cavity.sealed and not found:
        item.update(escape_holes=1, escape_hole_diameters_mm=[round(float(pitch), 4)],
                    min_escape_hole_mm=round(float(pitch), JUDGED), escape_hole_uncertainty_mm=0.0,
                    escape_hole_at_most=True)
    return item


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
    return nearest_segments(points, starts, ends, chunk)[0]


def past_segments(points: np.ndarray, starts: np.ndarray, ends: np.ndarray, margins: np.ndarray,
                  chunk: int = 2048) -> np.ndarray:
    """Each point's least distance past a segment's own margin: ``min_k |p - segment k| - margins[k]`` (a point
    within some segment's margin reads 0 or less), ``chunk`` points at a time."""
    found = np.empty(len(points))
    for at in range(0, len(points), chunk):
        found[at:at + chunk] = (_nearest(points[at:at + chunk], starts, ends)[0] - margins[None, :]).min(axis=1)
    return found


def nearest_segments(points: np.ndarray, starts: np.ndarray, ends: np.ndarray,
                     chunk: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """Each point's distance to the nearest of the segments ``starts[k] -> ends[k]`` and that segment's ``k``,
    ``chunk`` points at a time."""
    found, which = np.empty(len(points)), np.zeros(len(points), dtype=int)
    for at in range(0, len(points), chunk):
        table = _nearest(points[at:at + chunk], starts, ends)[0]
        which[at:at + chunk] = table.argmin(axis=1)
        found[at:at + chunk] = table[np.arange(len(table)), which[at:at + chunk]]
    return found, which


def spread_points(tri: np.ndarray, cap: int = 4000) -> np.ndarray:
    """About ``cap`` points spread over the triangles ``tri`` (k, 3, 3) by area: each triangle's corners and a
    grid across it about the spacing the cap gives -- rows from the corner opposite its shortest side to that
    side, each row as many points across as its width needs (at most 60 rows, 60 a row). A sliver (a long thin
    facet of a strut) is laid out along its length alone: a square grid by its longest side put 1891 points on
    each, 183000 on a 97-triangle region of a lattice."""
    edges = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    areas = 0.5 * np.linalg.norm(edges, axis=1)
    total = float(areas.sum())
    if total <= 0:
        return tri.reshape(-1, 3)
    spacing = math.sqrt(total / cap)
    tri = np.array(tri, dtype=float)  # a plain array: a mesh's tracked one costs a hash a slice
    sides = np.stack([np.linalg.norm(tri[:, (k + 2) % 3] - tri[:, (k + 1) % 3], axis=1) for k in range(3)], axis=1)
    apex = np.argmin(sides, axis=1)  # side k is opposite corner k
    at = np.arange(len(tri))
    a, b, c = tri[at, apex], tri[at, (apex + 1) % 3], tri[at, (apex + 2) % 3]
    rows = np.clip(np.ceil(sides.max(axis=1) / spacing), 1, 60).astype(int)
    across = sides[at, apex]
    # every row of every triangle: its triangle and its place s from the apex (0) to the shortest side (1)
    owner = np.repeat(at, rows + 1)
    start = np.cumsum(rows + 1) - (rows + 1)
    s = (np.arange(len(owner)) - start[owner]) / rows[owner]
    count = np.where(s > 0, np.clip(np.ceil(s * across[owner] / spacing), 1, 60), 0).astype(int)
    # every point of every row: its row and its place w across it
    row = np.repeat(np.arange(len(owner)), count + 1)
    first = np.cumsum(count + 1) - (count + 1)
    w = np.where(count[row] > 0, (np.arange(len(row)) - first[row]) / np.maximum(count[row], 1), 0.0)[:, None]
    k, sr = owner[row], s[row][:, None]
    return a[k] + sr * ((1.0 - w) * (b[k] - a[k]) + w * (c[k] - a[k]))


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


#: Point-segment pairs a block of ``_least_distances`` holds at once: about 16 MB a table.
PAIRS_PER_BLOCK = 2_000_000


def _segment_distances(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The (points, segments) table of distances from each point to each segment ``a[k] -> b[k]`` (as
    ``_least_distances`` reads them: for a few points)."""
    points, a, b = (np.asarray(x, dtype=float).reshape(-1, 3) for x in (points, a, b))
    centre = points.mean(axis=0)
    P, A, E = points - centre, a - centre, b - a
    ee = np.einsum("ij,ij->i", E, E)
    pe = P @ E.T - np.einsum("ij,ij->i", A, E)[None, :]
    t = np.clip(pe / np.where(ee > 0, ee, 1.0)[None, :], 0.0, 1.0)
    rr = np.einsum("ij,ij->i", P, P)[:, None] - 2.0 * (P @ A.T) + np.einsum("ij,ij->i", A, A)[None, :]
    return np.sqrt(np.maximum(rr - 2.0 * t * pe + t * t * ee[None, :], 0.0))


def _least_distances(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Each point's distance to the nearest of the segments ``a[k] -> b[k]``, from matrix products in blocks of
    ``PAIRS_PER_BLOCK`` pairs -- no (points, segments, 3) table: a lattice's overhang of 3000 points over
    twenty thousand supporting edges took 121 s and 6 GB that way. Centred on the points first, so the products
    keep their digits wherever the part stands."""
    points, a, b = (np.asarray(x, dtype=float).reshape(-1, 3) for x in (points, a, b))
    centre = points.mean(axis=0)
    P, A = points - centre, a - centre
    E = b - a
    ee = np.einsum("ij,ij->i", E, E)
    safe = np.where(ee > 0, ee, 1.0)
    ae, aa = np.einsum("ij,ij->i", A, E), np.einsum("ij,ij->i", A, A)
    found = np.empty(len(P))
    step = max(1, PAIRS_PER_BLOCK // max(1, len(A)))
    for at in range(0, len(P), step):
        block = P[at:at + step]
        pe = block @ E.T - ae[None, :]            # (p - a) . e
        t = np.clip(pe / safe[None, :], 0.0, 1.0)
        rr = np.einsum("ij,ij->i", block, block)[:, None] - 2.0 * (block @ A.T) + aa[None, :]   # |p - a|^2
        d2 = rr - 2.0 * t * pe + t * t * ee[None, :]
        found[at:at + step] = np.sqrt(np.maximum(d2.min(axis=1), 0.0))
    return found


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
    d = _least_distances(points, a, b)
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
                # only a support within the reach plus twice the grid's half-diagonal of the point can be any
                # grid point's nearest: the others are left out, the answer the same
                near = _segment_distances(point[None], a, b)[0] <= reach + 2.0 * math.sqrt(2.0) * scale * (1 + 1e-9)
                dl = _least_distances(local, a[near], b[near]) if near.any() else _least_distances(local, a, b)
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
    """The build-volume family of a part whose box is ``lo``..``hi`` in ``machine`` (``volume_mm``, ``origin``;
    ``largest_mm`` where the volume is a typical machine assumed: the largest of the technology's, and whether
    the part fits that in some axis orientation)."""
    volume = np.array(machine["volume_mm"], dtype=float)
    box = np.asarray(hi, dtype=float) - np.asarray(lo, dtype=float)
    ratio, order = fit(box, volume)
    placed = max(float(box[k]) / float(volume[k]) for k in range(3))
    largest: dict[str, Any] = {"largest_volume_mm": None, "largest_fill_ratio": None, "fits_largest": None}
    if machine.get("largest_mm"):
        most = fit(box, np.array(machine["largest_mm"], dtype=float))[0]
        largest = {"largest_volume_mm": [float(v) for v in machine["largest_mm"]],
                   "largest_fill_ratio": round(most, JUDGED), "fits_largest": bool(most <= 1.0 + 1e-9)}
    return {**largest, "volume_mm": [float(v) for v in volume], "volume_origin": machine["origin"],
            "bbox_mm": [round(float(v), 4) for v in box], "fill_ratio": round(ratio, JUDGED),
            "fits": bool(ratio <= 1.0 + 1e-9), "as_placed_fill_ratio": round(placed, 4),
            "best_axes": ",".join("xyz"[k] for k in order), "max_dimension_mm": round(float(box.max()), JUDGED),
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
                     cosmetic: set[int] | None = None,
                     at_limit: Callable[[np.ndarray], np.ndarray] | None = None) -> list[dict[str, Any]]:
    """Each candidate rotation's facts: support volume and contact area (and the contact on ``cosmetic``
    owners), build height, bed contact area, the down-facing area under ``angle_limit``, the area under
    ``shallow_deg`` from horizontal (not flat) that stair-steps, and the box. ``at_limit(R)``: the triangles
    (a mask) that, turned by ``R``, read under the limit and are at it (``support``'s ``skip``)."""
    rows = []
    for name, R in candidates.items():
        W = V @ R.T
        normals, areas = frame(W, F)
        z = W[F][:, :, 2]
        zmin = float(W[:, 2].min())
        tilt = angles(normals)
        on_plate = z.max(axis=1) <= zmin + 1e-3 * max(1.0, pitch)
        down = normals[:, 2] < -1e-9
        skip = at_limit(R) if at_limit is not None else None
        held = support(W, F, angle_limit, pitch, plate_z=zmin, owners=owners, skip=skip)
        under = (tilt < angle_limit - ANGLE_EPS) & (~skip if skip is not None else True)
        on_cosmetic = sum(area for owner, area in held["per_owner_mm2"].items() if cosmetic and owner in cosmetic)
        box = W.max(axis=0) - W.min(axis=0)
        rows.append({"orientation": name, "rotation": np.round(R, 6).tolist(), "rotate": rot_text(R),
                     "support_volume_mm3": round(held["volume_mm3"], 2),
                     "support_contact_mm2": round(held["contact_area_mm2"], 2),
                     "support_contact_cosmetic_mm2": round(float(on_cosmetic), 2),
                     "build_height_mm": round(float(box[2]), 3),
                     "bed_contact_mm2": round(float(areas[down & on_plate & (tilt < 1.0)].sum()), 2),
                     "overhang_area_mm2": round(float(areas[down & ~on_plate & under].sum()), 2),
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
