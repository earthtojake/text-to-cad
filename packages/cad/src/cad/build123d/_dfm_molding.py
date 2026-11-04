"""Injection molding's measurements of exact geometry (``cad._internal.dfm.molding`` says what they are for).

Every part of the document is measured along the pull on its B-rep, each finding at a face's ref:

- **draft**: per face, its angle to the pull -- exact for a plane, for a cylinder or cone whose axis runs
  along the pull (zero, the half-angle), the least over points sampled on the face otherwise -- and which
  way it opens: ``+pull`` (released by the half withdrawing along the pull), ``-pull``, ``none`` (zero
  draft, either half) or ``split`` (the face turns through the pull: the parting line crosses it);
- **undercuts**: points sampled on every face shot along the way the face opens with exact rays; a point
  the part blocks is trapped (a zero-draft one only when both ways are blocked). Trapped faces that touch
  are one feature; what releases it is found by more rays (``meshops_molding.classify_undercut``);
- **thickness**: the rolling-ball wall under every sampled point (the exact ray straight through bounds
  it), the nominal wall (the area-weighted median), each face's thin and thick readings, abrupt changes;
- **ribs**: two opposite planar faces close together, both standing on one base face (a concave edge or
  a concave fillet between), taller than thick; **bosses**: a convex cylinder standing on a face square
  to its axis, with the coaxial hole inside it if it has one;
- **corners**: every internal corner -- a concave edge with no fillet (radius 0) or a concave fillet
  face (its radius) -- with its radius over the wall meeting there;
- **projection**: the part triangulated (each triangle naming its face) and projected on the parting
  plane, the covered area counted on a raster sized to the part; its spans and depth;
- **parting**: the outline's silhouette (where faces opening one way meet faces opening the other, the
  zero-draft walls on the outline, the curved faces turning through the pull there), whether one flat
  plane takes it and at what height, and the depth either side.

With ``candidates`` the pulls are ranked instead: x, y, z and the part's principal axes. A family that
raises leaves ``{"error": ...}`` and the report says so (``partial``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cad._internal import meshops_molding as ops
from cad.build123d import _dfm_brep

__all__ = ["measure"]

#: Points sampled per part, spread over its faces by area (each face at least ``_LEAST_PER_FACE``).
_SAMPLES = 2400
_LEAST_PER_FACE = 12
_FACE_POINTS = 6000
#: Rays the undercut release search spends on one part, at most (largest features first).
_RELEASE_RAYS = 200000
_MOST_PER_FACE = 400
#: The denser set of surface points the rolling ball is tested against.
_BALL_POINTS = 6000
#: The sampled points the wall thickness is read at, at most (each a rolling ball solved exactly).
_THICK_POINTS = 1600
#: Candidates sample fewer points: six pulls, each its own undercut rays.
_CANDIDATE_SAMPLES = 1200
#: A face reads as thick when its thickest point is this many times the nominal wall (reported, not judged).
_THICK_RATIO = 1.5
#: At most this many items per family, worst first.
_ITEMS = 300
_HIST_DEG = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


def _r(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits) + 0.0


def _xyz(point: Any) -> list[float]:
    return [round(float(value), 4) + 0.0 for value in point]


def _safe(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - a family that fails is reported, never raised
        detail = f"{type(exc).__name__}: {exc}".splitlines()[0]
        return {"error": detail[:300]}


# --- one part's geometry ---------------------------------------------------------------------------------


def _samples(face: Any, count: int) -> list[tuple[np.ndarray, np.ndarray, float]]:
    """About ``count`` points spread evenly over ``face``, each ON the surface, with its outward normal and the
    area it stands for: the face's triangulation, each triangle cut into n x n by its LONGEST edge against the
    spacing ``count`` asks for (so a long thin triangle down a bore is sampled along its length, not once at
    its middle), each sub-triangle's centre mapped back to the surface through the triangle's UV."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location

    box = face.bounding_box()
    deflection = max(1e-3, 0.02 * max(box.size.X, box.size.Y, box.size.Z))
    BRepMesh_IncrementalMesh(face.wrapped, deflection, False, 0.5, True)
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
    if triangulation is None or triangulation.NbTriangles() == 0:
        return []
    trsf = location.Transformation()
    count_nodes = triangulation.NbNodes()
    nodes = np.array([[(p := triangulation.Node(i).Transformed(trsf)).X(), p.Y(), p.Z()]
                      for i in range(1, count_nodes + 1)])
    uvs = (np.array([(triangulation.UVNode(i).X(), triangulation.UVNode(i).Y()) for i in range(1, count_nodes + 1)])
           if triangulation.HasUVNodes() else None)
    corners = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]) - 1
    a, b, c = nodes[corners[:, 0]], nodes[corners[:, 1]], nodes[corners[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = float(areas.sum())
    if total <= 0.0:
        return []
    spacing = math.sqrt(total / max(1, count))
    longest = np.max(np.stack([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                               np.linalg.norm(a - c, axis=1)]), axis=0)
    # Every sub-triangle centre first (cheap), then as many as the face asks for, evenly, and only those
    # mapped onto the surface.
    picks: list[tuple[int, float, float, float]] = []
    for index, ((ia, ib, ic), area, edge) in enumerate(zip(corners, areas, longest)):
        if area <= 0.0:
            continue
        cuts = int(min(24, max(1, math.ceil(max(edge / spacing, math.sqrt(area / spacing ** 2))))))
        weights = []
        for i in range(cuts):
            for j in range(cuts - i):
                weights.append(((i + 1 / 3) / cuts, (j + 1 / 3) / cuts))
                if i + j <= cuts - 2:
                    weights.append(((i + 2 / 3) / cuts, (j + 2 / 3) / cuts))
        # A sliver needs points along its length, not n x n of them: keep as many as its area asks for (at
        # least one per spacing along its longest edge), evenly through the sub-triangles.
        wanted = int(min(len(weights), max(cuts, math.ceil(area / spacing ** 2))))
        if wanted < len(weights):
            weights = [weights[k] for k in np.unique(np.linspace(0, len(weights) - 1, wanted).astype(int))]
        share = float(area) / len(weights)
        picks.extend((index, wa, wb, share) for wa, wb in weights)
    if len(picks) > max(count, 1):
        # A face meshed finer than its share of points (a small face of a detailed part): its points thinned
        # evenly to the share, each standing for the area it now covers, so the points grow with the area
        # asked for, not with the triangles.
        total_share = sum(pick[3] for pick in picks)
        picks = [picks[k] for k in np.unique(np.linspace(0, len(picks) - 1, max(count, 1)).astype(int))]
        scale = total_share / sum(pick[3] for pick in picks)
        picks = [(index, wa, wb, share * scale) for index, wa, wb, share in picks]
    from OCP.BRepGProp import BRepGProp_Face

    props = BRepGProp_Face(face.wrapped)
    found: list[tuple[np.ndarray, np.ndarray, float]] = []
    for index, wa, wb, share in picks:
        ia, ib, ic = corners[index]
        wc = 1.0 - wa - wb
        if uvs is not None:
            u, v = wa * uvs[ia] + wb * uvs[ib] + wc * uvs[ic]
            point, normal = _dfm_brep.point_normal(face, float(u), float(v), props)
        else:
            point = wa * nodes[ia] + wb * nodes[ib] + wc * nodes[ic]
            normal = np.cross(nodes[ib] - nodes[ia], nodes[ic] - nodes[ia])
            normal = normal / (np.linalg.norm(normal) or 1.0)
        found.append((point, normal, share))
    return found


@dataclass
class _Geometry:
    """One part, read once for every family: its faces' surfaces and areas, points sampled over them, its
    exact rays, its edges and which faces they join."""

    part: _dfm_brep.Part
    budget: int = _SAMPLES
    faces: list[Any] = field(default_factory=list)
    surfaces: list[Any] = field(default_factory=list)
    areas: np.ndarray = field(default_factory=lambda: np.zeros(0))
    points: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    normals: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    weights: np.ndarray = field(default_factory=lambda: np.zeros(0))
    owner: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))   # face ordinal, 1-based
    spacing: np.ndarray = field(default_factory=lambda: np.zeros(0))
    _edges: list[Any] | None = None
    _rays: Any = None
    _mesh: Any = None
    _intersectors: dict[int, Any] | None = None
    _links: dict[int, list[tuple[int, Any]]] | None = None
    _grids: dict | None = None
    _by_face: Any = None
    _vertices: dict[int, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.faces = self.part.faces()
        self.surfaces = [_dfm_brep.surface(face) for face in self.faces]
        self.areas = np.array([float(face.area) for face in self.faces])
        total = float(self.areas.sum()) or 1.0
        box = self.part.shape.bounding_box()
        self.lo = np.array([box.min.X, box.min.Y, box.min.Z])
        self.hi = np.array([box.max.X, box.max.Y, box.max.Z])
        self.diagonal = float(np.linalg.norm(self.hi - self.lo)) or 1.0
        self.eps = min(max(1e-4 * self.diagonal, 1e-5), 0.01)
        points, normals, weights, owner, spacing = [], [], [], [], []
        # Each face at least _LEAST_PER_FACE points, fewer (down to two) on a part of many faces, so the points
        # -- and the rays cast from them -- grow with the faces no faster than _FACE_POINTS in all.
        least = max(2, min(_LEAST_PER_FACE, _FACE_POINTS // max(1, len(self.faces))))
        for ordinal, (face, area) in enumerate(zip(self.faces, self.areas), start=1):
            count = int(min(_MOST_PER_FACE, max(least, round(self.budget * area / total))))
            found = _samples(face, count) if area > 0 else []
            for point, normal, share in found:
                points.append(point)
                normals.append(normal)
                weights.append(share)
                owner.append(ordinal)
                spacing.append(math.sqrt(max(area, 1e-12) / max(len(found), 1)))
        self.points = np.array(points).reshape(-1, 3)
        self.normals = np.array(normals).reshape(-1, 3)
        self.weights = np.array(weights)
        self.owner = np.array(owner, dtype=int)
        self.spacing = np.array(spacing)

    @property
    def rays(self) -> Any:
        if self._rays is None:
            self._rays = _dfm_brep.Rays(self.part.shape)
        return self._rays

    @property
    def mesh(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The part triangulated, each triangle naming its face: what projections and the rolling ball use."""
        if self._mesh is None:
            deflection = min(max(self.diagonal / 2000.0, 1e-3), 0.5)
            self._mesh = _dfm_brep.triangles(self.part.shape, deflection, 0.3)
        return self._mesh

    @property
    def edges(self) -> list[Any]:
        if self._edges is None:
            self._edges = _dfm_brep.edges(self.part)
        return self._edges

    def ref(self, ordinal: int) -> str:
        return self.part.ref("face", int(ordinal))

    def _mesh_crosses(self, ray: np.ndarray, face: np.ndarray, origins: np.ndarray, directions: np.ndarray
                      ) -> np.ndarray:
        """For (ray, face) pairs (face indices 0-based): whether the ray's line meets one of the face's
        triangles (``mesh``), each widened by a tenth of itself, at or beyond the ray's start."""
        if self._by_face is None:
            vertices, triangles, owners = self.mesh
            order = np.argsort(owners, kind="stable")
            counts = np.bincount(owners, minlength=len(self.faces) + 1)[1:]
            starts = np.concatenate([[0], np.cumsum(counts)[:-1]]).astype(int)
            a, b, c = (vertices[triangles[order, k]] for k in range(3))
            self._by_face = (starts, counts, a, b - a, c - a)
        starts, counts, a, e1, e2 = self._by_face
        per = counts[face]
        # Only a face of few triangles is screened (a large face is one exact test, cheaper than its
        # triangles); a face with none is left to the exact test.
        meshed = (per > 0) & (per <= 48)
        per = np.where(meshed, per, 0)
        found = ~meshed
        if not meshed.any():
            return found
        pair = np.repeat(np.arange(len(ray)), per)
        tri = np.repeat(starts[face], per) + np.arange(int(per.sum())) - np.repeat(np.cumsum(per) - per, per)
        d, o = directions[ray[pair]], origins[ray[pair]]
        p = np.cross(d, e2[tri])
        det = np.einsum("ij,ij->i", e1[tri], p)
        good = np.abs(det) > 1e-18
        inv = np.where(good, 1.0 / np.where(good, det, 1.0), 0.0)
        tv = o - a[tri]
        u = np.einsum("ij,ij->i", tv, p) * inv
        q = np.cross(tv, e1[tri])
        v = np.einsum("ij,ij->i", d, q) * inv
        t = np.einsum("ij,ij->i", e2[tri], q) * inv
        slack = 0.1
        reach = 1e-3 * self.diagonal
        hit = ~good | ((u >= -slack) & (v >= -slack) & (u + v <= 1 + slack) & (t > -reach))
        np.logical_or.at(found, pair[hit], True)
        return found

    def cast(self, origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        """The distance from each origin to the first face along its direction, inf for none."""
        return self.cast_faces(origins, directions)[0]

    def _grid(self, direction: np.ndarray) -> Any:
        """The faces' boxes seen along ``direction``: each box's shadow on the plane square to it, binned on a
        grid, so a ray along it meets only the boxes over the cell its origin projects to (cached per
        direction: the release search casts along a few dozen)."""
        key = tuple(np.round(direction, 9))
        if self._grids is None:
            self._grids = {}
        found = self._grids.get(key)
        if found is not None:
            return found
        u, v = ops.basis(direction)
        boxes = self.rays.boxes
        corners = np.stack([np.stack([boxes[:, 0 + 3 * i], boxes[:, 1 + 3 * j], boxes[:, 2 + 3 * k]], axis=1)
                            for i in (0, 1) for j in (0, 1) for k in (0, 1)], axis=1)       # (F, 8, 3)
        pu, pv = corners @ u, corners @ v
        low = np.stack([pu.min(axis=1), pv.min(axis=1)], axis=1)
        high = np.stack([pu.max(axis=1), pv.max(axis=1)], axis=1)
        origin = low.min(axis=0)
        span = np.maximum(high.max(axis=0) - origin, 1e-9)
        cells = int(min(128, max(4, 2 * math.sqrt(len(boxes)))))
        size = span / cells
        i0 = np.clip(((low - origin) / size).astype(int), 0, cells - 1)
        i1 = np.clip(((high - origin) / size).astype(int), 0, cells - 1)
        # Every (face, cell) its shadow covers, at once: a face's rows times its columns.
        rows, cols = i1[:, 0] - i0[:, 0] + 1, i1[:, 1] - i0[:, 1] + 1
        count = rows * cols
        face = np.repeat(np.arange(len(boxes)), count)
        local = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
        cell = (i0[face, 0] + local // cols[face]) * cells + (i0[face, 1] + local % cols[face])
        order = np.argsort(cell, kind="stable")
        bounds = np.searchsorted(cell[order], np.arange(cells * cells + 1))
        found = (u, v, origin, size, cells, (face[order], bounds))
        self._grids[key] = found
        return found

    def cast_faces(self, origins: np.ndarray, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """``cast``, with the ordinal of the face each ray first meets (0 for none). Rays sharing one
        direction meet only the boxes over their cell of that direction's grid (``_grid``); others are pruned
        by every face's box at once; then each meets its candidate faces exactly, nearest box first, until no
        nearer crossing can follow."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
        from OCP.IntCurvesFace import IntCurvesFace_Intersector

        o_all = np.asarray(origins, dtype=float).reshape(-1, 3)
        d_all = np.asarray(directions, dtype=float).reshape(-1, 3)
        d_all = d_all / np.where(np.linalg.norm(d_all, axis=1) > 0, np.linalg.norm(d_all, axis=1), 1.0)[:, None]
        found = np.full(len(o_all), np.inf)
        faces = np.zeros(len(o_all), dtype=int)
        if not len(o_all):
            return found, faces
        rays = self.rays
        boxes = rays.boxes
        skip = 1e-3 * self.eps
        if self._intersectors is None:
            self._intersectors = {}
        # Rays grouped by direction: a group of a few or more casts over that direction's grid.
        keys = np.round(d_all, 9)
        groups: dict[tuple, list[int]] = {}
        for ray, key in enumerate(map(tuple, keys)):
            groups.setdefault(key, []).append(ray)
        grid_of = {}
        if len(boxes) > 64:
            for key, members in groups.items():
                if len(members) >= 4:
                    grid_of[key] = self._grid(d_all[members[0]])

        for key, members in groups.items():
            members = np.asarray(members)
            grid = grid_of.get(key)
            # Every (ray, face) pair whose box the ray might cross: the faces over each ray's grid cell, or every
            # face where the direction has no grid.
            if grid is not None:
                u, v, origin, size, cells, (binned, bounds) = grid
                fa = (o_all[members] @ u - origin[0]) / size[0]
                fb = (o_all[members] @ v - origin[1]) / size[1]
                inside = (fa >= -1e-6) & (fa <= cells + 1e-6) & (fb >= -1e-6) & (fb <= cells + 1e-6)
                members = members[inside]  # outside every box's shadow: the line meets no face
                cell = (np.clip(fa[inside].astype(int), 0, cells - 1) * cells
                        + np.clip(fb[inside].astype(int), 0, cells - 1))
                counts = bounds[cell + 1] - bounds[cell]
                ray = np.repeat(members, counts)
                firsts = np.repeat(bounds[cell], counts)
                face = binned[firsts + np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts, counts)]
            else:
                ray = np.repeat(members, len(boxes))
                face = np.tile(np.arange(len(boxes)), len(members))
            if not len(ray):
                continue
            o, d = o_all[ray], d_all[ray]
            lows, highs = boxes[face, :3], boxes[face, 3:]
            flat = np.abs(d) <= 1e-300
            with np.errstate(divide="ignore", invalid="ignore"):
                inverse = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, d))
                t1, t2 = (lows - o) * inverse, (highs - o) * inverse
            lo = np.where(flat, -np.inf, np.minimum(t1, t2)).max(axis=1)
            hi = np.where(flat, np.inf, np.maximum(t1, t2)).min(axis=1)
            across = np.all(~flat | ((lows <= o) & (o <= highs)), axis=1)
            keep = across & (lo <= hi) & (hi >= skip)
            ray, face, enter = ray[keep], face[keep], np.maximum(lo[keep], skip)
            if len(ray):
                # The face's triangles first, every pair at once: a face none of whose triangles the ray
                # meets (each widened by a tenth, beyond any chord's sag) it does not cross, and is left
                # out of the exact intersections -- a ray through a row of contacts tests the few it hits.
                crosses = self._mesh_crosses(ray, face, o_all, d_all)
                ray, face, enter = ray[crosses], face[crosses], enter[crosses]
            order = np.lexsort((enter, ray))
            ray, face, enter = ray[order], face[order], enter[order]
            cuts = np.flatnonzero(np.diff(ray)) + 1
            for begin, stop in zip(np.concatenate([[0], cuts]), np.concatenate([cuts, [len(ray)]])):
                if begin >= stop:
                    continue
                index = int(ray[begin])
                line = gp_Lin(gp_Pnt(*o_all[index]), gp_Dir(*d_all[index]))
                best, which = math.inf, 0
                for k in range(begin, stop):
                    if enter[k] > best:
                        break
                    candidate = int(face[k])
                    intersector = self._intersectors.get(candidate)
                    if intersector is None:
                        intersector = self._intersectors[candidate] = IntCurvesFace_Intersector(
                            rays.faces[candidate], 1e-7)
                    intersector.Perform(line, skip, best if math.isfinite(best) else 1e9)
                    if not intersector.IsDone():
                        continue
                    for hit in range(1, intersector.NbPnt() + 1):
                        w = float(intersector.WParameter(hit))
                        if skip <= w < best:
                            best, which = w, candidate + 1
                if which:
                    found[index], faces[index] = best, which
        return found, faces

    def vertices(self, ordinal: int) -> np.ndarray:
        """A face's vertices and its sampled points: what its extent along a direction is read from."""
        if ordinal not in self._vertices:
            face = self.faces[ordinal - 1]
            corners = [np.array([v.X, v.Y, v.Z]) for v in face.vertices()]
            edge_points = []
            for edge in face.edges():
                for t in (0.25, 0.5, 0.75):
                    try:
                        at = edge.position_at(t)
                        edge_points.append(np.array([at.X, at.Y, at.Z]))
                    except Exception:  # noqa: BLE001 - a degenerate edge adds no point
                        continue
            own = self.points[self.owner == ordinal]
            found = np.vstack([np.array(corners + edge_points).reshape(-1, 3), own])
            if not len(found):
                # A closed face with no vertex, no edge and no sample: its box's corners stand for it.
                box = face.bounding_box()
                found = np.array([[x, y, z] for x in (box.min.X, box.max.X) for y in (box.min.Y, box.max.Y)
                                  for z in (box.min.Z, box.max.Z)])
            self._vertices[ordinal] = found
        return self._vertices[ordinal]

    def neighbours(self) -> dict[int, list[tuple[int, Any]]]:
        """Each face's neighbours across its edges, with the edge (read once)."""
        if self._links is not None:
            return self._links
        found: dict[int, list[tuple[int, Any]]] = {}
        for edge in self.edges:
            a, b = edge.faces
            found.setdefault(a, []).append((b, edge))
            found.setdefault(b, []).append((a, edge))
        self._links = found
        return found


# --- draft -----------------------------------------------------------------------------------------------


@dataclass
class _FaceDraft:
    ordinal: int
    draft: float          # degrees: the least over the face
    lean: float           # the face's mean n . p (its opening's sign)
    opens: str            # +pull, -pull, none, split
    exact: bool
    zero_area: float      # area under zero_tol
    sample_drafts: np.ndarray


def _face_drafts(geo: _Geometry, pull: np.ndarray, zero_tol: float) -> list[_FaceDraft]:
    tol = math.sin(math.radians(zero_tol))
    drafts: list[_FaceDraft] = []
    along_all = geo.normals @ pull
    for ordinal, (surface, area) in enumerate(zip(geo.surfaces, geo.areas), start=1):
        mine = geo.owner == ordinal
        along = along_all[mine]
        weights = geo.weights[mine]
        sample = np.degrees(np.arcsin(np.clip(np.abs(along), 0.0, 1.0)))
        exact = False
        if surface.kind == "plane" and surface.normal is not None:
            lean = float(np.asarray(surface.normal) @ pull)
            draft = math.degrees(math.asin(min(1.0, abs(lean))))
            sample = np.full(len(along), draft)
            exact = True
        elif surface.kind in ("cylinder", "cone") and surface.axis is not None and \
                abs(abs(float(np.asarray(surface.axis) @ pull)) - 1.0) < 1e-9:
            draft = 0.0 if surface.kind == "cylinder" else abs(float(surface.half_angle_deg or 0.0))
            lean = float(np.average(along, weights=weights)) if len(along) else 0.0
            if surface.kind == "cylinder":
                lean = 0.0
            sample = np.full(len(along), draft)
            exact = True
        else:
            draft = float(sample.min()) if len(sample) else 90.0
            lean = float(np.average(along, weights=weights)) if len(along) else 0.0
        if exact:
            opens = "none" if draft < zero_tol else ("+pull" if lean > 0 else "-pull")
            zero_area = float(area) if draft < zero_tol else 0.0
        else:
            up, down = bool((along > tol).any()), bool((along < -tol).any())
            opens = "split" if up and down else "+pull" if up else "-pull" if down else "none"
            zero_area = float(weights[sample < zero_tol].sum() / max(weights.sum(), 1e-12) * area) if len(weights) else 0.0
        drafts.append(_FaceDraft(ordinal, float(draft), lean, opens, exact, zero_area, sample))
    return drafts


def _centroid(geo: _Geometry, ordinal: int) -> list[float]:
    mine = geo.owner == ordinal
    if not mine.any():
        return _xyz(geo.vertices(ordinal).mean(axis=0))
    points, weights = geo.points[mine], geo.weights[mine]
    mean = (points * weights[:, None]).sum(axis=0) / max(weights.sum(), 1e-12)
    return _xyz(points[int(np.argmin(np.linalg.norm(points - mean, axis=1)))])


def _extent(geo: _Geometry, ordinal: int, direction: np.ndarray) -> tuple[float, float]:
    heights = geo.vertices(ordinal) @ direction
    return float(heights.min()), float(heights.max())


def _draft(geos: list[_Geometry], drafts: list[list[_FaceDraft]], pull: np.ndarray, wall_limit: float,
           zero_tol: float) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    total = wall = zero = drafted = drafted_moment = 0.0
    opening = {"+pull": 0.0, "-pull": 0.0, "none": 0.0, "split": 0.0}
    histogram: dict[str, float] = {}
    edges = _HIST_DEG + [wall_limit]
    zero_faces: list[dict[str, Any]] = []
    for geo, faces in zip(geos, drafts):
        total += float(geo.areas.sum())
        for face in faces:
            area = float(geo.areas[face.ordinal - 1])
            if face.draft >= wall_limit or area <= 0:
                continue
            wall += area
            opening[face.opens] += area
            low, high = _extent(geo, face.ordinal, pull)
            item = {"location": geo.ref(face.ordinal), "draft_deg": _r(face.draft, 3), "area_mm2": _r(area, 2),
                    "opens": face.opens, "surface": geo.surfaces[face.ordinal - 1].kind,
                    "exact": face.exact, "depth_mm": _r(high - low, 3), "xyz": _centroid(geo, face.ordinal)}
            items.append(item)
            mine = geo.owner == face.ordinal
            share = geo.weights[mine] / max(float(geo.weights[mine].sum()), 1e-12) * area
            for lo_deg, hi_deg in zip(edges[:-1], edges[1:]):
                if hi_deg <= lo_deg:
                    continue
                band = float(share[(face.sample_drafts >= lo_deg) & (face.sample_drafts < hi_deg)].sum())
                if band > 0:
                    key = f"{lo_deg:g}-{hi_deg:g}deg"
                    histogram[key] = round(histogram.get(key, 0.0) + band, 2)
            if face.zero_area > 0:
                zero += face.zero_area
                zero_faces.append({"location": item["location"], "area_mm2": _r(face.zero_area, 2),
                                   "centroid_xyz": item["xyz"], "surface": item["surface"],
                                   "extent_along_pull_mm": item["depth_mm"], "opens_toward": face.opens})
            else:
                drafted += area
                drafted_moment += area * float(np.sum(face.sample_drafts * share) / max(share.sum(), 1e-12))
    items.sort(key=lambda item: (item["draft_deg"], -(item["area_mm2"] or 0)))
    zero_faces.sort(key=lambda face: -(face["area_mm2"] or 0))
    result: dict[str, Any] = {
        "pull_axis": [_r(v) for v in pull], "wall_limit_deg": wall_limit, "zero_tol_deg": zero_tol,
        "wall_area_mm2": _r(wall, 2), "wall_area_pct_of_surface": _r(100 * wall / total, 1) if total else 0.0,
        "non_wall_area_mm2": _r(total - wall, 2), "wall_draft_histogram_mm2": histogram,
        "wall_area_by_opening_mm2": {key: _r(value, 2) for key, value in opening.items()},
        "zero_draft_wall_area_mm2": _r(zero, 2), "zero_draft_face_count": len(zero_faces),
        "zero_draft_tangent_area_mm2": 0.0,
        "zero_draft_tangent_note": "exact geometry: a curved face tangent to the pull along a line has no area there",
        "drafted_wall_area_mm2": _r(drafted, 2),
        "drafted_wall_mean_draft_deg": _r(drafted_moment / drafted, 3) if drafted else None,
        "largest_zero_draft_faces": zero_faces[:8],
        "wall_face_count": len(items),
        "items": items[:_ITEMS],
        "method": ("per face on the B-rep: a plane's angle to the pull exactly, a cylinder's or cone's whose axis "
                   "runs along the pull exactly (zero, the half-angle), any other face the least over points "
                   "sampled on it; faces at or above wall_limit_deg are not walls"),
    }
    measured = [item for item in items if item["opens"] != "split"]
    if measured:
        worst = measured[0]
        result["min_wall_draft"] = {"draft_deg": worst["draft_deg"], "area_mm2": worst["area_mm2"],
                                    "location": worst["location"], "location_xyz": worst["xyz"],
                                    "opens_toward": worst["opens"], "surface": worst["surface"],
                                    "exact": worst["exact"]}
        result["lowest_draft_wall_faces"] = [
            {key: item[key] for key in ("location", "draft_deg", "area_mm2", "surface", "opens")}
            | {"location_xyz": item["xyz"]} for item in measured[:8]]
    else:
        result["note"] = "no wall faces below wall_limit_deg for this pull axis"
    return result


# --- undercuts -------------------------------------------------------------------------------------------


@dataclass
class _Trapped:
    trapped: np.ndarray       # per sample
    blocker: np.ndarray       # the face that blocks it, 0 for none
    zero: np.ndarray          # per sample: zero draft (both ways tried)


def _trap(geo: _Geometry, pull: np.ndarray, zero_tol: float) -> _Trapped:
    tol = math.sin(math.radians(zero_tol))
    along = geo.normals @ pull
    origins = geo.points + geo.normals * geo.eps
    sign = np.where(along >= 0, 1.0, -1.0)
    zero = np.abs(along) <= tol
    first, first_face = geo.cast_faces(origins, sign[:, None] * pull[None, :])
    blocked = np.isfinite(first)
    blocker = np.where(blocked, first_face, 0)
    if zero.any():
        index = np.nonzero(zero & blocked)[0]
        other, other_face = geo.cast_faces(origins[index], -sign[index, None] * pull[None, :])
        both = np.isfinite(other)
        blocked[index] = both
        blocker[index] = np.where(both, blocker[index], 0)
    return _Trapped(blocked, blocker, zero)


def _features(geo: _Geometry, trapped: _Trapped) -> list[list[int]]:
    """Trapped faces (at least two trapped points, or a fiftieth of the face), grouped where they touch."""
    faces = []
    for ordinal in range(1, len(geo.faces) + 1):
        mine = geo.owner == ordinal
        count = int((trapped.trapped & mine).sum())
        share = float(geo.weights[trapped.trapped & mine].sum()) / max(float(geo.weights[mine].sum()), 1e-12)
        if count >= 2 or (count and share >= 0.02):
            faces.append(ordinal)
    chosen = set(faces)
    links = geo.neighbours()
    groups: list[list[int]] = []
    seen: set[int] = set()
    for start in faces:
        if start in seen:
            continue
        group, stack = [], [start]
        seen.add(start)
        while stack:
            face = stack.pop()
            group.append(face)
            for other, _edge in links.get(face, []):
                if other in chosen and other not in seen:
                    seen.add(other)
                    stack.append(other)
        groups.append(sorted(group))
    return groups


def _undercut_part(geo: _Geometry, pull: np.ndarray, zero_tol: float, classify: bool = True) -> dict[str, Any]:
    trapped = _trap(geo, pull, zero_tol)
    groups = _features(geo, trapped)
    in_group = np.isin(geo.owner, [face for group in groups for face in group])
    trapped_mask = trapped.trapped & in_group

    def counted_mask(group: list[int]) -> np.ndarray:
        return trapped_mask & np.isin(geo.owner, group)
    items: list[dict[str, Any]] = []
    releases: dict = {}
    spent = [0]

    def counted(origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        spent[0] += len(origins)
        return geo.cast(origins, directions)

    # The largest features first: a part of hundreds of them (a connector's contacts) spends its release
    # rays (_RELEASE_RAYS) on the largest, and says which it did not search ("unknown").
    order = sorted(groups, key=lambda group: -float(geo.weights[counted_mask(group)].sum()))
    for group in order:
        mine = counted_mask(group)
        area = float(geo.weights[mine].sum())
        per_face = {face: float(geo.weights[mine & (geo.owner == face)].sum()) for face in group}
        # The face that best names the undercut: the largest of those mostly trapped (a snap's underside,
        # not the strip of wall it shadows); else the largest trapped area.
        whole = {face: area for face, area in per_face.items()
                 if area >= 0.5 * float(geo.weights[geo.owner == face].sum())}
        largest = max(whole or per_face, key=(whole or per_face).get)
        points = geo.points[mine] + geo.normals[mine] * geo.eps
        normals = geo.normals[mine]
        item: dict[str, Any] = {"location": geo.ref(largest), "faces": [geo.ref(face) for face in group],
                                "trapped_area_mm2": _r(area, 2), "xyz": _xyz(geo.points[mine].mean(axis=0)),
                                "blocked_by": [geo.ref(face) for face in
                                               sorted({int(f) for f in trapped.blocker[mine] if f and f not in group})]}
        if classify:
            if spent[0] < _RELEASE_RAYS:
                release = ops.classify_undercut(points, normals, pull, counted, scale=geo.diagonal,
                                                zero_tol_deg=zero_tol, cache=releases)
            else:
                release = {"release": "unknown", "kind": None, "directions": [], "vectors": [], "angled": [],
                           "stroke_mm": None}
            item.update(_release_fields(release, geo.points[mine], pull))
        items.append(item)
    items.sort(key=lambda item: -(item["trapped_area_mm2"] or 0))
    leaning = trapped.trapped & ~trapped.zero & in_group
    zero = trapped.trapped & trapped.zero & in_group
    largest_faces = []
    for ordinal in sorted({int(f) for f in geo.owner[trapped_mask]}):
        mine = trapped_mask & (geo.owner == ordinal)
        largest_faces.append({"location": geo.ref(ordinal), "area_mm2": _r(float(geo.weights[mine].sum()), 2),
                              "centroid_xyz": _xyz(geo.points[mine].mean(axis=0))})
    largest_faces.sort(key=lambda face: -(face["area_mm2"] or 0))
    return {"items": items, "groups": groups, "area": float(geo.weights[trapped_mask].sum()),
            "surface": float(geo.areas.sum()),
            "faces": len({int(f) for f in geo.owner[trapped_mask]}), "leaning": float(geo.weights[leaning].sum()),
            "zero": float(geo.weights[zero].sum()), "largest": largest_faces}


def _release_fields(release: dict[str, Any], points: np.ndarray, pull: np.ndarray) -> dict[str, Any]:
    vectors = release.get("vectors") or []
    if vectors:
        side = np.asarray(vectors[0], dtype=float)
        across = np.cross(pull, side)
        across /= np.linalg.norm(across) or 1.0
    else:
        side, across = ops.basis(pull)
    heights, widths = points @ pull, points @ across
    return {"kind": release["kind"], "release": release["release"], "side_actions": release["directions"],
            "side_action_count": len(release["directions"]) if release["release"] == "side_action" else 0,
            "angled": any(release.get("angled") or []), "stroke_mm": _r(release.get("stroke_mm"), 3),
            "height_mm": _r(float(heights.max() - heights.min()), 3),
            "width_mm": _r(float(widths.max() - widths.min()), 3)}


def _undercuts(geos: list[_Geometry], pull: np.ndarray, zero_tol: float,
               parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if parts is None:
        parts = [_undercut_part(geo, pull, zero_tol) for geo in geos]
    items = sorted((item for part in parts for item in part["items"]), key=lambda item: -(item["trapped_area_mm2"] or 0))
    surface = sum(part["surface"] for part in parts)
    area = sum(part["area"] for part in parts)
    releases = [item.get("release") for item in items]
    result = {
        "pull_axis": [_r(v) for v in pull],
        "method": ("points sampled on every face, each shot along the way its face opens with exact rays (a "
                   "zero-draft point both ways); a blocked point is trapped; trapped faces that touch are one "
                   "feature, released by rays along slides round the parting plane (and tilted 45 deg), a "
                   "lifter's short move, or a collapsible core's; each part is tested against itself"),
        "candidate_area_mm2": _r(area, 2),
        "candidate_area_pct_of_surface": _r(100 * area / surface, 2) if surface else 0.0,
        "candidate_face_count": sum(part["faces"] for part in parts),
        "leaning_blocked_area_mm2": _r(sum(part["leaning"] for part in parts), 2),
        "trapped_zero_draft_area_mm2": _r(sum(part["zero"] for part in parts), 2),
        "largest_candidate_faces": sorted((face for part in parts for face in part["largest"]),
                                          key=lambda face: -(face["area_mm2"] or 0))[:8],
        "undercut_count": len(items),
        "external_count": sum(1 for item in items if item.get("kind") == "external"),
        "internal_count": sum(1 for item in items if item.get("kind") == "internal"),
        "side_action_count": sum(item.get("side_action_count") or 0 for item in items),
        "lifter_count": releases.count("lifter"),
        "collapsible_core_count": releases.count("collapsible_core"),
        "unreleasable_count": releases.count("none"),
        "unsearched_count": releases.count("unknown"),
        "items": items[:_ITEMS],
    }
    if len(geos) > 1:
        result["note"] = "several parts: each is tested against itself, none shadows another"
    return result


# --- thickness -------------------------------------------------------------------------------------------


@dataclass
class _Thickness:
    values: np.ndarray        # per sample, mm (nan unmeasured)
    edge_held: np.ndarray     # per sample: the ball is held by a face across a convex edge of its own face
    nominal: float | None
    per_face: dict[int, dict[str, Any]]


def _thickness_subset(geo: _Geometry) -> np.ndarray:
    """The sampled points the wall is read at: at most ``_THICK_POINTS``, shared among the faces by area (each
    face at least four), evenly through each face's own."""
    if len(geo.points) <= _THICK_POINTS:
        return np.arange(len(geo.points))
    total = float(geo.areas.sum()) or 1.0
    faces = len(geo.faces)
    # Each face at least four points while the faces leave room, one while they still do, else by area alone
    # (a part of thousands of small faces: its small faces unread, their walls their neighbours').
    least = 4 if 4 * faces <= _THICK_POINTS else 1 if faces <= _THICK_POINTS else 0
    chosen = []
    by_face = np.argsort(geo.owner, kind="stable")
    bounds = np.searchsorted(geo.owner[by_face], np.arange(1, faces + 2))
    for ordinal, area in enumerate(geo.areas, start=1):
        own = by_face[bounds[ordinal - 1]:bounds[ordinal]]
        want = int(min(len(own), max(least, round(_THICK_POINTS * area / total))))
        if not want:
            continue
        chosen.append(own[np.unique(np.linspace(0, len(own) - 1, want).astype(int))])
    return np.concatenate(chosen) if chosen else np.arange(0)


def _thickness_part(geo: _Geometry) -> _Thickness:
    subset = _thickness_subset(geo)
    points, normals, owner = geo.points[subset], geo.normals[subset], geo.owner[subset]
    # the exact ray straight through, cast from just inside the face
    ray = geo.cast(points - normals * geo.eps, -normals) + geo.eps
    vertices, triangles, owners = geo.mesh
    cap = np.full(len(geo.points), np.inf)
    for ordinal, surface in enumerate(geo.surfaces, start=1):
        if surface.concave is False and surface.kind in ("cylinder", "sphere", "torus"):
            bend = surface.minor_radius if surface.kind == "torus" else surface.radius
            cap[geo.owner == ordinal] = float(bend or np.inf)
    read, bound = ops.ball_thickness(points, normals, ray, vertices, triangles, others=geo.points,
                                     point_face=owner, triangle_face=owners, others_face=geo.owner,
                                     cap=cap[subset])
    values = np.full(len(geo.points), np.nan)
    values[subset] = read
    bound_all = np.full(len(geo.points), -1, dtype=int)
    bound_all[subset] = bound
    bound = bound_all
    convex: dict[int, set[int]] = {}
    for edge in geo.edges:
        a, b = edge.faces
        # A convex edge, or a tangent join onto a convex curved face (whose chords crease like an edge).
        if (not edge.concave and not edge.smooth) or (edge.smooth and (geo.surfaces[a - 1].concave is False
                                                                        or geo.surfaces[b - 1].concave is False)):
            convex.setdefault(a, set()).add(b)
            convex.setdefault(b, set()).add(a)
    held = np.array([index >= 0 and int(owners[index]) in convex.get(int(face), set())
                     for index, face in zip(bound, geo.owner)], dtype=bool)
    finite = np.isfinite(values)
    clean = finite & ~held
    if clean.any() and float(geo.weights[clean].sum()) >= 0.5 * float(geo.weights[finite].sum()):
        nominal = ops.weighted_median(values[clean], geo.weights[clean])
    else:
        nominal = ops.weighted_median(values, geo.weights)
    per_face: dict[int, dict[str, Any]] = {}
    for ordinal in range(1, len(geo.faces) + 1):
        mine = (geo.owner == ordinal) & finite
        if not mine.any():
            continue
        v, w = values[mine], geo.weights[mine]
        top = int(np.argmax(v))
        tidy = clean[mine]
        # Narrow: a face the ball cannot sit on -- most of its points held by a face round a convex edge, or
        # the face narrower (its area over its span) than twice the widest ball it holds.
        corners = geo.vertices(ordinal)
        span = 2.0 * float(np.linalg.norm(corners - corners.mean(axis=0), axis=1).max()) if len(corners) else 0.0
        width = float(geo.areas[ordinal - 1]) / span if span > 0 else 0.0
        narrow = (float(w[tidy].sum()) < 0.3 * float(w.sum())
                  or width < 2.0 * float(v.max()))
        if narrow:
            median = low = float(v.max())
        else:
            # Most of the face is clear of its outside edges: the area median of those points.
            median, low = ops.weighted_median(v[tidy], w[tidy]), ops.weighted_quantile(v[tidy], w[tidy], 0.1)
        per_face[ordinal] = {"median": median, "low": low, "max": float(v[top]), "at": geo.points[mine][top],
                             "narrow": narrow}
    links = geo.neighbours()
    nearest = ops.nearest_broad_all(list(range(1, len(geo.faces) + 1)),
                                    lambda face: [o for o, _e in links.get(face, [])],
                                    lambda face: face in per_face and not per_face[face]["narrow"])
    for ordinal, face in per_face.items():
        # A narrow face (a rib's top, a plate's end, a bore through a wall): every point is near an outside
        # edge and reads low, so it closes the wall its broad neighbours across those edges measure.
        if face["narrow"]:
            walls = [per_face[other]["median"] for other in convex.get(ordinal, set())
                     if other in per_face and not per_face[other]["narrow"]]
            if not walls:
                walls = [per_face[other]["median"] for other in nearest.get(ordinal, [])]
            if walls:
                face["median"] = face["low"] = float(np.median(walls))
                face["max"] = max(face["max"], face["median"])
    if per_face:
        # The nominal wall: the area median of the faces' own walls (a narrow face's taken from its neighbours),
        # so a chunky part whose points all sit near an outside edge still reads its section.
        nominal = ops.weighted_median(np.array([face["median"] for face in per_face.values()]),
                                      np.array([float(geo.areas[ordinal - 1]) for ordinal in per_face]))
    return _Thickness(values, held, nominal, per_face)


def _thickness(geos: list[_Geometry], thick: list[_Thickness]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    medians: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    nominals = []
    for geo, measured in zip(geos, thick):
        nominal = measured.nominal
        nominals.append({"part": geo.part.owner or geo.part.name, "nominal_mm": _r(nominal, 3)})
        if nominal is None or nominal <= 0:
            continue
        found = ops.transitions(geo.points, measured.values, geo.owner, ~measured.edge_held, geo.spacing, nominal)
        for ordinal, face in measured.per_face.items():
            item = {"location": geo.ref(ordinal), "thickness_mm": _r(face["median"], 3),
                    "min_mm": _r(face["low"], 3), "max_mm": _r(face["max"], 3),
                    "nominal_mm": _r(nominal, 3), "ratio_to_nominal": _r(face["max"] / nominal, 3),
                    "thin_ratio": _r((face["median"] or 0) / nominal, 3), "xyz": _xyz(face["at"])}
            if ordinal in found:
                change = found[ordinal]
                item["transition_ratio"] = _r(change["ratio"], 3)
                item["transition_mm"] = [_r(value, 3) for value in change["thickness"]]
            items.append(item)
            medians.append(face["median"])
            lows.append(face["low"])
            highs.append(face["max"])
            if face["max"] > _THICK_RATIO * nominal:
                sections.append({"location": item["location"], "thickness_mm": item["max_mm"],
                                 "ratio_to_nominal": item["ratio_to_nominal"], "xyz": item["xyz"]})
    values = np.concatenate([measured.values for measured in thick]) if thick else np.zeros(0)
    weights = np.concatenate([geo.weights for geo in geos]) if geos else np.zeros(0)
    thinnest = sorted(items, key=lambda item: item["thickness_mm"] if item["thickness_mm"] is not None else 1e18)
    thickest = sorted(items, key=lambda item: -(item["ratio_to_nominal"] or 0))
    abrupt = sorted((item for item in items if item.get("transition_ratio") is not None),
                    key=lambda item: item["transition_ratio"])
    chosen, seen = [], set()
    for item in [*thinnest[:_ITEMS // 3], *thickest[:_ITEMS // 3], *abrupt[:_ITEMS // 3]]:
        if id(item) not in seen:
            seen.add(id(item))
            chosen.append(item)
    sections.sort(key=lambda section: -(section["ratio_to_nominal"] or 0))
    nominal = nominals[0]["nominal_mm"] if len(nominals) == 1 else None
    result = {
        "nominal_mm": nominal if nominal is not None else _r(ops.weighted_median(values, weights), 3),
        "min_mm": _r(min(medians), 3) if medians else None,
        "min_point_mm": _r(min(lows), 3) if lows else None,
        "max_mm": _r(max(highs), 3) if highs else None,
        "median_mm": _r(ops.weighted_median(values, weights), 3),
        "ratio_max_nominal": _r(max(highs) / nominal, 3) if highs and nominal else None,
        "thick_ratio_reported": _THICK_RATIO,
        "thick_sections": sections[:20], "thick_section_count": len(sections),
        "sample_count": int(np.isfinite(values).sum()), "face_count": len(items),
        "items": chosen,
        "method": ("rolling ball: at each point sampled on the faces, the diameter of the largest ball touching "
                   "the surface there that stays inside the part, never more than the exact ray straight through; "
                   "a face's thickness_mm is the area median of its points, min_mm the 10th percentile, max_mm "
                   "the most; the nominal wall is the area median over the part, leaving out the points held by "
                   "a face round a convex edge (they read low)"),
    }
    if len(nominals) > 1:
        result["per_part"] = nominals
    return result


# --- ribs, bosses, corners -------------------------------------------------------------------------------


def _face_wall(thick: _Thickness, ordinal: int) -> float | None:
    face = thick.per_face.get(ordinal)
    return None if face is None else face["median"]


def _bases(geo: _Geometry, ordinal: int, links: dict[int, list[tuple[int, Any]]],
           square_to: np.ndarray, square: bool = True) -> list[tuple[int, float, int]]:
    """The planar faces a face stands on: (base ordinal, fillet radius (0 sharp), the fillet's ordinal or 0).
    A base meets the face at a concave edge, or across a concave fillet (cylinder or torus) both of whose
    joins are tangent. ``square``: the base's normal is square to ``square_to`` (a rib's); else along it."""
    found = []

    def fits(other: int) -> bool:
        surface = geo.surfaces[other - 1]
        if surface.kind != "plane" or surface.normal is None:
            return False
        lean = abs(float(np.asarray(surface.normal) @ square_to))
        return lean < math.sin(math.radians(20.0)) if square else lean > math.cos(math.radians(5.0))

    for other, edge in links.get(ordinal, []):
        if edge.concave and not edge.smooth and fits(other):
            found.append((other, 0.0, 0))
        elif edge.smooth:
            fillet = geo.surfaces[other - 1]
            if fillet.kind not in ("cylinder", "torus") or not fillet.concave:
                continue
            radius = float(fillet.minor_radius if fillet.kind == "torus" else fillet.radius or 0.0)
            for beyond, join in links.get(other, []):
                if beyond != ordinal and join.smooth and fits(beyond):
                    found.append((beyond, radius, other))
    return found


def _same_plane(geo: _Geometry, a: int, b: int) -> bool:
    if a == b:
        return True
    sa, sb = geo.surfaces[a - 1], geo.surfaces[b - 1]
    if sa.normal is None or sb.normal is None:
        return False
    na, nb = np.asarray(sa.normal), np.asarray(sb.normal)
    if float(na @ nb) < math.cos(math.radians(0.5)):
        return False
    return abs(float((np.asarray(sb.origin) - np.asarray(sa.origin)) @ na)) < 1e-3 * max(1.0, geo.diagonal * 1e-3)


def _ribs_part(geo: _Geometry, thick: _Thickness, drafts: list[_FaceDraft], nominal: float | None,
               used: set[int]) -> list[dict[str, Any]]:
    links = geo.neighbours()
    planes = [ordinal for ordinal, surface in enumerate(geo.surfaces, start=1)
              if surface.kind == "plane" and surface.normal is not None]
    bases = {ordinal: _bases(geo, ordinal, links, np.asarray(geo.surfaces[ordinal - 1].normal)) for ordinal in planes}
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    # Where rays from each candidate face, straight into the material, come out (the face opposite): one cast
    # for every candidate's points together.
    by_face = np.argsort(geo.owner, kind="stable")
    bounds = np.searchsorted(geo.owner[by_face], np.arange(1, len(geo.faces) + 2))
    standing = [a for a in planes if bases[a] and bounds[a] > bounds[a - 1]]
    index = np.concatenate([by_face[bounds[a - 1]:bounds[a]] for a in standing]) if standing else np.zeros(0, int)
    all_distance, all_hit = geo.cast_faces(geo.points[index] - geo.normals[index] * geo.eps, -geo.normals[index])
    offsets = np.concatenate([[0], np.cumsum([bounds[a] - bounds[a - 1] for a in standing])]).astype(int)
    for position, a in enumerate(standing):
        na = np.asarray(geo.surfaces[a - 1].normal)
        mine = geo.owner == a
        distance = all_distance[offsets[position]:offsets[position + 1]] + geo.eps
        hit = all_hit[offsets[position]:offsets[position + 1]]
        for b in sorted({int(face) for face in hit if face and face != a}):
            if (min(a, b), max(a, b)) in seen or b not in bases or not bases[b]:
                continue
            nb = np.asarray(geo.surfaces[b - 1].normal)
            if float(na @ nb) > -math.cos(math.radians(12.0)):
                continue
            share = float(geo.weights[mine][hit == b].sum()) / max(float(geo.weights[mine].sum()), 1e-12)
            if share < 0.5:
                continue
            pairs = [(ba, bb) for ba in bases[a] for bb in bases[b] if _same_plane(geo, ba[0], bb[0])]
            if not pairs:
                continue

            def standing(pair: tuple[tuple[int, float, int], tuple[int, float, int]]) -> float:
                base = pair[0][0]
                normal = np.asarray(geo.surfaces[base - 1].normal)
                return float(((geo.vertices(a) - np.asarray(geo.surfaces[base - 1].origin)) @ normal).max())

            # A rib touching walls as well as its floor stands on the face it is shortest from.
            (base, fillet_a, fa), (_base_b, fillet_b, fb) = min(pairs, key=standing)
            nbase = np.asarray(geo.surfaces[base - 1].normal)
            across = distance[hit == b]
            root, tip = float(across.max()), float(across.min())
            height = standing(((base, 0.0, 0), (base, 0.0, 0)))
            along = np.cross(nbase, na)
            along /= np.linalg.norm(along) or 1.0
            span = geo.vertices(a) @ along
            length = float(span.max() - span.min())
            if root <= 0 or height < 1.0 * root or length < 1.5 * root:
                continue
            seen.add((min(a, b), max(a, b)))
            wall = _face_wall(thick, base) or nominal
            gaps = []
            for face in (a, b):
                own = geo.owner == face
                outward = geo.cast(geo.points[own] + geo.normals[own] * geo.eps, geo.normals[own])
                finite = outward[np.isfinite(outward)]
                if len(finite) >= 0.5 * own.sum():
                    gaps.append(float(np.median(finite)))
            gap = min(gaps) if gaps else None
            fillet = min(fillet_a, fillet_b)
            draft = min(drafts[a - 1].draft, drafts[b - 1].draft)
            used.update({a, b, fa, fb} - {0})
            items.append({
                "location": geo.ref(a), "faces": [geo.ref(a), geo.ref(b), geo.ref(base)],
                "thickness_mm": _r(root, 3), "tip_thickness_mm": _r(tip, 3), "height_mm": _r(height, 3),
                "length_mm": _r(length, 3), "wall_mm": _r(wall, 3),
                "thickness_ratio": _r(root / wall, 3) if wall else None,
                "height_ratio": _r(height / wall, 3) if wall else None,
                "height_to_thickness": _r(height / root, 3),
                "base_fillet_mm": _r(fillet, 3), "base_fillet_ratio": _r(fillet / root, 3),
                "base_fillet_wall_ratio": _r(fillet / wall, 3) if wall else None,
                "draft_deg": _r(draft, 3), "gap_mm": _r(gap, 3),
                "gap_to_thickness": _r(gap / root, 3) if gap is not None else None,
                "gap_to_wall": _r(gap / wall, 3) if gap is not None and wall else None,
                "xyz": _centroid(geo, a)})
    return items


def _bosses_part(geo: _Geometry, thick: _Thickness, nominal: float | None, used: set[int]) -> list[dict[str, Any]]:
    links = geo.neighbours()
    items: list[dict[str, Any]] = []
    holes = [(ordinal, surface) for ordinal, surface in enumerate(geo.surfaces, start=1)
             if surface.kind == "cylinder" and surface.concave and surface.axis is not None]
    taken: set[int] = set()
    for ordinal, surface in enumerate(geo.surfaces, start=1):
        if surface.kind != "cylinder" or surface.concave is not False or surface.axis is None or ordinal in taken:
            continue
        axis = np.asarray(surface.axis)
        origin = np.asarray(surface.origin)
        bases = _bases(geo, ordinal, links, axis, square=False)
        if not bases:
            continue
        base, fillet, fillet_face = bases[0]
        nbase = np.asarray(geo.surfaces[base - 1].normal)
        obase = np.asarray(geo.surfaces[base - 1].origin)
        heights = (geo.vertices(ordinal) - obase) @ nbase
        height = float(heights.max())
        if height <= 0:
            continue
        radius = float(surface.radius or 0.0)
        inner = None
        for hole, hs in holes:
            ha = np.asarray(hs.axis)
            if abs(abs(float(ha @ axis)) - 1.0) > 1e-6 or float(hs.radius or 0) >= radius:
                continue
            offset = np.asarray(hs.origin) - origin
            if np.linalg.norm(offset - axis * float(offset @ axis)) > 1e-3 * max(radius, 1.0):
                continue
            span = (geo.vertices(hole) - obase) @ nbase
            if span.max() < 0.5 * height:
                continue
            if inner is None or float(hs.radius) > inner[1]:
                inner = (hole, float(hs.radius), float(span.min()))
        taken.add(ordinal)
        used.update({ordinal, fillet_face} - {0})
        wall_ref = _face_wall(thick, base) or nominal
        wall = radius - inner[1] if inner else 2.0 * radius
        items.append({
            "location": geo.ref(ordinal), "faces": [geo.ref(ordinal), geo.ref(base)] + ([geo.ref(inner[0])] if inner else []),
            "od_mm": _r(2 * radius, 3), "id_mm": _r(2 * inner[1], 3) if inner else None, "hollow": inner is not None,
            "boss_wall_mm": _r(wall, 3), "wall_mm": _r(wall_ref, 3),
            "wall_ratio": _r(wall / wall_ref, 3) if wall_ref else None,
            "od_to_id": _r(radius / inner[1], 3) if inner else None, "height_mm": _r(height, 3),
            "height_to_od": _r(height / (2 * radius), 3), "base_fillet_mm": _r(fillet, 3),
            "hole_floor_above_base_mm": _r(inner[2], 3) if inner else None, "xyz": _centroid(geo, ordinal)})
    return items


def _corners_part(geo: _Geometry, thick: _Thickness, nominal: float | None, used: set[int]) -> list[dict[str, Any]]:
    links = geo.neighbours()
    items: list[dict[str, Any]] = []

    def wall(*faces: int) -> float | None:
        values = [value for face in faces if (value := _face_wall(thick, face))]
        return min(values) if values else nominal

    for edge in geo.edges:
        a, b = edge.faces
        if not edge.concave or edge.smooth or a in used or b in used:
            continue
        reference = wall(a, b)
        first = a if geo.areas[a - 1] <= geo.areas[b - 1] else b
        items.append({"location": geo.ref(first), "faces": [geo.ref(a), geo.ref(b)],
                      "edge": geo.part.ref("edge", edge.ordinal), "radius_mm": 0.0, "sharp": True,
                      "angle_deg": _r(edge.angle_deg, 2), "length_mm": _r(edge.length, 3),
                      "wall_mm": _r(reference, 3), "ratio_to_wall": 0.0, "xyz": _xyz(edge.midpoint)})
    for ordinal, surface in enumerate(geo.surfaces, start=1):
        if surface.kind not in ("cylinder", "torus") or not surface.concave or ordinal in used:
            continue
        # A fillet: joined tangentially to at least two faces (its ends may meet caps at sharp edges).
        joins = [(other, edge) for other, edge in links.get(ordinal, []) if edge.smooth]
        if len(joins) < 2:
            continue
        radius = float(surface.minor_radius if surface.kind == "torus" else surface.radius or 0.0)
        reference = wall(*(other for other, _edge in joins))
        items.append({"location": geo.ref(ordinal), "faces": [geo.ref(ordinal)] + [geo.ref(o) for o, _ in joins],
                      "radius_mm": _r(radius, 4), "sharp": False, "wall_mm": _r(reference, 3),
                      "ratio_to_wall": _r(radius / reference, 3) if reference else None,
                      "xyz": _centroid(geo, ordinal)})
    return items


def _features_family(name: str, per_part: list[list[dict[str, Any]]], key: str, worst_low: bool = True
                     ) -> dict[str, Any]:
    items = [item for part in per_part for item in part]
    items.sort(key=lambda item: (item.get(key) if item.get(key) is not None else math.inf) * (1 if worst_low else -1))
    return {"count": len(items), "items": items[:_ITEMS]}


# --- projection and parting ------------------------------------------------------------------------------


def _projection_part(geo: _Geometry, pull: np.ndarray) -> tuple[dict[str, Any], dict[str, Any], np.ndarray]:
    vertices, triangles, _owners = geo.mesh
    u, v = ops.basis(pull)
    flat = np.stack([vertices @ u, vertices @ v], axis=1)
    projection = ops.raster(flat, triangles)
    heights = vertices @ pull
    span = flat.max(axis=0) - flat.min(axis=0) if len(flat) else np.zeros(2)
    item = {"location": geo.part.owner or geo.part.name or "part", "part": geo.part.owner or geo.part.name or "part",
            "projected_area_mm2": _r(projection["area"], 2), "area_error_mm2": _r(projection["area_error"], 2),
            "raster_resolution_mm": _r(projection["cell"], 6),
            "depth_along_pull_mm": _r(float(heights.max() - heights.min()), 3) if len(heights) else 0.0,
            "span_major_mm": _r(float(span.max()), 3), "span_minor_mm": _r(float(span.min()), 3),
            "volume_mm3": _r(float(geo.part.shape.volume), 2)}
    return item, projection, vertices


def _projection(items: list[dict[str, Any]], pull: np.ndarray) -> dict[str, Any]:
    return {"pull_axis": [_r(v) for v in pull],
            "projected_area_mm2": _r(sum(item["projected_area_mm2"] or 0 for item in items), 1),
            "area_error_mm2": _r(sum(item["area_error_mm2"] or 0 for item in items), 2),
            "raster_resolution_mm": max(item["raster_resolution_mm"] for item in items) if items else None,
            "depth_along_pull_mm": max(item["depth_along_pull_mm"] for item in items) if items else None,
            "volume_mm3": _r(sum(item["volume_mm3"] or 0 for item in items), 1),
            "method": ("the part triangulated on its B-rep and projected on the parting plane; the area is the "
                       "cells of a raster 2000 across the part whose centres a triangle covers, good to "
                       "area_error_mm2 (half the outline's cells)"),
            "items": items}


def _envelope(projected: list[dict[str, Any]], partings: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Per part, its size against the mold: spans across the pull, depth along it and from the parting."""
    items = []
    for index, item in enumerate(projected):
        part = partings[index] if partings and index < len(partings) else None
        depth = max(part["depth_above"], part["depth_below"]) if part else None
        items.append({"location": item["location"], "span_major_mm": item["span_major_mm"],
                      "span_minor_mm": item["span_minor_mm"], "depth_along_pull_mm": item["depth_along_pull_mm"],
                      "depth_from_parting_mm": _r(depth, 3), "volume_mm3": item["volume_mm3"]})
    return {"items": items,
            "method": "spans of the part's projection on the parting plane (along its axes), its depth along the "
                      "pull, and the farther of its depths above and below the parting plane"}


def _turns(geo: _Geometry, face: _FaceDraft, pull: np.ndarray) -> list[float]:
    """The heights along the pull at which a split face turns through it."""
    surface = geo.surfaces[face.ordinal - 1]
    if surface.kind == "sphere" and surface.origin is not None:
        return [float(np.asarray(surface.origin) @ pull)]
    if surface.kind == "cylinder" and surface.axis is not None and abs(float(np.asarray(surface.axis) @ pull)) < 1e-9:
        return [float(np.asarray(surface.origin) @ pull)]
    if surface.kind == "torus" and surface.axis is not None and \
            abs(abs(float(np.asarray(surface.axis) @ pull)) - 1.0) < 1e-9:
        return [float(np.asarray(surface.origin) @ pull)]
    mine = geo.owner == face.ordinal
    points, along = geo.points[mine], geo.normals[mine] @ pull
    if not len(points):
        return []
    order = np.argsort(np.abs(along))[: max(2, len(points) // 10)]
    return [float(value) for value in points[order] @ pull]


def _parting_part(geo: _Geometry, drafts: list[_FaceDraft], projection: dict[str, Any], vertices: np.ndarray,
                  pull: np.ndarray, wall_limit: float, trapped: set[int] | None = None) -> dict[str, Any]:
    """The part's parting (``ops.parting``), leaving out the faces of its undercuts: a slide forms those,
    and the parting line runs round them."""
    trapped = trapped or set()
    u, v = ops.basis(pull)
    heights = vertices @ pull if len(vertices) else geo.points @ pull
    if not len(heights):
        heights = np.array([float(geo.lo @ pull), float(geo.hi @ pull)])
    top, bottom = float(heights.max()), float(heights.min())
    depth = top - bottom
    tolerance = max(1e-3 * depth, 0.01)

    def on_outline(points: np.ndarray) -> bool:
        flat = np.stack([points @ u, points @ v], axis=1)
        return bool(ops.near_outline(projection, flat, 3.0).any())

    elements: list[dict[str, Any]] = []
    opening = {face.ordinal: face.opens for face in drafts}
    for edge in geo.edges:
        a, b = edge.faces
        if {opening.get(a), opening.get(b)} != {"+pull", "-pull"} or a in trapped or b in trapped:
            continue
        shape_edge = geo.part.edges()[edge.ordinal - 1]
        points = []
        for t in np.linspace(0.0, 1.0, 9):
            at = shape_edge.position_at(float(t))
            points.append([at.X, at.Y, at.Z])
        points = np.array(points)
        if not on_outline(points):
            continue
        along = points @ pull
        face = a if opening[a] == "+pull" else b
        elements.append({"kind": "edge", "location": geo.ref(face), "edge": geo.part.ref("edge", edge.ordinal),
                         "low": float(along.min()), "high": float(along.max()), "weight": float(edge.length),
                         "xyz": _xyz(edge.midpoint)})
    for face in drafts:
        if face.opens not in ("none", "split") or face.draft >= wall_limit or face.ordinal in trapped:
            continue
        points = geo.vertices(face.ordinal)
        if not on_outline(points):
            continue
        if face.opens == "none":
            low, high = _extent(geo, face.ordinal, pull)
            elements.append({"kind": "wall", "location": geo.ref(face.ordinal), "low": low, "high": high,
                             "weight": float(geo.areas[face.ordinal - 1]), "xyz": _centroid(geo, face.ordinal)})
        else:
            turns = _turns(geo, face, pull)
            if turns:
                elements.append({"kind": "turn", "location": geo.ref(face.ordinal), "low": min(turns),
                                 "high": max(turns), "weight": float(geo.areas[face.ordinal - 1]),
                                 "xyz": _centroid(geo, face.ordinal)})
    found = ops.parting(elements, top, bottom, tolerance)
    off = {id(element) for element in found["off_plane"]}
    items = [{"location": element["location"], "kind": element["kind"],
              "low_mm": _r(element["low"], 4), "high_mm": _r(element["high"], 4),
              "on_plane": id(element) not in off, "xyz": element["xyz"],
              **({"edge": element["edge"]} if "edge" in element else {})} for element in elements]
    items.sort(key=lambda item: (item["on_plane"], item["location"]))
    return {"part": geo.part.owner or geo.part.name, "flat": found["flat"], "height": found["height"],
            "range": found["range"], "depth_above": found["depth_above"], "depth_below": found["depth_below"],
            "tolerance": tolerance, "items": items, "off": len(found["off_plane"])}


def _parting(parts: list[dict[str, Any]], pull: np.ndarray) -> dict[str, Any]:
    items = [item for part in parts for item in part["items"]]
    flats = [part["flat"] for part in parts]
    depth = max((max(part["depth_above"], part["depth_below"]) for part in parts), default=None)
    first = parts[0] if parts else None
    result = {
        "pull_axis": [_r(v) for v in pull],
        "flat_parting_possible": None if any(flat is None for flat in flats) else all(flats),
        "parting_plane_height_mm": _r(first["height"], 4) if first else None,
        "parting_plane_range_mm": [_r(value, 4) for value in first["range"]] if first and first["range"] else None,
        "depth_above_mm": _r(first["depth_above"], 3) if first else None,
        "depth_below_mm": _r(first["depth_below"], 3) if first else None,
        "depth_from_parting_mm": _r(depth, 3),
        "silhouette_count": len(items), "off_plane_count": sum(part["off"] for part in parts),
        "items": items[:_ITEMS],
        "method": ("the outline's silhouette: edges where a face opening along the pull meets one opening "
                   "against it, zero-draft walls and curved faces turning through the pull, those within three "
                   "raster cells of the projected outline; one flat plane takes them when every edge and turn is "
                   "level (to tolerance_mm) at one height that every wall spans"),
        "tolerance_mm": _r(first["tolerance"], 4) if first else None,
    }
    if len(parts) > 1:
        result["per_part"] = [{"part": part["part"], "flat": part["flat"], "height_mm": _r(part["height"], 4),
                               "depth_from_parting_mm": _r(max(part["depth_above"], part["depth_below"]), 3)}
                              for part in parts]
    return result


# --- the report ------------------------------------------------------------------------------------------


def _scale(geos: list[_Geometry]) -> dict[str, Any]:
    if not geos:
        return {"declared_units": "mm", "units_suspect": False}
    lo = np.min([geo.lo for geo in geos], axis=0)
    hi = np.max([geo.hi for geo in geos], axis=0)
    return {"declared_units": "mm", "bbox_mm": _xyz(hi - lo), "bbox_diagonal_mm": _r(float(np.linalg.norm(hi - lo)), 4),
            "units_suspect": False,
            "note": "the document declares its units and is read in millimetres; no unit is guessed"}


def _mark_partial(report: dict[str, Any]) -> None:
    def failed(value: Any) -> bool:
        if isinstance(value, dict):
            return "error" in value or any(failed(item) for item in value.values())
        if isinstance(value, list):
            return any(failed(item) for item in value)
        return False

    sections = sorted(key for key, value in report.items() if failed(value))
    report["partial"] = bool(sections)
    report["partial_sections"] = sections


def _families(geos: list[_Geometry], pull: np.ndarray, wall_limit: float, zero_tol: float) -> dict[str, Any]:
    drafts = [_face_drafts(geo, pull, zero_tol) for geo in geos]
    report: dict[str, Any] = {"scale": _scale(geos)}
    report["draft"] = _safe(_draft, geos, drafts, pull, wall_limit, zero_tol)
    under_parts = _safe(lambda: [_undercut_part(geo, pull, zero_tol) for geo in geos])
    if isinstance(under_parts, dict):
        report["undercuts"] = under_parts
        trapped: list[set[int]] = [set() for _ in geos]
    else:
        report["undercuts"] = _safe(_undercuts, geos, pull, zero_tol, under_parts)
        trapped = [{face for group in part["groups"] for face in group} for part in under_parts]
    thick = _safe(lambda: [_thickness_part(geo) for geo in geos])
    if isinstance(thick, dict):
        for name in ("thickness", "ribs", "bosses", "corners"):
            report[name] = dict(thick)
    else:
        report["thickness"] = _safe(_thickness, geos, thick)
        used: list[set[int]] = [set() for _ in geos]
        report["ribs"] = _safe(lambda: _features_family("ribs", [
            _ribs_part(geo, t, d, t.nominal, u) for geo, t, d, u in zip(geos, thick, drafts, used)],
            "thickness_ratio", worst_low=False))
        report["bosses"] = _safe(lambda: _features_family("bosses", [
            _bosses_part(geo, t, t.nominal, u) for geo, t, u in zip(geos, thick, used)], "wall_ratio",
            worst_low=False))
        report["corners"] = _safe(lambda: _features_family("corners", [
            _corners_part(geo, t, t.nominal, u) for geo, t, u in zip(geos, thick, used)], "ratio_to_wall"))
    projected = _safe(lambda: [_projection_part(geo, pull) for geo in geos])
    if isinstance(projected, dict):
        report["projection"] = projected
        report["parting"] = dict(projected)
    else:
        report["projection"] = _safe(_projection, [item for item, _p, _v in projected], pull)
        partings = _safe(lambda: [_parting_part(geo, d, p, v, pull, wall_limit, t)
                                  for geo, d, (_i, p, v), t in zip(geos, drafts, projected, trapped)])
        report["parting"] = partings if isinstance(partings, dict) else _safe(_parting, partings, pull)
        report["envelope"] = _safe(_envelope, [item for item, _p, _v in projected],
                                   None if isinstance(partings, dict) else partings)
    return report


def _principal_axes(geos: list[_Geometry]) -> list[np.ndarray]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(geos[0].part.shape.wrapped, props)
    principal = props.PrincipalProperties()
    axes = []
    for getter in (principal.FirstAxisOfInertia, principal.SecondAxisOfInertia, principal.ThirdAxisOfInertia):
        d = getter()
        axes.append(np.array([d.X(), d.Y(), d.Z()]))
    return axes


def _candidates(geos: list[_Geometry], wall_limit: float, zero_tol: float) -> dict[str, Any]:
    named = [(name, np.array(axis, dtype=float)) for name, axis in
             (("x", (1.0, 0.0, 0.0)), ("y", (0.0, 1.0, 0.0)), ("z", (0.0, 0.0, 1.0)))]
    try:
        for index, axis in enumerate(_principal_axes(geos)):
            unit = axis / (np.linalg.norm(axis) or 1.0)
            if any(abs(abs(float(unit @ other)) - 1.0) < 1.5e-4 for _name, other in named[:3]):
                continue
            named.append((f"principal{index}", unit))
    except Exception:  # noqa: BLE001 - no inertia frame: the world axes alone
        pass
    rows = []
    for name, axis in named:
        def row(axis: np.ndarray = axis) -> dict[str, Any]:
            drafts = [_face_drafts(geo, axis, zero_tol) for geo in geos]
            draft = _draft(geos, drafts, axis, wall_limit, zero_tol)
            parts = [_undercut_part(geo, axis, zero_tol) for geo in geos]
            under = _undercuts(geos, axis, zero_tol, parts)
            projected = [_projection_part(geo, axis) for geo in geos]
            parting = _parting([_parting_part(geo, d, p, v, axis, wall_limit,
                                              {face for group in part["groups"] for face in group})
                                for geo, d, (_i, p, v), part in zip(geos, drafts, projected, parts)], axis)
            below_1 = sum(value for key, value in draft["wall_draft_histogram_mm2"].items()
                          if float(key.split("-")[1].rstrip("deg")) <= 1.0)
            return {"undercut_candidate_area_mm2": under["candidate_area_mm2"],
                    "undercut_count": under["undercut_count"], "side_action_count": under["side_action_count"],
                    "lifter_count": under["lifter_count"] + under["collapsible_core_count"],
                    "unreleasable_count": under["unreleasable_count"],
                    "wall_area_mm2": draft["wall_area_mm2"], "zero_draft_wall_area_mm2": draft["zero_draft_wall_area_mm2"],
                    "wall_area_below_1deg_mm2": _r(below_1, 2),
                    "min_wall_draft_deg": (draft.get("min_wall_draft") or {}).get("draft_deg"),
                    "flat_parting": parting["flat_parting_possible"],
                    "projected_area_mm2": sum(item["projected_area_mm2"] or 0 for item, _p, _v in projected),
                    "depth_from_parting_mm": parting["depth_from_parting_mm"]}

        measured = _safe(row)
        rows.append({"pull": name, "axis": [_r(v) for v in axis], **measured})
    return {"wall_limit_deg": wall_limit, "zero_tol_deg": zero_tol,
            "note": ("draft magnitude is the same for +axis and -axis pulls; the lean direction differs. principal* "
                     "are the part's own principal axes of inertia: a part modelled off-axis was drafted about one"),
            "candidates": rows}


def measure(document: _dfm_brep.Document, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The molding report of ``document``: facts alone, every family's ``items`` at a ref."""
    wall_limit, zero_tol = float(options["wall_limit"]), float(options["zero_tol"])
    if candidates:
        geos = [_Geometry(part, budget=_CANDIDATE_SAMPLES) for part in document.parts]
        report = {"scale": _scale(geos), "pulls": _safe(_candidates, geos, wall_limit, zero_tol)}
    else:
        pull = ops.pull_vector(options["pull"])
        geos = [_Geometry(part) for part in document.parts]
        report = _families(geos, pull, wall_limit, zero_tol)
    _mark_partial(report)
    return report
