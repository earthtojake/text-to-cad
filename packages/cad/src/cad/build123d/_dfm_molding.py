"""Injection molding's measurements of exact geometry (``cad._internal.dfm.molding`` says what they are for).

Every part of the document is measured along the pull on its B-rep, each finding at a face's ref:

- **draft**: per face, its angle to the pull -- exact for a plane, for a cylinder or cone whose axis runs
  along the pull (zero, the half-angle), the least over points sampled on the face and along its edges
  otherwise (a round tangent to a wall square to the pull is zero there) -- and which
  way it opens: ``+pull`` (released by the half withdrawing along the pull), ``-pull``, ``none`` (zero
  draft, either half) or ``split`` (the face turns through the pull: the parting line crosses it);
- **undercuts**: points sampled on every face shot along the way the face opens with exact rays; a point
  the part blocks is trapped (a zero-draft one only when both ways are blocked). Trapped faces that touch
  are one group, split where its trapped points lie apart (two snaps under one lid are two features); what
  releases each is found by more rays (``meshops_molding.classify_undercut``);
- **thickness**: the rolling-ball wall under every sampled point (the exact ray straight through bounds
  it), the nominal wall (the area-weighted median), each face's thin and thick readings (``feature``: a rib's
  or a boss's face, else wall), the thinnest faces refined to the exact least distance to a face across
  (``_refine_thin``) and the thickest to their greatest ball over the face (``_refine_thick``); **transitions**: each step read on its stepped side (two parallel faces at two
  wall offsets, the chain of faces between them: its run over the change, ``ops.steps``), and on a free-form
  face no step takes in the rolling ball's steepest change;
- **ribs**: two opposite planar faces close together, both standing on one base face (a concave edge or
  a concave fillet between), taller than thick -- a snap arm (``kind``: snap) where a trapped face, its barb,
  touches it; **bosses**: a convex cylinder (or a cone drafted 5 deg or less) standing on a face square to
  its axis, with the coaxial hole inside it if it has one, and its root's fillet (0: sharp);
- **corners**: every internal corner -- a concave edge with no fillet (radius 0) or a concave fillet
  face (its radius; a free-form blend's from its curvature) -- with its radius over the wall meeting there;
- **projection**: the part triangulated (each triangle naming its face) and projected on the parting
  plane, the covered area counted on a raster sized to the part; its spans and depth;
- **parting**: the outline's silhouette (where faces opening one way meet faces opening the other, the
  zero-draft walls on the outline, the curved faces turning through the pull there), whether one flat
  plane takes it and at what height, and the depth either side.

With ``candidates`` the pulls are ranked instead: x, y, z and the part's principal axes. A check of one pull
asks of each of those whether it does better (``_pull_check``), each read only as far as it still can. A family
that raises leaves ``{"error": ...}`` and the report says so (``partial``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cad._internal import meshops_molding as ops
from cad._internal.dfm import checkpoint
from cad._internal.dfm._common import mm
from cad._internal.dfm.molding import BUMP_OFF_MM, DEFAULT_PULL, better_pull, dominates
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
#: Points along each edge a curved face's draft is also read at (``_Geometry.boundary_normals``).
_BOUNDARY_POINTS = 9
#: The sampled points the wall thickness is read at, at most (each a rolling ball solved exactly).
_THICK_POINTS = 1600
#: Candidates sample fewer points: six pulls, each its own undercut rays.
_CANDIDATE_SAMPLES = 1200
#: A face reads as thick when its thickest point is this many times the nominal wall (reported, not judged).
_THICK_RATIO = 1.5
#: At most this many items per family, worst first.
_ITEMS = 300
_HIST_DEG = [0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0]


#: The digits a figure a rule reads is kept to: the comparison is of the measurement, never of its display
#: (a wall exactly 30 / 18 of the nominal is at the 1 / 0.6 limit, not over it as 1.667 would read).
_JUDGED = 9
#: The digits a sampled length is good to, in millimetres: a wall read by the rolling ball off a triangulation,
#: a rib's thickness off its rays. A ratio a rule reads is of lengths at this precision -- the report's own
#: figures -- so a 1 mm fillet on a wall that reads 2.00001 is at the 0.5 limit, not 0.499997 and under it.
_LENGTH = 3


def _r(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), digits) + 0.0


def _xyz(point: Any) -> list[float]:
    return [round(float(value), 4) + 0.0 for value in point]


# How many (ray, face) pairs ``_mesh_crosses`` screens between two checkpoints.
_CROSSES_AT_ONCE = 1 << 16


def _safe(fn: Any, *args: Any) -> Any:
    checkpoint()  # between families
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
    checkpoint()
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location

    deflection = _dfm_brep.deflection_for(face)  # the face's own size: the same however the part is turned
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
    _contact: tuple[np.ndarray, list[dict[str, Any]]] | None = None
    _boundary: dict[int, np.ndarray] | None = None

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
    def contact(self) -> np.ndarray:
        """Per sampled point: does it lie on another solid of this part (``_contacts``)? Such a point is on no
        surface of the molded part -- two solids touching, not fused -- and no wall, draft or undercut of it."""
        if self._contact is None:
            try:
                self._contact = _contacts(self)
            except Exception:  # noqa: BLE001 - a contact the kernel cannot classify leaves every point a surface's
                self._contact = (np.zeros(len(self.points), dtype=bool), [])
        return self._contact[0]

    @property
    def touching(self) -> list[dict[str, Any]]:
        """The pairs of this part's solids that touch without being fused (``_contacts``)."""
        if self._contact is None:
            try:
                self._contact = _contacts(self)
            except Exception:  # noqa: BLE001 - a contact the kernel cannot classify leaves every point a surface's
                self._contact = (np.zeros(len(self.points), dtype=bool), [])
        return self._contact[1]

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

    def boundary_normals(self, ordinal: int) -> np.ndarray:
        """The face's outward normals along its edges (``_BOUNDARY_POINTS`` an edge, on its curves in the face's
        (u, v)): where a curved face's draft is least when it is least at its boundary -- a fillet tangent to a
        wall square to the pull reaches zero draft on the tangent edge, which no sample inside it lands on."""
        if self._boundary is None:
            self._boundary = {}
        found = self._boundary.get(ordinal)
        if found is None:
            from OCP.BRepAdaptor import BRepAdaptor_Curve2d
            from OCP.BRepGProp import BRepGProp_Face
            from OCP.TopAbs import TopAbs_EDGE
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopoDS import TopoDS

            face = self.faces[ordinal - 1]
            props = BRepGProp_Face(face.wrapped)
            normals = []
            explorer = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
            while explorer.More():
                try:
                    curve = BRepAdaptor_Curve2d(TopoDS.Edge(explorer.Current()), face.wrapped)
                    first, last = curve.FirstParameter(), curve.LastParameter()
                    for k in range(_BOUNDARY_POINTS):
                        uv = curve.Value(first + (last - first) * k / (_BOUNDARY_POINTS - 1))
                        _, normal = _dfm_brep.point_normal(face, uv.X(), uv.Y(), props)
                        if float(np.linalg.norm(normal)) > 0.5:
                            normals.append(normal)
                except Exception:  # noqa: BLE001 - an edge with no curve in the face adds no point
                    pass
                explorer.Next()
            found = np.array(normals).reshape(-1, 3)
            self._boundary[ordinal] = found
        return found

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
        if len(ray) > _CROSSES_AT_ONCE:
            # A batch at a time, each a checkpoint apart: a large part has millions of pairs to screen.
            return np.concatenate([self._mesh_crosses(ray[at:at + _CROSSES_AT_ONCE], face[at:at + _CROSSES_AT_ONCE],
                                                      origins, directions)
                                   for at in range(0, len(ray), _CROSSES_AT_ONCE)])
        checkpoint()
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
            checkpoint()  # a batch of rays at a time
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
                # a free-form face's triangulation screens the rest, and bounds where each ray can cross it
                can, near = rays.screen.pairs(o_all, d_all, ray, face, skip, 1e9)
                ray, face = ray[can], face[can]
                enter = np.where(np.isnan(near[can]), enter[can], np.maximum(enter[can], np.nan_to_num(near[can])))
            order = np.lexsort((enter, ray))
            ray, face, enter = ray[order], face[order], enter[order]
            cuts = np.flatnonzero(np.diff(ray)) + 1
            for begin, stop in zip(np.concatenate([[0], cuts]), np.concatenate([cuts, [len(ray)]])):
                if begin >= stop:
                    continue
                index = int(ray[begin])
                checkpoint()
                line = gp_Lin(gp_Pnt(*o_all[index]), gp_Dir(*d_all[index]))
                best, which = math.inf, 0
                for k in range(begin, stop):
                    if enter[k] > best:
                        break
                    candidate = int(face[k])
                    intersector = self._intersectors.get(candidate)
                    if intersector is None:
                        intersector = self._intersectors[candidate] = _dfm_brep.Intersector(
                            rays.faces[candidate], 1e-7, rays.screen, candidate)
                    # a crossing the kernel cannot find (a degenerate patch) is counted against the face by the
                    # intersector (``Screen.failed``), and the ray goes on to the next face
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
        checkpoint()
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
            edge = geo.boundary_normals(ordinal) @ pull
            if len(edge):
                # its least over its edges too: a round's draft falls to the wall's it is tangent to there
                draft = min(draft, float(np.degrees(np.arcsin(np.clip(np.abs(edge), 0.0, 1.0))).min()))
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
        contact = geo.contact
        for face in faces:
            area = float(geo.areas[face.ordinal - 1])
            if face.draft >= wall_limit or area <= 0:
                continue
            mine = geo.owner == face.ordinal
            if mine.any() and float(geo.weights[mine & contact].sum()) >= 0.5 * float(geo.weights[mine].sum()):
                continue  # a face lying on another of the part's solids: no wall of the molded part
            wall += area
            opening[face.opens] += area
            low, high = _extent(geo, face.ordinal, pull)
            item = {"location": geo.ref(face.ordinal), "draft_deg": _r(face.draft, _JUDGED), "area_mm2": _r(area, 2),
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
                   "sampled on it and along its edges; faces at or above wall_limit_deg are not walls"),
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
    across: np.ndarray        # per sample: the face it stands in a crevice with (``_CREVICE``), 0 for none


#: A part of more solids than this is not searched for solids touching (a component model's contacts).
_CONTACT_SOLIDS = 24


