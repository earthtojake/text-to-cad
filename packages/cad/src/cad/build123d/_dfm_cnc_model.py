"""One part's topology for the CNC measurements (``_dfm_cnc``): its faces, their surfaces and samples, the
edges between them, which way each face lies against a direction, exact rays that say what face they hit and
its normal there, and the machine's approach directions.

Everything here is measured on the B-rep (``_dfm_brep``): a face's samples are points on its surface, a ray
is an exact line against the part's faces (``IntCurvesFace_Intersector`` on each face whose box the line
meets, nearest first).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from cad.build123d import _dfm_brep as brep

__all__ = ["Hit", "Model", "Stations", "WORLD", "about", "directions_for", "edge_normals", "fibonacci", "framed",
           "machine_frame", "stations", "stations_at", "unit"]

#: The six directions a three-axis machine approaches from.
WORLD = tuple(np.array(axis, dtype=float) for axis in
              ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)))
#: Two directions within this of each other (|cos|) are the same direction.
SAME = 0.9999
#: A face whose every normal is within this (|cos|) of perpendicular to a direction lies along it.
ALONG = 0.02
#: The direction a point's material is told along (``Model.solid``): oblique to every axis, so no ray of it runs
#: along a face of a part drawn square.
SOLID_RAY = np.array([0.2672612419124244, 0.5345224838248488, 0.8017837257372732])
#: The directions a point the first ray met a face at nearly edge-on (or at once) is told along again, in turn,
#: before the solid classifier (a tenth of a second a point on a free-form part) is asked: the same ray's
#: components turned about, oblique to every axis and to each other.
SOLID_RAYS = (SOLID_RAY, SOLID_RAY[[2, 0, 1]], SOLID_RAY[[1, 2, 0]])
#: How far off its face a ray starts, so it does not hit the face it leaves.
LIFT = 1e-3
#: The sample budget: about ``SAMPLE_SCALE * sqrt(faces)`` points shared over the faces by area, at most
#: ``SAMPLE_CAP``, every face at least one and at most ``FACE_SAMPLES``: the rays cast grow with the faces'
#: count once (one point each), not with the part's area or its triangulation.
SAMPLE_SCALE = 400.0
SAMPLE_CAP = 6000
FACE_SAMPLES = 16
#: The part is triangulated once, its chord deflection this share of its box's diagonal.
MESH_SHARE = 0.003
#: The ray grids kept, one per direction, the least recently used dropped first.
GRIDS_KEPT = 64
#: Rays whose boxes are tested together: as many as keep rays x faces under this (a slab test holds a few arrays
#: of that many numbers), 256 at most -- so a part of any face count takes bounded memory a batch.
BATCH_PAIRS = 1_000_000


def unit(vector: Iterable[float]) -> np.ndarray:
    v = np.asarray(vector if isinstance(vector, np.ndarray) else list(vector), dtype=float)
    size = float(np.linalg.norm(v))
    return v / size if size > 1e-300 else v


def fibonacci(count: int) -> list[np.ndarray]:
    """``count`` directions spread evenly over the sphere."""
    golden = math.pi * (3.0 - math.sqrt(5.0))
    found = []
    for index in range(count):
        z = 1.0 - 2.0 * (index + 0.5) / count
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = golden * index
        found.append(np.array([radius * math.cos(theta), radius * math.sin(theta), z]))
    return found


def about(axis: np.ndarray, step_deg: float = 15.0) -> list[np.ndarray]:
    """The directions perpendicular to ``axis`` every ``step_deg`` degrees: a rotary table's."""
    a = unit(axis)
    seed = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = unit(np.cross(a, seed))
    v = np.cross(a, u)
    steps = int(round(360.0 / step_deg))
    return [unit(math.cos(2 * math.pi * k / steps) * u + math.sin(2 * math.pi * k / steps) * v)
            for k in range(steps)]


def directions_for(axes: int, rotary: np.ndarray | None = None) -> list[np.ndarray]:
    """The approach directions of a machine of ``axes`` axes: three, the six world axes; four, those and every
    15 degrees about the rotary axis; five, those and 200 more spread over the sphere."""
    found = list(WORLD)
    if axes >= 4 and rotary is not None:
        found += [d for d in about(rotary) if not any(abs(float(d @ w)) > SAME for w in found)]
    if axes >= 5:
        found += fibonacci(200)
    return found


def _xyz(value: Any) -> tuple[float, float, float]:
    return (float(value.X()), float(value.Y()), float(value.Z()))


#: Two clusters' directions within this of square (|cos|: a cluster's own width, ``SAME``'s angle) are square
#: to each other: a frame's second axis, squared to its first exactly.
SQUARE = math.sqrt(1.0 - SAME * SAME)
#: The heaviest directions a frame is tried about.
FRAME_SEEDS = 6


def _signed_permutations() -> list[np.ndarray]:
    import itertools

    found = []
    for order in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            m = np.zeros((3, 3))
            for row, (column, sign) in enumerate(zip(order, signs)):
                m[row, column] = sign
            if np.linalg.det(m) > 0:
                found.append(m)
    return found


_PERMUTATIONS = _signed_permutations()


