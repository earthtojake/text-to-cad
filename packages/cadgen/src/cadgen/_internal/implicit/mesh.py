"""Contour a signed distance field into a triangle mesh with surface nets.

Surface nets, not marching cubes: one vertex per grid cell the surface
crosses and one quad per crossed grid edge joining the four cells around
it. It needs no case table, is watertight by construction, and gives
evenly sized triangles for the same grid. The vertex is placed the way
dual contouring places it: where the tangent planes at the cell's edge
crossings meet (a least-squares solve, regularised toward the crossings'
mean and kept inside the cell), so a box edge or a hole's rim comes out
sharp instead of chamfered by the grid -- the field supplies an exact
normal at every crossing, which is what makes this cheap here. Normals
come from the field's gradient, so a sphere shades like a sphere at any
grid size; where a face normal disagrees with the field's by more than
``crease_deg`` (the two sides of an edge) the vertex is split so the edge
shades sharp.

Every vertex carries the id of the leaf that owns it -- the primitive in
the author's code whose surface it lies on -- and every triangle the leaf
at its centroid. That is what the GLB writer turns into one named node per
leaf, so a part meshed here maps back to the lines that made it.

numpy only. The field is evaluated in chunks so a fine grid does not hold
its intermediates all at once.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field as dataclass_field

import numpy as np

from cadgen._internal.implicit.field import Bounds, Field, leaves

__all__ = ["Mesh", "contour", "grid_for", "sample", "MAX_SAMPLES"]

#: The largest grid a single contour will sample (points, not cells). A 300^3
#: grid is 27M points; past this a resolution is refused rather than swapping.
MAX_SAMPLES = 40_000_000
_CHUNK = 1 << 20


@dataclass
class Mesh:
    """A triangle mesh in the field's own coordinates (CAD Z-up, the author's units)."""

    vertices: np.ndarray  # (V, 3) float64
    triangles: np.ndarray  # (T, 3) int64, counter-clockwise seen from outside
    normals: np.ndarray  # (V, 3) float64, unit
    vertex_leaf: np.ndarray  # (V,) int32, index into ``leaves``
    triangle_leaf: np.ndarray  # (T,) int32
    leaves: list[Field] = dataclass_field(default_factory=list)
    resolution: float = 0.0
    grid: tuple[int, int, int] = (0, 0, 0)
    bounds: Bounds | None = None
    timings: dict = dataclass_field(default_factory=dict)

    @property
    def triangle_count(self) -> int:
        return int(len(self.triangles))

    @property
    def vertex_count(self) -> int:
        return int(len(self.vertices))

    def area(self) -> float:
        v = self.vertices
        t = self.triangles
        cross = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
        return float(0.5 * np.linalg.norm(cross, axis=1).sum())

    def volume(self) -> float:
        """Enclosed volume by the divergence theorem (positive for an outward-facing closed mesh)."""
        v = self.vertices
        t = self.triangles
        return float(abs(np.einsum("ij,ij->i", v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum()) / 6.0)

    def centroid(self) -> tuple[float, float, float]:
        """Centre of mass of the enclosed solid (uniform density)."""
        v = self.vertices
        t = self.triangles
        a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
        vol6 = np.einsum("ij,ij->i", a, np.cross(b, c))
        total = vol6.sum()
        if abs(total) < 1e-12:
            return self.bounds.center if self.bounds else (0.0, 0.0, 0.0)
        centre = ((a + b + c) * vol6[:, None]).sum(axis=0) / (4.0 * total)
        return tuple(map(float, centre))

    def flat_shaded(self) -> tuple[np.ndarray, np.ndarray]:
        """Unwelded ``(T*3, 3)`` positions and per-facet unit normals (what an STL stores)."""
        v = self.vertices[self.triangles]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        length = np.linalg.norm(n, axis=1, keepdims=True)
        return v.reshape(-1, 3), n / np.where(length < 1e-20, 1.0, length)


def grid_for(bounds: Bounds, resolution: float, *, pad_cells: int = 2) -> tuple[np.ndarray, tuple[int, int, int], float]:
    """The sampling grid: origin, point counts per axis, and the cell size actually used."""
    if resolution <= 0:
        raise ValueError("resolution must be positive (the size of a grid cell, in the model's units)")
    size = np.asarray(bounds.size, float)
    cells = np.maximum(np.ceil(size / resolution).astype(int), 1) + 2 * pad_cells
    points = cells + 1
    if int(np.prod(points)) > MAX_SAMPLES:
        raise ValueError(
            f"resolution {resolution:g} needs a {cells[0]}x{cells[1]}x{cells[2]} grid "
            f"({int(np.prod(points)):,} samples); raise the resolution above "
            f"{bounds.diagonal / (MAX_SAMPLES ** (1 / 3) - 2 * pad_cells) * math.sqrt(3):.3g} or shrink the bounds"
        )
    origin = np.asarray(bounds.min, float) - pad_cells * resolution
    return origin, (int(points[0]), int(points[1]), int(points[2])), float(resolution)


def sample(field: Field, origin: np.ndarray, shape: tuple[int, int, int], h: float) -> np.ndarray:
    """Evaluate the field on the grid, ``(nx, ny, nz)`` distances, chunked."""
    nx, ny, nz = shape
    xs = origin[0] + h * np.arange(nx)
    ys = origin[1] + h * np.arange(ny)
    zs = origin[2] + h * np.arange(nz)
    values = np.empty(nx * ny * nz, dtype=np.float64)
    total = nx * ny * nz
    ids = {id(leaf): i for i, leaf in enumerate(leaves(field))}
    for start in range(0, total, _CHUNK):
        stop = min(start + _CHUNK, total)
        flat = np.arange(start, stop)
        i, rem = np.divmod(flat, ny * nz)
        j, k = np.divmod(rem, nz)
        pts = np.stack([xs[i], ys[j], zs[k]], axis=1)
        values[start:stop] = field._eval(pts, ids)[0]
    return values.reshape(nx, ny, nz)


def _crossings(values: np.ndarray, origin: np.ndarray, h: float, axis: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The grid edges along ``axis`` the surface crosses: the crossing mask over
    all edges, and for the crossing ones their ``(i, j, k)`` and the point where
    the surface cuts them (linear interpolation of the two samples)."""
    lo = values[tuple(slice(0, -1) if a == axis else slice(None) for a in range(3))]
    hi = values[tuple(slice(1, None) if a == axis else slice(None) for a in range(3))]
    cross = (lo <= 0.0) != (hi <= 0.0)
    idx = np.argwhere(cross)
    a, b = lo[cross], hi[cross]
    denominator = a - b
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(np.abs(denominator) < 1e-30, 0.5, a / denominator)
    point = origin + h * idx.astype(np.float64)
    point[:, axis] += h * np.clip(t, 0.0, 1.0)
    return cross, idx, point


