"""Injection molding's geometry that exact and mesh measurements share, numpy alone.

Both integrations measure a part along one pull: the build123d one on its B-rep (``cad.build123d._dfm_molding``,
points sampled on the faces and exact rays), the trimesh one on a mesh (``cad.trimesh._molding``, triangle
centres and the mesh's rays). What they do with those points is the same and lives here, so an STL and the
STEP it came from answer from one algorithm:

- ``basis``, ``direction_name``, ``lateral_directions``: the parting plane's axes and a direction's name;
- ``raster``, ``near_outline``: a projection's covered cells, its outline and its area;
- ``ball_thickness``: the wall under each point, the diameter of the largest ball touching the surface
  there (the rolling-ball thickness), never more than the ray straight through;
- ``weighted_median``, ``weighted_quantile``, ``transitions``: the nominal wall and abrupt changes of it;
- ``classify_undercut``: what releases a trapped feature -- side actions (how many, which way, how far),
  a lifter, a collapsible core, or nothing -- from rays the caller casts;
- ``parting``: whether one flat parting plane takes the part's outline, and at what height.

A ``cast(origins, directions)`` is the caller's: the distance to the first surface each ray meets, ``inf``
where it meets none.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

__all__ = ["ball_thickness", "basis", "classify_undercut", "direction_name", "even_points", "lateral_directions",
           "near_outline", "nearest_broad", "parting", "pull_vector", "raster", "transitions", "weighted_median", "weighted_quantile"]

Cast = Callable[[np.ndarray, np.ndarray], np.ndarray]

#: The projection's raster: this many cells across the part's longer span, so a part in metres and a
#: 2 m panel each get a grid sized to them.
RASTER_CELLS_ACROSS = 2000
#: A feature's points tested for its release, at most (evenly chosen): the rays scale with them.
RELEASE_POINTS = 96


_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def pull_vector(spec: str) -> np.ndarray:
    """``z``, ``+z``, ``-y``, or ``x,y,z`` components, normalised. A leading sign belongs to an axis NAME
    only: ``-1,0,1`` is a vector whose first component is negative, not the negation of ``1,0,1``."""
    text = (spec or "").strip().lower()
    if not text:
        raise ValueError("pull is empty; give an axis name (z, -y) or three comma-separated components")
    named = text[1:] if text[:1] in "+-" else text
    if named in _AXES:
        vec = np.array(_AXES[named], dtype=float) * (-1.0 if text[:1] == "-" else 1.0)
    else:
        try:
            parts = [float(v) for v in text.split(",")]
        except ValueError as exc:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}") from exc
        if len(parts) != 3:
            raise ValueError(f"pull must be an axis name or three comma-separated components, got {spec!r}")
        vec = np.array(parts, dtype=float)
    norm = float(np.linalg.norm(vec))
    if not np.isfinite(norm) or norm == 0.0:
        raise ValueError("pull vector has zero length")
    return vec / norm + 0.0  # + 0.0 so a negated axis prints 0.0, not -0.0


def basis(pull: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two unit axes spanning the plane square to ``pull`` (the parting plane's), right-handed with it. For a
    world-axis pull they are world axes (z: x, y; y: z, x; x: y, z), so a side action reads ``+x``."""
    p = np.asarray(pull, dtype=float)
    p = p / np.linalg.norm(p)
    axis = int(np.argmax(np.abs(p)))
    helper = np.zeros(3)
    helper[(axis + 1) % 3] = 1.0
    u = helper - p * float(helper @ p)
    u /= np.linalg.norm(u)
    v = np.cross(p, u)
    return u, v / np.linalg.norm(v)


def direction_name(vector: Sequence[float], tolerance_deg: float = 0.5) -> str:
    """``+x``, ``-z`` for a world axis (to within ``tolerance_deg``), else ``x,y,z`` components."""
    d = np.asarray(vector, dtype=float)
    d = d / (np.linalg.norm(d) or 1.0)
    axis = int(np.argmax(np.abs(d)))
    if abs(d[axis]) >= math.cos(math.radians(tolerance_deg)):
        return ("+" if d[axis] > 0 else "-") + "xyz"[axis]
    return ",".join(f"{value + 0.0:.3f}" for value in d)


