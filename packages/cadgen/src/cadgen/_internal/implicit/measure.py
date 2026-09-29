"""Spatial questions as expressions over fields.

Because every shape is a distance field, "how thick", "how far apart" and
"do they touch" are evaluations, not topology walks. Everything here is
sampled -- on a grid or on a contoured surface -- so each answer states
the resolution it was taken at and is exact only to that resolution.
"""

from __future__ import annotations

import math

import numpy as np

from cadgen._internal.implicit.field import Bounds, Field, Intersection
from cadgen._internal.implicit.mesh import Mesh, contour, grid_for, sample

__all__ = ["measure", "clearance", "interference", "thickness", "probe"]


def _default_resolution(bounds: Bounds, resolution: float | None) -> float:
    return float(resolution) if resolution else bounds.diagonal / 120.0


def probe(field: Field, points) -> list[dict]:
    """Signed distance, owning leaf and unit normal at each point."""
    pts = np.asarray(points, float).reshape(-1, 3)
    d, owner = field.evaluate(pts)
    n = field.normal(pts)
    return [
        {
            "point": [float(x) for x in pts[i]],
            "distance": float(d[i]),
            "inside": bool(d[i] <= 0.0),
            "leaf": int(owner[i]),
            "normal": [float(x) for x in n[i]],
        }
        for i in range(len(pts))
    ]


def measure(field: Field, *, resolution: float | None = None, mesh: Mesh | None = None) -> dict:
    """Bounds, volume, surface area and centroid of the solid, plus per-leaf surface share.

    The volume comes from the contoured mesh (so it agrees with what is
    exported); the resolution used is reported with it.
    """
    m = mesh or contour(field, resolution=resolution)
    tight = Bounds.of_points(m.vertices) if m.vertex_count else field.bounds
    leaf_area: dict[int, float] = {}
    if m.triangle_count:
        v = m.vertices[m.triangles]
        areas = 0.5 * np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1)
        for leaf_id in np.unique(m.triangle_leaf):
            leaf_area[int(leaf_id)] = float(areas[m.triangle_leaf == leaf_id].sum())
    return {
        "resolution": m.resolution,
        "bounds": {"min": list(tight.min), "max": list(tight.max), "size": list(tight.size)},
        "volume": m.volume(),
        "surface_area": m.area(),
        "centroid": list(m.centroid()),
        "triangles": m.triangle_count,
        "leaves": [
            {
                "id": index,
                "kind": leaf.kind,
                "label": leaf.label or "",
                "site": leaf.site or "",
                "surface_area": leaf_area.get(index, 0.0),
            }
            for index, leaf in enumerate(m.leaves)
        ],
    }


def clearance(a: Field, b: Field, *, resolution: float | None = None) -> dict:
    """The least distance from ``a``'s surface to ``b`` (negative: they interpenetrate by that much).

    Sampled at ``a``'s contoured vertices, so the answer is exact to the
    resolution; ``b``'s field supplies the metric.
    """
    m = contour(a, resolution=resolution)
    if m.vertex_count == 0:
        return {"clearance": math.inf, "resolution": m.resolution, "at": None, "touching": False}
    d = b.distance(m.vertices)
    i = int(np.argmin(d))
    return {
        "clearance": float(d[i]),
        "at": [float(x) for x in m.vertices[i]],
        "touching": bool(d[i] <= m.resolution),
        "resolution": m.resolution,
    }


def interference(a: Field, b: Field, *, resolution: float | None = None) -> dict:
    """The volume the two solids share, and its bounding box (zero when they are apart)."""
    both = Intersection((a, b))
    box = a.bounds.intersection(b.bounds)
    if min(box.size) <= 0:
        return {"volume": 0.0, "bounds": None, "resolution": _default_resolution(a.bounds, resolution)}
    h = _default_resolution(box, resolution)
    origin, shape, h = grid_for(box, h)
    values = sample(both, origin, shape, h)
    inside = values <= 0.0
    count = int(inside.sum())
    if count == 0:
        return {"volume": 0.0, "bounds": None, "resolution": h}
    idx = np.argwhere(inside)
    lo = origin + h * idx.min(axis=0)
    hi = origin + h * idx.max(axis=0)
    return {"volume": count * h**3, "bounds": {"min": lo.tolist(), "max": hi.tolist()}, "resolution": h}


