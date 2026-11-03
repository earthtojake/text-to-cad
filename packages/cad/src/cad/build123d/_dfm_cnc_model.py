"""One part's topology for the CNC measurements (``_dfm_cnc``): its faces, their surfaces and samples, the
edges between them, which way each face lies against a direction, exact rays that say what face they hit and
its normal there, and the machine's approach directions.

Everything here is measured on the B-rep (``_dfm_brep``): a face's samples are points on its surface, a ray
is an exact line against the part's faces (``IntCurvesFace_Intersector`` on each face whose box the line
meets, nearest first).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from cad.build123d import _dfm_brep as brep

__all__ = ["Hit", "Model", "edges", "WORLD", "about", "directions_for", "edge_normals", "fibonacci", "unit"]

#: The six directions a three-axis machine approaches from.
WORLD = tuple(np.array(axis, dtype=float) for axis in
              ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)))
#: Two directions within this of each other (|cos|) are the same direction.
SAME = 0.9999
#: A face whose every normal is within this (|cos|) of perpendicular to a direction lies along it.
ALONG = 0.02
#: How far off its face a ray starts, so it does not hit the face it leaves.
LIFT = 1e-3


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


@dataclass(frozen=True)
class Hit:
    distance: float
    face: int          # the ordinal of the face hit, 0 for one the part does not know
    normal: np.ndarray  # its outward normal there


class Model:
    """A part's faces, surfaces, edges, samples and rays, each computed once."""

    def __init__(self, part: brep.Part, sample_count: int = 6) -> None:
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
        self.sample_count = sample_count
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

    # --- faces -------------------------------------------------------------------------------------------

    def ref(self, ordinal: int) -> str:
        return self.part.ref("face", ordinal)

    def face(self, ordinal: int) -> Any:
        return self.faces[ordinal - 1]

    def surface(self, ordinal: int) -> brep.Surface:
        return self.surfaces[ordinal - 1]

    def samples(self, ordinal: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Points on the face, their outward normals and the areas they stand for, as arrays."""
        found = self._samples.get(ordinal)
        if found is None:
            face = self.face(ordinal)
            try:
                box = face.bounding_box(optimal=False)
                deflection = max(1e-3, 0.02 * max(box.size.X, box.size.Y, box.size.Z))
                points = brep.samples(face, self.sample_count, deflection=deflection)
            except Exception:  # noqa: BLE001 - a face that does not triangulate has no samples
                points = []
            if points:
                found = (np.array([s.point for s in points]), np.array([s.normal for s in points]),
                         np.array([s.area for s in points]))
            else:
                found = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0))
            self._samples[ordinal] = found
        return found

    def outline(self, ordinal: int) -> np.ndarray:
        """Points along the face's edges (and its samples): what its extent along a direction is taken of."""
        found = self._outline.get(ordinal)
        if found is None:
            from OCP.BRepAdaptor import BRepAdaptor_Curve

            points = []
            for edge in self.face(ordinal).edges():
                try:
                    curve = BRepAdaptor_Curve(edge.wrapped)
                    first, last = curve.FirstParameter(), curve.LastParameter()
                    for k in range(17):
                        p = curve.Value(first + (last - first) * k / 16)
                        points.append((p.X(), p.Y(), p.Z()))
                except Exception:  # noqa: BLE001
                    continue
            sampled = self.samples(ordinal)[0]
            found = np.vstack([np.array(points).reshape(-1, 3), sampled]) if points else sampled
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
        values = np.concatenate([self.outline(i) @ d for i in range(1, self.n + 1)])
        return float(values.min()), float(values.max())

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
        face = self.face(ordinal)
        perimeter = sum(edge.length for edge in face.edges())
        return float(2.0 * face.area / perimeter) if perimeter > 0 else 0.0

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
        return self._cast(origin, direction, skip, 1e9, False) is not None

    def escape_all(self, points: np.ndarray, normals: np.ndarray, direction: np.ndarray,
                   skip: float = 1e-4, chunk: int = 256) -> np.ndarray:
        """``escapes`` for many points along one direction, their boxes tested together."""
        d = unit(direction)
        found = np.zeros(len(points), dtype=bool)
        origins = points + normals * LIFT
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
        for start in range(0, len(origins), chunk):
            block, ways = origins[start:start + chunk], dirs[start:start + chunk]
            same = bool(np.all(np.abs(ways - ways[0]) < 1e-12))  # a plane's samples share one normal
            mask, enter = self._slabs(block, ways[0] if same else ways, skip, 1e9)
            for row in range(len(block)):
                index = np.flatnonzero(mask[row])
                order = np.argsort(enter[row, index])
                hit = self._cast(block[row], ways[row], skip, 1e9, True, (index[order], enter[row, index][order]))
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
