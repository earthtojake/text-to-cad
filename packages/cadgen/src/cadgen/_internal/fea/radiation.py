"""Thermal radiation on a :class:`~cadgen._internal.fea.femspace.FemSpace`: to the surroundings, and between faces.

Two kinds of radiating face, both grey and diffuse (one emissivity, the same
in every direction):

- **To the surroundings** (an entry without ``surface_to_surface``): each face
  loses ε σ (T⁴ − T∞⁴) per area to surroundings at ``ambient_C`` that it sees
  whole, as if nothing of the part stood in the way. Kelvin inside, °C outside.
- **Between faces** (entries with ``surface_to_surface: true``): every such face
  also sees the others. Their surface triangles are grouped into patches (at
  most :data:`MAX_PATCHES`, each a compact piece of one face, by recursive
  bisection along its longest side). The view factor from patch i to patch j is
  the area-weighted sum over i's triangles of the view factor from the
  triangle's centroid to each of j's triangles: Lambert's contour integral (exact
  for a flat triangle wholly in front of the point), the point-to-point kernel
  cos θi cos θj A / (π r²) where a triangle straddles the point's tangent plane.
  Obstruction is ray casting: a few points of each patch are joined to a few of
  the other's, every segment tested (Möller-Trumbore) against every surface
  triangle of the part, culled through a grid of boxes; the share of segments
  that get through scales that pair's view factor. Reciprocity is then imposed
  (A_i F_ij = A_j F_ji, the mean of the two), no row may sum past 1, and what a
  patch does not see of the others (1 − Σ F_ij) is the surroundings at its
  entry's ambient (a face nobody named counts as the surroundings too).
  The radiosity of the enclosure is solved exactly:
  J = ε E + (1 − ε)(F J + F∞ E∞), q = J − F J − F∞ E∞, so each patch's net
  flux out is linear in the patches' black-body powers E = σ T⁴ (at each patch's
  area-mean temperature): q = G E + h. G and h are formed once (dense, a few
  hundred patches square).

The heat equation gains a nonlinear boundary term, solved by Newton's method on
the T⁴ (:func:`newton_solve`): the surroundings' term is a boundary mass with
4 ε σ T³, and the exchange's tangent, W G diag(4 σ T̄³ / a) Wᵀ, is low-rank
(W maps a node to the patches it lies on), so each Newton step solves the
sparse system bordered by the patches' unknowns instead of forming it.

Units are the engine's: mm, s, mW; σ is 5.670374419e-11 mW/(mm² K⁴).
Numeric imports live inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

    from cadgen._internal.fea.femspace import FemSpace

__all__ = [
    "KELVIN", "MAX_PATCHES", "Radiation", "SIGMA", "assemble", "newton_solve", "patches_of", "surface_triangles",
    "view_factors",
]

#: Stefan-Boltzmann, W/(m² K⁴), and in the engine's mW/(mm² K⁴).
SIGMA_SI = 5.670374419e-8
SIGMA = SIGMA_SI * 1e-3
KELVIN = 273.15
#: At most this many patches carry the exchange between faces; at least this many triangles' worth each where few.
MAX_PATCHES = 300
#: Rays tested per pair of patches for obstruction: this many points of each, joined pairwise.
RAY_POINTS = 4
#: The contour integral runs from at most this many source points; past it, points are grouped (and the
#: point-to-point kernel used throughout), a stated accuracy cost.
MAX_SOURCES = 4000
#: Newton on the T⁴: the largest change (K) a converged step leaves, as a share of the temperature span; iterations.
NEWTON_TOL, MAX_NEWTON = 1e-9, 60


@dataclass
class Ambient:
    """Faces radiating to their surroundings: the boundary basis of their facets, ε, the ambient (°C)."""

    boundary: Any
    emissivity: float
    ambient: float
    index: int                      # the study's radiation entry


@dataclass
class Enclosure:
    """Faces that see each other: their patches, the node-to-patch map and the radiosity operator."""

    #: (nodes, patches) sparse: W[k, i] = ∫ over patch i of node k's shape function.
    W: Any
    area: "np.ndarray"              # (patches,) mm²
    entry: "np.ndarray"             # (patches,) the study's radiation entry of each
    emissivity: "np.ndarray"
    ambient_power: "np.ndarray"     # (patches,) σ T∞⁴ of each patch's surroundings, mW/mm²
    G: "np.ndarray"                 # (patches, patches): q = G E + h
    h: "np.ndarray"
    F: "np.ndarray"                 # (patches, patches) view factors, reciprocity imposed
    to_ambient: "np.ndarray"        # (patches,) 1 - Σ_j F_ij
    notes: dict = field(default_factory=dict)

    def mean_temperature(self, T: "np.ndarray") -> "np.ndarray":
        return (self.W.T @ T) / self.area

    def flux(self, T: "np.ndarray") -> "np.ndarray":
        """Each patch's net radiative flux out, mW/mm²."""
        E = SIGMA * (self.mean_temperature(T) + KELVIN) ** 4
        return self.G @ E + self.h