def lateral_directions(pull: np.ndarray, count: int = 8) -> np.ndarray:
    """``count`` unit directions in the parting plane, evenly round from its first axis."""
    u, v = basis(pull)
    angles = np.arange(count) * (2.0 * math.pi / count)
    return np.cos(angles)[:, None] * u[None, :] + np.sin(angles)[:, None] * v[None, :]


# --- projection ------------------------------------------------------------------------------------------


def raster(points: np.ndarray, triangles: np.ndarray, cells_across: int = RASTER_CELLS_ACROSS,
           row_cells: int = 250_000) -> dict[str, Any]:
    """The cells 2D triangles cover: ``grid`` (rows, cols), ``origin`` (its lower corner), ``cell`` (a cell's
    side), ``area`` (covered cells times a cell's area), ``outline`` (covered cells with an uncovered
    neighbour) and ``area_error`` (half the outline's cells: a cell counts when its centre lies in a
    triangle, so the area is good to about half a cell all round the outline)."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    tri = np.asarray(triangles, dtype=int).reshape(-1, 3)
    if not len(pts) or not len(tri):
        empty = np.zeros((1, 1), dtype=bool)
        return {"grid": empty, "origin": np.zeros(2), "cell": 1.0, "area": 0.0, "outline": empty, "area_error": 0.0}
    span = pts.max(axis=0) - pts.min(axis=0)
    cell = float(max(span.max(), 1e-9)) / cells_across
    lo = pts.min(axis=0) - 2 * cell
    hi = pts.max(axis=0) + 2 * cell
    size = np.maximum(np.ceil((hi - lo) / cell).astype(int), 1)
    grid = np.zeros((size[1], size[0]), dtype=bool)
    corners = (pts[tri] - lo) / cell
    for a, b, c in corners:
        x0 = max(0, int(np.floor(min(a[0], b[0], c[0]))))
        x1 = min(size[0] - 1, int(np.ceil(max(a[0], b[0], c[0]))))
        y0 = max(0, int(np.floor(min(a[1], b[1], c[1]))))
        y1 = min(size[1] - 1, int(np.ceil(max(a[1], b[1], c[1]))))
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12 or x1 < x0 or y1 < y0:
            continue
        width = x1 - x0 + 1
        xx = (np.arange(x0, x1 + 1, dtype=np.float64) + 0.5)[None, :]
        band = max(1, int(row_cells // width))
        for r0 in range(y0, y1 + 1, band):
            r1 = min(y1, r0 + band - 1)
            yy = (np.arange(r0, r1 + 1, dtype=np.float64) + 0.5)[:, None]
            w0 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / den
            w1 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / den
            grid[r0:r1 + 1, x0:x1 + 1] |= (w0 >= -1e-9) & (w1 >= -1e-9) & ((w0 + w1) <= 1 + 1e-9)
    padded = np.pad(grid, 1)
    inner = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    outline = grid & ~inner
    return {"grid": grid, "origin": lo, "cell": cell, "area": float(grid.sum()) * cell * cell,
            "outline": outline, "area_error": 0.5 * float(outline.sum()) * cell * cell}


def near_outline(projection: dict[str, Any], points: np.ndarray, band_cells: float = 3.0) -> np.ndarray:
    """Whether each 2D point lies within ``band_cells`` cells of the projection's outline."""
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    if not len(pts):
        return np.zeros(0, dtype=bool)
    outline = projection["outline"]
    rows, cols = np.nonzero(outline)
    if not len(rows):
        return np.zeros(len(pts), dtype=bool)
    height, width = outline.shape
    key = ("_dilated", float(band_cells))
    dilated = projection.get(key)
    if dilated is None:
        reach = int(math.ceil(band_cells))
        dilated = np.zeros_like(outline)
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                if dx * dx + dy * dy > band_cells * band_cells:
                    continue
                dilated[np.clip(rows + dy, 0, height - 1), np.clip(cols + dx, 0, width - 1)] = True
        projection[key] = dilated
    index = np.floor((pts - projection["origin"]) / projection["cell"]).astype(int)
    inside = (index[:, 0] >= 0) & (index[:, 0] < width) & (index[:, 1] >= 0) & (index[:, 1] < height)
    found = np.zeros(len(pts), dtype=bool)
    found[inside] = dilated[index[inside, 1], index[inside, 0]]
    return found


# --- wall thickness --------------------------------------------------------------------------------------


