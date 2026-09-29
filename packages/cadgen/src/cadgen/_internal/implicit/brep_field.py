"""A B-rep as a signed distance field: the way INTO the field for any STEP.

A build123d shape (a STEP, or a `$cad` model's result) becomes a leaf that
answers the same question every primitive does -- how far is this point from
my surface, negative inside -- so a B-rep can be shelled, blended with a
primitive, cut, patterned or measured in the field. And because the leaf keeps
the shape, the way OUT (``brep.py``) uses the original B-rep exactly: a STEP
that goes through a sharp boolean with a primitive comes back as a STEP with
no approximation at all.

How the distance is evaluated, fast enough to contour a million-point grid:

1. the shape is tessellated once at a chord tolerance well under the grid
   cell, and every triangle is covered with sample points at about the cell
   spacing (vectorised: triangles are grouped by how many subdivisions they
   need);
2. a k-d tree over the samples (scipy, which build123d already depends on)
   finds each query point's nearest sample, which names a triangle;
3. the distance is the exact point-to-triangle distance to that triangle,
   and the sign comes from the angle-weighted pseudonormal at the closest
   point (Baerentzen and Aanaes): the face's normal inside a triangle, the
   two faces' sum on an edge, the angle-weighted sum at a vertex. A face
   normal alone gives the wrong sign above a convex rim (a hole's edge seen
   from above), which is where a solid's faces meet; the pseudonormal is
   right wherever the surface is closed. The tessellation's vertices are
   welded first so faces know their neighbours.

The error is the tessellation's chord error plus the rare case where the
nearest sample's triangle is not the nearest triangle; both are a small
fraction of a grid cell at the spacing used. The sampler is rebuilt when a
finer grid asks for it (``prepare``), never coarser.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

__all__ = ["BrepSampler", "shape_bounds"]


def shape_bounds(shape: Any) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    box = shape.bounding_box()
    return (float(box.min.X), float(box.min.Y), float(box.min.Z)), (float(box.max.X), float(box.max.Y), float(box.max.Z))


def _closest_on_triangles(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The closest point on each triangle to each point (Ericson's region walk, vectorised),
    and which region it lies in: 0 inside, 1/2/3 at vertex a/b/c, 4/5/6 on edge ab/bc/ca.

    The sequential algorithm returns at the first region that matches; here every
    region is computed and applied in reverse order, so the earliest region wins.
    """
    ab, ac, ap = b - a, c - a, p - a
    d1 = np.einsum("ij,ij->i", ab, ap)
    d2 = np.einsum("ij,ij->i", ac, ap)
    bp = p - b
    d3 = np.einsum("ij,ij->i", ab, bp)
    d4 = np.einsum("ij,ij->i", ac, bp)
    cp = p - c
    d5 = np.einsum("ij,ij->i", ab, cp)
    d6 = np.einsum("ij,ij->i", ac, cp)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    with np.errstate(divide="ignore", invalid="ignore"):
        v_ab = np.clip(d1 / (d1 - d3), 0.0, 1.0)
        w_ac = np.clip(d2 / (d2 - d6), 0.0, 1.0)
        w_bc = np.clip((d4 - d3) / ((d4 - d3) + (d5 - d6)), 0.0, 1.0)
        denom = va + vb + vc
        v_in = np.where(np.abs(denom) < 1e-300, 0.0, vb / denom)
        w_in = np.where(np.abs(denom) < 1e-300, 0.0, vc / denom)
    closest = a + ab * v_in[:, None] + ac * w_in[:, None]
    region = np.zeros(len(p), dtype=np.int8)
    col = lambda mask: mask[:, None]  # noqa: E731
    for mask, point, code in (
        ((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), b + (c - b) * w_bc[:, None], 5),
        ((vb <= 0) & (d2 >= 0) & (d6 <= 0), a + ac * w_ac[:, None], 6),
        ((d6 >= 0) & (d5 <= d6), c, 3),
        ((vc <= 0) & (d1 >= 0) & (d3 <= 0), a + ab * v_ab[:, None], 4),
        ((d3 >= 0) & (d4 <= d3), b, 2),
        ((d1 <= 0) & (d2 <= 0), a, 1),
    ):
        closest = np.where(col(mask), point, closest)
        region = np.where(mask, code, region)
    return closest, region