@dataclass
class Radiation:
    """Every radiating face of a study: what the heat equation adds, its tangent and its powers per entry."""

    space: Any
    ambient: list[Ambient] = field(default_factory=list)
    enclosure: Enclosure | None = None
    entries: int = 0

    def residual(self, T: "np.ndarray") -> "np.ndarray":
        """The net radiative power out of every node, mW (added to K T - f)."""
        import numpy as np
        from skfem import LinearForm, asm

        out = np.zeros(len(T))
        for entry in self.ambient:
            e, ta = entry.emissivity, (entry.ambient + KELVIN) ** 4

            @LinearForm
            def loss(v, w, e=e, ta=ta):
                return e * SIGMA * ((w["T"] + KELVIN) ** 4 - ta) * v

            out += asm(loss, entry.boundary, T=entry.boundary.interpolate(T))
        if self.enclosure is not None:
            out += self.enclosure.W @ self.enclosure.flux(T)
        return out

    def local_tangent(self, T: "np.ndarray"):
        """The surroundings' tangent, ∫ 4 ε σ T³ u v on their faces (sparse); zero without any."""
        from scipy import sparse
        from skfem import BilinearForm, asm

        n = len(T)
        J = sparse.csr_matrix((n, n))
        for entry in self.ambient:
            e = entry.emissivity

            @BilinearForm
            def tangent(u, v, w, e=e):
                return 4.0 * e * SIGMA * (w["T"] + KELVIN) ** 3 * u * v

            J = J + asm(tangent, entry.boundary, T=entry.boundary.interpolate(T))
        return J.tocsr()

    def exchange_tangent(self, T: "np.ndarray"):
        """The exchange's tangent as (W, G, c): W G diag(c) Wᵀ, c = 4 σ T̄³ / a. None without an enclosure."""
        if self.enclosure is None:
            return None
        enc = self.enclosure
        c = 4.0 * SIGMA * (enc.mean_temperature(T) + KELVIN) ** 3 / enc.area
        return enc.W, enc.G, c

    def powers(self, T: "np.ndarray") -> list[float]:
        """The net power (W) each radiation entry sends out, in the study's order."""
        import numpy as np
        from skfem import LinearForm, asm

        out = [0.0] * self.entries
        for entry in self.ambient:
            e, ta = entry.emissivity, (entry.ambient + KELVIN) ** 4

            @LinearForm
            def loss(v, w, e=e, ta=ta):
                return e * SIGMA * ((w["T"] + KELVIN) ** 4 - ta) * v

            out[entry.index] += float(asm(loss, entry.boundary, T=entry.boundary.interpolate(T)).sum()) / 1e3
        if self.enclosure is not None:
            enc = self.enclosure
            per = enc.flux(T) * enc.area / 1e3
            for index in range(self.entries):
                out[index] += float(per[enc.entry == index].sum())
        return [float(value) for value in out]

    @property
    def ambients(self) -> list[float]:
        """Every ambient (°C) a radiating face sees."""
        values = [entry.ambient for entry in self.ambient]
        if self.enclosure is not None:
            values += [float((p / SIGMA) ** 0.25 - KELVIN) for p in sorted(set(self.enclosure.ambient_power.tolist()))]
        return values


# -- surface geometry ---------------------------------------------------------------------------------