#: The surface points a first, loose bound on the ball is taken from, at most (evenly chosen).
BOUND_POINTS = 12000


def _point_bound(p: np.ndarray, n: np.ndarray, q: np.ndarray, radius: np.ndarray, floor: float,
                 chunk: int = 64) -> np.ndarray:
    """The ball radius each point allows against the surface points ``q`` alone: an upper bound on the
    exact one (a subset of the surface can only hold a ball less tightly)."""
    radius = radius.copy()
    if not len(q) or not len(p):
        return radius  # nothing else on the surface (a part of one closed face): the ray alone bounds it
    q = q[_subset(len(q), BOUND_POINTS)]
    for start in range(0, len(p), chunk):
        stop = min(len(p), start + chunk)
        d = q[None, :, :] - p[start:stop, None, :]
        depth = -np.einsum("cmk,ck->cm", d, n[start:stop])
        square = np.einsum("cmk,cmk->cm", d, d)
        with np.errstate(divide="ignore", invalid="ignore"):
            candidate = np.where(depth > floor, square / (2.0 * np.maximum(depth, floor)), np.inf)
        radius[start:stop] = np.minimum(radius[start:stop], candidate.min(axis=1))
    return radius


def _exact_balls(p: np.ndarray, n: np.ndarray, a_t: np.ndarray, b_t: np.ndarray, c_t: np.ndarray,
                 allowed: np.ndarray, floor: float) -> tuple[np.ndarray, np.ndarray]:
    """For each point ``p[k]`` (outward normal ``n[k]``): the least radius at which the ball tangent there
    (centre p - r n) meets one of the triangles it is ``allowed`` (corners ``a_t``, ``b_t``, ``c_t``), and that
    triangle's index (-1 for none)."""
    P, N = p[:, None, :], n[:, None, :]
    A, B, Cc = a_t[None], b_t[None], c_t[None]
    best = np.full(allowed.shape, np.inf)

    def dot(x, y):
        return np.einsum("kmj,kmj->km", x, y)

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        for corner in (A, Cc, B):
            d = corner - P
            h = -dot(d, np.broadcast_to(N, d.shape))
            best = np.minimum(best, np.where(h > floor, dot(d, d) / (2.0 * h), np.inf))
        # edges: g(t) = (|a|^2 + 2t a.e + t^2 |e|^2) / (2 (h0 + t h1)) is stationary where
        # |e|^2 h1 t^2 + 2 |e|^2 h0 t + (2 a.e h0 - |a|^2 h1) = 0
        for start, end in ((A, B), (B, Cc), (Cc, A)):
            a = start - P
            e = np.broadcast_to(end - start, a.shape)
            nn = np.broadcast_to(N, a.shape)
            h0, h1 = -dot(a, nn), -dot(e, nn)
            ae, aa, ee = dot(a, e), dot(a, a), dot(e, e)
            qa, qb, qc = ee * h1, 2.0 * ee * h0, 2.0 * ae * h0 - aa * h1
            disc = qb * qb - 4.0 * qa * qc
            root = np.sqrt(np.maximum(disc, 0.0))
            linear = np.abs(qa) < 1e-30 * np.maximum(ee, 1e-30)
            for sign in (-1.0, 1.0):
                t = np.where(linear, -qc / np.where(np.abs(qb) > 0, qb, np.inf), (-qb + sign * root) / (2.0 * qa))
                hh = h0 + t * h1
                ok = (disc >= 0) & (t > 0) & (t < 1) & (hh > floor)
                best = np.minimum(best, np.where(ok, (aa + 2 * t * ae + t * t * ee) / (2.0 * hh), np.inf))
        # insides: the sphere tangent at p and to the triangle's plane, touching inside the triangle
        m = np.cross(b_t - a_t, c_t - a_t)
        size = np.linalg.norm(m, axis=1)
        good = size > 0
        m = m / np.where(good, size, 1.0)[:, None]
        v0, v1 = b_t - a_t, c_t - a_t
        d00, d01, d11 = (np.einsum("ij,ij->i", v0, v0), np.einsum("ij,ij->i", v0, v1),
                         np.einsum("ij,ij->i", v1, v1))
        den = d00 * d11 - d01 * d01
        w = np.einsum("mj,kmj->km", m, P - A)
        mn = np.einsum("mj,kj->km", m, n)
        for sign in (-1.0, 1.0):
            r = w / (mn + sign)
            centre = P - r[:, :, None] * N
            touch = centre - np.einsum("mj,kmj->km", m, centre - A)[:, :, None] * m[None]
            rel = touch - A
            d20, d21 = np.einsum("kmj,mj->km", rel, v0), np.einsum("kmj,mj->km", rel, v1)
            bv = (d11 * d20 - d01 * d21) / den
            bw = (d00 * d21 - d01 * d20) / den
            hh = -np.einsum("kmj,kj->km", touch - P, n)
            ok = (good[None] & np.isfinite(r) & (r > 0) & (bv >= -1e-9) & (bw >= -1e-9) & (bv + bw <= 1 + 1e-9)
                  & (hh > floor))
            best = np.minimum(best, np.where(ok, r, np.inf))
    best = np.where(allowed, best, np.inf)
    if not best.shape[1]:
        return np.full(len(p), np.inf), np.full(len(p), -1)
    pick = np.argmin(best, axis=1)
    least = best[np.arange(len(p)), pick]
    return least, np.where(np.isfinite(least), pick, -1)


