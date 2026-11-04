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

__all__ = ["Hit", "Model", "WORLD", "about", "directions_for", "edge_normals", "fibonacci", "unit"]

#: The six directions a three-axis machine approaches from.
WORLD = tuple(np.array(axis, dtype=float) for axis in
              ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)))
#: Two directions within this of each other (|cos|) are the same direction.
SAME = 0.9999
#: A face whose every normal is within this (|cos|) of perpendicular to a direction lies along it.
ALONG = 0.02
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


def unit(vector: Iterable[float]) -> np.ndarray:
    v = np.asarray(list(vector), dtype=float)
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


@dataclass(frozen=True)
class Hit:
    distance: float
    face: int          # the ordinal of the face hit, 0 for one the part does not know
    normal: np.ndarray  # its outward normal there


class Model:
    """A part's faces, surfaces, edges, samples and rays, each computed once."""

    def __init__(self, part: brep.Part) -> None:
        self.part = part
        self.faces = part.faces()
        self.n = len(self.faces)
        self.surfaces = [brep.surface(face) for face in self.faces]
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
        normals = self.samples(ordinal)[1]
        return len(normals) >= 3 and bool(np.all(np.abs(normals @ d) < ALONG))

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
            from OCP.IntCurvesFace import IntCurvesFace_Intersector

            found = IntCurvesFace_Intersector(self.faces[index].wrapped, 1e-7)
            self._face_intersectors[index] = found
        return found

    def _cast(self, origin: Iterable[float], direction: Iterable[float], skip: float, end: float,
              nearest: bool, given: tuple[np.ndarray, np.ndarray] | None = None
              ) -> tuple[float, int, float, float] | None:
        """The ray's nearest crossing (or, with ``nearest`` False, any crossing): its distance, the face's
        index and the (u, v) on it. Each face the ray's line could cross, by its box, is intersected exactly
        (``IntCurvesFace_Intersector``), nearest box first, until no nearer crossing can follow."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        o = np.asarray(list(origin), dtype=float)
        d = unit(direction)
        self.rays_cast += 1
        if given is None:
            candidates, entries = self._candidates(o, d, skip, end)
        else:
            candidates, entries = given
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

    def escape_all(self, points: np.ndarray, normals: np.ndarray, direction: np.ndarray,
                   skip: float = 1e-4, chunk: int = 256) -> np.ndarray:
        """``escapes`` for many points along one direction, their boxes tested together."""
        d = unit(direction)
        found = np.zeros(len(points), dtype=bool)
        origins = points + normals * LIFT
        grid = self._shared(d, len(points))
        if grid is not None:
            for row, origin in enumerate(origins):
                found[row] = self._cast(origin, d, skip, 1e9, False, grid.candidates(origin, skip, 1e9)) is None
            return found
        for start in range(0, len(points), chunk):
            block = origins[start:start + chunk]
            mask, enter = self._slabs(block, d, skip, 1e9)
            for row in range(len(block)):
                index = np.flatnonzero(mask[row])
                if not len(index):
                    found[start + row] = True
                    continue
                order = np.argsort(enter[row, index])
                given = (index[order], enter[row, index][order])
                found[start + row] = self._cast(block[row], d, skip, 1e9, False, given) is None
        return found

    def first_all(self, origins: np.ndarray, directions: np.ndarray, skip: float = 1e-4,
                  chunk: int = 256) -> list[Hit | None]:
        """``first`` for many rays, each its own direction, their boxes tested together."""
        found: list[Hit | None] = []
        dirs = directions / np.maximum(np.linalg.norm(directions, axis=1), 1e-300)[:, None]
        same = len(dirs) > 0 and bool(np.all(np.abs(dirs - dirs[0]) < 1e-12))  # a plane's samples share one
        grid = self._shared(dirs[0], len(dirs)) if same else None
        for start in range(0, len(origins), chunk):
            block, ways = origins[start:start + chunk], dirs[start:start + chunk]
            mask, enter = (None, None) if grid is not None else self._slabs(block, ways, skip, 1e9)
            for row in range(len(block)):
                if grid is not None:
                    given = grid.candidates(block[row], skip, 1e9)
                else:
                    index = np.flatnonzero(mask[row])
                    order = np.argsort(enter[row, index])
                    given = (index[order], enter[row, index][order])
                hit = self._cast(block[row], ways[row], skip, 1e9, True, given)
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

    def escapes(self, point: np.ndarray, normal: np.ndarray, direction: np.ndarray) -> bool:
        """Whether a straight line from the point (just off its face) along ``direction`` leaves the part."""
        return not self.blocked(point + normal * LIFT, direction)


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