def _weld(v: np.ndarray, t: np.ndarray, tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    """Merge coincident vertices (build123d tessellates each face on its own) so faces share edges."""
    key = np.round(v / tolerance).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return v[first], inverse.reshape(-1)[t]


class BrepSampler:
    """The surface of one shape as samples with triangles, queried by nearest sample."""

    def __init__(self, shape: Any, spacing: float) -> None:
        from scipy.spatial import cKDTree

        self.spacing = float(spacing)
        lo, hi = shape_bounds(shape)
        diagonal = math.dist(lo, hi) or 1.0
        tolerance = max(min(self.spacing / 10.0, diagonal * 1e-3), 1e-4)
        vertices, triangles = shape.tessellate(tolerance, 0.3)
        v = np.array([(p.X, p.Y, p.Z) for p in vertices], dtype=np.float64).reshape(-1, 3)
        t = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
        if len(t) == 0:
            raise ValueError("the shape has no surface to sample")
        v, t = _weld(v, t, max(tolerance * 0.5, 1e-7))
        a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal, axis=1, keepdims=True)
        keep = length[:, 0] > 1e-20
        t, a, b, c, normal, length = t[keep], a[keep], b[keep], c[keep], normal[keep], length[keep]
        self.a, self.b, self.c = a, b, c
        self.normal = normal / length
        self.triangle_index = t
        self._pseudonormals(v, t)
        # Cover every triangle with a barycentric lattice fine enough that the nearest
        # sample's triangle is the nearest triangle: subdivisions = longest edge / spacing.
        longest = np.maximum.reduce([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - a, axis=1), np.linalg.norm(c - b, axis=1)])
        k = np.maximum(np.ceil(longest / self.spacing).astype(np.int64), 1)
        k = np.minimum(k, 64)
        points, owner = [], []
        for level in np.unique(k):
            idx = np.nonzero(k == level)[0]
            u, w = np.meshgrid(np.arange(level + 1), np.arange(level + 1), indexing="ij")
            mask = (u + w) <= level
            u, w = u[mask], w[mask]
            bary = np.stack([level - u - w, u, w], axis=1) / level  # (S, 3) weights for a, b, c
            pts = (bary[None, :, 0, None] * a[idx][:, None, :] + bary[None, :, 1, None] * b[idx][:, None, :] + bary[None, :, 2, None] * c[idx][:, None, :])
            points.append(pts.reshape(-1, 3))
            owner.append(np.repeat(idx, len(bary)))
        self.points = np.concatenate(points)
        self.owner = np.concatenate(owner)
        self.tree = cKDTree(self.points)
        self.samples = len(self.points)
        self.triangles = len(self.a)

    def _pseudonormals(self, v: np.ndarray, t: np.ndarray) -> None:
        """Angle-weighted vertex normals and edge normals (the two adjacent faces' sum), per triangle corner and edge."""
        n = self.normal
        corners = [self.a, self.b, self.c]
        vertex_normal = np.zeros_like(v)
        for i in range(3):
            p0, p1, p2 = corners[i], corners[(i + 1) % 3], corners[(i + 2) % 3]
            u, w = p1 - p0, p2 - p0
            cos = np.einsum("ij,ij->i", u, w) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(w, axis=1), 1e-300)
            angle = np.arccos(np.clip(cos, -1.0, 1.0))
            np.add.at(vertex_normal, t[:, i], n * angle[:, None])
        length = np.linalg.norm(vertex_normal, axis=1, keepdims=True)
        self.vertex_normal = vertex_normal / np.where(length < 1e-20, 1.0, length)
        # Edges: key (min, max) vertex pair -> summed face normals of the triangles on it.
        edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        edges.sort(axis=1)
        key = edges[:, 0] * len(v) + edges[:, 1]
        unique, inverse = np.unique(key, return_inverse=True)
        edge_normal = np.zeros((len(unique), 3))
        np.add.at(edge_normal, inverse, np.tile(n, (3, 1)))
        length = np.linalg.norm(edge_normal, axis=1, keepdims=True)
        edge_normal = edge_normal / np.where(length < 1e-20, 1.0, length)
        # Per triangle: the normals of its edges ab, bc, ca.
        self.edge_normal = edge_normal[inverse].reshape(3, -1, 3).transpose(1, 0, 2)

    def distance(self, p: np.ndarray) -> np.ndarray:
        _, nearest = self.tree.query(p, workers=-1)
        tri = self.owner[nearest]
        closest, region = _closest_on_triangles(p, self.a[tri], self.b[tri], self.c[tri])
        d = np.linalg.norm(p - closest, axis=1)
        t = self.triangle_index[tri]
        pseudo = self.normal[tri].copy()
        for code, corner in ((1, 0), (2, 1), (3, 2)):
            mask = region == code
            pseudo[mask] = self.vertex_normal[t[mask, corner]]
        for code, edge in ((4, 0), (5, 1), (6, 2)):
            mask = region == code
            pseudo[mask] = self.edge_normal[tri[mask], edge]
        side = np.einsum("ij,ij->i", p - closest, pseudo)
        return np.where(side < 0, -d, d)