def surface_triangles(space: "FemSpace", rows) -> tuple["np.ndarray", "np.ndarray", "np.ndarray", "np.ndarray"]:
    """Boundary triangles ``rows`` (indices into ``space.boundary_quadratic``): their corners (T, 3, 3), area,
    unit normal pointing out of the part (away from the element each closes) and centroid."""
    import numpy as np

    rows = np.asarray(rows, dtype=np.int64)
    corners = space.dof_locations[space.boundary_quadratic[rows][:, :3]]
    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    normal = cross / np.where(area > 0, 2.0 * area, 1.0)[:, None]
    if len(rows):
        element = space.mesh.f2t[0, space.facets_of_rows(rows)]
        inside = space.mesh.p[:, space.mesh.t[:, element]].mean(axis=1).T
        flip = np.einsum("ij,ij->i", normal, inside - corners[:, 0]) > 0
        normal[flip] *= -1.0
    return corners, area, normal, corners.mean(axis=1)


def patches_of(centroids: "np.ndarray", area: "np.ndarray", face: "np.ndarray", limit: int = MAX_PATCHES) -> "np.ndarray":
    """Each triangle's patch: every face split into compact pieces by area, at most ``limit`` in all.

    A face gets a share of ``limit`` by its area (at least one); its triangles are split recursively at the
    median of the longest side of the piece with the most area until the face has its share.
    Deterministic: no random start.
    """
    import numpy as np

    patch = np.zeros(len(area), dtype=np.int64)
    faces = list(dict.fromkeys(face.tolist()))
    total = float(area.sum()) or 1.0
    next_id = 0
    for f in faces:
        members = np.flatnonzero(face == f)
        share = max(1, min(len(members), int(round(limit * float(area[members].sum()) / total))))
        groups = [members]
        while len(groups) < share:
            largest = max(range(len(groups)), key=lambda g: (float(area[groups[g]].sum()), len(groups[g])))
            group = groups[largest]
            if len(group) < 2:
                break
            points = centroids[group]
            axis = int(np.argmax(points.max(axis=0) - points.min(axis=0)))
            order = group[np.argsort(points[:, axis], kind="stable")]
            half = len(order) // 2
            groups[largest:largest + 1] = [order[:half], order[half:]]
        for group in groups:
            patch[group] = next_id
            next_id += 1
    return patch


# -- view factors -------------------------------------------------------------------------------------


def _point_to_triangles(points, normals, corners, centroids, tri_normals, tri_area) -> "np.ndarray":
    """(P, T) view factor from each point (with its normal) to each flat triangle, unobstructed.

    Lambert's contour integral where the triangle lies wholly in front of the point; the point-to-point
    kernel where it straddles the point's tangent plane but its centroid is in front; 0 where the triangle
    is behind the point, or faces away from it.
    """
    import numpy as np

    rel = corners[None, :, :, :] - points[:, None, None, :]                  # (P, T, 3, 3)
    height = np.einsum("pk,ptvk->ptv", normals, rel)                         # each corner above the point's plane
    to_point = points[:, None, :] - centroids[None, :, :]                     # (P, T, 3)
    facing = np.einsum("tk,ptk->pt", tri_normals, to_point) > 1e-12 * np.maximum(np.linalg.norm(to_point, axis=2), 1.0)
    front = (height > 0).all(axis=2) & facing
    result = np.zeros(height.shape[:2])
    if front.any():
        p_index, t_index = np.nonzero(front)
        R = rel[p_index, t_index]                                             # (M, 3, 3)
        n = normals[p_index]
        total = np.zeros(len(p_index))
        for a, b in ((0, 1), (1, 2), (2, 0)):
            cross = np.cross(R[:, a], R[:, b])
            length = np.linalg.norm(cross, axis=1)
            cos = np.einsum("mk,mk->m", R[:, a], R[:, b]) / np.maximum(
                np.linalg.norm(R[:, a], axis=1) * np.linalg.norm(R[:, b], axis=1), 1e-300)
            angle = np.arccos(np.clip(cos, -1.0, 1.0))
            total += angle * np.einsum("mk,mk->m", n, cross) / np.maximum(length, 1e-300)
        result[p_index, t_index] = np.abs(total) / (2.0 * math.pi)
    partly = ~front & facing & (np.einsum("pk,ptk->pt", normals, -to_point) > 0)
    if partly.any():
        p_index, t_index = np.nonzero(partly)
        d = -to_point[p_index, t_index]
        r2 = np.einsum("mk,mk->m", d, d)
        cos_i = np.einsum("mk,mk->m", normals[p_index], d) / np.sqrt(r2)
        cos_j = np.einsum("mk,mk->m", tri_normals[t_index], -d) / np.sqrt(r2)
        result[p_index, t_index] = np.clip(cos_i * cos_j * tri_area[t_index] / (math.pi * r2), 0.0, 1.0)
    return result


