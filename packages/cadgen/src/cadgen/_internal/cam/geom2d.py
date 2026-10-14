"""2D geometry the planners share: sections of the part at a height, offsets, booleans, polygon <-> path rings.

* :class:`Sections` slices the part's tessellation (in a setup's WCS) at a height ``z`` and returns the material
  there as shapely polygons (even-odd from the slice's closed rings). Slicing the mesh rather than the B-rep keeps it
  fast and robust; its error is the tessellation's deflection (0.01 mm by default), which the checks' tolerances
  allow for. A slice through a vertex (a floor) is nudged up 1e-7 mm: the material just above it.
* :func:`footprint` is a set of triangles projected onto the WCS XY plane (a floor face's outline).
* :func:`offset` buffers with round joins at a chord tolerance (:func:`quad_segs`); :func:`rings` lists a region's
  boundary rings oriented for climb or conventional milling: climb keeps the material on the right of travel
  (with a clockwise spindle), so a ring with material outside it (a pocket wall) runs counter-clockwise and a ring
  around material (an island, an outside profile) runs clockwise.

Stdlib at import; numpy and shapely inside.
"""

from __future__ import annotations

import math

__all__ = ["Sections", "footprint", "offset", "quad_segs", "rings", "ring_length", "polygons_of"]


def quad_segs(radius: float, tolerance: float) -> int:
    """Segments per quarter circle so a buffered arc of ``radius`` stays within ``tolerance`` of the true arc."""
    if radius <= tolerance:
        return 2
    step = 2.0 * math.acos(max(-1.0, 1.0 - tolerance / radius))
    return max(2, min(256, int(math.ceil((math.pi / 2) / max(step, 1e-6)))))


def polygons_of(geometry) -> list:
    """The polygons of any shapely geometry (empty, a polygon, a multipolygon, a collection)."""
    import shapely

    if geometry is None or geometry.is_empty:
        return []
    return [part for part in shapely.get_parts(geometry) if part.geom_type == "Polygon" and not part.is_empty]


def offset(geometry, distance: float, *, tolerance: float = 0.01, radius: float | None = None):
    """``geometry`` grown (positive) or shrunk (negative) by ``distance`` with round joins; arcs within
    ``tolerance`` of true for a corner of ``radius`` (default: the distance)."""
    segments = quad_segs(abs(radius if radius is not None else distance) or 1.0, tolerance)
    return geometry.buffer(distance, quad_segs=segments, join_style="round")


def rings(region, *, climb: bool = True) -> list:
    """Every boundary ring of ``region`` as an (N, 2) closed array, oriented for ``climb`` (or conventional),
    exteriors first. ``region`` is where the tool centre may go: its exterior has material outside it, its holes
    have material inside them."""
    import numpy as np
    from shapely.geometry.polygon import orient

    out = []
    for polygon in polygons_of(region):
        # orient(1.0): exterior counter-clockwise, holes clockwise = material on the right = climb.
        oriented = orient(polygon, 1.0 if climb else -1.0)
        out.append(np.asarray(oriented.exterior.coords))
        out.extend(np.asarray(ring.coords) for ring in oriented.interiors)
    return out


def ring_length(ring) -> float:
    import numpy as np

    ring = np.asarray(ring)
    return float(np.linalg.norm(np.diff(ring, axis=0), axis=1).sum())


def footprint(vertices, triangles):
    """The union of ``triangles`` (indices into ``vertices``, (N, 3) WCS) projected onto XY."""
    import numpy as np
    import shapely

    tris = np.asarray(vertices)[np.asarray(triangles)][:, :, :2]
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    area = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    tris = tris[area > 1e-12]
    if not len(tris):
        return shapely.Polygon()
    closed = np.concatenate([tris, tris[:, :1]], axis=1)
    return shapely.union_all(shapely.polygons(closed)).buffer(0)