def machine_frame(faces: list[Any], surfaces: list[brep.Surface]) -> tuple[np.ndarray, float]:
    """The frame a part is machined in, read from its own geometry -- never the world's, so a part turned in
    its model is machined as it is drawn: the rotation (rows: the machine's X, Y and Z in the part's
    coordinates) whose axes the most of the part's area lies along -- each plane's normal and each cylinder's,
    cone's or torus's axis, weighted by its face's area --, and the share of that area it aligns.

    Two tolerances, two meanings. Directions within ``SAME`` of each other are one **cluster** (a face's own
    noise, a few tenths of a degree of draft), its direction their mean by area. A face is **aligned** with a
    frame by how near its direction is to an axis: wholly where it is the axis, not at all ``SAME`` away, by the
    square of the angle between -- so the world's frame, a tenth of a degree off a part's own, aligns less of
    it than the part's own does, however small the tilt (a part tilted 0.05 or 0.8 degrees is machined in its
    own frame, as one tilted 37 is).

    Candidates: the world's own frame, and about each of the ``FRAME_SEEDS`` heaviest clusters a frame whose
    second axis is the heaviest cluster square to it (within a cluster's width, then squared to it exactly;
    else the world axis most nearly square). Ranked by the area they align, as printing ranks orientations by
    its figures; the world's frame wins a tie (a frame's own noise, 1e-9 of the area), and of the 24 rotations
    that are one frame, the one nearest the world's is taken (a part drawn square stays as drawn)."""
    vectors, weights = [], []
    for face, s in zip(faces, surfaces):
        v = s.normal if s.kind == "plane" else s.axis if s.kind in ("cylinder", "cone", "torus") else None
        if v is None:
            continue
        try:
            area = float(face.area)
        except Exception:  # noqa: BLE001 - a face with no area weighs nothing
            continue
        if area > 0.0:
            vectors.append(unit(v))
            weights.append(area)
    identity = np.eye(3)
    if not vectors:
        return identity, 0.0
    d, w = np.array(vectors), np.array(weights)
    total = float(w.sum())

    def aligned(frame: np.ndarray) -> float:
        # 1 - cos is half the angle squared: all of a face on an axis, none of one ``SAME`` off it
        off = 1.0 - np.abs(d @ frame.T).max(axis=1)
        return float((w * np.clip(1.0 - off / (1.0 - SAME), 0.0, 1.0)).sum())

    clusters: list[list[Any]] = []  # [the heaviest member's direction, weight, the members' sum], sign free
    for i in np.argsort(-w):
        for cluster in clusters:
            along = float(d[i] @ cluster[0])
            if abs(along) > SAME:
                cluster[1] += float(w[i])
                cluster[2] = cluster[2] + d[i] * (w[i] if along > 0 else -w[i])
                break
        else:
            clusters.append([d[i], float(w[i]), d[i] * w[i]])
    clusters = [[unit(total), weight] for _, weight, total in sorted(clusters, key=lambda cluster: -cluster[1])]
    candidates = [identity]
    for a, _ in clusters[:FRAME_SEEDS]:
        square = [b for b, _ in clusters if abs(float(a @ b)) < SQUARE]
        seconds = square[:2] or [min(identity, key=lambda axis: abs(float(axis @ a)))]
        for b in seconds:
            b = unit(b - a * float(b @ a))
            candidates.append(np.array([a, b, np.cross(a, b)]))
    best = identity
    best_score = aligned(identity)
    for frame in candidates[1:]:
        score = aligned(frame)
        if score > best_score + 1e-9 * total:
            best, best_score = frame, score
    if best is not identity:
        best = max((p @ best for p in _PERMUTATIONS), key=lambda m: float(np.trace(m)))
        if np.allclose(best, identity, atol=1e-9):
            best = identity  # the world's, to the kernel's own noise
    return best, best_score / total


def framed(part: brep.Part, rotation: np.ndarray) -> brep.Part:
    """``part`` turned by ``rotation`` (about the origin) into its machine frame: the same faces and edges in
    the same ordinals, so every ref is the part's own."""
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


def turned(surface: brep.Surface, rotation: np.ndarray) -> brep.Surface:
    """``surface`` as it lies once its part is ``framed`` by ``rotation``."""
    import dataclasses

    changes = {key: tuple(float(v) for v in rotation @ np.asarray(getattr(surface, key)))
               for key in ("normal", "origin", "axis") if getattr(surface, key) is not None}
    return dataclasses.replace(surface, **changes) if changes else surface


_GP: tuple[Any, Any, Any] | None = None


def _gp() -> tuple[Any, Any, Any]:
    """``gp_Dir``, ``gp_Lin`` and ``gp_Pnt``, imported once: an import a ray cost a tenth of its cast."""
    global _GP
    if _GP is None:
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        _GP = (gp_Dir, gp_Lin, gp_Pnt)
    return _GP


def _spread(count: int) -> list[tuple[float, float]]:
    """``count`` barycentric points spread over a triangle: the centres of its pieces when it is cut in
    ``ceil(sqrt(count))`` along each side, taken evenly."""
    if count <= 1:
        return [(1 / 3, 1 / 3)]
    cuts = int(math.ceil(math.sqrt(count)))
    centres = []
    for i in range(cuts):
        for j in range(cuts - i):
            centres.append(((i + 1 / 3) / cuts, (j + 1 / 3) / cuts))
            if i + j + 1 < cuts:
                centres.append(((i + 2 / 3) / cuts, (j + 2 / 3) / cuts))
    step = len(centres) / count
    return [centres[int(k * step)] for k in range(count)]