def thickness(field: Field, *, resolution: float | None = None) -> dict:
    """Wall thickness across the part.

    From every surface vertex on a face (not on a crease) a ray is cast into
    the solid along the inward normal, sphere-traced on the field until it
    exits; its length is the wall there. ``min_thickness`` is the shortest
    ray -- and a knife edge (a cut through a sloping wall) is genuinely near
    zero there, so ``p05_thickness`` (the 5th percentile over the surface) and
    ``median_thickness`` say what the walls are like away from such an edge.
    ``max_thickness`` is the largest inscribed sphere (twice the deepest
    inside distance on the grid). All are exact only to the resolution.
    """
    m = contour(field, resolution=resolution, crease_deg=0)
    box = field.bounds
    h = m.resolution
    origin, shape, h = grid_for(box, h)
    values = sample(field, origin, shape, h)
    deepest = float(-values.min()) if values.size else 0.0
    idx = np.unravel_index(int(np.argmin(values)), values.shape)
    deepest_at = (origin + h * np.asarray(idx, float)).tolist()
    if m.vertex_count == 0:
        return {"max_thickness": 2 * deepest, "max_at": deepest_at, "min_thickness": 0.0, "min_at": None, "resolution": h}
    # Cast only from vertices that sit on a face, not on a crease: a vertex at a sharp
    # edge has the edge's bisector for a normal and its ray would graze one face.
    keep = _on_a_face(m, crease_deg=35.0)
    rays = _inward_rays(field, m.vertices[keep], m.normals[keep], limit=box.diagonal, floor=h * 0.25)
    if not len(rays) or not np.isfinite(rays).any():
        return {"max_thickness": 2 * deepest, "max_at": deepest_at, "min_thickness": 0.0, "min_at": None, "resolution": h}
    i = int(np.argmin(rays))
    starts = m.vertices[keep]
    finite = rays[np.isfinite(rays)]
    return {
        "max_thickness": 2 * deepest,
        "max_at": deepest_at,
        "min_thickness": float(rays[i]),
        "min_at": [float(x) for x in starts[i]],
        "p05_thickness": float(np.percentile(finite, 5)),
        "median_thickness": float(np.percentile(finite, 50)),
        "resolution": h,
    }


def _on_a_face(m: Mesh, *, crease_deg: float) -> np.ndarray:
    """Vertices whose normal agrees with every triangle around them to within ``crease_deg``."""
    v = m.vertices[m.triangles]
    face_n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    length = np.linalg.norm(face_n, axis=1, keepdims=True)
    face_n = face_n / np.where(length < 1e-20, 1.0, length)
    agreement = np.einsum("tcj,tj->tc", m.normals[m.triangles], face_n)
    worst = np.ones(len(m.vertices))
    np.minimum.at(worst, m.triangles.reshape(-1), agreement.reshape(-1))
    return worst >= math.cos(math.radians(crease_deg))


def _inward_rays(field: Field, starts: np.ndarray, normals: np.ndarray, *, limit: float, floor: float) -> np.ndarray:
    """Length of the ray from each surface point into the solid until it leaves it (sphere tracing).

    A mesh vertex sits within a cell of the surface, not on it, so each ray
    first steps by the field's own distance onto the surface and ``floor``
    past it. A start that is still outside (a vertex at a sharp edge, whose
    normal is the edge's bisector) casts no ray and reports ``inf``; the
    face vertices beside it cover that wall.
    """
    direction = -normals
    d0 = field.distance(starts)
    t = d0 + floor
    p = starts + direction * t[:, None]
    alive = field.distance(p) < 0.0
    t = np.where(alive, t, np.inf)
    for _ in range(256):
        if not alive.any():
            break
        idx = np.nonzero(alive)[0]
        p = starts[idx] + direction[idx] * t[idx][:, None]
        d = field.distance(p)
        inside = d < 0.0
        alive[idx[~inside]] = False
        t[idx[inside]] += np.maximum(-d[inside], floor)
        alive &= t <= limit
    finite = np.isfinite(t)
    t = np.where(finite, t - d0 - floor, np.inf)  # measure from the surface, not the vertex
    return np.where(t > limit, limit, t)