class Sections:
    """Material sections of a mesh at heights; built once per setup, cached per height."""

    def __init__(self, vertices, triangles):
        import numpy as np

        self.vertices = np.asarray(vertices, dtype=float)
        self.triangles = np.asarray(triangles, dtype=np.int64)
        corners = self.vertices[self.triangles]
        self.zmin = corners[:, :, 2].min(axis=1)
        self.zmax = corners[:, :, 2].max(axis=1)
        self._heights = np.unique(self.vertices[:, 2])
        self._cache: dict[float, object] = {}
        self.open_pieces = 0

    @property
    def top(self) -> float:
        return float(self.zmax.max())

    @property
    def bottom(self) -> float:
        return float(self.zmin.min())

    def at(self, z: float):
        """The material at height ``z`` as a shapely (Multi)Polygon (empty above or below the part)."""
        key = round(float(z), 7)
        if key not in self._cache:
            self._cache[key] = self._slice(float(z))
        return self._cache[key]

    def _slice(self, z: float):
        import numpy as np
        import shapely

        # A slice through a vertex (a floor, a step's edge) is taken a hair above it, so the slice is the material
        # just over that height and every wall standing on it is cut.
        for _ in range(20):
            k = int(np.searchsorted(self._heights, z))
            near = [self._heights[i] for i in (k - 1, k) if 0 <= i < len(self._heights)]
            if not any(abs(h - z) < 1e-9 for h in near):
                break
            z += 1e-7
        crossing = (self.zmin < z) & (self.zmax > z)
        corners = self.vertices[self.triangles[crossing]]
        if not len(corners):
            return shapely.Polygon()
        segments = []
        for a_index, b_index in ((0, 1), (1, 2), (2, 0)):
            a, b = corners[:, a_index], corners[:, b_index]
            # Canonical endpoint order by coordinates, so the two triangles sharing an edge compute the same point.
            swap = (a[:, 2] > b[:, 2]) | ((a[:, 2] == b[:, 2]) & ((a[:, 0] > b[:, 0]) | ((a[:, 0] == b[:, 0]) & (a[:, 1] > b[:, 1]))))
            lo = np.where(swap[:, None], b, a)
            hi = np.where(swap[:, None], a, b)
            cross = (lo[:, 2] < z) & (hi[:, 2] > z)
            t = np.where(cross, (z - lo[:, 2]) / np.where(cross, hi[:, 2] - lo[:, 2], 1.0), 0.0)
            point = lo[:, :2] + (hi[:, :2] - lo[:, :2]) * t[:, None]
            segments.append((cross, point))
        (c0, p0), (c1, p1), (c2, p2) = segments
        starts = np.where(c0[:, None], p0, p1)
        ends = np.where((c0 & c1)[:, None], p1, p2)
        lines = np.stack([starts, ends], axis=1)
        lines = lines[np.linalg.norm(lines[:, 1] - lines[:, 0], axis=1) > 1e-12]
        merged = shapely.line_merge(shapely.multilinestrings(lines))
        closed, open_ = [], []
        for piece in shapely.get_parts(merged):
            coords = shapely.get_coordinates(piece)
            if len(coords) >= 4 and np.allclose(coords[0], coords[-1], atol=1e-9):
                closed.append(coords)
            else:
                open_.append(piece)
        if open_:
            # A crack in the tessellation: snap to a fine grid and join again.
            snapped = shapely.line_merge(shapely.set_precision(shapely.union_all(open_), 1e-6))
            for piece in shapely.get_parts(snapped):
                coords = shapely.get_coordinates(piece)
                if len(coords) >= 4 and np.allclose(coords[0], coords[-1], atol=1e-6):
                    closed.append(coords)
                else:
                    self.open_pieces += 1
        filled = shapely.Polygon()
        for coords in closed:
            ring = shapely.Polygon(coords)
            if not ring.is_valid:
                ring = ring.buffer(0)
            if ring.area > 1e-12:
                filled = filled.symmetric_difference(ring)
        return filled