class _Projected:
    """The faces' boxes seen along one direction: each box's shadow on the plane square to it (the hull of its
    eight corners) and its span along it, the shadows bucketed in a grid of about ``sqrt(faces)`` cells a
    side. A ray along the direction meets only the boxes whose shadow holds its origin's: the few in its
    cell, not every face."""

    def __init__(self, boxes: np.ndarray, d: np.ndarray) -> None:
        seed = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        self.u = unit(np.cross(d, seed))
        self.v = np.cross(d, self.u)
        self.d = d
        corners = np.stack([boxes[:, [i, j, k]] for i in (0, 3) for j in (1, 4) for k in (2, 5)], axis=1)
        pu, pv, pt = corners @ self.u, corners @ self.v, corners @ d
        self.u0, self.u1 = pu.min(axis=1), pu.max(axis=1)
        self.v0, self.v1 = pv.min(axis=1), pv.max(axis=1)
        self.t0, self.t1 = pt.min(axis=1), pt.max(axis=1)
        count = len(boxes)
        side = max(1, min(128, int(math.sqrt(count))))
        self.side = side
        self.lo = np.array([self.u0.min(), self.v0.min()]) if count else np.zeros(2)
        span = np.array([self.u1.max() - self.lo[0], self.v1.max() - self.lo[1]]) if count else np.ones(2)
        self.cell = np.maximum(span / side, 1e-12)
        i0 = np.clip(((self.u0 - self.lo[0]) / self.cell[0]).astype(int), 0, side - 1)
        i1 = np.clip(((self.u1 - self.lo[0]) / self.cell[0]).astype(int), 0, side - 1)
        j0 = np.clip(((self.v0 - self.lo[1]) / self.cell[1]).astype(int), 0, side - 1)
        j1 = np.clip(((self.v1 - self.lo[1]) / self.cell[1]).astype(int), 0, side - 1)
        # a shadow over many cells (a housing's outer face) is in every query; the rest are bucketed
        spans = (i1 - i0 + 1) * (j1 - j0 + 1)
        wide = spans > max(16, side * side // 16)
        self.wide = np.flatnonzero(wide)
        narrow = np.flatnonzero(~wide)
        counts = spans[narrow]
        faces = np.repeat(narrow, counts)
        offset = np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts, counts)
        width = (j1 - j0 + 1)[faces]
        cells = (i0[faces] + offset // width) * side + j0[faces] + offset % width
        order = np.argsort(cells, kind="stable")
        cells, faces = cells[order], faces[order]
        bounds = np.searchsorted(cells, np.arange(side * side + 1))
        self.buckets = [np.concatenate([faces[bounds[c]:bounds[c + 1]], self.wide]) for c in range(side * side)]

    def candidates(self, origin: np.ndarray, skip: float, end: float) -> tuple[np.ndarray, np.ndarray]:
        """The faces whose boxes a ray from ``origin`` along the direction meets, nearest first, and where
        it enters each."""
        pu, pv, pt = float(origin @ self.u), float(origin @ self.v), float(origin @ self.d)
        fi = (pu - self.lo[0]) / self.cell[0]
        fj = (pv - self.lo[1]) / self.cell[1]
        if not (0.0 <= fi <= self.side and 0.0 <= fj <= self.side):
            return np.zeros(0, dtype=int), np.zeros(0)  # outside every shadow
        i, j = min(int(fi), self.side - 1), min(int(fj), self.side - 1)
        index = self.buckets[i * self.side + j]
        if not len(index):
            return index, np.zeros(0)
        keep = ((self.u0[index] <= pu) & (pu <= self.u1[index]) & (self.v0[index] <= pv) & (pv <= self.v1[index])
                & (self.t1[index] - pt >= skip) & (self.t0[index] - pt <= end))
        index = index[keep]
        enter = np.maximum(self.t0[index] - pt, skip)
        order = np.argsort(enter)
        return index[order], enter[order]

    def candidates_all(self, origins: np.ndarray, skip: float, end: float) -> list[tuple[np.ndarray, np.ndarray]]:
        """``candidates`` for many origins, their boxes tested together: the same faces in the same order."""
        origins = np.asarray(origins, dtype=float).reshape(-1, 3)
        none = (np.zeros(0, dtype=int), np.zeros(0))
        pu, pv, pt = origins @ self.u, origins @ self.v, origins @ self.d
        fi = (pu - self.lo[0]) / self.cell[0]
        fj = (pv - self.lo[1]) / self.cell[1]
        inside = (0.0 <= fi) & (fi <= self.side) & (0.0 <= fj) & (fj <= self.side)
        rows = np.flatnonzero(inside)
        if not len(rows):
            return [none] * len(origins)
        cells = (np.minimum(fi[rows].astype(int), self.side - 1) * self.side
                 + np.minimum(fj[rows].astype(int), self.side - 1))
        buckets = [self.buckets[int(cell)] for cell in cells]
        counts = np.array([len(bucket) for bucket in buckets], dtype=np.int64)
        index = np.concatenate(buckets) if len(buckets) else np.zeros(0, dtype=int)
        ray = np.repeat(rows, counts)
        keep = ((self.u0[index] <= pu[ray]) & (pu[ray] <= self.u1[index]) & (self.v0[index] <= pv[ray])
                & (pv[ray] <= self.v1[index]) & (self.t1[index] - pt[ray] >= skip) & (self.t0[index] - pt[ray] <= end))
        enter = np.maximum(self.t0[index] - pt[ray], skip)
        found = [none] * len(origins)
        bounds = np.concatenate([[0], np.cumsum(counts)])
        for k, row in enumerate(rows):
            a, b = bounds[k], bounds[k + 1]
            mine = keep[a:b]
            picked, entries = index[a:b][mine], enter[a:b][mine]
            order = np.argsort(entries)  # as ``candidates`` sorts one ray's: ties fall alike
            found[row] = (picked[order], entries[order])
        return found


@dataclass(frozen=True)
class Hit:
    distance: float
    face: int          # the ordinal of the face hit, 0 for one the part does not know
    normal: np.ndarray  # its outward normal there


class Model:
    """A part's faces, surfaces, edges, samples and rays, each computed once."""

    def __init__(self, part: brep.Part, surfaces: list[brep.Surface] | None = None) -> None:
        self.part = part
        self.faces = part.faces()
        self.n = len(self.faces)
        self.surfaces = surfaces if surfaces is not None else [brep.surface(face) for face in self.faces]
        self.edges = brep.edges(part)
        self.adjacent: dict[int, list[brep.Edge]] = {i: [] for i in range(1, self.n + 1)}
        for edge in self.edges:
            self.adjacent[edge.faces[0]].append(edge)
            if edge.faces[1] != edge.faces[0]:
                self.adjacent[edge.faces[1]].append(edge)
        self._samples: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
        self._outline: dict[int, np.ndarray] = {}
        self._face_boxes: np.ndarray | None = None
        self._face_intersectors: dict[int, Any] = {}
        self._screen: brep.Screen | None = None
        self.area = float(part.shape.area)
        box = part.shape.bounding_box()
        self.box_min = np.array([box.min.X, box.min.Y, box.min.Z])
        self.box_max = np.array([box.max.X, box.max.Y, box.max.Z])
        self.size = float(np.linalg.norm(self.box_max - self.box_min)) or 1.0
        self.rays_cast = 0
        self._meshes: list[tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray]] | None = None
        self._quota: np.ndarray | None = None
        self._projected: OrderedDict[tuple[float, ...], _Projected] = OrderedDict()
        self._extents: dict[tuple[float, ...], tuple[float, float]] = {}
        self._sweeps: dict[int, np.ndarray] = {}
        self._stations: dict[tuple[int, int], Stations] = {}
        self._classifier: Any = None

    def shed(self) -> None:
        """Drop what the part's measurement made and its report no longer reads -- its mesh, samples, grids,
        stations, ray screen and intersectors, made again if asked -- so an assembly's parts are not all held at
        once."""
        self._meshes = None
        self._screen = None
        self._face_intersectors.clear()
        self._quota = None
        self._samples.clear()
        self._outline.clear()
        self._projected.clear()
        self._extents.clear()
        self._sweeps.clear()
        self._stations.clear()
        self._classifier = None

    # --- faces -------------------------------------------------------------------------------------------

    def ref(self, ordinal: int) -> str:
        return self.part.ref("face", ordinal)

    def face(self, ordinal: int) -> Any:
        return self.faces[ordinal - 1]

    def surface(self, ordinal: int) -> brep.Surface:
        return self.surfaces[ordinal - 1]

    def _mesh(self) -> list[tuple[np.ndarray, np.ndarray | None, np.ndarray, np.ndarray]]:
        """Each face's triangulation, the part meshed once: its nodes, their (u, v) on the surface, its
        triangles and their areas."""
        if self._meshes is None:
            from OCP.BRep import BRep_Tool
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.TopLoc import TopLoc_Location

            BRepMesh_IncrementalMesh(self.part.shape.wrapped, max(1e-4, MESH_SHARE * self.size), False, 0.35, True)
            meshes = []
            empty = (np.zeros((0, 3)), None, np.zeros((0, 3), dtype=int), np.zeros(0))
            for face in self.faces:
                location = TopLoc_Location()
                triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
                if triangulation is None or triangulation.NbTriangles() == 0:
                    meshes.append(empty)
                    continue
                trsf = location.Transformation()
                count = triangulation.NbNodes()
                nodes = np.array([_xyz(triangulation.Node(i).Transformed(trsf)) for i in range(1, count + 1)])
                uvs = (np.array([(triangulation.UVNode(i).X(), triangulation.UVNode(i).Y())
                                 for i in range(1, count + 1)]) if triangulation.HasUVNodes() else None)
                tris = np.array([triangulation.Triangle(i).Get()
                                 for i in range(1, triangulation.NbTriangles() + 1)]) - 1
                areas = 0.5 * np.linalg.norm(np.cross(nodes[tris[:, 1]] - nodes[tris[:, 0]],
                                                      nodes[tris[:, 2]] - nodes[tris[:, 0]]), axis=1)
                meshes.append((nodes, uvs, tris, areas))
            self._meshes = meshes
        return self._meshes

    def mesh_area(self, ordinal: int) -> float:
        """The face's area by its triangulation (exact for a plane; within the chord for a curved face)."""
        return float(self._mesh()[ordinal - 1][3].sum())

    def largest(self) -> int:
        """The ordinal of the part's largest face."""
        return 1 + int(np.argmax([float(mesh[3].sum()) for mesh in self._mesh()])) if self.n else 1

    def quota(self, ordinal: int) -> int:
        """How many points this face is sampled at (see ``SAMPLE_SCALE``)."""
        if self._quota is None:
            areas = np.array([float(mesh[3].sum()) for mesh in self._mesh()])
            budget = min(float(SAMPLE_CAP), SAMPLE_SCALE * math.sqrt(max(1, self.n)))
            total = float(areas.sum()) or 1.0
            self._quota = np.clip(np.rint(budget * areas / total), 1, FACE_SAMPLES).astype(int)
        return int(self._quota[ordinal - 1])

    def samples(self, ordinal: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Points on the face, their outward normals and the areas they stand for, as arrays: ``quota`` points
        spread by area over the face's triangles (stratified along their running area), each the surface
        itself at its (u, v)."""
        found = self._samples.get(ordinal)
        if found is None:
            found = self._sample(ordinal)
            self._samples[ordinal] = found
        return found

    def _sample(self, ordinal: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        nodes, uvs, tris, areas = self._mesh()[ordinal - 1]
        total = float(areas.sum())
        if not len(tris) or total <= 0.0:
            return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0)
        count = self.quota(ordinal)
        running = np.cumsum(areas)
        picks = np.searchsorted(running, (np.arange(count) + 0.5) / count * total)
        picks = np.minimum(picks, len(tris) - 1)
        face = self.face(ordinal)
        points, normals = [], []
        for triangle, many in zip(*np.unique(picks, return_counts=True)):
            a, b, c = tris[triangle]
            for wa, wb in _spread(int(many)):
                wc = 1.0 - wa - wb
                if uvs is not None:
                    u, v = wa * uvs[a] + wb * uvs[b] + wc * uvs[c]
                    point, normal = brep.point_normal(face, float(u), float(v))
                else:
                    point = wa * nodes[a] + wb * nodes[b] + wc * nodes[c]
                    normal = unit(np.cross(nodes[b] - nodes[a], nodes[c] - nodes[a]))
                points.append(point)
                normals.append(normal)
        share = total / len(points)
        return np.array(points), np.array(normals), np.full(len(points), share)

    def edge_points(self, ordinal: int, per_edge: int = 17) -> np.ndarray:
        """Points along the face's edges, ``per_edge`` each, ends included."""
        from OCP.BRepAdaptor import BRepAdaptor_Curve

        points = []
        for edge in self.face(ordinal).edges():
            try:
                curve = BRepAdaptor_Curve(edge.wrapped)
                first, last = curve.FirstParameter(), curve.LastParameter()
                for k in range(per_edge):
                    p = curve.Value(first + (last - first) * k / (per_edge - 1))
                    points.append((p.X(), p.Y(), p.Z()))
            except Exception:  # noqa: BLE001
                continue
        return np.array(points).reshape(-1, 3)

    def outline(self, ordinal: int) -> np.ndarray:
        """Points on the face's boundary and over it -- its triangulation's nodes, and along a freeform face's
        edges 17 points each --: what its extent along a direction is taken of."""
        found = self._outline.get(ordinal)
        if found is None:
            nodes = self._mesh()[ordinal - 1][0]
            if self.surface(ordinal).kind not in ("plane", "cylinder", "cone", "sphere", "torus"):
                found = np.vstack([nodes, self.edge_points(ordinal)])
            else:
                found = nodes
            if not len(found):
                found = self.samples(ordinal)[0]
            self._outline[ordinal] = found
        return found

    def extent(self, ordinal: int, direction: np.ndarray) -> tuple[float, float]:
        """The face's lowest and highest place along ``direction``."""
        values = self.outline(ordinal) @ direction
        return (float(values.min()), float(values.max())) if len(values) else (0.0, 0.0)

    def part_extent(self, direction: np.ndarray) -> tuple[float, float]:
        """The part's lowest and highest place along ``direction`` (exact along a world axis)."""
        d = unit(direction)
        for axis in range(3):
            if abs(d[axis]) > SAME:
                low, high = float(self.box_min[axis]), float(self.box_max[axis])
                return (low, high) if d[axis] > 0 else (-high, -low)
        key = tuple(np.round(d, 9))
        if key not in self._extents:
            values = np.concatenate([self.outline(i) @ d for i in range(1, self.n + 1)])
            self._extents[key] = (float(values.min()), float(values.max()))
        return self._extents[key]

    def along(self, ordinal: int, direction: np.ndarray) -> bool:
        """Whether the face lies along ``direction``: a wall a tool on that axis cuts with its side."""
        s = self.surface(ordinal)
        d = unit(direction)
        if s.kind == "plane":
            return abs(float(np.asarray(s.normal) @ d)) < ALONG
        if s.kind == "cylinder":
            return abs(float(np.asarray(s.axis) @ d)) > SAME
        if s.kind in ("cone", "sphere", "torus"):
            return False
        if s.kind == "extrusion":
            # a curve swept along a line (a glyph's side, a profile's): along the line, whatever its samples
            return abs(float(self.sweep(ordinal) @ d)) > SAME
        normals = self.samples(ordinal)[1]
        return len(normals) >= 3 and bool(np.all(np.abs(normals @ d) < ALONG))

    def sweep(self, ordinal: int) -> np.ndarray:
        """A surface of linear extrusion's direction (a unit vector)."""
        found = self._sweeps.get(ordinal)
        if found is None:
            from OCP.BRepAdaptor import BRepAdaptor_Surface

            direction = BRepAdaptor_Surface(self.face(ordinal).wrapped).Direction()
            found = unit((direction.X(), direction.Y(), direction.Z()))
            self._sweeps[ordinal] = found
        return found

    def facing(self, ordinal: int, direction: np.ndarray) -> bool:
        """Whether the face is a plane whose outward normal is ``direction``: a floor a tool on that axis cuts
        with its end."""
        s = self.surface(ordinal)
        return s.kind == "plane" and float(np.asarray(s.normal) @ unit(direction)) > SAME

    def neighbours(self, ordinal: int) -> list[tuple[brep.Edge, int]]:
        return [(edge, edge.faces[1] if edge.faces[0] == ordinal else edge.faces[0])
                for edge in self.adjacent.get(ordinal, [])]

    def span_rad(self, ordinal: int) -> float:
        """The angle a cylinder's or a cone's face sweeps about its axis (its u range)."""
        from OCP.BRepTools import BRepTools

        umin, umax, _, _ = BRepTools.UVBounds_s(self.face(ordinal).wrapped)
        return float(min(2 * math.pi, max(0.0, umax - umin)))

    def size_mm(self, ordinal: int) -> float:
        """A face's width: twice its area over its perimeter (a strip's width, a disk's radius)."""
        perimeter = sum(edge.length for edge in self.adjacent.get(ordinal, []))
        area = float(self._mesh()[ordinal - 1][3].sum())
        return float(2.0 * area / perimeter) if perimeter > 0 else math.sqrt(area)

    def center(self, ordinal: int) -> list[float]:
        points, _, areas = self.samples(ordinal)
        if len(points):
            return brep.rounded((points * areas[:, None]).sum(axis=0) / max(areas.sum(), 1e-300))
        c = self.face(ordinal).center()
        return brep.rounded((c.X, c.Y, c.Z))

    # --- rays --------------------------------------------------------------------------------------------

    def _boxes(self) -> np.ndarray:
        if self._face_boxes is None:
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib

            boxes = np.zeros((self.n, 6))
            for index, face in enumerate(self.faces):
                bnd = Bnd_Box()
                BRepBndLib.Add_s(face.wrapped, bnd, False)
                bnd.Enlarge(1e-4 * self.size + 1e-6)
                low, high = bnd.CornerMin(), bnd.CornerMax()
                boxes[index] = (low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z())
            self._face_boxes = boxes
        return self._face_boxes

    def _slabs(self, origins: np.ndarray, d: np.ndarray, skip: float, end: float) -> tuple[np.ndarray, np.ndarray]:
        """For rays from each of ``origins`` along ``d``: which faces' boxes each meets between ``skip`` and
        ``end`` (a mask, rays by faces) and where it enters them (a slab test over every box at once)."""
        boxes = self._boxes()
        if d.ndim == 1 and np.count_nonzero(np.abs(d) > 1e-12) == 1:
            # along a world axis: the boxes across the ray's line, and where along it each begins
            axis = int(np.argmax(np.abs(d)))
            sign = 1.0 if d[axis] > 0 else -1.0
            others = [k for k in range(3) if k != axis]
            mask = np.ones((len(origins), len(boxes)), dtype=bool)
            for k in others:
                mask &= (boxes[None, :, k] <= origins[:, None, k]) & (origins[:, None, k] <= boxes[None, :, 3 + k])
            near = boxes[None, :, axis] if sign > 0 else boxes[None, :, 3 + axis]
            far = boxes[None, :, 3 + axis] if sign > 0 else boxes[None, :, axis]
            enter = (near - origins[:, None, axis]) * sign
            leave = (far - origins[:, None, axis]) * sign
            return mask & (leave >= skip) & (enter <= end), np.maximum(enter, skip)
        lows, highs = boxes[None, :, :3], boxes[None, :, 3:]
        o = origins[:, None, :]
        d = d[:, None, :] if d.ndim == 2 else d
        flat = np.abs(d) <= 1e-300
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, d))
            t1 = (lows - o) * inverse
            t2 = (highs - o) * inverse
        lo = np.where(flat, -np.inf, np.minimum(t1, t2))
        hi = np.where(flat, np.inf, np.maximum(t1, t2))
        inside = np.all(~flat | ((lows <= o) & (o <= highs)), axis=2)
        enter = lo.max(axis=2)
        leave = hi.min(axis=2)
        return inside & (enter <= leave) & (leave >= skip) & (enter <= end), np.maximum(enter, skip)

    def _candidates(self, o: np.ndarray, d: np.ndarray, skip: float, end: float) -> tuple[np.ndarray, np.ndarray]:
        """The faces whose boxes the ray meets, nearest box first, and where it enters each."""
        mask, enter = self._slabs(o[None, :], d, skip, end)
        index = np.flatnonzero(mask[0])
        order = np.argsort(enter[0, index])
        return index[order], enter[0, index][order]

    def _intersector(self, index: int) -> Any:
        found = self._face_intersectors.get(index)
        if found is None:
            found = brep.Intersector(self.faces[index].wrapped, 1e-7, self.screen, index)
            self._face_intersectors[index] = found
        return found

    @property
    def screen(self) -> brep.Screen:
        """Which faces a ray can cross, by their triangulations (``brep.Screen``), read as rays ask."""
        if self._screen is None:
            self._screen = brep.Screen([face.wrapped for face in self.faces], self.size)
        return self._screen

    def _cast(self, origin: Iterable[float], direction: Iterable[float], skip: float, end: float,
              nearest: bool, given: tuple[np.ndarray, np.ndarray] | None = None
              ) -> tuple[float, int, float, float] | None:
        """The ray's nearest crossing (or, with ``nearest`` False, any crossing): its distance, the face's
        index and the (u, v) on it. Each face the ray's line could cross, by its box, is intersected exactly
        (``IntCurvesFace_Intersector``), nearest box first, until no nearer crossing can follow."""
        gp_Dir, gp_Lin, gp_Pnt = _gp()  # noqa: N806 - the kernel's names

        o = np.asarray(origin if isinstance(origin, np.ndarray) else list(origin), dtype=float)
        d = unit(direction)
        self.rays_cast += 1
        if given is None:
            candidates, entries = self._candidates(o, d, skip, end)
        else:
            candidates, entries = given
        candidates, entries = self.screen.order(o, d, candidates, entries, skip, end)
        if not len(candidates):
            return None
        line = gp_Lin(gp_Pnt(*o), gp_Dir(*d))
        best: tuple[float, int, float, float] | None = None
        for index, entry in zip(candidates, entries):
            if best is not None and entry > best[0]:
                break
            intersector = self._intersector(int(index))
            intersector.Perform(line, skip, end if best is None else best[0])
            if not intersector.IsDone():
                continue
            for k in range(1, intersector.NbPnt() + 1):
                w = float(intersector.WParameter(k))
                if w < skip or w > end:
                    continue
                if best is None or w < best[0]:
                    best = (w, int(index), float(intersector.UParameter(k)), float(intersector.VParameter(k)))
            if best is not None and not nearest:
                return best
        return best

    def first(self, origin: Iterable[float], direction: Iterable[float], skip: float = 1e-4,
              end: float = 1e9) -> Hit | None:
        """The nearest face the ray crosses beyond ``skip``: its distance, ordinal and outward normal there."""
        found = self._cast(origin, direction, skip, end, True)
        if found is None:
            return None
        distance, index, u, v = found
        try:
            _, normal = brep.point_normal(self.faces[index], u, v)
        except Exception:  # noqa: BLE001
            normal = np.zeros(3)
        return Hit(distance, index + 1, normal)

    def blocked(self, origin: Iterable[float], direction: Iterable[float], skip: float = 1e-4) -> bool:
        """Whether the ray crosses any face beyond ``skip``."""
        o, d = np.asarray(list(origin), dtype=float), unit(direction)
        grid = self._shared(d, 1)
        given = grid.candidates(o, skip, 1e9) if grid is not None else None
        return self._cast(o, d, skip, 1e9, False, given) is not None

    def blocked_each(self, origins: np.ndarray, directions: np.ndarray, skip: float = 1e-4) -> np.ndarray:
        """``blocked`` for many rays, each its own direction: the same candidates each ``blocked`` reads (a grid's
        where one is made along its direction, else every box's), the boxes of those with none tested
        together."""
        origins = np.asarray(origins, dtype=float).reshape(-1, 3)
        ways = np.array([unit(d) for d in np.asarray(directions, dtype=float).reshape(-1, 3)]).reshape(-1, 3)
        givens: list[Any] = [None] * len(origins)
        general = []
        for row, (o, d) in enumerate(zip(origins, ways)):
            grid = self._shared(d, 1)
            if grid is not None:
                givens[row] = grid.candidates(o, skip, 1e9)
            elif np.count_nonzero(np.abs(d) > 1e-12) == 1:
                givens[row] = self._candidates(o, d, skip, 1e9)  # along a world axis: its own slab test
            else:
                general.append(row)
        chunk = self._batch()
        for start in range(0, len(general), chunk):
            rows = general[start:start + chunk]
            mask, enter = self._slabs(origins[rows], ways[rows], skip, 1e9)
            for k, row in enumerate(rows):
                index = np.flatnonzero(mask[k])
                order = np.argsort(enter[k, index])
                givens[row] = (index[order], enter[k, index][order])
        found = np.zeros(len(origins), dtype=bool)
        for row, given in enumerate(givens):
            found[row] = bool(len(given[0])) and self._cast(origins[row], ways[row], skip, 1e9, False, given) is not None
        return found

    def projected(self, direction: np.ndarray, build: bool = True) -> _Projected | None:
        """The faces' boxes seen along ``direction`` in a grid (``_Projected``), made once per direction."""
        d = unit(direction)
        key = tuple(np.round(d, 9))
        found = self._projected.get(key)
        if found is not None:
            self._projected.move_to_end(key)
        elif build:
            found = _Projected(self._boxes(), d)
            self._projected[key] = found
            if len(self._projected) > GRIDS_KEPT:
                self._projected.popitem(last=False)
        return found

    def _shared(self, d: np.ndarray, count: int) -> _Projected | None:
        """The grid along ``d`` where it pays: once made, or along a world axis, or for 4 rays or more (a grid
        costs about what 8 rays tested against every face's box do)."""
        world = any(abs(float(d @ w)) > 1 - 1e-12 for w in WORLD[::2])
        return self.projected(d, build=world or count >= 4)

    def _batch(self) -> int:
        """How many rays' boxes are tested together (``BATCH_PAIRS``)."""
        return max(8, min(256, BATCH_PAIRS // max(1, self.n)))

    def escape_all(self, points: np.ndarray, normals: np.ndarray, direction: np.ndarray,
                   skip: float = 1e-4) -> np.ndarray:
        """``escapes`` for many points along one direction, their boxes tested together."""
        d = unit(direction)
        chunk = self._batch()
        found = np.zeros(len(points), dtype=bool)
        origins = points + normals * LIFT
        grid = self._shared(d, len(points))
        for start in range(0, len(points), chunk):
            block = origins[start:start + chunk]
            if grid is not None:
                givens = grid.candidates_all(block, skip, 1e9)
            else:
                mask, enter = self._slabs(block, d, skip, 1e9)
                givens = []
                for row in range(len(block)):
                    index = np.flatnonzero(mask[row])
                    order = np.argsort(enter[row, index])
                    givens.append((index[order], enter[row, index][order]))
            for row, given in enumerate(givens):
                found[start + row] = not len(given[0]) or self._cast(block[row], d, skip, 1e9, False, given) is None
        return found

    def first_all(self, origins: np.ndarray, directions: np.ndarray, skip: float = 1e-4) -> list[Hit | None]:
        """``first`` for many rays, each its own direction, their boxes tested together."""
        found: list[Hit | None] = []
        chunk = self._batch()
        dirs = directions / np.maximum(np.linalg.norm(directions, axis=1), 1e-300)[:, None]
        same = len(dirs) > 0 and bool(np.all(np.abs(dirs - dirs[0]) < 1e-12))  # a plane's samples share one
        grid = self._shared(dirs[0], len(dirs)) if same else None
        for start in range(0, len(origins), chunk):
            block, ways = origins[start:start + chunk], dirs[start:start + chunk]
            mask, enter = (None, None) if grid is not None else self._slabs(block, ways, skip, 1e9)
            if grid is not None:
                givens = grid.candidates_all(block, skip, 1e9)
            else:
                givens = []
                for row in range(len(block)):
                    index = np.flatnonzero(mask[row])
                    order = np.argsort(enter[row, index])
                    givens.append((index[order], enter[row, index][order]))
            for row, given in enumerate(givens):
                hit = self._cast(block[row], ways[row], skip, 1e9, True, given) if len(given[0]) else None
                if hit is None:
                    found.append(None)
                    continue
                distance, face, u, v = hit
                try:
                    _, normal = brep.point_normal(self.faces[face], u, v)
                except Exception:  # noqa: BLE001
                    normal = np.zeros(3)
                found.append(Hit(distance, face + 1, normal))
        return found

    def solid(self, points: np.ndarray) -> np.ndarray:
        """Whether each point lies in the part's material (on its boundary is not): the first face a ray from it
        meets looks away from it (the ray leaving the material there), by the model's own ray cast along one
        oblique direction; a ray that meets a face nearly edge-on is cast again along the next of ``SOLID_RAYS``,
        and one that meets a face at once (on the boundary), or edge-on along all three, is classified exactly
        instead (one classifier kept). A solid classifier costs 40 to 400 ms a point on a freeform part, a ray a
        fraction of one."""
        points = np.asarray(points, dtype=float).reshape(-1, 3)
        found = np.zeros(len(points), dtype=bool)
        if not len(points):
            return found
        grazing, doubtful = list(range(len(points))), []
        for ray in SOLID_RAYS:
            if not grazing:
                break
            hits = self.first_all(points[grazing], np.tile(ray, (len(grazing), 1)), skip=1e-7)
            still = []
            for k, hit in zip(grazing, hits):
                if hit is None:
                    continue  # it leaves the part: outside
                facing = float(np.asarray(hit.normal) @ ray)
                if hit.distance < 1e-6:
                    doubtful.append(k)  # on the boundary, or all but: the classifier's (on is not in)
                elif abs(facing) < 0.05:
                    still.append(k)  # met edge-on: told along the next ray
                else:
                    found[k] = facing > 0.0
            grazing = still
        doubtful += grazing
        if doubtful:
            if self._classifier is None:
                from OCP.BRepClass3d import BRepClass3d_SolidClassifier

                self._classifier = BRepClass3d_SolidClassifier(self.part.shape.wrapped)
            from OCP.gp import gp_Pnt
            from OCP.TopAbs import TopAbs_IN

            for k in doubtful:
                self._classifier.Perform(gp_Pnt(*(float(v) for v in points[k])), 1e-6)
                found[k] = self._classifier.State() == TopAbs_IN
        return found

    def escapes(self, point: np.ndarray, normal: np.ndarray, direction: np.ndarray) -> bool:
        """Whether a straight line from the point (just off its face) along ``direction`` leaves the part."""
        return not self.blocked(point + normal * LIFT, direction)


@dataclass(frozen=True)
class Stations:
    """Places along an edge, its ends just inside it: the points, the edge's tangent there and the outward
    normals of its two faces (``Edge.faces`` order) there, each an array of one row a station."""
    points: np.ndarray
    tangents: np.ndarray
    normals_a: np.ndarray
    normals_b: np.ndarray
    spacing: float  # the length of edge a station stands for


def stations(model: Model, edge: brep.Edge, count: int) -> Stations:
    """``count`` stations evenly along ``edge`` by its length (``stations_at``), each set computed once."""
    key = (edge.ordinal, count)
    found = model._stations.get(key)
    if found is None:
        found = stations_at(model, edge, np.linspace(0.0, 1.0, count))
        model._stations[key] = found
    return found


def stations_at(model: Model, edge: brep.Edge, fractions: np.ndarray) -> Stations:
    """Stations at ``fractions`` (0 to 1) of ``edge``'s length, the ends inset from its vertices by a twentieth
    of a millimetre (a tenth of the edge where it is shorter), where a ray from the end itself would graze the
    face the edge's end meets."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d
    from OCP.GCPnts import GCPnts_AbscissaPoint
    from OCP.gp import gp_Pnt, gp_Vec

    shape = model.part.edges()[edge.ordinal - 1]
    curve = BRepAdaptor_Curve(shape.wrapped)
    first, last = curve.FirstParameter(), curve.LastParameter()
    length = float(edge.length)
    inset = min(0.05, 0.1 * length)
    faces = [model.face(ordinal) for ordinal in edge.faces]
    on = [BRepAdaptor_Curve2d(shape.wrapped, face.wrapped) for face in faces]
    rows: list[list[np.ndarray]] = [[], [], [], []]
    for fraction in np.asarray(fractions, dtype=float):
        along = inset + float(fraction) * (length - 2 * inset)
        try:
            at = GCPnts_AbscissaPoint(curve, along, first)
            t = at.Parameter() if at.IsDone() else first + along / length * (last - first)
        except Exception:  # noqa: BLE001 - a curve the kernel cannot measure along is read by its parameter
            t = first + along / length * (last - first)
        point, tangent = gp_Pnt(), gp_Vec()
        curve.D1(t, point, tangent)
        size = tangent.Magnitude()
        rows[0].append(np.array(_xyz(point)))
        rows[1].append(np.array(_xyz(tangent)) / size if size > 1e-300 else np.asarray(edge.tangent, dtype=float))
        for k, (face, adaptor) in enumerate(zip(faces, on)):
            uv = adaptor.Value(t)
            rows[2 + k].append(brep.point_normal(face, uv.X(), uv.Y())[1])
    spacing = length / max(1, len(rows[0]) - 1)
    return Stations(*(np.array(row).reshape(-1, 3) for row in rows), spacing)  # type: ignore[arg-type]


def edge_normals(model: Model, edge: brep.Edge) -> tuple[np.ndarray, np.ndarray]:
    """The outward normals of an edge's two faces at its midpoint."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d

    shape = model.part.edges()[edge.ordinal - 1]
    curve = BRepAdaptor_Curve(shape.wrapped)
    t = (curve.FirstParameter() + curve.LastParameter()) / 2.0
    normals = []
    for ordinal in edge.faces:
        face = model.face(ordinal)
        uv = BRepAdaptor_Curve2d(shape.wrapped, face.wrapped).Value(t)
        normals.append(brep.point_normal(face, uv.X(), uv.Y())[1])
    return normals[0], normals[1]