def _contacts(geo: _Geometry) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Which sampled points of ``geo`` lie on another of its part's solids, and the pairs of solids that touch so.

    Two solids of one part that touch but are not fused share a face, or a stretch of one: each solid's face
    there lies on the other's, a point stepped off it lands in the other solid's material, and its rays cross
    that material, so a molding check reads the pair's contact as a trapped wall. One molded part is one solid:
    the contact is no surface of it, and the pair is said, to be fused."""
    mask = np.zeros(len(geo.points), dtype=bool)
    solids = geo.part.solids()
    if len(solids) < 2 or len(solids) > _CONTACT_SOLIDS or not len(geo.points):
        return mask, []
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    from OCP.gp import gp_Pnt

    maps = []
    for solid in solids:
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(solid.wrapped, faces)
        maps.append(faces)
    home = np.array([next((index for index, faces in enumerate(maps) if faces.Contains(face.wrapped)), -1)
                     for face in geo.faces])
    boxes = []
    for solid in solids:
        box = solid.bounding_box()
        boxes.append((np.array([box.min.X, box.min.Y, box.min.Z]) - geo.eps,
                      np.array([box.max.X, box.max.Y, box.max.Z]) + geo.eps))
    stepped = geo.points + geo.normals * geo.eps
    owners = home[geo.owner - 1]
    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    for other, solid in enumerate(solids):
        checkpoint()
        low, high = boxes[other]
        near = np.nonzero((owners != other) & (owners >= 0) & np.all(stepped >= low, axis=1)
                          & np.all(stepped <= high, axis=1))[0]
        if not len(near):
            continue
        classifier = BRepClass3d_SolidClassifier(solid.wrapped)
        for index in near:
            x, y, z = (float(value) for value in stepped[index])
            classifier.Perform(gp_Pnt(x, y, z), 0.5 * geo.eps)
            if classifier.State() in (TopAbs_IN, TopAbs_ON):
                mask[index] = True
                key = (min(int(owners[index]), other), max(int(owners[index]), other))
                pair = pairs.setdefault(key, {"area": 0.0, "faces": set(), "points": []})
                pair["area"] += float(geo.weights[index])
                pair["faces"].add(int(geo.owner[index]))
                pair["points"].append(geo.points[index])
    touching = []
    for (a, b), pair in sorted(pairs.items(), key=lambda kv: -kv[1]["area"]):
        faces = sorted(pair["faces"])
        # Both solids' faces are counted: the contact's own area is half of theirs.
        touching.append({"location": geo.ref(faces[0]), "part": geo.part.owner or geo.part.name,
                         "solids": [a + 1, b + 1], "faces": [geo.ref(face) for face in faces],
                         "contact_area_mm2": _r(0.5 * pair["area"], 2),
                         "xyz": _xyz(np.mean(pair["points"], axis=0))})
    return mask, touching


#: A point whose own normal meets another face within this many of the offsets its rays start at (``_Geometry.eps``:
#: 0.03 mm at most) stands in a crevice, two faces nearer than steel can stand between. Stepped off its face it
#: lands in the other face's material, where every ray is blocked: it is no undercut's (the square end of a rib run
#: into a drafted wall stands a hair off the wall above where it is buried, the gap opening along the pull), and
#: is said as a crevice instead.
_CREVICE = 3.0


def _blocked(geo: _Geometry, points: np.ndarray, normals: np.ndarray, pull: np.ndarray, zero_tol: float
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per point on the part's surface, with its outward normal: whether it is trapped along ``pull`` -- a ray
    from just off it along the way its face opens meets the part (a zero-draft point's both ways) --, the face
    that blocks it (0: none), whether it reads zero draft, and the face it stands in a crevice with (0: none;
    ``_CREVICE``: such a point is never trapped)."""
    tol = math.sin(math.radians(zero_tol))
    along = normals @ pull
    origins = points + normals * geo.eps
    sign = np.where(along >= 0, 1.0, -1.0)
    zero = np.abs(along) <= tol
    first, first_face = geo.cast_faces(origins, sign[:, None] * pull[None, :])
    blocked = np.isfinite(first)
    blocker = np.where(blocked, first_face, 0)
    if zero.any():
        index = np.nonzero(zero & blocked)[0]
        other, _other_face = geo.cast_faces(origins[index], -sign[index, None] * pull[None, :])
        both = np.isfinite(other)
        blocked[index] = both
        blocker[index] = np.where(both, blocker[index], 0)
    across = np.zeros(len(points), dtype=int)
    index = np.nonzero(blocked)[0]
    if len(index):
        # from the surface itself, straight out: the face across, where it is nearer than steel can stand
        gap, face = geo.cast_faces(points[index], normals[index])
        across[index] = np.where(gap <= _CREVICE * geo.eps, face, 0)
        blocked &= across == 0
    return blocked, np.where(blocked, blocker, 0), zero, across


def _trap(geo: _Geometry, pull: np.ndarray, zero_tol: float) -> _Trapped:
    blocked, blocker, zero, across = _blocked(geo, geo.points, geo.normals, pull, zero_tol)
    # A point on another of the part's solids (``_contacts``) is no surface of the molded part.
    blocked &= ~geo.contact
    return _Trapped(blocked, np.where(blocked, blocker, 0), zero, np.where(geo.contact, 0, across))


#: Trapped points within this many sample spacings of one another (the larger of the two points') are one
#: feature: two snaps under one lid are two features though the lid's face shadows both.
_FEATURE_REACH = 3.0
#: A group of more trapped points than this is not split (its pairs would cost more than they tell).
_SPLIT_MOST = 4000


def _features(geo: _Geometry, trapped: _Trapped) -> list[np.ndarray]:
    """The trapped features, each a mask of the sampled points: trapped faces (at least two trapped points,
    or a fiftieth of the face) grouped where they touch, each group's trapped points then split where they
    lie apart (``_clusters``)."""
    found = []
    for group in _face_groups(geo, trapped):
        mask = trapped.trapped & np.isin(geo.owner, group)
        index = np.nonzero(mask)[0]
        for cluster in _clusters(geo.points[index], _FEATURE_REACH * geo.spacing[index]):
            part = np.zeros(len(geo.points), dtype=bool)
            part[index[cluster]] = True
            found.append(part)
    return found