#: How strongly a cell's vertex is pulled toward the mean of its crossings when the
#: crossing normals alone do not pin it (a flat face: one plane, two free directions).
_QEF_REGULARISATION = 0.05


def contour(
    field: Field,
    *,
    resolution: float | None = None,
    bounds: Bounds | None = None,
    crease_deg: float = 35.0,
    project_steps: int = 1,
) -> Mesh:
    """Mesh the zero level set of ``field``.

    resolution: grid cell size in the model's units. Omitted, a 1/120th of the
        bounding diagonal.
    bounds: where to look. Omitted, the field's own (conservative) bounds.
    crease_deg: the angle between a face normal and the field's normal past
        which a vertex is split so the edge shades sharp.
    project_steps: Newton steps that pull each vertex onto the true surface
        after placement (a vertex at a sharp edge already sits on it and stays).
    """
    t0 = time.perf_counter()
    timings: dict[str, float] = {}
    box = bounds or field.bounds
    if box.diagonal <= 0 or not math.isfinite(box.diagonal) or box.diagonal > 1e8:
        raise ValueError(
            "the field has no finite bounds: an unbounded field (a half space) must be intersected "
            "with a bounded solid, and a custom field must declare bounds"
        )
    h = float(resolution) if resolution else box.diagonal / 120.0
    origin, shape, h = grid_for(box, h)
    all_leaves = leaves(field)
    field.prepare(h)

    values = sample(field, origin, shape, h)
    timings["sample_s"] = time.perf_counter() - t0
    t1 = time.perf_counter()

    cells_shape = tuple(n - 1 for n in shape)
    n_cells = int(np.prod(cells_shape))
    strides = np.array([cells_shape[1] * cells_shape[2], cells_shape[2], 1], dtype=np.int64)
    accum = np.zeros((n_cells, 3), dtype=np.float64)
    count = np.zeros(n_cells, dtype=np.int64)
    # The QEF's normal equations per cell: sum of n n^T (3x3) and of n (n . p) (3).
    ata = np.zeros((n_cells, 9), dtype=np.float64)
    atb = np.zeros((n_cells, 3), dtype=np.float64)
    crossings = []
    for axis in range(3):
        cross, edge_idx, point = _crossings(values, origin, h, axis)
        crossings.append(cross)
        if len(edge_idx) == 0:
            continue
        normal = field.normal(point)
        outer = (normal[:, :, None] * normal[:, None, :]).reshape(-1, 9)
        rhs = normal * np.einsum("ij,ij->i", normal, point)[:, None]
        # An edge along `axis` at grid index (i, j, k) borders the four cells whose
        # other two indices are (n-1, n) each; add its crossing to all of them.
        other = [a for a in range(3) if a != axis]
        for da in (0, 1):
            for db in (0, 1):
                cell = edge_idx.copy()
                cell[:, other[0]] -= da
                cell[:, other[1]] -= db
                inside = ((cell >= 0) & (cell < np.asarray(cells_shape))).all(axis=1)
                flat = (cell[inside] @ strides)
                count += np.bincount(flat, minlength=n_cells)
                for c in range(3):
                    accum[:, c] += np.bincount(flat, weights=point[inside, c], minlength=n_cells)
                    atb[:, c] += np.bincount(flat, weights=rhs[inside, c], minlength=n_cells)
                for c in range(9):
                    ata[:, c] += np.bincount(flat, weights=outer[inside, c], minlength=n_cells)
    count = count.reshape(cells_shape)
    accum = accum.reshape((*cells_shape, 3))
    ata = ata.reshape((*cells_shape, 3, 3))
    atb = atb.reshape((*cells_shape, 3))
    active = count > 0
    cell_index = np.full(cells_shape, -1, dtype=np.int64)
    n_active = int(active.sum())
    if n_active == 0:
        empty = np.zeros((0, 3))
        return Mesh(empty, np.zeros((0, 3), np.int64), empty, np.zeros(0, np.int32), np.zeros(0, np.int32), all_leaves, h, cells_shape, box, timings)
    cell_index[active] = np.arange(n_active)
    mass = accum[active] / count[active][:, None]
    # Dual contouring's placement: the point closest to every crossing's tangent
    # plane, pulled gently toward the mass point so a flat face (one plane) and a
    # single edge (two) still have a unique answer, then kept inside its cell.
    reg = _QEF_REGULARISATION
    system = ata[active] + reg * np.eye(3)[None, :, :]
    target = atb[active] + reg * mass
    vertices = np.linalg.solve(system, target[..., None])[..., 0]

    # Pull each vertex onto the surface along the gradient; keep it inside its cell
    # so the connectivity the grid decided stays valid.
    cell_ijk = np.argwhere(active)
    cell_lo = origin + h * cell_ijk
    cell_hi = cell_lo + h
    vertices = np.clip(vertices, cell_lo, cell_hi)
    for _ in range(max(0, int(project_steps))):
        d = field.distance(vertices)
        g = field.gradient(vertices, h * 1e-3)
        gg = np.einsum("ij,ij->i", g, g)
        step = g * (d / np.where(gg < 1e-20, 1.0, gg))[:, None]
        vertices = np.clip(vertices - step, cell_lo, cell_hi)

    # Quads: one per crossed interior edge, wound about the edge so the outside faces out.
    quads = []
    for axis in range(3):
        cross = crossings[axis]
        other = [a for a in range(3) if a != axis]
        # Interior edges only: the four cells around them all exist.
        interior = [slice(None)] * 3
        interior[other[0]] = slice(1, cross.shape[other[0]] - 1)
        interior[other[1]] = slice(1, cross.shape[other[1]] - 1)
        edge_idx = np.argwhere(cross[tuple(interior)])
        if len(edge_idx) == 0:
            continue
        edge_idx[:, other[0]] += 1
        edge_idx[:, other[1]] += 1
        lo = values[tuple(edge_idx.T)]
        inside_low = lo <= 0.0
        # Right-handed loop of the four cells about +axis: (a-1,b-1) (a,b-1) (a,b) (a-1,b)
        # in (other[0], other[1]) order for x and z edges; y edges take the (z, x) plane.
        if axis == 1:
            loop = [(-1, -1), (-1, 0), (0, 0), (0, -1)]
        else:
            loop = [(-1, -1), (0, -1), (0, 0), (-1, 0)]
        corners = []
        for da, db in loop:
            c = edge_idx.copy()
            c[:, other[0]] += da
            c[:, other[1]] += db
            corners.append(cell_index[tuple(c.T)])
        quad = np.stack(corners, axis=1)
        quad = np.where(inside_low[:, None], quad, quad[:, ::-1])
        quads.append(quad)
    if not quads:
        empty = np.zeros((0, 3))
        return Mesh(empty, np.zeros((0, 3), np.int64), empty, np.zeros(0, np.int32), np.zeros(0, np.int32), all_leaves, h, cells_shape, box, timings)
    quad = np.concatenate(quads, axis=0)
    assert (quad >= 0).all(), "a crossed edge borders an inactive cell"
    triangles = np.concatenate([quad[:, [0, 1, 2]], quad[:, [0, 2, 3]]], axis=0)
    # Drop degenerate triangles (two corners in one cell cannot happen with distinct cells, but be safe).
    keep = (triangles[:, 0] != triangles[:, 1]) & (triangles[:, 1] != triangles[:, 2]) & (triangles[:, 0] != triangles[:, 2])
    triangles = triangles[keep]
    timings["contour_s"] = time.perf_counter() - t1
    t2 = time.perf_counter()

    normals = field.normal(vertices)
    _, vertex_leaf = field.evaluate(vertices)
    centroids = vertices[triangles].mean(axis=1)
    _, triangle_leaf = field.evaluate(centroids)
    triangle_leaf = _settle_leaf_boundaries(triangles, triangle_leaf)

    # Crease: where a face's normal disagrees with the field's normal at a corner,
    # give that corner its own vertex carrying the face normal.
    if crease_deg > 0 and len(triangles):
        v = vertices[triangles]
        face_n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        length = np.linalg.norm(face_n, axis=1, keepdims=True)
        face_n = face_n / np.where(length < 1e-20, 1.0, length)
        cos_limit = math.cos(math.radians(crease_deg))
        corner_n = normals[triangles]  # (T, 3, 3)
        agree = np.einsum("tcj,tj->tc", corner_n, face_n)
        split = agree < cos_limit
        if split.any():
            n_split = int(split.sum())
            t_idx, c_idx = np.nonzero(split)
            new_vertices = vertices[triangles[t_idx, c_idx]]
            new_normals = face_n[t_idx]
            new_leaf = vertex_leaf[triangles[t_idx, c_idx]]
            base = len(vertices)
            triangles = triangles.copy()
            triangles[t_idx, c_idx] = base + np.arange(n_split)
            vertices = np.concatenate([vertices, new_vertices])
            normals = np.concatenate([normals, new_normals])
            vertex_leaf = np.concatenate([vertex_leaf, new_leaf])
    timings["attributes_s"] = time.perf_counter() - t2
    timings["total_s"] = time.perf_counter() - t0

    return Mesh(
        vertices=vertices,
        triangles=triangles.astype(np.int64),
        normals=normals,
        vertex_leaf=vertex_leaf.astype(np.int32),
        triangle_leaf=triangle_leaf.astype(np.int32),
        leaves=all_leaves,
        resolution=h,
        grid=cells_shape,
        bounds=box,
        timings=timings,
    )