def ball_thickness(points: np.ndarray, normals: np.ndarray, ray: np.ndarray, vertices: np.ndarray,
                   triangles: np.ndarray, others: np.ndarray | None = None, *,
                   point_face: np.ndarray | None = None, triangle_face: np.ndarray | None = None,
                   others_face: np.ndarray | None = None, cap: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """The rolling-ball wall thickness under each point: the diameter of the largest ball touching the
    surface at the point (its centre straight in along the inward normal) that no triangle of the surface
    (``vertices``, ``triangles``) cuts into, never more than ``ray`` (the exact distance straight through).
    Returns the thickness (nan where nothing bounds the ball: an open shell) and the triangle bounding each
    ball (-1 where the ray does).

    A point q beyond the tangent plane at p lies inside the ball of radius r centred at p - r n when
    r > |q - p|^2 / (2 (p - q) . n), so the ball's radius is the least of that over the surface: over each
    triangle the least of its corners, its edges (a quadratic's root) and its inside (the sphere tangent to
    its plane), each exact. The surface points ``others`` (and the corners) bound it first, so only the
    triangles within reach of that bound are solved. A plate's face reads its thickness; its narrow end
    reads it too (the faces either side hold the ball), where a ray along the normal reads the plate's
    length; a boss reads its diameter; the root of a rib, the section a sink forms over. Within half a wall
    of a convex edge the ball is held by the face round the corner and reads less (twice the distance to
    the edge): low by an outside edge, never high.

    Points sampled on exact faces lie off a triangulation of them (a chord runs inside a convex face), so
    with ``point_face`` and ``triangle_face`` (and ``others_face``) a point is not held by its own face's triangles
    near it (within three of them); ``cap``
    gives its own face's bound instead (a convex cylinder's or sphere's radius, inf for a plane)."""
    p_all = np.asarray(points, dtype=float).reshape(-1, 3)
    n_all = np.asarray(normals, dtype=float).reshape(-1, 3)
    verts = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tris = np.asarray(triangles, dtype=int).reshape(-1, 3)
    radius = np.asarray(ray, dtype=float) / 2.0
    radius = np.where(np.isfinite(radius), radius, np.inf)
    if cap is not None:
        radius = np.minimum(radius, np.asarray(cap, dtype=float))
    bound = np.full(len(p_all), -1, dtype=int)
    if not len(p_all) or not len(tris):
        return np.where(np.isfinite(radius), 2.0 * radius, np.nan), bound
    own = point_face is not None and triangle_face is not None
    scale = float(np.linalg.norm(verts.max(axis=0) - verts.min(axis=0))) or 1.0
    floor = 1e-9 * scale
    a_t, b_t, c_t = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    centroid = (a_t + b_t + c_t) / 3.0
    reach = np.max(np.stack([np.linalg.norm(corner - centroid, axis=1) for corner in (a_t, b_t, c_t)]), axis=0)
    if own:
        # The bound from points must leave each point's own face out too: the points are the faces'.
        upper = radius.copy()
        faces = np.asarray(point_face)
        tri_face = np.asarray(triangle_face)
        extra = np.asarray(others, dtype=float).reshape(-1, 3) if others is not None else np.zeros((0, 3))
        extra_face = np.asarray(others_face) if others_face is not None else np.full(len(extra), -1)
        q_face = np.concatenate([tri_face, extra_face])
        q = np.vstack([centroid, extra])
        for face in np.unique(faces):
            mine = faces == face
            upper[mine] = _point_bound(p_all[mine], n_all[mine], q[q_face != face], radius[mine], floor)
    else:
        q = np.vstack([verts, centroid] + ([np.asarray(others, dtype=float).reshape(-1, 3)] if others is not None else []))
        upper = _point_bound(p_all, n_all, q, radius, floor)
    upper = np.where(np.isfinite(upper), upper, scale)
    tri_face = np.asarray(triangle_face) if own else None
    if own:
        # A point is kept from its own face's triangles only near it (three of that face's typical triangles
        # across), where a chord runs inside the surface the point lies on; farther off they bound the ball as
        # any face does (a one-face ellipsoid's far side).
        longest = np.max(np.stack([np.linalg.norm(b_t - a_t, axis=1), np.linalg.norm(c_t - b_t, axis=1),
                                   np.linalg.norm(a_t - c_t, axis=1)]), axis=0)
        typical = {int(face): float(np.median(longest[tri_face == face])) for face in np.unique(tri_face)}
        keep_off = np.array([3.0 * typical.get(int(face), 0.0) for face in np.asarray(point_face)])
    # Points a few at a time (neighbours in the sampled order lie near one another, so their triangles mostly
    # coincide): each solves the triangles within its own ball's reach (2 r of the bound), its own face's left out.
    chunk = 24
    for start in range(0, len(p_all), chunk):
        index = np.arange(start, min(len(p_all), start + chunk))
        distance = np.linalg.norm(centroid[None, :, :] - p_all[index, None, :], axis=2) - reach[None, :]
        near = distance <= 2.0 * upper[index, None] * (1 + 1e-9)
        if own:
            near &= (tri_face[None, :] != np.asarray(point_face)[index, None]) | (distance > keep_off[index, None])
        columns = np.nonzero(near.any(axis=0))[0]
        if not len(columns):
            continue
        least, pick = _exact_balls(p_all[index], n_all[index], a_t[columns], b_t[columns], c_t[columns],
                                   near[:, columns], floor)
        tighter = least < radius[index]
        radius[index[tighter]] = least[tighter]
        bound[index[tighter]] = columns[pick[tighter]]
    return np.where(np.isfinite(radius), 2.0 * radius, np.nan), bound


def even_points(vertices: np.ndarray, triangles: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """About ``count`` points spread over a mesh by area, with no randomness: the triangles in order, each
    given the points its share of the running area asks for (a running quota, so a small triangle beside a
    large one is neither always skipped nor always sampled), each point the centre of one of an n x n cut of
    its triangle, taken evenly. Returns the points, their triangles and the area each stands for. The same
    mesh gives the same points on every platform; a mesh whose vertices move slightly gives points that move
    with them."""
    verts = np.asarray(vertices, dtype=float).reshape(-1, 3)
    tris = np.asarray(triangles, dtype=int).reshape(-1, 3)
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = float(areas.sum())
    if total <= 0 or not len(tris):
        return np.zeros((0, 3)), np.zeros(0, dtype=int), np.zeros(0)
    quota = total / max(1, count)
    running = np.cumsum(areas) / quota
    wanted = np.floor(running + 0.5).astype(int) - np.floor(np.concatenate([[0.0], running[:-1]]) + 0.5).astype(int)
    points, owner, weights = [], [], []
    for index in np.nonzero(wanted > 0)[0]:
        k = int(wanted[index])
        cuts = int(math.ceil(math.sqrt(k)))
        bary = []
        for i in range(cuts):
            for j in range(cuts - i):
                bary.append(((i + 1 / 3) / cuts, (j + 1 / 3) / cuts))
                if i + j <= cuts - 2:
                    bary.append(((i + 2 / 3) / cuts, (j + 2 / 3) / cuts))
        chosen = np.array(bary)[np.unique(np.linspace(0, len(bary) - 1, k).astype(int))]
        wa, wb = chosen[:, 0:1], chosen[:, 1:2]
        points.append(wa * a[index] + wb * b[index] + (1.0 - wa - wb) * c[index])
        owner.append(np.full(len(chosen), index))
        weights.append(np.full(len(chosen), float(areas[index]) / len(chosen)))
    if not points:
        return np.zeros((0, 3)), np.zeros(0, dtype=int), np.zeros(0)
    return np.vstack(points), np.concatenate(owner).astype(int), np.concatenate(weights)


def nearest_broad(start: int, neighbours: Callable[[int], Any], broad: Callable[[int], bool],
                  most: int = 6) -> list[int]:
    """The broad faces nearest ``start`` across its neighbours (one ring after another, at most ``most``
    rings out): where a narrow face -- a fillet's strip, a corner's patch, a rib's top -- takes its wall."""
    seen, ring = {start}, [start]
    for _ in range(most):
        following = []
        for face in ring:
            for other in neighbours(face):
                if other not in seen:
                    seen.add(other)
                    following.append(other)
        found = [face for face in following if broad(face)]
        if found:
            return found
        if not following:
            break
        ring = following
    return []


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float | None:
    """The finite value at ``quantile`` of the weight, lowest first; None for none."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    keep = np.isfinite(v) & (w > 0)
    if not keep.any():
        return None
    order = np.argsort(v[keep])
    share = np.cumsum(w[keep][order])
    index = min(int(np.searchsorted(share, quantile * share[-1])), int(keep.sum()) - 1)
    return float(v[keep][order][index])


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    return weighted_quantile(values, weights, 0.5)


def transitions(points: np.ndarray, thickness: np.ndarray, groups: np.ndarray, usable: np.ndarray,
                spacing: np.ndarray | float, nominal: float, least_change: float = 0.5) -> dict[int, dict[str, Any]]:
    """The steepest change of wall thickness along each group's surface (a face, a mesh region): over pairs
    of usable points of one group within four sample spacings whose thicknesses differ by at least
    ``least_change`` times the nominal wall, the distance between them per unit of thickness change -- the
    transition's length over its height, which a gradual taper keeps large and a step makes small. Per
    group: ``ratio`` (the least found), the pair's points and their thicknesses."""
    found: dict[int, dict[str, Any]] = {}
    p = np.asarray(points, dtype=float)
    t = np.asarray(thickness, dtype=float)
    g = np.asarray(groups)
    gap = np.broadcast_to(np.asarray(spacing, dtype=float), t.shape)
    ok = np.asarray(usable, dtype=bool) & np.isfinite(t)
    change = least_change * nominal
    for group in np.unique(g[ok]):
        index = np.nonzero(ok & (g == group))[0]
        if len(index) < 2:
            continue
        if len(index) > 1200:
            index = index[np.linspace(0, len(index) - 1, 1200).astype(int)]
        d = np.linalg.norm(p[index][:, None, :] - p[index][None, :, :], axis=2)
        dt = np.abs(t[index][:, None] - t[index][None, :])
        pair = (d <= 4.0 * float(np.max(gap[index]))) & (d > 0) & (dt >= change)
        if not pair.any():
            continue
        ratio = np.where(pair, d / np.maximum(dt, 1e-12), np.inf)
        a, b = np.unravel_index(int(np.argmin(ratio)), ratio.shape)
        found[int(group)] = {"ratio": float(ratio[a, b]), "points": (p[index[a]], p[index[b]]),
                             "thickness": (float(t[index[a]]), float(t[index[b]]))}
    return found


# --- undercuts -------------------------------------------------------------------------------------------


def _freed_after(points: np.ndarray, side: np.ndarray, pulls: Sequence[np.ndarray], cast: Cast,
                 strokes: np.ndarray) -> np.ndarray:
    """Per point, the least of ``strokes`` (ascending) after which a move along ``side``, itself clear,
    then along one of ``pulls`` leaves the part; inf where none does."""
    n = len(points)
    best = np.full(n, np.inf)
    ahead = cast(points, np.repeat(side[None, :], n, axis=0))

    def clear(index: np.ndarray, stroke: np.ndarray) -> np.ndarray:
        moved = points[index] + stroke[:, None] * side[None, :]
        free = np.zeros(len(moved), dtype=bool)
        for pull in pulls:
            left = ~free
            if left.any():
                free[left] = ~np.isfinite(cast(moved[left], np.repeat(pull[None, :], int(left.sum()), axis=0)))
        return free & (ahead[index] > stroke)

    previous = 0.0
    for stroke in strokes:
        open_ = np.nonzero(~np.isfinite(best) & (ahead > stroke))[0]
        if len(open_):
            free = clear(open_, np.full(len(open_), float(stroke)))
            found = open_[free]
            if len(found):
                # Bisect between the last stroke that did not clear and this one.
                lo, hi = np.full(len(found), previous), np.full(len(found), float(stroke))
                for _ in range(5):
                    mid = 0.5 * (lo + hi)
                    ok = clear(found, mid)
                    hi = np.where(ok, mid, hi)
                    lo = np.where(ok, lo, mid)
                best[found] = hi
        previous = float(stroke)
        if np.isfinite(best).all():
            break
    return best


def _subset(count: int, most: int) -> np.ndarray:
    return np.arange(count) if count <= most else np.unique(np.linspace(0, count - 1, most).astype(int))


def classify_undercut(points: np.ndarray, normals: np.ndarray, pull: np.ndarray, cast: Cast, *, scale: float,
                      zero_tol_deg: float, stroke_limit: float | None = None) -> dict[str, Any]:
    """What releases a trapped feature, from its points (already offset off the surface), their outward
    normals, the pull and ``cast``. Directions tried: eight round the parting plane, the feature's own mean
    lateral normal, and each of those tilted 45 degrees toward either pull (an angled slide).

    - ``side_action``: from every point a ray leaves the part along one of at most four directions, none
      of whose faces leans against it (n . s at least -sin(zero_tol)); ``directions`` the fewest covering
      the feature, ``stroke_mm`` the farthest any must travel before the pull is clear;
    - ``lifter``: no direction leaves the part (the feature faces the part's inside) but one short move
      along one direction, at most ``stroke_limit`` (a quarter of ``scale`` by default), clears every point
      for a pull: a lifter or an internal slide;
    - ``collapsible_core``: every point is cleared so, but along directions round an axis that no one
      direction serves (an internal groove or thread round the pull);
    - ``none``: some point is cleared by none of these (a sealed pocket, an interlock).
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    nrm = np.asarray(normals, dtype=float).reshape(-1, 3)
    chosen_points = _subset(len(pts), RELEASE_POINTS)
    pts, nrm = pts[chosen_points], nrm[chosen_points]
    p = np.asarray(pull, dtype=float)
    p = p / np.linalg.norm(p)
    tol = math.sin(math.radians(max(zero_tol_deg, 0.05)))
    lateral = lateral_directions(p, 8)
    total = nrm.sum(axis=0)
    mean = total - p * float(total @ p)
    if np.linalg.norm(mean) > 1e-3 * len(nrm):
        lateral = np.vstack([mean / np.linalg.norm(mean), lateral])
    tilted = np.vstack([(lateral + p) / math.sqrt(2.0), (lateral - p) / math.sqrt(2.0)])
    candidates = np.vstack([lateral, tilted])
    n = len(pts)
    if not n:
        return {"release": "none", "kind": "internal", "directions": [], "vectors": [], "angled": [],
                "stroke_mm": None}
    frees = np.zeros((len(candidates), n), dtype=bool)
    for index, side in enumerate(candidates):
        if index == len(lateral) and frees[:index].all(axis=1).any():
            break  # one plain slide frees it all: no angled one is needed
        leans = nrm @ side >= -tol
        if leans.any():
            frees[index] = leans & ~np.isfinite(cast(pts, np.repeat(side[None, :], n, axis=0)))
    if frees.any(axis=0).all():
        chosen: list[int] = []
        left = np.ones(n, dtype=bool)
        plain = np.arange(len(candidates)) < len(lateral)
        while left.any() and len(chosen) < 4:
            gain = (frees & left[None, :]).sum(axis=1) - np.where(plain, 0.0, 0.5)
            pick = int(np.argmax(gain))
            if gain[pick] <= 0:
                break
            chosen.append(pick)
            left &= ~frees[pick]
        if not left.any():
            # Each point goes to the slide that frees it in the shortest travel; the stroke is the longest
            # any slide then needs.
            travel = np.full((len(chosen), n), np.inf)
            for row, pick in enumerate(chosen):
                travel[row, frees[pick]] = _strokes(pts[frees[pick]], candidates[pick], p, cast, scale)
            best = travel.min(axis=0)
            used = sorted({int(row) for row in np.argmin(travel, axis=0)})
            chosen = [chosen[row] for row in used]
            return {"release": "side_action", "kind": "external",
                    "directions": [direction_name(candidates[pick]) for pick in chosen],
                    "vectors": [candidates[pick] for pick in chosen],
                    "angled": [not bool(plain[pick]) for pick in chosen],
                    "stroke_mm": float(best[np.isfinite(best)].max()) if np.isfinite(best).any() else float(scale)}
    limit = float(stroke_limit if stroke_limit is not None else 0.25 * scale)
    strokes = np.unique(np.concatenate([np.geomspace(max(limit * 2e-3, 1e-4), limit, 16), [limit]]))
    freed = np.full((len(lateral), n), np.inf)
    for index, side in enumerate(lateral):
        freed[index] = _freed_after(pts, side, (p, -p), cast, strokes)
    common = np.max(freed, axis=1)
    if np.isfinite(common).any():
        pick = int(np.argmin(common))
        return {"release": "lifter", "kind": "internal", "directions": [direction_name(lateral[pick])],
                "vectors": [lateral[pick]], "angled": [False], "stroke_mm": float(common[pick])}
    each = np.min(freed, axis=0)
    if np.isfinite(each).all():
        return {"release": "collapsible_core", "kind": "internal", "directions": [], "vectors": [], "angled": [],
                "stroke_mm": float(each.max())}
    return {"release": "none", "kind": "internal", "directions": [], "vectors": [], "angled": [], "stroke_mm": None}


def _strokes(points: np.ndarray, side: np.ndarray, pull: np.ndarray, cast: Cast, scale: float) -> np.ndarray:
    """How far a slide along ``side`` travels before each point clears a pull (``scale`` where none does)."""
    if not len(points):
        return np.zeros(0)
    strokes = np.unique(np.concatenate([np.geomspace(max(scale * 2e-4, 1e-4), scale, 20), [scale]]))
    freed = _freed_after(points, side, (pull, -pull), cast, strokes)
    return np.where(np.isfinite(freed), freed, scale)


# --- parting ---------------------------------------------------------------------------------------------


def parting(elements: list[dict[str, Any]], top: float, bottom: float, tolerance: float) -> dict[str, Any]:
    """Whether one flat plane square to the pull can carry the parting line round the outline.

    Each element is a piece of the outline with its ``low`` and ``high`` along the pull: a silhouette edge
    (``kind`` ``edge``: a face opening one way meets one opening the other), a zero-draft wall on the
    outline (``wall``: the line may run anywhere up it) or a curved face turning through the pull there
    (``turn``: the heights it turns at). One plane at height h takes an edge or a turn only where its span
    is within ``tolerance`` and holds h, a wall where h lies up it. Returns ``flat``, the plane's ``height``
    (the middle of what every element allows; else the elements' weighted median height), the ``range``
    allowed, the elements no flat plane takes (``off_plane``) and the depths either side."""
    if not elements:
        middle = 0.5 * (top + bottom)
        return {"flat": None, "height": middle, "range": None, "off_plane": [],
                "depth_above": top - middle, "depth_below": middle - bottom}
    lo, hi = -math.inf, math.inf
    for element in elements:
        lo = max(lo, element["low"] - tolerance)
        hi = min(hi, element["high"] + tolerance)
    slanted = [element for element in elements
               if element["kind"] != "wall" and element["high"] - element["low"] > tolerance]
    flat = lo <= hi and not slanted
    off: list[dict[str, Any]] = []
    if flat:
        lo, hi = max(lo, bottom), min(hi, top)
        if lo > hi:
            lo = hi = min(max(lo, bottom), top)
        height = 0.5 * (lo + hi)
    else:
        heights = np.array([0.5 * (element["low"] + element["high"]) for element in elements])
        weights = np.array([max(float(element.get("weight", 1.0)), 1e-9) for element in elements])
        height = float(weighted_median(heights, weights) or 0.0)
        off = [element for element in elements
               if not (element["low"] - tolerance <= height <= element["high"] + tolerance)
               or (element["kind"] != "wall" and element["high"] - element["low"] > tolerance)]
    return {"flat": bool(flat), "height": float(height), "range": [float(lo), float(hi)] if flat else None,
            "off_plane": off, "depth_above": float(top - height), "depth_below": float(height - bottom)}