def _clusters(points: np.ndarray, reach: np.ndarray) -> list[np.ndarray]:
    """``points`` grouped where two lie within the larger of their ``reach`` (union-find over the pairs);
    one group where there are too many to pair (``_SPLIT_MOST``)."""
    count = len(points)
    if count <= 1 or count > _SPLIT_MOST:
        return [np.arange(count)] if count else []
    parent = np.arange(count)

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = int(parent[i])
        return i

    step = max(1, 2_000_000 // count)
    for start in range(0, count, step):
        stop = min(count, start + step)
        d = np.linalg.norm(points[start:stop, None, :] - points[None, :, :], axis=2)
        near = d <= np.maximum(reach[start:stop, None], reach[None, :])
        for i, j in zip(*np.nonzero(near)):
            a, b = root(int(i) + start), root(int(j))
            if a != b:
                parent[a] = b
    labels = np.array([root(i) for i in range(count)])
    return [np.nonzero(labels == label)[0] for label in np.unique(labels)]


def _face_groups(geo: _Geometry, trapped: _Trapped) -> list[list[int]]:
    """Trapped faces (at least two trapped points, or a fiftieth of the face), grouped where they touch."""
    faces = []
    for ordinal in range(1, len(geo.faces) + 1):
        checkpoint()
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


def _own_directions(geo: _Geometry, faces: list[int]) -> list[np.ndarray]:
    """The directions a feature's own faces (``faces``, the ones that name it first) give a slide to try
    (``ops.slide_directions``): a bore's axis (a cylinder's, a cone's), a slot's run (square to two of its planes'
    normals, where they meet), a plane's normal (a pocket's floor) -- exact, where the eight directions round the
    parting plane are a grid the feature need not lie on (a hole drilled 20 degrees off x, a slot in a part whose
    own frame is a twelfth of a degree off its walls)."""
    axes, normals = [], []
    for face in faces[:8]:
        surface = geo.surfaces[face - 1]
        if surface.kind in ("cylinder", "cone") and surface.axis is not None:
            axes.append(np.asarray(surface.axis, dtype=float))
        elif surface.kind == "plane" and surface.normal is not None:
            normals.append(np.asarray(surface.normal, dtype=float))
    runs = []
    for index, a in enumerate(normals):
        for b in normals[index + 1:]:
            run = np.cross(a, b)
            size = float(np.linalg.norm(run))
            if size > math.sin(math.radians(5.0)):
                runs.append(run / size)
    found: list[np.ndarray] = []
    near = math.cos(math.radians(ops.IN_PLANE_DEG))
    for vector in (*axes, *runs, *normals):
        if not any(abs(float(vector @ other)) > near for other in found):
            found.append(vector)
    return found[:ops.OWN_DIRECTIONS]


#: A feature nothing releases fails the part, so one that rests on fewer trapped points than ``_CONFIRM_UNDER`` is
#: read again before it is said: its faces sampled ``_CONFIRM_DENSER`` times as densely, the new points beside its
#: trapped ones tested as those were. Fewer than ``_CONFIRM_POINTS`` of them trapped and it was a sample's
#: reading, no feature; else the denser points say what releases it.
_CONFIRM_UNDER = 12
_CONFIRM_DENSER = 4
_CONFIRM_POINTS = 2


def _denser(geo: _Geometry, mask: np.ndarray, pull: np.ndarray, zero_tol: float) -> tuple[np.ndarray, np.ndarray]:
    """The trapped points of a feature (``mask``) sampled again, denser (``_CONFIRM_DENSER``): on each of its
    faces, the new points within a sample's spacing and a half of one of its trapped points; those trapped
    (``_blocked``), with their normals."""
    index = np.nonzero(mask)[0]
    points, normals = [], []
    for face in sorted({int(f) for f in geo.owner[index]}):
        own = index[geo.owner[index] == face]
        count = int((geo.owner == face).sum())
        found = _samples(geo.faces[face - 1], _CONFIRM_DENSER * max(count, _LEAST_PER_FACE))
        if not found:
            continue
        pts = np.array([point for point, _normal, _share in found]).reshape(-1, 3)
        nrm = np.array([normal for _point, normal, _share in found]).reshape(-1, 3)
        apart = np.linalg.norm(pts[:, None, :] - geo.points[own][None, :, :], axis=2)
        near = (apart <= 1.5 * geo.spacing[own][None, :]).any(axis=1)
        points.append(pts[near])
        normals.append(nrm[near])
    if not points:
        return np.zeros((0, 3)), np.zeros((0, 3))
    pts, nrm = np.vstack(points), np.vstack(normals)
    blocked = _blocked(geo, pts, nrm, pull, zero_tol)[0]
    return pts[blocked], nrm[blocked]


def _stroke(geo: _Geometry, release: dict[str, Any], index: np.ndarray) -> float | None:
    """A side action's stroke: its tested points' farthest travel (``stroke_mm``), each face's carried on to the
    face's end where the face ends within two sample spacings beyond its farthest-travelling point, against the
    slide. The points are sampled inside a face, never on its far edge: a pin through a 2 mm wall travels the
    2 mm, not the 1.7 its deepest sample does. (A groove round a boss ends half-way round, far beyond: its
    slide's stroke is its samples'.) ``index``: the feature's points among the part's."""
    stroke = release.get("stroke_mm")
    if stroke is None or release.get("release") != "side_action":
        return stroke
    farthest: dict[tuple[int, int], tuple[int, float]] = {}   # per face and slide: its point, its travel
    for point, slide, travel in release.get("travel") or ():
        at = int(index[point])
        key = (int(geo.owner[at]), slide)
        if key not in farthest or travel > farthest[key][1]:
            farthest[key] = (at, travel)
    for (face, slide), (at, travel) in farthest.items():
        direction = np.asarray(release["vectors"][slide], dtype=float)
        beyond = float(geo.points[at] @ direction) - float((geo.vertices(face) @ direction).min())
        if 0.0 < beyond <= 2.0 * float(geo.spacing[at]):
            stroke = max(stroke, travel + beyond)
    return stroke


def _undercut_part(geo: _Geometry, pull: np.ndarray, zero_tol: float, classify: bool = True,
                   depth: bool = True) -> dict[str, Any]:
    checkpoint()  # a part at a time
    trapped = _trap(geo, pull, zero_tol)
    items: list[dict[str, Any]] = []
    kept: list[np.ndarray] = []
    slides: list[np.ndarray] = []
    unconfirmed = 0
    spent = [0]

    def counted(origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
        spent[0] += len(origins)
        return geo.cast(origins, directions)

    # The largest features first: a part of hundreds of them (a connector's contacts) spends its release
    # rays (_RELEASE_RAYS) on the largest, and says which it did not search ("unknown").
    features = _features(geo, trapped)
    for mine in sorted(features, key=lambda mask: -float(geo.weights[mask].sum())):
        group = sorted({int(face) for face in geo.owner[mine]})
        index = np.nonzero(mine)[0]
        area = float(geo.weights[mine].sum())
        per_face = {face: float(geo.weights[mine & (geo.owner == face)].sum()) for face in group}
        # The face that best names the undercut: the largest of those mostly trapped (a snap's underside,
        # not the strip of wall it shadows); else the largest trapped area.
        whole = {face: area for face, area in per_face.items()
                 if area >= 0.5 * float(geo.weights[geo.owner == face].sum())}
        largest = max(whole or per_face, key=(whole or per_face).get)
        item: dict[str, Any] = {"location": geo.ref(largest), "faces": [geo.ref(face) for face in group],
                                "trapped_faces": [geo.ref(face) for face in sorted(whole)],
                                "trapped_area_mm2": _r(area, _JUDGED), "xyz": _xyz(geo.points[mine].mean(axis=0)),
                                "blocked_by": [geo.ref(face) for face in
                                               sorted({int(f) for f in trapped.blocker[mine] if f and f not in group})]}
        if classify:
            if spent[0] < _RELEASE_RAYS:
                own = _own_directions(geo, sorted(whole, key=lambda f: -whole[f])
                                      + sorted(set(per_face) - set(whole), key=lambda f: -per_face[f]))
                options = {"scale": geo.diagonal, "zero_tol_deg": zero_tol, "own": own, "box": (geo.lo, geo.hi),
                           "lip_limit": 2.0 * BUMP_OFF_MM, "depth": depth}
                release = ops.classify_undercut(geo.points[mine] + geo.normals[mine] * geo.eps, geo.normals[mine],
                                                pull, counted, **options)
                release["stroke_mm"] = _stroke(geo, release, index)
                fields = _release_fields(release, geo.points[mine], pull)
                if fields["release"] == "none" and len(index) < _CONFIRM_UNDER:
                    # An error to be: read again on denser points before it is said (``_CONFIRM_UNDER``).
                    points, normals = _denser(geo, mine, pull, zero_tol)
                    if len(points) < _CONFIRM_POINTS:
                        unconfirmed += 1
                        continue
                    release = ops.classify_undercut(points + normals * geo.eps, normals, pull, counted, **options)
                    fields = _release_fields(release, points, pull)
                    item["confirmed_points"] = len(points)
            else:
                release = {"release": "unknown", "kind": None, "directions": [], "vectors": [], "angled": [],
                           "stroke_mm": None}
                fields = _release_fields(release, geo.points[mine], pull)
            item.update(fields)
            # what the rule of features nothing releases reads: the area, none where it is released, and no
            # figure where its release was not searched (not measured, never passed)
            item["unreleasable_area_mm2"] = {"none": item["trapped_area_mm2"], "unknown": None}.get(fields["release"], 0.0)
            item["leaning"] = ", ".join(geo.ref(face).rsplit("/", 1)[-1] for face in sorted(whole or per_face))
            if fields["release"] == "side_action":
                slides.extend(np.asarray(vector, dtype=float) for vector in release["vectors"])
        items.append(item)
        kept.append(mine)
    groups = [sorted({int(face) for face in geo.owner[mask]}) for mask in kept]
    in_group = np.isin(geo.owner, [face for group in groups for face in group])
    trapped_mask = np.logical_or.reduce(kept) if kept else np.zeros(len(geo.points), dtype=bool)
    leaning = trapped.trapped & ~trapped.zero & in_group
    zero = trapped.trapped & trapped.zero & in_group
    largest_faces = []
    for ordinal in sorted({int(f) for f in geo.owner[trapped_mask]}):
        mine = trapped_mask & (geo.owner == ordinal)
        largest_faces.append({"location": geo.ref(ordinal), "area_mm2": _r(float(geo.weights[mine].sum()), 2),
                              "centroid_xyz": _xyz(geo.points[mine].mean(axis=0))})
    largest_faces.sort(key=lambda face: -(face["area_mm2"] or 0))
    # One slide serves every feature it frees along its direction: the part's slides are its features' distinct
    # directions (within a degree), not their sum.
    distinct: list[np.ndarray] = []
    for vector in slides:
        if not any(float(vector @ other) > math.cos(math.radians(1.0)) for other in distinct):
            distinct.append(vector)
    return {"items": items, "groups": groups, "area": float(geo.weights[trapped_mask].sum()),
            "surface": float(geo.areas.sum()),
            "faces": len({int(f) for f in geo.owner[trapped_mask]}), "leaning": float(geo.weights[leaning].sum()),
            "zero": float(geo.weights[zero].sum()), "largest": largest_faces,
            "slides": [ops.direction_name(vector) for vector in distinct], "unconfirmed": unconfirmed,
            "crevices": _crevices(geo, trapped)}


def _crevices(geo: _Geometry, trapped: _Trapped) -> list[dict[str, Any]]:
    """The crevices the trapped test met (``_CREVICE``): per pair of faces, where and over how much of the first."""
    found: dict[tuple[int, int], dict[str, Any]] = {}
    for index in np.nonzero(trapped.across)[0]:
        key = (int(geo.owner[index]), int(trapped.across[index]))
        pair = found.setdefault(key, {"area": 0.0, "points": []})
        pair["area"] += float(geo.weights[index])
        pair["points"].append(geo.points[index])
    return [{"location": geo.ref(a), "faces": [geo.ref(a), geo.ref(b)], "area_mm2": _r(pair["area"], 3),
             "gap_under_mm": _r(_CREVICE * geo.eps, 4), "xyz": _xyz(np.mean(pair["points"], axis=0))}
            for (a, b), pair in sorted(found.items(), key=lambda kv: -kv[1]["area"])]


def _release_fields(release: dict[str, Any], points: np.ndarray, pull: np.ndarray) -> dict[str, Any]:
    vectors = release.get("vectors") or []
    if vectors:
        side = np.asarray(vectors[0], dtype=float)
        across = np.cross(pull, side)
        across /= np.linalg.norm(across) or 1.0
    else:
        side, across = ops.basis(pull)
    heights, widths = points @ pull, points @ across
    found = release["release"]
    depth = release.get("depth_mm")
    slide = release.get("slide_depth_mm")
    allowance = BUMP_OFF_MM
    # A feature this shallow against the pull is stripped off it as the part ejects, or one no slide
    # frees cleanly is scraped over its lip by the slide (BUMP_OFF_MM, text-to-cad's own figure).
    over = None
    if depth is not None and depth <= allowance and found in ("side_action", "lifter", "collapsible_core", "none"):
        over = "the pull"
    elif found == "none" and slide is not None and slide <= allowance:
        over = "a slide"
    stroke = _r(release.get("stroke_mm"), 3)
    fields = {"kind": release["kind"], "release": "bump_off" if over else found,
              "side_actions": release["directions"],
              "side_action_count": len(release["directions"]) if found == "side_action" and not over else 0,
              "angled": any(release.get("angled") or []), "stroke_mm": stroke,
              "height_mm": _r(float(heights.max() - heights.min()), 3),
              "width_mm": _r(float(widths.max() - widths.min()), 3)}
    fields["depth_said"] = "its depth unmeasured (the part's release budget spent)"
    if depth is not None:
        fields["depth_mm"] = _r(depth, 4)
        fields["depth_said"] = (f"at least {mm(_r(depth, 3))} mm deep against the pull"
                                if release.get("depth_limited") else f"{mm(_r(depth, 3))} mm deep against the pull")
    if slide is not None:
        fields["slide_depth_mm"] = _r(slide, 4)
        fields["depth_said"] += (f", more than {mm(_r(slide, 3))} mm against its best slide"
                                 if release.get("slide_depth_limited") else
                                 f", {mm(_r(slide, 3))} mm against its best slide")
    if over:
        fields["bump_off_over"] = over
        fields["interference_mm"] = _r(depth if over == "the pull" else slide, 4)
    return fields


def _undercuts(geos: list[_Geometry], pull: np.ndarray, zero_tol: float,
               parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if parts is None:
        parts = [_undercut_part(geo, pull, zero_tol) for geo in geos]
    items = sorted((item for part in parts for item in part["items"]), key=lambda item: -(item["trapped_area_mm2"] or 0))
    surface = sum(part["surface"] for part in parts)
    area = sum(part["area"] for part in parts)
    releases = [item.get("release") for item in items]
    crevices = [crevice for part in parts for crevice in part["crevices"]]
    result = {
        "pull_axis": [_r(v) for v in pull],
        "method": ("points sampled on every face, each shot along the way its face opens with exact rays (a "
                   "zero-draft point both ways); a blocked point is trapped, but one standing in a crevice (another "
                   "face within three ray offsets straight out of it); trapped faces that touch are one group, "
                   "split where its trapped points lie apart: each piece a feature, released by rays along slides "
                   "(its own faces' directions and eight round the parting plane; angled only where no plain ones "
                   "free it), a lifter's short move, or a collapsible core's; one nothing releases that rests on "
                   "few points is read again on denser ones; each part is tested against itself"),
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
        # a part's side actions are its distinct slide directions: one slide serves every feature along its way
        "side_action_count": sum(len(part["slides"]) for part in parts),
        "side_action_directions": [name for part in parts for name in part["slides"]],
        "lifter_count": releases.count("lifter"),
        "collapsible_core_count": releases.count("collapsible_core"),
        "unreleasable_count": releases.count("none"),
        "bump_off_count": releases.count("bump_off"),
        "unsearched_count": releases.count("unknown"),
        "unconfirmed_count": sum(part["unconfirmed"] for part in parts),
        "crevice_count": len(crevices),
        "crevice_area_mm2": _r(sum(crevice["area_mm2"] or 0.0 for crevice in crevices), 3),
        "crevices": crevices[:20],
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
        checkpoint()
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
        checkpoint()
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
        checkpoint()
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
        checkpoint()
        mine = (geo.owner == ordinal) & finite
        if not mine.any():
            continue
        v, w = values[mine], geo.weights[mine]
        top = int(np.argmax(v))
        tidy = clean[mine]
        # Narrow: a face the ball cannot sit on -- most of its points held by a face round a convex edge (a
        # rib's top, a plate's end). A face merely narrow is read as it is: its balls are its own wall.
        narrow = float(w[tidy].sum()) < 0.3 * float(w.sum())
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
        _refine_thin(geo, per_face, bound, owners, links)
        if nominal:
            _refine_thick(geo, per_face, float(nominal), cap, convex, values)
    return _Thickness(values, held, nominal, per_face)


#: Faces whose thickest sampled ball reaches this share of the nominal wall, and is still under the thick-section
#: limit (``molding.thick_section``'s ratio), have that thickest refined: past the limit, or under the share, the
#: verdict cannot change.
_THICK_REFINED_SHARE = 1.2
#: At most this many faces are refined, thickest first; each search runs at most this many rounds of eight trials
#: from each of its starts, a gain under ``_THICK_GAIN`` of the nominal wall counting as none.
_THICK_REFINED_FACES = 32
_THICK_ROUNDS = 16
_THICK_STARTS = 2
_THICK_GAIN = 0.01
#: A search settles once its step is this share of the face's (u, v) span: near its greatest the ball changes
#: with the square of the distance, so the last hundredth moves the figure by less than the gain.
_THICK_SETTLED = 1e-2


def _thick_limit() -> float:
    """``molding.thick_section``'s ratio to the nominal wall (the rules' own, read once)."""
    from cad._internal.dfm import molding as rules_side

    return float(next(rule.limit for rule in rules_side.RULES.rules if rule.id == "molding.thick_section"))


def _refine_thick(geo: _Geometry, per_face: dict[int, dict[str, Any]], nominal: float, cap: np.ndarray,
                  convex: dict[int, set[int]], values: np.ndarray) -> None:
    """The greatest ball over each face whose thickest sample lies where the thick-section verdict could turn
    (between ``_THICK_REFINED_SHARE`` and the rule's limit times the nominal wall), not at its samples alone: a
    pattern search over the face's own (u, v) from each of its ``_THICK_STARTS`` thickest samples, every start's
    eight neighbours solved together a round (``ops.ball_thickness``, as the samples are), the step halved where
    none gains ``_THICK_GAIN`` of the nominal wall, settled at ``_THICK_SETTLED`` of the face's span, each trial inside the face (on its boundary a convex edge's
    other face passes through the point) and no ball held across a convex edge of it. Only the triangles and
    samples within the limit's diameter of the face are tried: a ball under it is bound there, so the figure is
    exact below the limit, and the search stops once a ball reaches it (the face is thick, whatever more). Four
    alike blind holes' floors, sampled where each placement put the points, read 2.6 to 3.1 mm against a true
    4.0; refined, they read thick alike in every placement."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepTools import BRepTools
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.TopAbs import TopAbs_IN
    from OCP.gp import gp_Pnt, gp_Pnt2d

    limit = _thick_limit() * nominal
    gain = _THICK_GAIN * nominal
    vertices, triangles, owners = geo.mesh
    order = sorted(((face["max"], ordinal) for ordinal, face in per_face.items()
                    if _THICK_REFINED_SHARE * nominal <= face["max"] < limit), reverse=True)
    if order:
        corners = vertices[triangles]
        tri_hi, tri_lo = corners.max(axis=1), corners.min(axis=1)
    for _, ordinal in order[:_THICK_REFINED_FACES]:
        checkpoint()
        face = per_face[ordinal]
        shape = geo.faces[ordinal - 1]
        surface = BRep_Tool.Surface_s(shape.wrapped)
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(shape.wrapped)
        mine = np.flatnonzero((geo.owner == ordinal) & np.isfinite(values))
        if not len(mine):
            continue
        # the neighbourhood a ball under the limit lies in
        box = shape.bounding_box()
        lo = np.array([box.min.X, box.min.Y, box.min.Z]) - limit * 1.05
        hi = np.array([box.max.X, box.max.Y, box.max.Z]) + limit * 1.05
        near = np.flatnonzero(np.all((tri_hi >= lo) & (tri_lo <= hi), axis=1))
        local_tris, local_owner = triangles[near], owners[near]
        around = np.flatnonzero(np.all((geo.points >= lo) & (geo.points <= hi), axis=1))
        bend = cap[mine[0]]
        classifier = BRepClass_FaceClassifier()

        def on_face(u: float, v: float) -> bool:
            classifier.Perform(shape.wrapped, gp_Pnt2d(u, v), 1e-7)
            return classifier.State() == TopAbs_IN

        def thickness(uv: list[tuple[float, float]]) -> np.ndarray:
            rows = [_dfm_brep.point_normal(shape, u, v) for u, v in uv]
            pts = np.array([p for p, _ in rows]).reshape(-1, 3)
            nrm = np.array([n for _, n in rows]).reshape(-1, 3)
            ray = geo.cast(pts - nrm * geo.eps, -nrm) + geo.eps
            read, held_by = ops.ball_thickness(pts, nrm, ray, vertices, local_tris, others=geo.points[around],
                                               point_face=np.full(len(pts), ordinal), triangle_face=local_owner,
                                               others_face=geo.owner[around], cap=np.full(len(pts), bend))
            held = np.array([b >= 0 and int(local_owner[b]) in convex.get(ordinal, set()) for b in held_by],
                            dtype=bool)
            return np.where(np.isfinite(read) & ~held, read, -np.inf)

        searches = []
        for k in mine[np.argsort(-values[mine])][:_THICK_STARTS]:
            projected = GeomAPI_ProjectPointOnSurf(gp_Pnt(*geo.points[k]), surface)
            if projected.NbPoints():
                searches.append({"uv": projected.LowerDistanceParameters(), "best": float(values[k]),
                                 "du": (umax - umin) / 4.0, "dv": (vmax - vmin) / 4.0})
        for _ in range(_THICK_ROUNDS):
            live = [search for search in searches
                    if search["du"] > _THICK_SETTLED * max(umax - umin, 1e-12)
                    or search["dv"] > _THICK_SETTLED * max(vmax - vmin, 1e-12)]
            if not live or max(search["best"] for search in searches) >= limit:
                break  # each search settled, or the face is thick whatever more it holds
            trials, owner_of = [], []
            for n, search in enumerate(live):
                u0, v0 = search["uv"]
                for a in (-1, 0, 1):
                    for b in (-1, 0, 1):
                        if (a or b) and on_face(u0 + a * search["du"], v0 + b * search["dv"]):
                            trials.append((u0 + a * search["du"], v0 + b * search["dv"]))
                            owner_of.append(n)
            read = thickness(trials) if trials else np.zeros(0)
            for n, search in enumerate(live):
                mine_trials = [k for k, o in enumerate(owner_of) if o == n]
                k = max(mine_trials, key=lambda j: read[j]) if mine_trials else None
                if k is not None and float(read[k]) > search["best"] + gain:
                    search["uv"], search["best"] = trials[k], float(read[k])
                else:
                    search["du"], search["dv"] = search["du"] / 2.0, search["dv"] / 2.0
        best = max(searches, key=lambda search: search["best"], default=None)
        if best is not None and best["best"] > face["max"]:
            face["max"] = best["best"]
            face["at"] = _dfm_brep.point_normal(shape, *best["uv"])[0]


#: The thinnest faces (by their least sampled wall) refined to the exact least distance to a face across.
_REFINED_FACES = 32
#: The faces across a face refined against, nearest first, at most.
_REFINED_ACROSS = 8
#: A face of more edges than this is not refined (a web around many holes: its sampled figure stands).
_REFINE_EDGES = 16
#: The least segment leaves the face within 45 degrees of its inward normal, and the face across looks on
#: along it (a wall's far side), by this cosine.
_FACING = math.cos(math.radians(45.0))


def _refine_thin(geo: _Geometry, per_face: dict[int, dict[str, Any]], bound: np.ndarray, owners: np.ndarray,
                 links: dict[int, list[tuple[int, Any]]]) -> None:
    """The thinnest faces' walls refined to the exact least distance between the face and a face across that
    its balls are held by (``BRepExtrema_DistShapeShape``, ``brep.least_segments``), as printing's and cnc's
    walls are (the faces across, of those whose box comes nearer than the face's least sampled wall: first those
    its rays into the material meet and its balls are held by, most often first, then the nearest boxes):
    the segment leaves the face within 45 degrees of its inward normal, the face across looks on
    along it, and a ray along it from the face meets that face first, at that length. A real thin wall
    between two samples -- a cut grazing a drafted corner, whose bounding faces' balls read 0.9 where the
    wall is 0.6 -- is never hidden: the face's least (``low``) and its wall (``median``) become it where it is
    thinner. Faces that share an edge or a corner are not refined (their least distance is 0)."""
    order = sorted((face["low"], ordinal) for ordinal, face in per_face.items() if not face["narrow"])
    boxes = np.array([[*(lambda b: (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z))(f.bounding_box())]
                      for f in geo.faces])
    for _, ordinal in order[:_REFINED_FACES]:
        checkpoint()
        face = per_face[ordinal]
        if len(links.get(ordinal, [])) > _REFINE_EDGES:
            continue
        # the faces across: those whose box comes nearer the face's than its least sampled wall, nearest first,
        # but its neighbours and the faces it shares a corner with
        mine = boxes[ordinal - 1]
        apart = np.linalg.norm(np.maximum(0.0, np.maximum(boxes[:, :3] - mine[3:], mine[:3] - boxes[:, 3:])), axis=1)
        near = {other for other, _ in links.get(ordinal, [])} | {ordinal}
        corners = {tuple(np.round([v.X, v.Y, v.Z], 6)) for v in geo.faces[ordinal - 1].vertices()}
        # those its rays into the material meet and its balls are held by first, most often met first; then
        # the rest whose box is near enough, nearest first
        mask = geo.owner == ordinal
        _, hit = geo.cast_faces(geo.points[mask] - geo.normals[mask] * geo.eps, -geo.normals[mask])
        met = np.concatenate([hit[hit > 0], owners[bound[mask & (bound >= 0)]]]).astype(int)
        seen, counts = np.unique(met, return_counts=True)
        ranked = [int(f) for f in seen[np.argsort(-counts, kind="stable")]]
        ranked += [int(other) + 1 for other in np.argsort(apart, kind="stable") if int(other) + 1 not in ranked]
        across = [other for other in ranked if apart[other - 1] < face["low"] and other not in near
                  and not any(tuple(np.round([v.X, v.Y, v.Z], 6)) in corners for v in geo.faces[other - 1].vertices())]
        best = None
        for other in across[:_REFINED_ACROSS]:
            try:
                segments = _dfm_brep.least_segments(geo.faces[ordinal - 1], geo.faces[other - 1],
                                                    len(links.get(other, [])) > _REFINE_EDGES)
            except Exception:  # noqa: BLE001 - a pair the kernel cannot measure keeps its sampled figure
                continue
            for length, pa, pb, normal, there in segments:
                if best is not None and length >= best[0]:
                    break
                way = (pb - pa) / length
                if float(way @ -normal) < _FACING or float(there @ way) < _FACING:
                    continue
                hit, first = geo.cast_faces((pa + way * geo.eps)[None], way[None])
                if int(first[0]) != other or abs(float(hit[0]) + geo.eps - length) > max(1e-4, 1e-3 * length):
                    continue
                best = (length, pa)
                break
        if best is not None and best[0] < face["low"]:
            face["low"] = best[0]
            face["median"] = min(face["median"], best[0])
            face["at"] = best[1]
            face["refined"] = True


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
        for ordinal, face in measured.per_face.items():
            item = {"location": geo.ref(ordinal), "thickness_mm": _r(face["median"], _LENGTH),
                    "min_mm": _r(face["low"], _LENGTH), "max_mm": _r(face["max"], _LENGTH),
                    "nominal_mm": _r(nominal, _LENGTH),
                    "ratio_to_nominal": _r(_r(face["max"], _LENGTH) / _r(nominal, _LENGTH), _JUDGED),
                    "thin_ratio": _r((face["median"] or 0) / nominal, 3), "feature": "wall",
                    "refined": bool(face.get("refined")), "xyz": _xyz(face["at"])}
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
    chosen, seen = [], set()
    for item in [*thinnest[:_ITEMS // 2], *thickest[:_ITEMS // 2]]:
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
                   "a face round a convex edge (they read low); feature: a rib's or a boss's face (their rules "
                   "judge them, the wall's range does not), else wall"),
    }
    if len(nominals) > 1:
        result["per_part"] = nominals
    return result


_TRANSITION_METHOD = ("each step read on its stepped side: two parallel faces facing the same way whose walls differ "
                     "by a quarter of the nominal or more and by about their offset (one face behind both), joined by a chain "
                     "of faces (a pad's side, a chamfer, a fillet); transition_ratio is the chain's run across "
                     "(square to the faces) over the change in wall, so a vertical step reads 0 and a chamfer its run "
                     "over its rise; the item names the chain's first face, min_mm and max_mm the two walls, at_xyz a "
                     "point on each seam. A free-form face, which no such faces bound, is read by the rolling ball: "
                     "the steepest change between two of its points within four sample spacings whose walls differ by "
                     "half the nominal (basis: ball)")


def _transition(location: str | None, change: dict[str, Any]) -> dict[str, Any]:
    """One step (``ops.steps``) or one face's steepest change of wall (``ops.transitions``) as an item: where it
    is and what it steps."""
    (a, b), (ta, tb) = change["points"], change["thickness"]
    if ta > tb:
        (a, b), (ta, tb) = (b, a), (tb, ta)
    length = change.get("length")
    item = {"transition_ratio": _r(change["ratio"], _JUDGED), "min_mm": _r(ta, 3), "max_mm": _r(tb, 3),
            "change_mm": _r(tb - ta, 3),
            "length_mm": _r(float(length if length is not None else np.linalg.norm(np.asarray(b) - np.asarray(a))), 3),
            "basis": "step" if "chain" in change else "ball",
            "xyz": _xyz((np.asarray(a) + np.asarray(b)) / 2.0), "at_xyz": [_xyz(a), _xyz(b)]}
    return ({"location": location} if location else {}) | item


def _side_walls(geo: _Geometry, measured: _Thickness, faces: list[int]) -> dict[int, float]:
    """The wall under each of ``faces``: the area median of its rolling balls clear of a convex edge, or its widest
    where none is (a rib's top: the rib's thickness)."""
    finite = np.isfinite(measured.values)
    walls: dict[int, float] = {}
    for ordinal in faces:
        mine = (geo.owner == ordinal) & finite
        if not mine.any():
            continue
        clean = mine & ~measured.edge_held
        value = (ops.weighted_median(measured.values[clean], geo.weights[clean]) if clean.any()
                 else float(measured.values[mine].max()))
        if value is not None:
            walls[ordinal] = float(value)
    return walls


def _transitions_part(geo: _Geometry, measured: _Thickness, skip: set[int]) -> list[dict[str, Any]]:
    """The part's steps (``ops.steps`` over its planar faces) and, on its free-form faces no step takes in, the
    rolling ball's steepest change (``ops.transitions``)."""
    checkpoint()  # a part at a time
    nominal = measured.nominal
    if nominal is None or nominal <= 0:
        return []
    links = geo.neighbours()
    planes = {ordinal: (np.asarray(surface.normal, dtype=float), np.asarray(surface.origin, dtype=float))
              for ordinal, surface in enumerate(geo.surfaces, start=1)
              if surface.kind == "plane" and surface.normal is not None and surface.origin is not None}
    walls = _side_walls(geo, measured, list(planes))
    shape_edges = geo.part.edges()
    cache: dict[tuple[int, int], np.ndarray] = {}

    def seams(a: int, b: int) -> np.ndarray:
        key = (a, b)
        if key not in cache:
            segments = []
            for other, edge in links.get(a, []):
                if other != b:
                    continue
                points = []
                for t in np.linspace(0.0, 1.0, 9):
                    at = shape_edges[edge.ordinal - 1].position_at(float(t))
                    points.append([at.X, at.Y, at.Z])
                points = np.array(points)
                segments.extend(zip(points[:-1], points[1:]))
            cache[key] = np.array(segments).reshape(-1, 2, 3)
        return cache[key]

    found = ops.steps(planes, lambda face: [other for other, _edge in links.get(face, [])], seams, walls, nominal,
                      skip=skip)
    items = [_transition(geo.ref(step["chain"][0]), step) for step in found]
    taken = set(skip) | {face for step in found for face in step["chain"]}
    free = np.array([ordinal not in planes and ordinal not in taken for ordinal in geo.owner], dtype=bool)
    usable = free & ~measured.edge_held
    if usable.any():
        for ordinal, change in ops.transitions(geo.points, measured.values, geo.owner, usable, geo.spacing,
                                               nominal).items():
            items.append(_transition(geo.ref(ordinal), change))
    return items


def _transitions(per_part: list[list[dict[str, Any]]]) -> dict[str, Any]:
    items = sorted((item for part in per_part for item in part), key=lambda item: item["transition_ratio"])
    return {"count": len(items), "items": items[:_ITEMS], "method": _TRANSITION_METHOD}


# --- ribs, bosses, corners -------------------------------------------------------------------------------


def _face_wall(thick: _Thickness, ordinal: int) -> float | None:
    face = thick.per_face.get(ordinal)
    return None if face is None else face["median"]


#: Surfaces a fillet may be when it is no cylinder or torus: a blend the kernel wrote as a spline (a
#: variable or a free-form fillet), read by its curvature (``_fillet_radius``).
_FREEFORM = ("bspline", "revolution", "extrusion", "offset", "other")


def _fillet_radius(geo: _Geometry, ordinal: int) -> float | None:
    """The radius of a concave fillet face, None where the face is none: a concave cylinder's or torus's
    own; a free-form face's (``_FREEFORM``) from its curvature at the middle of its parameters, concave where
    its sampled normals turn toward one another (a hollow) rather than apart (a round)."""
    cache = geo.__dict__.setdefault("_fillet_radii", {})
    if ordinal in cache:
        return cache[ordinal]
    surface = geo.surfaces[ordinal - 1]
    radius: float | None = None
    if surface.kind in ("cylinder", "torus"):
        if surface.concave:
            radius = float(surface.minor_radius if surface.kind == "torus" else surface.radius or 0.0)
    elif surface.kind in _FREEFORM:
        mine = geo.owner == ordinal
        points, normals = geo.points[mine], geo.normals[mine]
        if len(points) >= 3:
            dp = points[:, None, :] - points[None, :, :]
            dn = normals[:, None, :] - normals[None, :, :]
            turn = float(np.einsum("ijk,ijk->", dp, dn))
            scale = float(np.einsum("ijk,ijk->", dp, dp)) or 1.0
            if turn < -1e-9 * scale:
                radius = _curvature_radius(geo.faces[ordinal - 1])
    cache[ordinal] = radius
    return radius


def _curvature_radius(face: Any) -> float | None:
    """1 / the larger principal curvature at the middle of a face's parameters (None where it is flat)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepTools import BRepTools

    try:
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
        props = BRepLProp_SLProps(BRepAdaptor_Surface(face.wrapped, True), (umin + umax) / 2, (vmin + vmax) / 2, 2,
                                  1e-9)
        if not props.IsCurvatureDefined():
            return None
        bend = max(abs(props.MaxCurvature()), abs(props.MinCurvature()))
    except Exception:  # noqa: BLE001 - a face the kernel cannot differentiate there reads as no fillet
        return None
    return 1.0 / bend if bend > 1e-9 else None


def _bases(geo: _Geometry, ordinal: int, links: dict[int, list[tuple[int, Any]]],
           square_to: np.ndarray, square: bool = True) -> list[tuple[int, float, int]]:
    """The planar faces a face stands on: (base ordinal, fillet radius (0 sharp), the fillet's ordinal or 0).
    A base meets the face at a concave edge, or across a concave fillet (``_fillet_radius``: a cylinder, a
    torus or a free-form blend) both of whose joins are tangent. ``square``: the base's normal is square to
    ``square_to`` (a rib's); else along it."""
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
            radius = _fillet_radius(geo, other)
            if radius is None:
                continue
            for beyond, join in links.get(other, []):
                if beyond != ordinal and join.smooth and fits(beyond):
                    found.append((beyond, radius, other))
    return found


def _roots(geo: _Geometry, face: int, base: int, links: dict[int, list[tuple[int, Any]]]) -> list[tuple[float, int]]:
    """Where ``face`` meets the plane of ``base``: (fillet radius, the fillet's ordinal) for each concave
    fillet between them, (0, 0) for a sharp concave edge."""
    found = []
    for other, edge in links.get(face, []):
        if edge.concave and not edge.smooth and geo.surfaces[other - 1].kind == "plane" and _same_plane(geo, other,
                                                                                                         base):
            found.append((0.0, 0))
        elif edge.smooth and (radius := _fillet_radius(geo, other)) is not None:
            if any(beyond != face and join.smooth and geo.surfaces[beyond - 1].kind == "plane"
                   and _same_plane(geo, beyond, base) for beyond, join in links.get(other, [])):
                found.append((radius, other))
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
               used: set[int], trapped: set[int] | None = None, kinds: dict[int, str] | None = None
               ) -> list[dict[str, Any]]:
    """The part's ribs (see the module). A rib a trapped face touches -- one of its own faces, or a face beside
    them no larger than its side, not its base -- is a snap arm, its barb that face (``kind``: ``snap``, else
    ``rib``): judged by the snap rule, not the rib's height and spacing."""
    checkpoint()  # a part at a time
    links = geo.neighbours()
    trapped = trapped or set()
    kinds = kinds if kinds is not None else {}
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

    def opposite(position: int, a: int) -> list[tuple[int, np.ndarray, np.ndarray]]:
        """The faces across ``a`` that make a slab with it: opposite it (within 12 deg), met by half of its
        rays or more, and standing on a base as it does -- each with ``a``'s rays' lengths and where they came out."""
        na = np.asarray(geo.surfaces[a - 1].normal)
        mine = geo.owner == a
        distance = all_distance[offsets[position]:offsets[position + 1]] + geo.eps
        hit = all_hit[offsets[position]:offsets[position + 1]]
        found = []
        for b in sorted({int(face) for face in hit if face and face != a}):
            if b not in bases or not bases[b]:
                continue
            if float(na @ np.asarray(geo.surfaces[b - 1].normal)) > -math.cos(math.radians(12.0)):
                continue
            share = float(geo.weights[mine][hit == b].sum()) / max(float(geo.weights[mine].sum()), 1e-12)
            if share >= 0.5:
                found.append((b, distance, hit))
        return found

    slabs = {a: opposite(position, a) for position, a in enumerate(standing)}
    # A rib stands on a wall, not on the rib it crosses: a slab's own side is no base where there is another (two
    # ribs crossing closer than they are tall each read the other's side as the nearer face to stand on, and its
    # 1.2 mm as their wall).
    sides = {face for a, found in slabs.items() for b, _distance, _hit in found for face in (a, b)}
    for a in standing:
        na = np.asarray(geo.surfaces[a - 1].normal)
        for b, distance, hit in slabs[a]:
            if (min(a, b), max(a, b)) in seen:
                continue
            pairs = [(ba, bb) for ba in bases[a] for bb in bases[b] if _same_plane(geo, ba[0], bb[0])]
            pairs = [pair for pair in pairs if pair[0][0] not in sides] or pairs
            if not pairs:
                continue

            def stands(pair: tuple[tuple[int, float, int], tuple[int, float, int]]) -> float:
                base = pair[0][0]
                normal = np.asarray(geo.surfaces[base - 1].normal)
                return float(((geo.vertices(a) - np.asarray(geo.surfaces[base - 1].origin)) @ normal).max())

            # A rib touching walls as well as its floor stands on the face it is shortest from.
            (base, fillet_a, fa), (_base_b, fillet_b, fb) = min(pairs, key=stands)
            nbase = np.asarray(geo.surfaces[base - 1].normal)
            across = distance[hit == b]
            root, tip = float(across.max()), float(across.min())
            height = stands(((base, 0.0, 0), (base, 0.0, 0)))
            along = np.cross(nbase, na)
            along /= np.linalg.norm(along) or 1.0
            span = geo.vertices(a) @ along
            length = float(span.max() - span.min())
            if root <= 0 or height < 1.0 * root or length < 1.5 * root:
                continue
            seen.add((min(a, b), max(a, b)))
            # The rib's ends (faces joining both sides): their roots are the rib's too, sharp or filleted.
            # (No wider than the rib across it: a wall the rib runs into joins both sides too, and is no end.)
            ends = {end for end in ({other for other, _e in links.get(a, [])} & {other for other, _e in links.get(b, [])})
                    - {base, fa, fb, 0} if float(np.ptp(geo.vertices(end) @ na)) <= 1.5 * root + geo.eps}
            end_roots = [root for end in ends for root in _roots(geo, end, base, links)]
            used.update(ends | {fillet_face for _radius, fillet_face in end_roots} - {0})
            wall = _r(_face_wall(thick, base) or nominal, _LENGTH)
            root, height = float(_r(root, _LENGTH)), float(_r(height, _LENGTH))
            gaps = []
            for face in (a, b):
                own = geo.owner == face
                outward = geo.cast(geo.points[own] + geo.normals[own] * geo.eps, geo.normals[own])
                finite = outward[np.isfinite(outward)]
                if len(finite) >= 0.5 * own.sum():
                    gaps.append(float(np.median(finite)))
            gap = _r(min(gaps), _LENGTH) if gaps else None
            fillet = float(_r(min([fillet_a, fillet_b] + [radius for radius, _f in end_roots]), 4))
            # the rib's draft: the least of its sides' and its ends' (its top, square to the pull, has none to give)
            draft = min(drafts[face - 1].draft for face in (a, b, *ends))
            own = ({a, b, fa, fb} | ends | {fillet_face for _radius, fillet_face in end_roots}) - {0}
            used.update(own)
            side = min(float(geo.areas[a - 1]), float(geo.areas[b - 1]))
            beside = {other for face in ({a, b} | ends) for other, _edge in links.get(face, [])} - own - {base}
            barb = sorted(face for face in (({a, b} | ends | beside) & trapped)
                          if face in own or float(geo.areas[face - 1]) <= side)
            kind = "snap" if barb else "rib"
            kinds.update({face: kind for face in own})
            items.append({
                "location": geo.ref(a), "kind": kind, "faces": [geo.ref(a), geo.ref(b), geo.ref(base)],
                "ends": [geo.ref(face) for face in sorted(ends)],
                **({"barb": [geo.ref(face) for face in barb]} if barb else {}),
                "thickness_mm": _r(root, 3), "tip_thickness_mm": _r(tip, 3), "height_mm": _r(height, 3),
                "length_mm": _r(length, 3), "wall_mm": _r(wall, 3),
                "thickness_ratio": _r(root / wall, _JUDGED) if wall else None,
                "height_ratio": _r(height / wall, _JUDGED) if wall else None,
                "height_to_thickness": _r(height / root, _JUDGED),
                "base_fillet_mm": _r(fillet, _JUDGED), "base_fillet_ratio": _r(fillet / root, _JUDGED),
                "base_fillet_wall_ratio": _r(fillet / wall, _JUDGED) if wall else None,
                "draft_deg": _r(draft, _JUDGED), "gap_mm": _r(gap, 3),
                "gap_to_thickness": _r(gap / root, _JUDGED) if gap is not None else None,
                "gap_to_wall": _r(gap / wall, _JUDGED) if gap is not None and wall else None,
                "xyz": _centroid(geo, a)})
    return items


#: A boss or its core may be drafted: a cone this close to a cylinder (its half-angle, degrees) is one.
_BOSS_CONE_DEG = 5.0


def _round(surface: Any) -> bool:
    """A cylinder, or a cone drafted no more than ``_BOSS_CONE_DEG``: a boss's or a core's side."""
    return surface.kind == "cylinder" or (surface.kind == "cone" and surface.half_angle_deg is not None
                                          and abs(surface.half_angle_deg) <= _BOSS_CONE_DEG)


def _radius_at(surface: Any, point: np.ndarray) -> float:
    """A cylinder's radius, or a cone's where its axis passes ``point``'s height (its base, for a boss)."""
    radius = float(surface.radius or 0.0)
    if surface.kind != "cone":
        return radius
    height = float((np.asarray(point) - np.asarray(surface.origin)) @ np.asarray(surface.axis))
    return radius + height * math.tan(math.radians(float(surface.half_angle_deg or 0.0)))


def _bosses_part(geo: _Geometry, thick: _Thickness, nominal: float | None, used: set[int],
                 kinds: dict[int, str] | None = None) -> list[dict[str, Any]]:
    checkpoint()  # a part at a time
    links = geo.neighbours()
    kinds = kinds if kinds is not None else {}
    items: list[dict[str, Any]] = []
    holes = [(ordinal, surface) for ordinal, surface in enumerate(geo.surfaces, start=1)
             if _round(surface) and surface.concave and surface.axis is not None]
    taken: set[int] = set()
    for ordinal, surface in enumerate(geo.surfaces, start=1):
        checkpoint()
        if not _round(surface) or surface.concave is not False or surface.axis is None or ordinal in taken:
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
        radius = _radius_at(surface, obase)
        inner = None
        for hole, hs in holes:
            ha = np.asarray(hs.axis)
            if abs(abs(float(ha @ axis)) - 1.0) > 1e-6 or _radius_at(hs, obase) >= radius:
                continue
            offset = np.asarray(hs.origin) - origin
            if np.linalg.norm(offset - axis * float(offset @ axis)) > 1e-3 * max(radius, 1.0):
                continue
            span = (geo.vertices(hole) - obase) @ nbase
            if span.max() < 0.5 * height:
                continue
            if inner is None or _radius_at(hs, obase) > inner[1]:
                inner = (hole, _radius_at(hs, obase), float(span.min()))
        taken.add(ordinal)
        used.update({ordinal, fillet_face} - {0})
        kinds.update({face: "boss" for face in {ordinal, fillet_face, inner[0] if inner else 0} - {0}})
        wall_ref = _r(_face_wall(thick, base) or nominal, _LENGTH)
        wall = float(_r(radius - inner[1] if inner else 2.0 * radius, _LENGTH))
        items.append({
            "location": geo.ref(ordinal), "faces": [geo.ref(ordinal), geo.ref(base)] + ([geo.ref(inner[0])] if inner else []),
            "od_mm": _r(2 * radius, 3), "id_mm": _r(2 * inner[1], 3) if inner else None, "hollow": inner is not None,
            "boss_wall_mm": _r(wall, 3), "wall_mm": _r(wall_ref, 3),
            "wall_ratio": _r(wall / wall_ref, _JUDGED) if wall_ref else None,
            "od_to_id": _r(radius / inner[1], 3) if inner else None, "height_mm": _r(height, 3),
            "height_to_od": _r(height / (2 * radius), 3), "base_fillet_mm": _r(fillet, _JUDGED),
            "hole_floor_above_base_mm": _r(inner[2], 3) if inner else None, "xyz": _centroid(geo, ordinal)})
    return items


def _corners_part(geo: _Geometry, thick: _Thickness, nominal: float | None, used: set[int]) -> list[dict[str, Any]]:
    checkpoint()  # a part at a time
    links = geo.neighbours()
    items: list[dict[str, Any]] = []

    def wall(*faces: int) -> float | None:
        values = [value for face in faces if (value := _face_wall(thick, face))]
        return _r(min(values) if values else nominal, _LENGTH)

    for edge in geo.edges:
        checkpoint()
        a, b = edge.faces
        if not edge.concave or edge.smooth or a in used or b in used:
            continue
        reference = wall(a, b)
        # at the smaller face; two of one area (a symmetric pair, equal but for the turn's noise) at the lower
        # ordinal, whichever way the edge lists them
        area_a, area_b = float(geo.areas[a - 1]), float(geo.areas[b - 1])
        same = abs(area_a - area_b) <= 1e-6 * max(area_a, area_b, 1e-12)
        first = min(a, b) if same else (a if area_a < area_b else b)
        items.append({"location": geo.ref(first), "faces": [geo.ref(a), geo.ref(b)],
                      "edge": geo.part.ref("edge", edge.ordinal), "radius_mm": 0.0, "sharp": True,
                      "angle_deg": _r(edge.angle_deg, 2), "length_mm": _r(edge.length, 3),
                      "wall_mm": _r(reference, 3), "ratio_to_wall": 0.0, "xyz": _xyz(edge.midpoint)})
    for ordinal, surface in enumerate(geo.surfaces, start=1):
        checkpoint()
        if ordinal in used or surface.kind not in ("cylinder", "torus", *_FREEFORM):
            continue
        # A fillet: joined tangentially to at least two faces (its ends may meet caps at sharp edges).
        joins = [(other, edge) for other, edge in links.get(ordinal, []) if edge.smooth]
        if len(joins) < 2:
            continue
        radius = _fillet_radius(geo, ordinal)
        if radius is None:
            continue
        reference = wall(*(other for other, _edge in joins))
        radius = float(_r(radius, 4))
        items.append({"location": geo.ref(ordinal), "faces": [geo.ref(ordinal)] + [geo.ref(o) for o, _ in joins],
                      "radius_mm": radius, "sharp": False, "wall_mm": reference,
                      "ratio_to_wall": _r(radius / reference, _JUDGED) if reference else None,
                      "xyz": _centroid(geo, ordinal)})
    return items


def _features_family(name: str, per_part: list[list[dict[str, Any]]], key: str, worst_low: bool = True
                     ) -> dict[str, Any]:
    items = [item for part in per_part for item in part]
    items.sort(key=lambda item: (item.get(key) if item.get(key) is not None else math.inf) * (1 if worst_low else -1))
    return {"count": len(items), "items": items[:_ITEMS]}


# --- projection and parting ------------------------------------------------------------------------------


def _projection_part(geo: _Geometry, pull: np.ndarray) -> tuple[dict[str, Any], dict[str, Any], np.ndarray]:
    checkpoint()  # a part at a time
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
        checkpoint()
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


def _families(geos: list[_Geometry], pull: np.ndarray, wall_limit: float, zero_tol: float,
              rotation: np.ndarray | None = None) -> dict[str, Any]:
    """Every family of ``geos`` along ``pull``; ``rotation``: the turn that put ``geos`` into their own frame
    (``measure``), by which ``pull_check`` turns the world's axes into it."""
    lost: dict[str, set[str]] = {}

    def tracked(names: tuple[str, ...], fn: Any, *args: Any) -> Any:
        """``_safe(fn, *args)``, the faces its rays the kernel failed to intersect said against each family it
        measures (``unmeasured_faces``)."""
        before = _failures(geos)
        try:
            return _safe(fn, *args)
        finally:
            refs = _lost_since(geos, before)
            for name in names if refs else ():
                lost.setdefault(name, set()).update(refs)

    drafts = [_face_drafts(geo, pull, zero_tol) for geo in geos]
    report: dict[str, Any] = {"scale": _scale(geos)}
    report["draft"] = tracked(("draft",), _draft, geos, drafts, pull, wall_limit, zero_tol)
    under_parts = tracked(("undercuts",), lambda: [_undercut_part(geo, pull, zero_tol) for geo in geos])
    if isinstance(under_parts, dict):
        report["undercuts"] = under_parts
        trapped: list[set[int]] = [set() for _ in geos]
    else:
        report["undercuts"] = tracked(("undercuts",), _undercuts, geos, pull, zero_tol, under_parts)
        trapped = [{face for group in part["groups"] for face in group} for part in under_parts]
    touching = tracked(("touching", "draft", "undercuts"),
                       lambda: {"items": [pair for geo in geos for pair in geo.touching]})
    if "error" in touching or touching["items"]:
        touching["count"] = len(touching.get("items") or [])
        report["touching"] = touching
    walled = ("thickness", "transitions", "ribs", "bosses", "corners")
    thick = tracked(walled, lambda: [_thickness_part(geo) for geo in geos])
    if isinstance(thick, dict):
        for name in ("thickness", "transitions", "ribs", "bosses", "corners"):
            report[name] = dict(thick)
    else:
        report["thickness"] = tracked(("thickness",), _thickness, geos, thick)
        used: list[set[int]] = [set() for _ in geos]
        kinds: list[dict[int, str]] = [{} for _ in geos]
        report["ribs"] = tracked(("ribs",), lambda: _features_family("ribs", [
            _ribs_part(geo, t, d, t.nominal, u, s, k) for geo, t, d, u, s, k in zip(geos, thick, drafts, used, trapped,
                                                                                    kinds)],
            "thickness_ratio", worst_low=False))
        report["bosses"] = tracked(("bosses",), lambda: _features_family("bosses", [
            _bosses_part(geo, t, t.nominal, u, k) for geo, t, u, k in zip(geos, thick, used, kinds)], "wall_ratio",
            worst_low=False))
        report["corners"] = tracked(("corners",), lambda: _features_family("corners", [
            _corners_part(geo, t, t.nominal, u) for geo, t, u in zip(geos, thick, used)], "ratio_to_wall"))
        report["transitions"] = tracked(("transitions",), lambda: _transitions([_transitions_part(geo, t, u)
                                                            for geo, t, u in zip(geos, thick, used)]))
        # A rib's or a boss's faces are judged by their rules, not the wall's range (``feature``).
        named = {geo.ref(face): kind for geo, part in zip(geos, kinds) for face, kind in part.items()}
        for item in (report["thickness"].get("items") or []) if isinstance(report["thickness"], dict) else []:
            item["feature"] = named.get(item.get("location"), "wall")
        # A rib's sides and ends are judged by its draft rules (molding.rib_draft, molding.draft_zero), once for
        # the rib, not as walls face by face (``feature``).
        sides = {face: item.get("kind") or "rib" for item in (report["ribs"].get("items") or [])
                 if isinstance(report["ribs"], dict)
                 for face in [*(item.get("faces") or [])[:2], *(item.get("ends") or [])]}
        # A face an undercut traps is formed by what releases it (a slide's, a lifter's), not along the pull: its
        # draft along the pull is no wall's either, and the undercut's rule is its one finding.
        formed = {face for item in (report["undercuts"].get("items") or []) if isinstance(report["undercuts"], dict)
                  for face in item.get("trapped_faces") or ()}
        for item in (report["draft"].get("items") or []) if isinstance(report["draft"], dict) else []:
            item["feature"] = sides.get(item.get("location"), "undercut" if item.get("location") in formed else "wall")
    # Each part's projection, and its parting read off it at once: a part's raster (millions of cells on a
    # detailed part) is dropped as soon as its parting is read, never every part's held together (phalanx's 107
    # parts: 1 GB). A parting that fails is the family's error, as a projection that fails is both's.
    partings: list[dict[str, Any]] | dict[str, Any] = []

    def projections() -> list[dict[str, Any]]:
        nonlocal partings
        items = []
        for geo, d, t in zip(geos, drafts, trapped):
            item, projection, vertices = _projection_part(geo, pull)
            items.append(item)
            if isinstance(partings, list):
                found = _safe(_parting_part, geo, d, projection, vertices, pull, wall_limit, t)
                if isinstance(found, dict) and set(found) == {"error"}:
                    partings = found
                else:
                    partings.append(found)
            del projection, vertices
        return items

    projected = _safe(projections)
    if isinstance(projected, dict):
        report["projection"] = projected
        report["parting"] = dict(projected)
    else:
        report["projection"] = _safe(_projection, projected, pull)
        report["parting"] = partings if isinstance(partings, dict) else _safe(_parting, partings, pull)
        report["envelope"] = _safe(_envelope, projected, None if isinstance(partings, dict) else partings)
    if len(geos) == 1 and len(geos[0].part.solids()) == 1 and "error" not in report["draft"] and \
            "error" not in report["undercuts"]:
        # One part of one solid: does another pull do better? (An assembly's parts, a part's solids, each open
        # their own way: no one pull to compare.)
        report["pull_check"] = tracked(("pull_check",), _pull_check, geos, pull,
                                       rotation if rotation is not None else np.eye(3), report, wall_limit, zero_tol)
    for name, refs in lost.items():
        family = report.get(name)
        if isinstance(family, dict) and "error" not in family:
            family["unmeasured_faces"] = sorted(refs)
    return report


def _failures(geos: list[_Geometry]) -> list[list[dict[int, int]]]:
    """Each part's rays' failures so far (``_dfm_brep.failures``)."""
    return [_dfm_brep.failures([geo._rays.screen]) if geo._rays is not None else [{}] for geo in geos]


def _lost_since(geos: list[_Geometry], before: list[list[dict[int, int]]]) -> set[str]:
    """The refs of the faces the kernel failed to intersect a ray with since ``before`` (``_failures``)."""
    found: set[str] = set()
    for geo, was in zip(geos, before):
        if geo._rays is not None:
            found |= {geo.ref(ordinal) for ordinal in
                      _dfm_brep.failed_ordinals(geo.part, [geo._rays.screen], [geo._rays.faces], was)}
    return found


def _unintersected(geos: list[_Geometry]) -> list[dict[str, Any]]:
    """Each part's ``rays_unintersected`` finding, at its faces."""
    found = [_dfm_brep.unintersected(geo.part, [geo._rays.screen], [geo._rays.faces])
             for geo in geos if geo._rays is not None]
    return [finding for finding in found if finding]


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


def _pull_row(draft: dict[str, Any], under: dict[str, Any]) -> dict[str, Any]:
    """What a pull is ranked by (``molding.ranked``), of its draft and undercuts families."""
    return {"undercut_candidate_area_mm2": under["candidate_area_mm2"],
            "undercut_count": under["undercut_count"], "side_action_count": under["side_action_count"],
            "lifter_count": under["lifter_count"] + under["collapsible_core_count"],
            "unreleasable_count": under["unreleasable_count"],
            "wall_area_mm2": draft["wall_area_mm2"], "zero_draft_wall_area_mm2": draft["zero_draft_wall_area_mm2"],
            "min_wall_draft_deg": (draft.get("min_wall_draft") or {}).get("draft_deg")}


def _named_pulls(geos: list[_Geometry], turn: np.ndarray, but: tuple[np.ndarray, ...] = ()) -> list[tuple[str, np.ndarray]]:
    """The pulls ranked: the world's x, y and z (turned by ``turn`` into the frame ``geos`` stand in) and the
    part's principal axes of inertia that are none of them, less any along one of ``but``."""
    named: list[tuple[str, np.ndarray]] = []

    def taken(unit: np.ndarray) -> bool:
        return any(abs(abs(float(unit @ other)) - 1.0) < 1.5e-4 for other in (*but, *(axis for _name, axis in named)))

    for name, axis in (("x", (1.0, 0.0, 0.0)), ("y", (0.0, 1.0, 0.0)), ("z", (0.0, 0.0, 1.0))):
        unit = turn @ np.array(axis, dtype=float)
        if not taken(unit):
            named.append((name, unit))
    try:
        for index, axis in enumerate(_principal_axes(geos)):
            unit = axis / (np.linalg.norm(axis) or 1.0)
            if not taken(unit):
                named.append((f"principal{index}", unit))
    except Exception:  # noqa: BLE001 - no inertia frame: the world axes alone
        pass
    return named


def _pull_check(geos: list[_Geometry], pull: np.ndarray, rotation: np.ndarray, report: dict[str, Any],
                wall_limit: float, zero_tol: float) -> dict[str, Any]:
    """Whether another pull does better than the one measured (``molding.better_pull``).

    The measured pull's row is the report's own figures (one reading of it, never a second); x, y, z and the
    part's principal axes are each read on the same sampled points, only as far as it can still do better
    (``molding.dominates``, a figure not yet read taken at its best): its draft first (no ray), then what it traps,
    then what releases that, then its parting. So a pull nothing beats costs nothing here -- nothing trapped and no wall without
    draft: no pull is read at all -- and one that leaves a wall without draft is not searched for undercuts.
    ``geos`` stand in the part's own frame (``rotation``): each axis is turned into it, and said in the world."""
    parting = report.get("parting") if isinstance(report.get("parting"), dict) else {}
    chosen = {"pull": ops.direction_name(pull), "axis": [_r(v) for v in pull], "measured": "full",
              **_pull_row(report["draft"], report["undercuts"]), "flat_parting": parting.get("flat_parting_possible")}
    if not dominates({"wall_area_mm2": chosen["wall_area_mm2"]}, chosen):
        return {"chosen": chosen, "candidates": [], "better": None,
                "note": "nothing is trapped and no wall is without draft along this pull: no pull does better"}
    rows = []
    for name, axis in _named_pulls(geos, rotation, (pull,)):
        checkpoint()  # a pull at a time
        draft = _draft(geos, [_face_drafts(geo, axis, zero_tol) for geo in geos], axis, wall_limit, zero_tol)
        row: dict[str, Any] = {"pull": name, "axis": [_r(v) for v in rotation.T @ axis], "measured": "draft",
                               "wall_area_mm2": draft["wall_area_mm2"],
                               "zero_draft_wall_area_mm2": draft["zero_draft_wall_area_mm2"],
                               "min_wall_draft_deg": (draft.get("min_wall_draft") or {}).get("draft_deg")}
        if dominates(row, chosen):
            parts = [_undercut_part(geo, axis, zero_tol, classify=False) for geo in geos]
            row.update(undercut_candidate_area_mm2=_r(sum(part["area"] for part in parts), 2),
                       undercut_count=sum(len(part["items"]) for part in parts), measured="trapped")
            if not row["undercut_count"]:
                row.update(side_action_count=0, lifter_count=0, unreleasable_count=0, measured="released")
            elif dominates(row, chosen):
                # what releases them: no depth against the pull (only whether a lip frees a feature)
                parts = [_undercut_part(geo, axis, zero_tol, depth=False) for geo in geos]
                row.update(_pull_row(draft, _undercuts(geos, axis, zero_tol, parts)), measured="released")
            if row["measured"] == "released" and dominates(row, chosen):
                # last, its parting: a pull that steps the parting line where this one's is flat does no better
                drafts = [_face_drafts(geo, axis, zero_tol) for geo in geos]
                flat = _parting([_parting_part(geo, d, *_projection_part(geo, axis)[1:], axis, wall_limit,
                                               {face for group in part["groups"] for face in group})
                                 for geo, d, part in zip(geos, drafts, parts)], axis)["flat_parting_possible"]
                row.update(flat_parting=flat, measured="full")
        rows.append(row)
    better = better_pull(chosen, rows)
    return {"chosen": chosen, "candidates": rows, "better": better["pull"] if better else None,
            "method": ("the measured pull's own figures against x, y, z and the part's principal axes, each read "
                       "only as far as it can still do better (measured: draft, then trapped, released, full): no "
                       "worse in features nothing releases, trapped area, actions, wall without draft and a flat "
                       "parting, and better in one")}


def _candidates(geos: list[_Geometry], wall_limit: float, zero_tol: float) -> dict[str, Any]:
    named = _named_pulls(geos, np.eye(3))
    rows = []
    for name, axis in named:
        def row(axis: np.ndarray = axis) -> dict[str, Any]:
            drafts = [_face_drafts(geo, axis, zero_tol) for geo in geos]
            draft = _draft(geos, drafts, axis, wall_limit, zero_tol)
            # a candidate pull is ranked by its releases: no depth against it (only whether a lip frees it)
            parts = [_undercut_part(geo, axis, zero_tol, depth=False) for geo in geos]
            under = _undercuts(geos, axis, zero_tol, parts)
            projected = [_projection_part(geo, axis) for geo in geos]
            parting = _parting([_parting_part(geo, d, p, v, axis, wall_limit,
                                              {face for group in part["groups"] for face in group})
                                for geo, d, (_i, p, v), part in zip(geos, drafts, projected, parts)], axis)
            below_1 = sum(value for key, value in draft["wall_draft_histogram_mm2"].items()
                          if float(key.split("-")[1].rstrip("deg")) <= 1.0)
            return {**_pull_row(draft, under), "wall_area_below_1deg_mm2": _r(below_1, 2),
                    "flat_parting": parting["flat_parting_possible"],
                    "projected_area_mm2": sum(item["projected_area_mm2"] or 0 for item, _p, _v in projected),
                    "depth_from_parting_mm": parting["depth_from_parting_mm"]}

        measured = _safe(row)
        rows.append({"pull": name, "axis": [_r(v) for v in axis], **measured})
    return {"wall_limit_deg": wall_limit, "zero_tol_deg": zero_tol,
            "note": ("draft magnitude is the same for +axis and -axis pulls; the lean direction differs. principal* "
                     "are the part's own principal axes of inertia: a part modelled off-axis was drafted about one"),
            "candidates": rows}


# --- the part's own frame about the pull -----------------------------------------------------------------------

#: Two in-plane moments of inertia within this share of each other leave the part's long direction unread: its
#: faces' normals, four-fold, take it.
_ISOTROPIC = 1e-3


def _turn_about(pull: np.ndarray, angle: float) -> np.ndarray:
    """The rotation by ``angle`` (radians) about ``pull``, a 3x3 matrix acting on column vectors."""
    p = pull / (np.linalg.norm(pull) or 1.0)
    k = np.array([[0.0, -p[2], p[1]], [p[2], 0.0, -p[0]], [-p[1], p[0], 0.0]])
    return np.eye(3) + math.sin(angle) * k + (1.0 - math.cos(angle)) * (k @ k)


def _frame_about(part: _dfm_brep.Part, pull: np.ndarray) -> np.ndarray:
    """The rotation about ``pull`` that turns ``part`` into its own frame: its long direction in the parting
    plane (the in-plane principal axis of least inertia; for a part as broad one way as the other, the four-fold
    mean of its planes' normals) along the plane's first axis (``ops.basis``), the way its mass leans along it
    first. A part turned about the pull in its model is then measured as drawn the other way: the same samples,
    the same rays, the same figures. The identity where the frame cannot be read (or is the world's)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    u, v = ops.basis(pull)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(part.shape.wrapped, props)
    if props.Mass() <= 0:
        return np.eye(3)
    matrix = props.MatrixOfInertia()
    inertia = np.array([[matrix.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
    centre = props.CentreOfMass()
    centre = np.array([centre.X(), centre.Y(), centre.Z()])
    plane = np.stack([u, v])
    moments, axes = np.linalg.eigh(plane @ inertia @ plane.T)
    faces = part.faces()
    areas = np.array([float(face.area) for face in faces])
    if moments[1] - moments[0] > _ISOTROPIC * max(abs(float(moments[1])), 1e-12):
        angle = math.atan2(float(axes[1, 0]), float(axes[0, 0]))
        turns = 2
    else:
        # As broad one way as the other: the planes' normals in the parting plane, four-fold (a square's sides).
        c4 = s4 = 0.0
        for face, area in zip(faces, areas):
            surface = _dfm_brep.surface(face)
            if surface.kind != "plane" or surface.normal is None:
                continue
            n = np.asarray(surface.normal, dtype=float)
            x, y = float(n @ u), float(n @ v)
            if x * x + y * y < 1e-6:
                continue
            phi = math.atan2(y, x)
            weight = float(area) * (x * x + y * y)
            c4 += weight * math.cos(4 * phi)
            s4 += weight * math.sin(4 * phi)
        if c4 * c4 + s4 * s4 < 1e-12 * max(float(areas.sum()), 1.0) ** 2:
            return np.eye(3)
        angle = math.atan2(s4, c4) / 4.0
        turns = 4
    # Which of the ``turns`` equivalent directions: the one the mass leans along (third moment of the faces' areas
    # about the centre), else the one nearest the world's (a part drawn square stays as drawn).
    centres = np.array([[(c := face.center()).X, c.Y, c.Z] for face in faces]) - centre
    size = float(np.linalg.norm(centres, axis=1).max()) or 1.0
    best, best_key = angle, None
    for k in range(turns):
        candidate = angle + 2 * math.pi * k / turns
        d = math.cos(candidate) * u + math.sin(candidate) * v
        lean = float((areas * (centres @ d) ** 3).sum()) / (max(float(areas.sum()), 1e-12) * size ** 3)
        nearest = abs(math.remainder(candidate, 2 * math.pi))
        key = (-round(lean, 6), round(nearest, 9))
        if best_key is None or key < best_key:
            best, best_key = candidate, key
    if abs(math.remainder(best, 2 * math.pi)) < 1e-12:
        return np.eye(3)
    return _turn_about(pull, -best)


def _framed(part: _dfm_brep.Part, rotation: np.ndarray) -> _dfm_brep.Part:
    """``part`` turned by ``rotation`` (about the origin): the same faces and edges in the same ordinals, so every
    ref is the part's own."""
    import dataclasses

    import build123d as bd
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    r = rotation
    trsf = gp_Trsf()
    trsf.SetValues(r[0, 0], r[0, 1], r[0, 2], 0.0, r[1, 0], r[1, 1], r[1, 2], 0.0, r[2, 0], r[2, 1], r[2, 2], 0.0)
    moved = bd.Shape.cast(part.shape.wrapped.Moved(TopLoc_Location(trsf)))
    return dataclasses.replace(part, shape=moved, _faces=None, _edges=None, _face_map=None, _edge_map=None,
                               _edge_context={})


def _side_back(name: Any, back: np.ndarray) -> Any:
    """A side action's direction (``+x``, ``x,y,z``) named in the world again."""
    if not isinstance(name, str):
        return name
    if name[:1] in "+-" and name[1:] in ("x", "y", "z"):
        vector = np.zeros(3)
        vector["xyz".index(name[1])] = 1.0 if name[0] == "+" else -1.0
    else:
        try:
            vector = np.array([float(value) for value in name.split(",")])
        except ValueError:
            return name
        if len(vector) != 3:
            return name
    return ops.direction_name(back @ vector)


def _unframed(value: Any, back: np.ndarray, key: str = "") -> Any:
    """``value`` (a report, or part of one) with every place and direction turned back by ``back``: each ``xyz``
    (and ``*_xyz``), a list of them, and each side action's name."""
    if isinstance(value, dict):
        return {k: _unframed(v, back, k) for k, v in value.items()}
    if key in ("side_actions", "side_action_directions") and isinstance(value, list):
        return [_side_back(name, back) for name in value]
    if key == "xyz" or key.endswith("_xyz"):
        if isinstance(value, list) and len(value) == 3 and all(isinstance(x, (int, float)) for x in value):
            return _xyz(back @ np.asarray(value, dtype=float))
        if isinstance(value, list) and value and all(isinstance(x, list) for x in value):
            return [_unframed(x, back, "xyz") for x in value]
        return value
    if isinstance(value, list):
        return [_unframed(item, back, key) for item in value]
    return value


def measure(document: _dfm_brep.Document, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The molding report of ``document``: facts alone, every family's ``items`` at a ref.

    Each part is measured in its own frame about the pull (``_frame_about``), so a part turned about the pull in its
    model reads the same figures, and every place and side action is said in the world again (``_unframed``). An
    assembly's parts, or a part of several solids, are measured as they stand: their frames are one another's."""
    wall_limit, zero_tol = float(options["wall_limit"]), float(options["zero_tol"])
    if candidates:
        geos = [_Geometry(part, budget=_CANDIDATE_SAMPLES) for part in document.parts]
        report = {"scale": _scale(geos), "pulls": _safe(_candidates, geos, wall_limit, zero_tol)}
    else:
        pull = ops.pull_vector(options.get("pull") or DEFAULT_PULL)
        rotation = np.eye(3)
        if len(document.parts) == 1 and len(document.parts[0].solids()) == 1:
            try:
                rotation = _frame_about(document.parts[0], pull)
            except Exception:  # noqa: BLE001 - a frame the kernel cannot read: the world's
                rotation = np.eye(3)
        if np.allclose(rotation, np.eye(3), atol=1e-12):
            geos = [_Geometry(part) for part in document.parts]
            report = _families(geos, pull, wall_limit, zero_tol)
        else:
            geos = [_Geometry(_framed(part, rotation)) for part in document.parts]
            report = _families(geos, pull, wall_limit, zero_tol, rotation)
            report = _unframed(report, rotation.T)
            report["frame"] = {"rotation_about_pull_deg": _r(math.degrees(math.atan2(
                float(rotation[1, 0]), float(rotation[0, 0]))), 6),
                "note": "measured in the part's own frame about the pull (its long direction along the "
                        "parting plane's first axis); every place and side action is the world's"}
        report["pull_given"] = options.get("pull") is not None
    _mark_partial(report)
    # the faces the kernel failed to intersect a ray with, said at each part's own faces (each family it cost names
    # them too: ``unmeasured_faces``)
    missed = _unintersected(geos)
    if missed:
        report["findings"] = missed
    return report