def _settle_leaf_boundaries(triangles: np.ndarray, triangle_leaf: np.ndarray, rounds: int = 3) -> np.ndarray:
    """Give each triangle the leaf most of its edge neighbours have, a few times over.

    Through a smooth blend two leaves are nearly equidistant over a band a
    cell or two wide, and the per-centroid decision dithers there. A triangle
    outvoted by two of its three neighbours takes their leaf, which removes
    the speckle and leaves the boundary where the majority already put it.
    """
    if len(triangles) == 0:
        return triangle_leaf
    edges = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges.sort(axis=1)
    owner = np.tile(np.arange(len(triangles)), 3)
    key = edges[:, 0].astype(np.int64) * (int(triangles.max()) + 1) + edges[:, 1]
    order = np.argsort(key, kind="stable")
    key, owner = key[order], owner[order]
    same = key[1:] == key[:-1]
    first, second = owner[:-1][same], owner[1:][same]
    # Both directions of every shared edge, grouped by triangle, three slots each.
    src = np.concatenate([first, second])
    nbr = np.concatenate([second, first])
    by_src = np.argsort(src, kind="stable")
    src, nbr = src[by_src], nbr[by_src]
    start = np.searchsorted(src, np.arange(len(triangles)))
    slot = np.arange(len(src)) - start[src]
    keep = slot < 3
    neighbours = np.full((len(triangles), 3), -1, dtype=np.int64)
    neighbours[src[keep], slot[keep]] = nbr[keep]
    valid = neighbours >= 0
    labels = triangle_leaf.copy()
    for _ in range(rounds):
        n = np.where(valid, labels[np.where(valid, neighbours, 0)], -1)
        n0, n1, n2 = n[:, 0], n[:, 1], n[:, 2]
        pick = np.where(n0 == n1, n0, np.where(n0 == n2, n0, np.where(n1 == n2, n1, -1)))
        changed = (pick >= 0) & (pick != labels)
        if not changed.any():
            break
        labels = np.where(changed, pick, labels)
    return labels.astype(np.int32)