def _point_to_points(points, normals, area_src, targets, target_normals, target_area) -> "np.ndarray":
    """(P, T) the point-to-point kernel cos θi cos θj A_j / (π r²), for grouped sources (a coarse fallback)."""
    import numpy as np

    d = targets[None, :, :] - points[:, None, :]
    r2 = np.maximum(np.einsum("ptk,ptk->pt", d, d), 1e-300)
    r = np.sqrt(r2)
    cos_i = np.einsum("pk,ptk->pt", normals, d) / r
    cos_j = -np.einsum("tk,ptk->pt", target_normals, d) / r
    # A target closer than its own size: the kernel would pass the solid angle it can subtend.
    kernel = np.clip(cos_i, 0.0, None) * np.clip(cos_j, 0.0, None) * target_area[None, :] / (math.pi * r2)
    return np.minimum(kernel, 0.5 * np.clip(cos_i, 0.0, None))


class _Blockers:
    """Every surface triangle of the part, in a grid of boxes, for segment-versus-triangle tests."""

    def __init__(self, corners: "np.ndarray", cells: int = 8):
        import numpy as np

        self.corners = corners
        low, high = corners.min(axis=(0, 1)), corners.max(axis=(0, 1))
        span = np.maximum(high - low, 1e-9)
        centre = corners.mean(axis=1)
        key = np.minimum(((centre - low) / span * cells).astype(np.int64), cells - 1)
        flat = (key[:, 0] * cells + key[:, 1]) * cells + key[:, 2]
        self.groups = [np.flatnonzero(flat == k) for k in np.unique(flat)]
        self.box_low = np.array([corners[g].min(axis=(0, 1)) for g in self.groups])
        self.box_high = np.array([corners[g].max(axis=(0, 1)) for g in self.groups])
        self.diagonal = float(np.linalg.norm(high - low))

    def blocked(self, start: "np.ndarray", end: "np.ndarray") -> "np.ndarray":
        """(S,) whether each segment start -> end passes through a surface triangle on its way."""
        import numpy as np

        d = end - start
        hit = np.zeros(len(start), dtype=bool)
        eps = 1e-9 * max(self.diagonal, 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = 1.0 / np.where(np.abs(d) > 1e-300, d, 1e-300)
        for group, low, high in zip(self.groups, self.box_low, self.box_high):
            t0 = (low[None, :] - eps - start) * inverse
            t1 = (high[None, :] + eps - start) * inverse
            enter = np.minimum(t0, t1).max(axis=1)
            leave = np.maximum(t0, t1).min(axis=1)
            candidates = np.flatnonzero(~hit & (enter <= leave) & (leave >= 0.0) & (enter <= 1.0))
            if not len(candidates):
                continue
            tri = self.corners[group]
            for chunk in range(0, len(candidates), 4096):
                rays = candidates[chunk:chunk + 4096]
                hit[rays] |= _segments_hit(start[rays], d[rays], tri)
        return hit


def _segments_hit(origin: "np.ndarray", direction: "np.ndarray", tri: "np.ndarray") -> "np.ndarray":
    """Möller-Trumbore: whether each segment origin + t direction, 0 < t < 1, crosses any of the triangles."""
    import numpy as np

    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    out = np.zeros(len(origin), dtype=bool)
    step = max(1, 2_000_000 // max(len(tri), 1))
    for start in range(0, len(origin), step):
        o = origin[start:start + step, None, :]
        d = direction[start:start + step, None, :]
        p = np.cross(d, e2[None])
        det = np.einsum("rtk,tk->rt", p, e1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - tri[None, :, 0]
        u = np.einsum("rtk,rtk->rt", s, p) * inv
        q = np.cross(s, e1[None])
        v = np.einsum("rtk,rtk->rt", d, q) * inv
        t = np.einsum("tk,rtk->rt", e2, q) * inv
        inside = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-6) & (t < 1 - 1e-6)
        out[start:start + step] = inside.any(axis=1)
    return out


def view_factors(corners: "np.ndarray", area: "np.ndarray", normal: "np.ndarray", centroid: "np.ndarray",
                 patch: "np.ndarray", blockers: "np.ndarray | None") -> tuple["np.ndarray", dict]:
    """(patches, patches) view factors between the patches the triangles make up, obstruction included.

    ``corners``, ``area``, ``normal``, ``centroid``: the radiating triangles; ``patch``: each one's patch;
    ``blockers``: every surface triangle of the part (T, 3, 3) that may stand between them, or None.
    Reciprocity is imposed and no row sums past 1. Returns the matrix and notes (method, rays cast).
    """
    import numpy as np

    count = int(patch.max()) + 1 if len(patch) else 0
    patch_area = np.bincount(patch, weights=area, minlength=count)
    notes: dict = {"patches": count, "triangles": int(len(area))}
    # The unobstructed view from every triangle's centroid to every triangle, summed into patches.
    if len(area) <= MAX_SOURCES:
        sources, s_normal, s_area, s_patch = centroid, normal, area, patch
        notes["method"] = "contour integral from each triangle's centroid"
        exact = True
    else:
        # Too many triangles: group them (each group a point with its area-weighted normal) and use the kernel.
        groups = patches_of(centroid, area, patch, limit=MAX_SOURCES)
        n_groups = int(groups.max()) + 1
        s_area = np.bincount(groups, weights=area, minlength=n_groups)
        sources = np.stack([np.bincount(groups, weights=area * centroid[:, k], minlength=n_groups) for k in range(3)], axis=1) / s_area[:, None]
        s_normal = np.stack([np.bincount(groups, weights=area * normal[:, k], minlength=n_groups) for k in range(3)], axis=1)
        s_normal /= np.maximum(np.linalg.norm(s_normal, axis=1), 1e-300)[:, None]
        s_patch = np.zeros(n_groups, dtype=np.int64)
        s_patch[groups] = patch
        notes["method"] = f"point-to-point kernel between {n_groups} groups of triangles"
        exact = False
    raw = np.zeros((count, count))
    chunk = max(1, 400_000 // max(len(area), 1))
    for start in range(0, len(sources), chunk):
        stop = start + chunk
        if exact:
            block = _point_to_triangles(sources[start:stop], s_normal[start:stop], corners, centroid, normal, area)
        else:
            block = _point_to_points(sources[start:stop], s_normal[start:stop], s_area[start:stop], sources, s_normal, s_area)
        # Summed into the target's patches, weighted by the source's area.
        targets = patch if exact else s_patch
        per_patch = np.zeros((block.shape[0], count))
        np.add.at(per_patch.T, targets, block.T)
        np.add.at(raw, s_patch[start:stop], s_area[start:stop, None] * per_patch)
    F = raw / np.maximum(patch_area, 1e-300)[:, None]

    # Obstruction: a few points of each patch joined to a few of the other's, each segment tested.
    rays = 0
    if blockers is not None and len(blockers) and count > 1:
        points = []
        for i in range(count):
            members = np.flatnonzero(patch == i)
            take = members[np.linspace(0, len(members) - 1, min(RAY_POINTS, len(members))).round().astype(np.int64)]
            # Off the surface by a hair along its normal, so a segment does not start on its own triangle.
            points.append(centroid[take] + 1e-6 * max(1.0, float(np.sqrt(patch_area[i]))) * normal[take])
        pairs = np.argwhere(np.triu(F + F.T, k=0) > 0)
        if len(pairs):
            starts, ends, owner = [], [], []
            for k, (i, j) in enumerate(pairs):
                a, b = points[i], points[j]
                grid_a = np.repeat(a, len(b), axis=0)
                grid_b = np.tile(b, (len(a), 1))
                starts.append(grid_a)
                ends.append(grid_b)
                owner.append(np.full(len(grid_a), k))
            start_all, end_all, owner_all = np.concatenate(starts), np.concatenate(ends), np.concatenate(owner)
            blocked = _Blockers(blockers).blocked(start_all, end_all)
            rays = int(len(start_all))
            clear = 1.0 - np.bincount(owner_all, weights=blocked.astype(float), minlength=len(pairs)) / np.bincount(owner_all, minlength=len(pairs))
            for (i, j), share in zip(pairs, clear):
                F[i, j] *= share
                if i != j:
                    F[j, i] *= share
    notes["rays"] = rays

    # Reciprocity (A_i F_ij = A_j F_ji, the mean of the two), then no row past 1.
    exchange = patch_area[:, None] * F
    exchange = 0.5 * (exchange + exchange.T)
    F = exchange / np.maximum(patch_area, 1e-300)[:, None]
    over = F.sum(axis=1)
    scale = np.where(over > 1.0, 1.0 / np.maximum(over, 1e-300), 1.0)
    F *= scale[:, None]
    notes["largest_row_sum"] = float(over.max()) if count else 0.0
    return F, notes


# -- assembling ---------------------------------------------------------------------------------------


def _node_weights(space, rows: "np.ndarray", area: "np.ndarray", patch: "np.ndarray", count: int):
    """W (nodes, patches): ∫ over each patch of each node's shape function on a flat triangle (a quadratic
    triangle's corners integrate to 0 and its mid-edge nodes to A/3; a linear one's corners to A/3)."""
    import numpy as np
    from scipy import sparse

    triangles = space.boundary_quadratic[rows]
    nodes = triangles[:, 3:6] if triangles.shape[1] == 6 else triangles[:, :3]
    data = np.repeat(area / 3.0, 3)
    W = sparse.coo_matrix((data, (nodes.ravel(), np.repeat(patch, 3))), shape=(space.scalar_count, count))
    return W.tocsr()


def assemble(space: "FemSpace", rows_of: list["np.ndarray"], emissivity: list[float], ambient: list[float],
             exchange: list[bool], *, log=None) -> Radiation:
    """The radiation of a study on ``space``: per entry its boundary rows (indices into
    ``space.boundary_quadratic``), ε, the ambient (°C) and whether it exchanges with the other such faces."""
    import numpy as np

    radiation = Radiation(space=space, entries=len(rows_of))
    s2s = [i for i, flag in enumerate(exchange) if flag]
    for index, rows in enumerate(rows_of):
        if index in s2s:
            continue
        facets = space.facets_of_rows(np.asarray(rows, dtype=np.int64))
        radiation.ambient.append(Ambient(space.scalar.boundary(facets), float(emissivity[index]), float(ambient[index]), index))
    if not s2s:
        return radiation
    rows = np.concatenate([np.asarray(rows_of[i], dtype=np.int64) for i in s2s])
    entry_of = np.concatenate([np.full(len(rows_of[i]), i) for i in s2s])
    corners, area, normal, centroid = surface_triangles(space, rows)
    face = space.volume.boundary_ordinal[rows] if space.volume is not None else entry_of
    patch = patches_of(centroid, area, face * 10_000 + entry_of)
    count = int(patch.max()) + 1
    every = np.arange(len(space.boundary_quadratic))
    blockers = space.dof_locations[space.boundary_quadratic[every][:, :3]]
    F, notes = view_factors(corners, area, normal, centroid, patch, blockers)
    if log:
        log(f"radiation: {count} patches, view factors by {notes['method']}, {notes['rays']} rays for obstruction")
    patch_area = np.bincount(patch, weights=area, minlength=count)
    patch_entry = np.zeros(count, dtype=np.int64)
    patch_entry[patch] = entry_of
    eps = np.array([emissivity[i] for i in patch_entry], dtype=float)
    ea = np.array([SIGMA * (ambient[i] + KELVIN) ** 4 for i in patch_entry], dtype=float)
    to_ambient = np.clip(1.0 - F.sum(axis=1), 0.0, 1.0)
    # J = ε E + (1-ε)(F J + F∞ E∞); q = J - F J - F∞ E∞.
    I = np.eye(count)
    A = I - (1.0 - eps)[:, None] * F
    inverse = np.linalg.inv(A)
    G = (I - F) @ inverse @ np.diag(eps)
    h = (I - F) @ inverse @ ((1.0 - eps) * to_ambient * ea) - to_ambient * ea
    radiation.enclosure = Enclosure(
        W=_node_weights(space, rows, area, patch, count), area=patch_area, entry=patch_entry, emissivity=eps,
        ambient_power=ea, G=G, h=h, F=F, to_ambient=to_ambient, notes=notes,
    )
    return radiation


def entry_view_factors(radiation: Radiation) -> list[list[float]] | None:
    """The view factors between the study's radiation entries (area-weighted over their patches), or None."""
    import numpy as np

    enc = radiation.enclosure
    if enc is None:
        return None
    n = radiation.entries
    out = np.zeros((n, n))
    for i in range(n):
        rows = enc.entry == i
        if not rows.any():
            continue
        weights = enc.area[rows] / enc.area[rows].sum()
        for j in range(n):
            out[i, j] = float(weights @ enc.F[np.ix_(rows, enc.entry == j)].sum(axis=1))
    return out.tolist()


# -- Newton on the T⁴ ---------------------------------------------------------------------------------


def newton_step(A, residual: "np.ndarray", free: "np.ndarray", radiation: Radiation, T: "np.ndarray",
                warnings: list[str], *, method: str | None = None, scale: float = 1.0) -> "np.ndarray":
    """The Newton correction on the free DOF: (A + scale × exchange tangent) δ = -residual, A sparse
    (conduction, films, the surroundings' tangent, and a capacity term in a time step)."""
    import numpy as np
    from scipy import sparse

    tangent = radiation.exchange_tangent(T)
    if tangent is None:
        from cadgen._internal.fea import operators

        delta = np.zeros(len(T))
        rhs = np.zeros(len(T))
        rhs[free] = -residual[free]
        delta[free], _ = operators.solve_spd(A, rhs, free, None, None, warnings, method=method)
        return delta
    from scipy.sparse.linalg import splu

    W, G, c = tangent
    c = scale * c
    Wf = W[free]
    n, m = len(free), G.shape[0]
    # Bordered: A δ + W t = b;  -t + G s = 0;  s - diag(c) Wᵀ δ = 0.
    block = sparse.bmat([
        [A[free][:, free], Wf, None],
        [None, -sparse.identity(m), sparse.csr_matrix(G)],
        [-(sparse.diags(c) @ Wf.T), None, sparse.identity(m)],
    ], format="csc")
    rhs = np.concatenate([-residual[free], np.zeros(2 * m)])
    solution = splu(block).solve(rhs)
    delta = np.zeros(len(T))
    delta[free] = solution[:n]
    return delta


def newton_solve(base, load: "np.ndarray", x: "np.ndarray", free: "np.ndarray", radiation: Radiation,
                 warnings: list[str], *, scale: float = 1.0, method: str | None = None) -> tuple["np.ndarray", int]:
    """Solve base x - load + scale × radiation(x) = 0 on the free DOF by Newton, from ``x`` (fixed DOF set).

    ``base`` is the sparse linear part (conduction and films; or C + dt K in a time step, with ``scale``
    dt). The step is damped so no temperature falls below absolute zero. Returns the state and the
    iterations taken.
    """
    import numpy as np

    x = np.array(x, dtype=float)
    span = max(1.0, float(np.ptp(x)) if len(x) else 1.0)
    iterations, change = 0, 0.0
    for iterations in range(1, MAX_NEWTON + 1):
        residual = base @ x - load + scale * radiation.residual(x)
        A = (base + scale * radiation.local_tangent(x)).tocsr()
        delta = newton_step(A, residual, free, radiation, x, warnings, method=method, scale=scale)
        # Damped: never past half the way to absolute zero in one step.
        falling = delta < 0
        alpha = 1.0
        if falling.any():
            room = (x[falling] + KELVIN) / -delta[falling]
            alpha = min(1.0, 0.5 * float(room.min())) if room.min() < 2.0 else 1.0
        x = x + alpha * delta
        change = float(np.abs(alpha * delta).max()) if len(delta) else 0.0
        span = max(span, float(np.ptp(x)))
        if change <= NEWTON_TOL * max(span, float(np.abs(x + KELVIN).max())):
            break
    else:
        warnings.append(f"the radiation's Newton iterations stopped after {MAX_NEWTON} with a last change of {change:.2g} °C")
    return x, iterations
