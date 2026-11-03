"""sheet's measurements of exact geometry (``cad._internal.dfm.sheet`` says what they are for), and the unfold.

**The sheet.** Every face is sampled (``_dfm_brep.samples``) and an exact ray cast from each sample into the
material, square to the face, to the next face it crosses. A planar face whose rays mostly reach an
opposite, antiparallel planar face is a *skin*; the area-weighted modal distance is the sheet's thickness
``t``. A pair of coaxial cylinders, one concave and one convex, whose rays cross ``t`` is a *bend*. A face
touching both faces of a pair (a skin and its opposite, a bend's inside and outside) is a cut *edge*; a cone
between a skin and a hole's wall is a countersink. Every other face, and every stretch of a skin whose rays
cross anything but ``t``, is not sheet (``not_sheet``: a boss, a pocket, a round, at its ref, with how far it
departs from ``t``).

**Bends.** The skins and the bends' cylinders joined by tangent edges form the sheet's two *sides*; the
side holding the largest skin is unfolded. Its coplanar skins are the flanges; each of its bend cylinders
joins one or two of them. A bend's inside radius is its concave cylinder's, its angle the angle the side's
cylinder spans about the axis (checked against the flanges' normals), its length the cylinder's extent along
the axis, and its tangent lines where the cylinders meet the flanges.

**The unfold.** From the largest flange, each flange is laid into the plane across the bends that join it
(a breadth-first walk): rotated flat about its bend and moved out by the bend allowance ``BA = angle *
(r + K t)`` (the length of the neutral surface, ``K`` the K-factor), the bend itself unrolled into a strip
``BA`` wide. The flanges' faces are moved exactly (a rigid transform each), so their holes and arcs stay
exact; a bend's strip is its cylinder's outline unrolled (exact for straight-ended bends, sampled where an
end is curved). The pieces are fused into the flat pattern (``unfold``). Holes, their distances (to the edge,
to each other, to each bend in four conventions), flanges' lengths, reliefs, notches, tabs and webs are all
measured on it, in the plane, by ``cad._internal.meshops_sheet``; each found place is mapped back onto the
part for its ref.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from cad._internal import meshops_sheet as plane
from cad._internal.dfm import Unmeasured
from cad._internal.dfm import sheet as rules_side
from cad.build123d import _dfm_brep as brep

__all__ = ["FAMILIES", "Unfolded", "measure", "unfold"]

#: The report's families, in order.
FAMILIES = ("parts", "not_sheet", "bends", "flanges", "channels", "reliefs", "hems", "curls", "holes",
            "hole_spacing", "hole_to_bend", "notches", "tabs", "webs", "gaps")
ITEM_CAP = 300
_PARALLEL = 0.9995


def _tolerance(thickness: float) -> float:
    """Two thicknesses this close are one."""
    return max(0.005, 0.002 * thickness)


def _r(value: Any, digits: int = 4) -> Any:
    if value is None:
        return None
    value = float(value)
    return round(value, digits) if math.isfinite(value) else None


def _xyz(point: Any) -> list[float]:
    return [round(float(value), 4) for value in point]


class _Sets:
    """Union-find over small integers."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def add(self, item: int) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: int) -> int:
        self.add(item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

    def groups(self) -> list[list[int]]:
        found: dict[int, list[int]] = {}
        for item in sorted(self.parent):
            found.setdefault(self.find(item), []).append(item)
        return list(found.values())


@dataclass
class _Hit:
    area: float
    distance: float | None
    face: int          # the face it reaches (0: none)
    point: np.ndarray


@dataclass
class _Bend:
    number: int
    side_faces: list[int]           # the unfolded side's cylinder faces
    other_faces: list[int]          # the partner side's
    inner: list[int]
    outer: list[int]
    axis: np.ndarray
    origin: np.ndarray
    e1: np.ndarray
    e2: np.ndarray
    radius_side: float
    inside_radius: float
    outside_radius: float
    phi0: float
    span: float
    w0: float
    w1: float
    flanges: dict[int, int] = field(default_factory=dict)   # flange number -> 0 (at phi0) or 1 (at phi0 + span)
    normals_angle: float | None = None
    k: float = 0.0
    k_source: str = ""
    allowance: float = 0.0
    # placed in the flat: the parent flange's side at x' < 0, the child's at x' > allowance
    parent: int | None = None
    child: int | None = None
    sigma: float = 1.0
    frame: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None   # origin, x', y' in the flat
    to_flat: np.ndarray | None = None                                # the parent's placement (4x4)
    placed: bool = False

    @property
    def angle(self) -> float:
        return math.degrees(self.span)

    def phi(self, points: np.ndarray) -> np.ndarray:
        rel = points - self.origin
        return np.arctan2(rel @ self.e2, rel @ self.e1)

    def w(self, points: np.ndarray) -> np.ndarray:
        return (points - self.origin) @ self.axis

    def tangent_point(self, end: int, w: float = 0.0, radius: float | None = None) -> np.ndarray:
        phi = self.phi0 + (self.span if end else 0.0)
        r = self.radius_side if radius is None else radius
        return self.origin + r * (math.cos(phi) * self.e1 + math.sin(phi) * self.e2) + w * self.axis

    def circumferential(self, end: int) -> np.ndarray:
        phi = self.phi0 + (self.span if end else 0.0)
        return -math.sin(phi) * self.e1 + math.cos(phi) * self.e2


@dataclass
class _Flange:
    number: int
    faces: list[int]
    normal: np.ndarray
    origin: np.ndarray
    area: float
    to_flat: np.ndarray | None = None
    via: int | None = None   # the bend it was reached by


@dataclass
class _Region:
    """A piece of the flat pattern and how to map its points back onto the part."""

    loop: plane.Loop
    to_part: Callable[[np.ndarray], np.ndarray]
    faces: list[int]


@dataclass
class _HoleLoop:
    loop: plane.Loop
    location_faces: list[int]
    xyz: np.ndarray
    in_bend: bool = False
    countersink: float | None = None


def _matrix(rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = rotation
    m[:3, 3] = translation
    return m


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=float).reshape(-1, 3)
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def _trsf(matrix: np.ndarray) -> Any:
    from OCP.gp import gp_Trsf

    trsf = gp_Trsf()
    m = matrix
    trsf.SetValues(m[0, 0], m[0, 1], m[0, 2], m[0, 3], m[1, 0], m[1, 1], m[1, 2], m[1, 3],
                   m[2, 0], m[2, 1], m[2, 2], m[2, 3])
    return trsf


def _perpendicular(axis: np.ndarray) -> np.ndarray:
    trial = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = trial - axis * float(trial @ axis)
    return e1 / np.linalg.norm(e1)


# --- faces: their neighbours and samples -------------------------------------------------------------------


@dataclass(frozen=True)
class _Join:
    """Two faces meeting at an edge, and whether they meet tangent (``smooth``)."""

    ordinal: int
    faces: tuple[int, int]
    smooth: bool
    midpoint: tuple[float, float, float]


def _adjacency(part: brep.Part) -> list[_Join]:
    """Every edge two faces of ``part`` share, whether they meet tangent there, and its midpoint: what
    ``_dfm_brep.edges`` gives less the corner's convexity, in time linear in the edges (each face's
    surface properties made once)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.collections import (
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape)

    ancestry = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(part.shape.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestry)
    props: dict[int, Any] = {}
    found: list[_Join] = []
    for index in range(1, ancestry.Extent() + 1):
        owners: list[Any] = []
        for owner in ancestry.FindFromIndex(index):
            if not any(owner.IsSame(other) for other in owners):
                owners.append(owner)
        if len(owners) != 2:
            continue
        edge = TopoDS.Edge(ancestry.FindKey(index))
        try:
            curve = BRepAdaptor_Curve(edge)
            t = (curve.FirstParameter() + curve.LastParameter()) / 2.0
            point = curve.Value(t)
            normals = []
            for owner in owners:
                face = TopoDS.Face(owner)
                ordinal = part.face_ordinal(face)
                if ordinal not in props:
                    props[ordinal] = BRepGProp_Face(face)
                uv = BRepAdaptor_Curve2d(edge, face).Value(t)
                p, n = gp_Pnt(), gp_Vec()
                props[ordinal].Normal(uv.X(), uv.Y(), p, n)
                size = n.Magnitude()
                normals.append((ordinal, np.array(brep._xyz(n)) / size if size > 1e-300 else np.zeros(3)))
        except Exception:  # noqa: BLE001 - a degenerate edge joins nothing to measure
            continue
        (a, na), (b, nb) = normals
        between = math.degrees(math.acos(max(-1.0, min(1.0, float(na @ nb)))))
        found.append(_Join(part.edge_ordinal(edge), (a, b), between < brep.SMOOTH_DEG, brep._xyz(point)))
    return found


def _samples(face: Any, count: int) -> list[brep.Sample]:
    """``count`` points on ``face`` spread by area, each on the surface with its outward normal and its share
    of the face's area: the face's triangulation's triangles taken at evenly spaced fractions of its
    cumulative area, each sample the surface at its triangle's middle (``_dfm_brep.samples`` evaluates every
    sub-triangle's; this evaluates only those taken, the surface's properties made once)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    box = face.bounding_box()
    brep._triangulated(face, max(1e-3, 0.02 * max(box.size.X, box.size.Y, box.size.Z)))
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
    if triangulation is None or triangulation.NbTriangles() == 0:
        return []
    trsf = location.Transformation()
    nodes = np.array([brep._xyz(triangulation.Node(i).Transformed(trsf)) for i in range(1, triangulation.NbNodes() + 1)])
    uvs = (np.array([(triangulation.UVNode(i).X(), triangulation.UVNode(i).Y())
                     for i in range(1, triangulation.NbNodes() + 1)]) if triangulation.HasUVNodes() else None)
    corners = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]) - 1
    a, b, c = nodes[corners[:, 0]], nodes[corners[:, 1]], nodes[corners[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    total = float(areas.sum())
    if total <= 0.0:
        return []
    cumulative = np.cumsum(areas)
    picks = np.searchsorted(cumulative, (np.arange(count) + 0.5) / count * total)
    picks = np.minimum(picks, len(areas) - 1)
    props = BRepGProp_Face(face.wrapped)
    found = []
    for k in picks:
        i, j, l = corners[k]
        if uvs is not None:
            u, v = (uvs[i] + uvs[j] + uvs[l]) / 3.0
            p, n = gp_Pnt(), gp_Vec()
            props.Normal(float(u), float(v), p, n)
            size = n.Magnitude()
            point = np.array(brep._xyz(p))
            normal = np.array(brep._xyz(n)) / size if size > 1e-300 else np.zeros(3)
        else:
            point = (nodes[i] + nodes[j] + nodes[l]) / 3.0
            normal = np.cross(nodes[j] - nodes[i], nodes[l] - nodes[i])
            normal = normal / (np.linalg.norm(normal) or 1.0)
        found.append(brep.Sample(point, normal, total / count))
    return found


# --- wires as points ---------------------------------------------------------------------------------------


def _edge_points(edge: Any, reverse: bool, count: int = 48) -> tuple[np.ndarray, str, Any]:
    """An edge's points in its wire's direction: a line's two ends, a curve sampled; its kind and its circle
    (centre, axis, radius) when it is one."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line

    curve = BRepAdaptor_Curve(edge)
    first, last = curve.FirstParameter(), curve.LastParameter()
    kind = curve.GetType()
    circle = None
    if kind == GeomAbs_Line:
        params = np.array([first, last])
        name = "line"
    elif kind == GeomAbs_Circle:
        circ = curve.Circle()
        radius = circ.Radius()
        sweep = abs(last - first)
        step = min(math.radians(5.0), 2.0 * math.acos(max(-1.0, 1.0 - plane.CHORD_MM / radius)) if radius > plane.CHORD_MM
                   else math.radians(5.0))
        n = int(min(720, max(2, math.ceil(sweep / max(step, 1e-4))))) + 1
        params = np.linspace(first, last, n)
        name = "circle"
        circle = (np.array(brep._xyz(circ.Location())), np.array(brep._xyz(circ.Position().Direction())), radius)
    else:
        params = np.linspace(first, last, count + 1)
        name = "curve"
    if reverse:
        params = params[::-1]
    points = np.array([brep._xyz(curve.Value(float(u))) for u in params])
    return points, name, circle


def _wire_loop(wire: Any, face: Any, mapping: Callable[[np.ndarray], np.ndarray] | None = None,
               label: Any = None) -> tuple[plane.Loop, np.ndarray, list[Any]]:
    """A wire of a face as a loop: its points (mapped into the plane by ``mapping``, else the face's own
    XY), each segment's straightness and source edge; also the wire's 3D points and its edges."""
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_REVERSED

    explorer = BRepTools_WireExplorer(wire, face)
    points3, straight, sources, circles, edges = [], [], [], [], []
    while explorer.More():
        edge = explorer.Current()
        reverse = explorer.Orientation() == TopAbs_REVERSED
        pts, kind, circle = _edge_points(edge, reverse)
        edges.append(edge)
        circles.append(circle)
        for i in range(len(pts) - 1):
            points3.append(pts[i])
            straight.append(kind == "line")
            sources.append(edge)
        explorer.Next()
    if not points3:
        return plane.Loop(np.zeros((0, 2)), np.zeros(0, bool)), np.zeros((0, 3)), edges
    points3 = np.array(points3)
    flat = mapping(points3) if mapping is not None else points3[:, :2]
    loop = plane.Loop(flat[:, :2], np.array(straight), sources, label)
    if circles and all(c is not None for c in circles):
        centres = np.array([c[0] for c in circles])
        radii = np.array([c[2] for c in circles])
        if np.ptp(radii) < 1e-7 and np.ptp(centres, axis=0).max() < 1e-7:
            centre = mapping(centres[:1]) if mapping is not None else centres[:1]
            loop.circle = (float(centre[0, 0]), float(centre[0, 1]), float(radii[0]))
    return loop, points3, edges


def _simplify(points: np.ndarray) -> np.ndarray:
    """A closed polygon without repeated or collinear points."""
    kept = [p for i, p in enumerate(points) if i == 0 or np.linalg.norm(p - points[i - 1]) > 1e-9]
    if len(kept) > 1 and np.linalg.norm(kept[0] - kept[-1]) <= 1e-9:
        kept.pop()
    changed = True
    while changed and len(kept) > 3:
        changed = False
        for i in range(len(kept)):
            a, b, c = kept[i - 1], kept[i], kept[(i + 1) % len(kept)]
            u, v = b - a, c - b
            if abs(u[0] * v[1] - u[1] * v[0]) <= 1e-9 * (np.linalg.norm(u) * np.linalg.norm(v) + 1e-300) \
                    and float(u @ v) >= 0:
                kept.pop(i)
                changed = True
                break
    return np.array(kept)


# --- the analysis ------------------------------------------------------------------------------------------


class _Analysis:
    def __init__(self, part: brep.Part, options: dict[str, Any]) -> None:
        self.part = part
        self.options = options
        self.faces = part.faces()
        self.surfaces = [brep.surface(face) for face in self.faces]
        self.areas = np.array([float(face.area) for face in self.faces])
        self.edges = _adjacency(part)
        self.neighbors: dict[int, set[int]] = {i: set() for i in range(1, len(self.faces) + 1)}
        self.smooth: dict[int, set[int]] = {i: set() for i in range(1, len(self.faces) + 1)}
        self.edge_faces: dict[int, tuple[int, int]] = {}
        for edge in self.edges:
            a, b = edge.faces
            self.neighbors[a].add(b)
            self.neighbors[b].add(a)
            self.edge_faces[edge.ordinal] = (a, b)
            if edge.smooth:
                self.smooth[a].add(b)
                self.smooth[b].add(a)
        self.rays = brep.Rays(part.shape)
        self.thickness: float | None = None
        self.why = ""
        self.skins: set[int] = set()
        self.bend_faces: set[int] = set()
        self.edge_set: set[int] = set()
        self.countersinks: dict[int, float] = {}
        self.wall_of: dict[int, int] = {}
        self.partners: dict[int, set[int]] = {}
        self.not_sheet: list[dict[str, Any]] = []
        self.bends: list[_Bend] = []
        self.flanges: list[_Flange] = []
        self.side: set[int] = set()
        self.flat: Any = None
        self.flat_loops: list[plane.Loop] = []
        self.holes: list[_HoleLoop] = []
        self.regions: list[_Region] = []
        self.unfold_note = ""
        self.overlap = 0.0
        self.sheet_fraction = 0.0
        self._boxes: tuple[np.ndarray, np.ndarray] | None = None

    def ref(self, ordinal: int) -> str:
        return self.part.ref("face", int(ordinal))

    # -- the sheet ----------------------------------------------------------------------------------------

    def _opposite(self, a: int, b: int) -> bool:
        sa, sb = self.surfaces[a - 1], self.surfaces[b - 1]
        if sa.kind == "plane" and sb.kind == "plane":
            return float(np.dot(sa.normal, sb.normal)) < -_PARALLEL
        if sa.kind == "cylinder" and sb.kind == "cylinder":
            return self._coaxial(sa, sb)
        return False

    @staticmethod
    def _coaxial(sa: brep.Surface, sb: brep.Surface, tolerance: float = 1e-4) -> bool:
        aa, ab = np.array(sa.axis), np.array(sb.axis)
        if abs(float(aa @ ab)) < _PARALLEL:
            return False
        offset = np.array(sb.origin) - np.array(sa.origin)
        return float(np.linalg.norm(offset - aa * float(offset @ aa))) < tolerance * max(1.0, sa.radius or 1.0)

    def probe(self) -> None:
        total = float(self.areas.sum())
        self.hits: dict[int, list[_Hit]] = {}
        for ordinal, face in enumerate(self.faces, start=1):
            share = self.areas[ordinal - 1] / total if total > 0 else 1.0
            count = 48 if share > 0.02 else 16 if share > 0.002 else 8
            found = []
            for sample in _samples(face, count):
                hit = self.rays.first(sample.point, -sample.normal, skip=1e-6)
                if hit is None:
                    found.append(_Hit(sample.area, None, 0, sample.point))
                else:
                    found.append(_Hit(sample.area, hit[0], self.part.face_ordinal(hit[1]), sample.point))
            self.hits[ordinal] = found

    def classify(self) -> None:
        planar = [(h.distance, h.area) for a, hs in self.hits.items() for h in hs
                  if h.distance is not None and h.face and self._opposite(a, h.face) and self.surfaces[a - 1].kind == "plane"]
        if not planar:
            planar = [(h.distance, h.area) for a, hs in self.hits.items() for h in hs
                      if h.distance is not None and h.face and self._opposite(a, h.face)]
        if not planar:
            self.why = "no face lies opposite another a constant distance across"
            across = [(round(h.distance, 3), h.area) for a, hs in self.hits.items() for h in hs
                      if h.distance is not None and self.surfaces[a - 1].kind not in ("plane", "cylinder")]
            if across:
                totals: dict[float, float] = {}
                for distance, area in across:
                    totals[distance] = totals.get(distance, 0.0) + area
                mode = max(totals, key=totals.get)
                if totals[mode] >= 0.5 * sum(area for _, area in across):
                    self.why = (f"a {mode:.4g} mm shell of freeform faces: formed or stamped, not cut flat and "
                                "bent on a brake")
            return
        distances = np.array([d for d, _ in planar])
        weights = np.array([w for _, w in planar])
        bins = np.round(distances / 1e-3).astype(np.int64)
        totals: dict[int, float] = {}
        for key, weight in zip(bins, weights):
            totals[int(key)] = totals.get(int(key), 0.0) + float(weight)
        peak = max(totals, key=lambda key: (totals[key], -key)) * 1e-3
        tolerance = _tolerance(peak)
        near = np.abs(distances - peak) <= tolerance
        thickness = float((distances[near] * weights[near]).sum() / weights[near].sum())
        self.thickness = thickness
        self.tolerance = tol = _tolerance(thickness)

        share: dict[int, float] = {}
        pair_area: dict[tuple[int, int], float] = {}
        for a, hs in self.hits.items():
            sampled = sum(h.area for h in hs) or 1.0
            good = 0.0
            for h in hs:
                if h.distance is not None and h.face and abs(h.distance - thickness) <= tol and self._opposite(a, h.face):
                    good += h.area
                    pair_area[(a, h.face)] = pair_area.get((a, h.face), 0.0) + h.area
            share[a] = good / sampled
        for (a, b), value in pair_area.items():
            sampled = sum(h.area for h in self.hits[a]) or 1.0
            if value >= 0.02 * sampled:
                self.partners.setdefault(a, set()).add(b)
                self.partners.setdefault(b, set()).add(a)
        for a in self.hits:
            kind = self.surfaces[a - 1].kind
            if share[a] >= 0.5 and kind == "plane":
                self.skins.add(a)
            elif share[a] >= 0.5 and kind == "cylinder":
                self.bend_faces.add(a)
        # a coaxial pair whose cylinders meet a skin square to their axis is a hole's wall and a round
        # outline (a washer), not a bend
        for a in list(self.bend_faces):
            axis = np.array(self.surfaces[a - 1].axis)
            for b in self.neighbors[a] - self.smooth[a]:
                if b in self.skins and abs(float(np.dot(self.surfaces[b - 1].normal, axis))) > _PARALLEL:
                    self.bend_faces.discard(a)
                    break
        paired = self.skins | self.bend_faces
        # a countersink: a cone about a skin's normal, meeting that skin and a coaxial hole wall; for the
        # cut edges below it stands in for the skin it is sunk into
        stands_for: dict[int, int] = {}
        for a in self.hits:
            surface = self.surfaces[a - 1]
            if a in paired or surface.kind != "cone":
                continue
            axis = np.array(surface.axis)
            skins = [b for b in self.neighbors[a] if b in self.skins
                     and abs(float(np.dot(self.surfaces[b - 1].normal, axis))) > _PARALLEL]
            walls = [b for b in self.neighbors[a] if self.surfaces[b - 1].kind == "cylinder"
                     and b not in paired and self._coaxial(surface, self.surfaces[b - 1], 1e-3)]
            if skins and walls:
                self.countersinks[a] = 2.0 * self._largest_circle(a)
                self.wall_of[a] = walls[0]
                stands_for[a] = skins[0]
        for a in self.hits:
            if a in paired or a in self.countersinks:
                continue
            near = {stands_for.get(b, b) for b in self.neighbors[a]}
            near = [b for b in near if b in paired]
            if any(c in self.partners.get(b, ()) for b in near for c in near):
                self.edge_set.add(a)
        sheet = paired | self.edge_set | set(self.countersinks)
        self.sheet_fraction = float(self.areas[[a - 1 for a in sheet]].sum() / self.areas.sum()) if sheet else 0.0
        for a, hs in self.hits.items():
            if a in sheet and a not in self.skins:
                continue
            valid = [h for h in hs if h.distance is not None and h.face not in self.countersinks]
            if a in self.skins:
                off = [h for h in valid if abs(h.distance - thickness) > tol]
                sampled = sum(h.area for h in hs) or 1.0
                if sum(h.area for h in off) < 0.02 * sampled:
                    continue
                worst = max(off, key=lambda h: abs(h.distance - thickness))
                kind = "thicker" if worst.distance > thickness else "thinner"
                self._not_sheet(a, kind, worst.distance, abs(worst.distance - thickness), worst.point,
                                sum(h.area for h in off) / sampled * self.areas[a - 1])
                continue
            kind = "unpaired"
            if valid:
                worst = max(valid, key=lambda h: abs(h.distance - thickness))
                local, deviation, point = worst.distance, abs(worst.distance - thickness), worst.point
                facing = [h for h in valid if h.face and self._opposite(a, h.face)]
                if facing and sum(h.area for h in facing) >= 0.5 * sum(h.area for h in hs):
                    kind = "thicker" if worst.distance > thickness else "thinner"
            else:
                box = self.faces[a - 1].bounding_box()
                local, deviation = None, max(box.size.X, box.size.Y, box.size.Z)
                centre = self.faces[a - 1].center()
                point = np.array([centre.X, centre.Y, centre.Z])
            self._not_sheet(a, kind, local, max(deviation, tol), point, self.areas[a - 1])

    def _largest_circle(self, ordinal: int) -> float:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle

        best = 0.0
        for edge in self.faces[ordinal - 1].edges():
            curve = BRepAdaptor_Curve(edge.wrapped)
            if curve.GetType() == GeomAbs_Circle:
                best = max(best, curve.Circle().Radius())
        return best

    def _not_sheet(self, ordinal: int, kind: str, local: float | None, deviation: float, point: Any,
                   area: float) -> None:
        self.not_sheet.append({"kind": kind, "surface": self.surfaces[ordinal - 1].kind,
                               "local_thickness_mm": _r(local), "deviation_mm": _r(deviation),
                               "area_mm2": _r(area, 3), "location": self.ref(ordinal), "xyz": _xyz(point)})

    # -- bends --------------------------------------------------------------------------------------------

    def find_bends(self) -> None:
        if self.thickness is None or not self.skins:
            return
        sides = _Sets()
        nodes = self.skins | self.bend_faces
        for a in nodes:
            sides.add(a)
            for b in self.smooth[a]:
                if b in nodes:
                    sides.join(a, b)
        groups = sides.groups()
        largest = max(self.skins, key=lambda a: (self.areas[a - 1], -a))
        self.side = next(set(group) for group in groups if largest in group)
        # flanges: the side's coplanar skins joined by tangent edges
        flats = _Sets()
        for a in self.side:
            if a in self.skins:
                flats.add(a)
                for b in self.smooth[a]:
                    if b in self.skins and b in self.side and self._coplanar(a, b):
                        flats.join(a, b)
        for number, members in enumerate(sorted(flats.groups(), key=lambda g: -self.areas[[m - 1 for m in g]].sum())):
            first = self.surfaces[members[0] - 1]
            self.flanges.append(_Flange(number, members, np.array(first.normal), np.array(first.origin),
                                        float(self.areas[[m - 1 for m in members]].sum())))
        flange_of = {face: flange.number for flange in self.flanges for face in flange.faces}
        cylinders = _Sets()
        for a in self.side & self.bend_faces:
            cylinders.add(a)
            for b in self.neighbors[a]:
                if b in self.side and b in self.bend_faces and self._same_cylinder(a, b):
                    cylinders.join(a, b)
        for number, members in enumerate(cylinders.groups()):
            bend = self._bend(number, members, flange_of)
            if bend is not None:
                self.bends.append(bend)

    def _coplanar(self, a: int, b: int) -> bool:
        sa, sb = self.surfaces[a - 1], self.surfaces[b - 1]
        if float(np.dot(sa.normal, sb.normal)) < _PARALLEL:
            return False
        return abs(float(np.dot(np.array(sb.origin) - np.array(sa.origin), sa.normal))) < 1e-6 * max(1.0, self.thickness or 1)

    def _same_cylinder(self, a: int, b: int) -> bool:
        sa, sb = self.surfaces[a - 1], self.surfaces[b - 1]
        return self._coaxial(sa, sb) and abs(sa.radius - sb.radius) < 1e-6 * max(1.0, sa.radius)

    def _boundary(self, faces: list[int], per_edge: int = 9) -> np.ndarray:
        points = []
        for a in faces:
            for edge in self.faces[a - 1].edges():
                for u in np.linspace(0.0, 1.0, per_edge):
                    p = edge.position_at(float(u))
                    points.append((p.X, p.Y, p.Z))
        return np.array(points)

    def _bend(self, number: int, members: list[int], flange_of: dict[int, int]) -> _Bend | None:
        surface = self.surfaces[members[0] - 1]
        axis = np.array(surface.axis, dtype=float)
        axis /= np.linalg.norm(axis)
        origin = np.array(surface.origin, dtype=float)
        e1 = _perpendicular(axis)
        e2 = np.cross(axis, e1)
        others = sorted({b for a in members for b in self.partners.get(a, ()) if b in self.bend_faces})
        if not others:
            return None
        other = self.surfaces[others[0] - 1]
        radii = {bool(surface.concave): surface.radius, bool(other.concave): other.radius}
        if True not in radii or False not in radii:
            return None
        inner = members if surface.concave else others
        outer = others if surface.concave else members
        points = self._boundary(members)
        rel = points - origin
        phis = np.sort(np.mod(np.arctan2(rel @ e2, rel @ e1), 2 * math.pi))
        gaps = np.diff(np.concatenate([phis, phis[:1] + 2 * math.pi]))
        widest = int(np.argmax(gaps))
        span = 2 * math.pi - float(gaps[widest])
        phi0 = float(phis[(widest + 1) % len(phis)])
        ws = rel @ axis
        bend = _Bend(number, sorted(members), others, sorted(inner), sorted(outer), axis, origin, e1, e2,
                     float(surface.radius), float(radii[True]), float(radii[False]), phi0, span,
                     float(ws.min()), float(ws.max()))
        for edge in self.edges:
            a, b = edge.faces
            if not edge.smooth:
                continue
            for cylinder, flat in ((a, b), (b, a)):
                if cylinder in members and flat in flange_of:
                    phi = float(bend.phi(np.array(edge.midpoint)[None])[0])
                    d0 = abs((phi - phi0 + math.pi) % (2 * math.pi) - math.pi)
                    d1 = abs((phi - phi0 - span + math.pi) % (2 * math.pi) - math.pi)
                    bend.flanges.setdefault(flange_of[flat], 0 if d0 <= d1 else 1)
        attached = list(bend.flanges)
        if len(attached) == 2:
            na, nb = (self.flanges[attached[0]].normal, self.flanges[attached[1]].normal)
            bend.normals_angle = math.degrees(math.acos(max(-1.0, min(1.0, float(na @ nb)))))
        t = float(self.thickness)
        given = self.options.get("k_factor")
        if given is not None:
            bend.k, bend.k_source = float(given), "given (--k-factor)"
        else:
            bend.k, bend.k_source = rules_side.k_factor(self.options.get("material"), self.options.get("rules"),
                                                        bend.inside_radius, t)
        bend.allowance = span * (bend.inside_radius + bend.k * t)
        return bend

    # -- the unfold ---------------------------------------------------------------------------------------

    def unfold(self) -> None:
        import build123d as bd
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform

        if not self.flanges:
            self.unfold_note = "no flat flange to unfold from"
            return
        base = self.flanges[0]
        normal = base.normal / np.linalg.norm(base.normal)
        x_axis = self._longest_direction(base) - normal * float(self._longest_direction(base) @ normal)
        x_axis /= np.linalg.norm(x_axis)
        y_axis = np.cross(normal, x_axis)
        rotation = np.vstack([x_axis, y_axis, normal])
        base.to_flat = _matrix(rotation, -rotation @ base.origin)
        by_flange: dict[int, list[_Bend]] = {}
        for bend in self.bends:
            for flange in bend.flanges:
                by_flange.setdefault(flange, []).append(bend)
        queue = [base.number]
        cycles = 0
        while queue:
            current = self.flanges[queue.pop(0)]
            for bend in by_flange.get(current.number, []):
                if bend.placed:
                    continue
                child_number = next((f for f in bend.flanges if f != current.number), None)
                if child_number is not None and self.flanges[child_number].to_flat is not None:
                    cycles += 1
                    bend.placed = True
                    continue
                self._place(bend, current, self.flanges[child_number] if child_number is not None else None)
                if child_number is not None:
                    queue.append(child_number)
        unreached = [f.number for f in self.flanges if f.to_flat is None]
        notes = []
        if cycles:
            notes.append(f"{cycles} bend(s) close a loop of flanges: the part does not unfold in one piece "
                         "without a cut (a seam)")
        if unreached:
            notes.append(f"{len(unreached)} flange(s) are joined to the rest by no bend")
        self.unfold_note = "; ".join(notes)
        pieces = []
        for flange in self.flanges:
            if flange.to_flat is None:
                continue
            trsf = _trsf(flange.to_flat)
            for a in flange.faces:
                moved = bd.Face(BRepBuilderAPI_Transform(self.faces[a - 1].wrapped, trsf, True).Shape())
                pieces.append(moved)
                self._flange_regions(a, flange)
        for bend in self.bends:
            if bend.to_flat is not None:
                pieces.extend(self._strip(bend))
        if not pieces:
            return
        total = sum(piece.area for piece in pieces)
        fused = pieces[0].fuse(*pieces[1:], tol=1e-6).clean() if len(pieces) > 1 else pieces[0]
        faces = fused.faces()
        self.flat = faces[0] if len(faces) == 1 else bd.Compound(children=list(faces))
        flat_area = sum(face.area for face in faces)
        self.overlap = max(0.0, total - flat_area) if total - flat_area > 1e-6 * total + 1e-6 else 0.0
        for face in faces:
            outer, _, _ = _wire_loop(face.outer_wire().wrapped, face.wrapped)
            outer.label = "outer"
            self.flat_loops.append(outer)
            for wire in face.inner_wires():
                loop, _, _ = _wire_loop(wire.wrapped, face.wrapped)
                loop.label = "hole"
                self.flat_loops.append(loop)

    def _longest_direction(self, flange: _Flange) -> np.ndarray:
        best, direction = -1.0, None
        for a in flange.faces:
            for edge in self.faces[a - 1].edges():
                if edge.geom_type.name == "LINE" and edge.length > best:
                    p0, p1 = edge.position_at(0), edge.position_at(1)
                    best, direction = edge.length, np.array([p1.X - p0.X, p1.Y - p0.Y, p1.Z - p0.Z])
        if direction is None:
            return _perpendicular(flange.normal)
        return direction / np.linalg.norm(direction)

    def _place(self, bend: _Bend, parent: _Flange, child: _Flange | None) -> None:
        end_parent = bend.flanges[parent.number]
        bend.parent = parent.number
        bend.sigma = 1.0 if end_parent == 0 else -1.0
        bend.to_flat = parent.to_flat
        bend.placed = True
        u = bend.sigma * bend.circumferential(end_parent)
        p0 = bend.tangent_point(end_parent)
        origin = _apply(parent.to_flat, p0[None])[0]
        x = parent.to_flat[:3, :3] @ u
        y = parent.to_flat[:3, :3] @ bend.axis
        bend.frame = (origin[:2], x[:2], y[:2])
        if child is None:
            return
        bend.child = child.number
        end_child = bend.flanges[child.number]
        v = bend.sigma * bend.circumferential(end_child)
        q0 = bend.tangent_point(end_child)
        rotation = np.outer(u, v) + np.outer(bend.axis, bend.axis) + np.outer(parent.normal, child.normal)
        translation = p0 + bend.allowance * u - rotation @ q0
        child.to_flat = parent.to_flat @ _matrix(rotation, translation)
        child.via = bend.number

    def _unroll(self, bend: _Bend) -> Callable[[np.ndarray], np.ndarray]:
        """Points of the bend's side cylinder into the flat (x, y, z=0)."""
        end_parent = 0 if bend.sigma > 0 else 1
        u = bend.sigma * bend.circumferential(end_parent)
        phi_parent = bend.phi0 + (bend.span if end_parent else 0.0)

        def mapped(points: np.ndarray) -> np.ndarray:
            s = np.mod(bend.sigma * (bend.phi(points) - phi_parent), 2 * math.pi)
            s = np.where(s > bend.span + (2 * math.pi - bend.span) / 2, s - 2 * math.pi, s)
            fraction = s / bend.span if bend.span > 1e-12 else np.zeros_like(s)
            w = bend.w(points)
            at = bend.tangent_point(end_parent)[None] + w[:, None] * bend.axis[None] + \
                (fraction * bend.allowance)[:, None] * u[None]
            return _apply(bend.to_flat, at)

        return mapped

    def _from_flat_bend(self, bend: _Bend) -> Callable[[np.ndarray], np.ndarray]:
        origin, x, y = bend.frame

        def back(points: np.ndarray) -> np.ndarray:
            rel = np.asarray(points, dtype=float).reshape(-1, 2) - origin
            xs, ws = rel @ x, rel @ y
            phi_parent = bend.phi0 + (bend.span if bend.sigma < 0 else 0.0)
            fraction = np.clip(xs / bend.allowance if bend.allowance > 1e-12 else 0.0, 0.0, 1.0)
            phi = phi_parent + bend.sigma * fraction * bend.span
            radial = np.cos(phi)[:, None] * bend.e1[None] + np.sin(phi)[:, None] * bend.e2[None]
            return bend.origin[None] + bend.radius_side * radial + ws[:, None] * bend.axis[None]

        return back

    def _strip(self, bend: _Bend) -> list[Any]:
        import build123d as bd

        mapping = self._unroll(bend)
        pieces = []
        for a in bend.side_faces:
            face = self.faces[a - 1]
            outer, points3, _ = _wire_loop(face.outer_wire().wrapped, face.wrapped, mapping)
            polygon = _simplify(np.column_stack([outer.points, np.zeros(len(outer.points))])[:, :2])
            if len(polygon) < 3:
                continue
            shape = bd.make_face(bd.Polyline(*[(float(x), float(y), 0.0) for x, y in polygon], close=True))
            for wire in face.inner_wires():
                loop, inner3, _ = _wire_loop(wire.wrapped, face.wrapped, mapping)
                ring = _simplify(loop.points)
                if len(ring) >= 3:
                    hole = bd.make_face(bd.Polyline(*[(float(x), float(y), 0.0) for x, y in ring], close=True))
                    shape = shape.cut(hole).faces()[0]
                    self._hole(wire, face, loop, inner3, in_bend=True)
            pieces.append(shape)
            self.regions.append(_Region(plane.Loop(polygon, np.ones(len(polygon), bool)), self._from_flat_bend(bend),
                                        sorted(self.neighbors[a] | {a})))
        return pieces

    def _flange_regions(self, ordinal: int, flange: _Flange) -> None:
        face = self.faces[ordinal - 1]
        mapping = lambda points: _apply(flange.to_flat, points)  # noqa: E731
        outer, _, _ = _wire_loop(face.outer_wire().wrapped, face.wrapped, mapping)
        inverse = np.linalg.inv(flange.to_flat)
        self.regions.append(_Region(outer, lambda points: _apply(
            inverse, np.column_stack([np.asarray(points).reshape(-1, 2), np.zeros(len(np.asarray(points).reshape(-1, 2)))])),
            sorted(self.neighbors[ordinal] | {ordinal})))
        for wire in face.inner_wires():
            loop, points3, _ = _wire_loop(wire.wrapped, face.wrapped, mapping)
            self._hole(wire, face, loop, points3)

    def _hole(self, wire: Any, face: Any, loop: plane.Loop, points3: np.ndarray, in_bend: bool = False) -> None:
        skin = self.part.face_ordinal(face)
        walls = []
        for edge in wire.edges():
            ordinal = self.part.edge_ordinal(edge)
            pair = self.edge_faces.get(ordinal)
            if pair:
                walls.extend(f for f in pair if f != skin and f not in walls)
        countersink = None
        through = None
        for wall in list(walls):
            if wall in self.countersinks:
                countersink = self.countersinks[wall]
                through = self.wall_of.get(wall)
                if through is not None:
                    walls = [through] + [w for w in walls if w != through]
        if through is not None:
            loop.through_diameter = 2.0 * float(self.surfaces[through - 1].radius)
        elif countersink is None:
            for cone, wall in self.wall_of.items():
                if wall in walls:
                    countersink = self.countersinks[cone]
        centre = points3.mean(axis=0) if len(points3) else np.zeros(3)
        self.holes.append(_HoleLoop(loop, walls or [skin], centre, in_bend, countersink))

    # -- back onto the part -------------------------------------------------------------------------------

    def locate(self, point: Any) -> tuple[str, list[float]]:
        """The ref of the part's face nearest a point of the flat pattern, and the point on the part."""
        import build123d as bd

        p = np.asarray(point, dtype=float).reshape(1, 2)
        best, region = math.inf, None
        for candidate in self.regions:
            inside = plane.inside(p, [candidate.loop])[0]
            d = 0.0 if inside else plane.segments_distance(p, p, candidate.loop.a, candidate.loop.b)[0]
            if d < best:
                best, region = d, candidate
        if region is None:
            return self.part.ref("face", 1), [float(p[0, 0]), float(p[0, 1]), 0.0]
        at = region.to_part(p)[0]
        vector = bd.Vector(*[float(v) for v in at])
        reach = 1e-3 + (self.thickness or 0.0)
        if self._boxes is None:
            boxes = [face.bounding_box() for face in self.faces]
            self._boxes = (np.array([(b.min.X, b.min.Y, b.min.Z) for b in boxes]),
                           np.array([(b.max.X, b.max.Y, b.max.Z) for b in boxes]))
        lo, hi = self._boxes
        faces = np.array(region.faces)
        bound = np.linalg.norm(np.maximum(0.0, np.maximum(lo[faces - 1] - at, at - hi[faces - 1])), axis=1)
        # a point of the outline lies on a cut edge's face: the nearest of those within a thickness, else
        # the nearest face of all; faces whose boxes are farther than the best found are not measured
        best: dict[bool, tuple[float, int]] = {}
        for k in np.argsort(bound):
            a = int(faces[k])
            if best and bound[k] > min(value[0] for value in best.values()) and bound[k] > reach:
                break
            d = self.faces[a - 1].distance_to(vector)
            edge = a in self.edge_set and d <= reach
            if edge not in best or d < best[edge][0]:
                best[edge] = (d, a)
        nearest = (best.get(True) or best[False])[1]
        return self.ref(nearest), _xyz(at)


# --- the families --------------------------------------------------------------------------------------------


def _bend_item(analysis: _Analysis, bend: _Bend) -> dict[str, Any]:
    t = float(analysis.thickness)
    angle = bend.angle
    tangent = math.tan(math.radians(angle) / 2) if angle < 179.0 else None
    kind = "hem" if 175.0 <= angle <= 185.0 else "curl" if angle > 185.0 else "bend"
    lines = []
    for end in (0, 1):
        for radius in (bend.inside_radius, bend.outside_radius):
            a = bend.tangent_point(end, bend.w0, radius)
            b = bend.tangent_point(end, bend.w1, radius)
            lines.append([_xyz(a), _xyz(b)])
    middle = (bend.w0 + bend.w1) / 2
    xyz = bend.origin + bend.inside_radius * (math.cos(bend.phi0 + bend.span / 2) * bend.e1 +
                                              math.sin(bend.phi0 + bend.span / 2) * bend.e2) + middle * bend.axis
    setback = bend.outside_radius * tangent if tangent is not None else None
    return {
        "kind": kind, "inside_radius_mm": _r(bend.inside_radius), "outside_radius_mm": _r(bend.outside_radius),
        "thickness_mm": _r(bend.outside_radius - bend.inside_radius),
        "radius_to_thickness": _r(bend.inside_radius / t if t else None),
        "angle_deg": _r(angle), "included_angle_deg": _r(180.0 - angle), "angle_from": "span of the bend's cylinder",
        "flanges_angle_deg": _r(bend.normals_angle), "length_mm": _r(bend.w1 - bend.w0),
        "axis": _xyz(bend.axis), "axis_origin": _xyz(bend.origin + bend.w0 * bend.axis),
        "tangent_lines": lines, "k_factor": _r(bend.k), "k_factor_source": bend.k_source,
        "bend_allowance_mm": _r(bend.allowance),
        "bend_deduction_mm": _r(2 * setback - bend.allowance) if setback is not None else None,
        "flange_count": len(bend.flanges),
        "location": analysis.ref(bend.inner[0]), "faces": [analysis.ref(a) for a in bend.inner + bend.outer],
        "xyz": _xyz(xyz),
    }


def _frame_points(bend: _Bend, xs: np.ndarray, ws: np.ndarray) -> np.ndarray:
    origin, x, y = bend.frame
    return origin[None] + np.asarray(xs)[:, None] * x[None] + np.asarray(ws)[:, None] * y[None]


def _barrier(points: np.ndarray) -> plane.Loop:
    return plane.Loop(np.asarray(points), np.ones(len(points), bool))


def _tangent_barriers(analysis: _Analysis, skip: _Bend | None = None) -> list[plane.Loop]:
    found = []
    for bend in analysis.bends:
        if bend.frame is None or bend is skip:
            continue
        for x in (0.0, bend.allowance):
            found.append(_barrier(_frame_points(bend, np.array([x, x]), np.array([bend.w0, bend.w1]))))
    return found


def _flanges(analysis: _Analysis, outer: list[plane.Loop]) -> tuple[list[dict], dict[tuple[int, int], dict]]:
    items, by_side = [], {}
    t = float(analysis.thickness)
    for bend in analysis.bends:
        if bend.frame is None:
            continue
        barriers = outer + _tangent_barriers(analysis, skip=bend)
        span = bend.w1 - bend.w0
        ws = bend.w0 + span * (0.04 + 0.92 * np.linspace(0.0, 1.0, 11))
        tangent = math.tan(math.radians(bend.angle) / 2) if bend.angle < 179.0 else None
        eps = 1e-6 * max(1.0, t)
        for side, flange_number, x0, sign in (("parent", bend.parent, 0.0, -1.0),
                                              ("child", bend.child, bend.allowance, 1.0)):
            if flange_number is None:
                continue
            origins = _frame_points(bend, np.full(len(ws), x0 + sign * eps), ws)
            direction = np.repeat((sign * bend.frame[1])[None], len(ws), axis=0)
            hit, _, _ = plane.cast(origins, direction, barriers, skip=1e-9)
            lengths = hit[np.isfinite(hit)] + eps
            if not len(lengths):
                continue
            least, half = float(lengths.min()), float(np.median(lengths))
            inside = bend.inside_radius * tangent if tangent is not None else None
            outside = bend.outside_radius * tangent if tangent is not None else None
            flange = analysis.flanges[flange_number]
            item = {
                "bend": analysis.ref(bend.inner[0]), "side": side,
                "length_tangent_mm": _r(least), "length_tangent_half_mm": _r(half),
                "length_inside_mm": _r(least + inside) if inside is not None else None,
                "length_inside_half_mm": _r(half + inside) if inside is not None else None,
                "length_outside_mm": _r(least + outside) if outside is not None else None,
                "length_outside_half_mm": _r(half + outside) if outside is not None else None,
                "length_outside_minus_radius_mm": _r(least + outside - bend.inside_radius) if outside is not None else None,
                "stations": len(lengths), "location": analysis.ref(flange.faces[0]),
            }
            at = _frame_points(bend, np.array([x0 + sign * least / 2]), np.array([ws[len(ws) // 2]]))
            item["xyz"] = analysis.locate(at[0])[1]
            items.append(item)
            by_side[(bend.number, flange_number)] = item
    return items, by_side


def _channels(analysis: _Analysis, by_side: dict[tuple[int, int], dict]) -> list[dict]:
    items = []
    for flange in analysis.flanges:
        bends = [b for b in analysis.bends if flange.number in b.flanges and b.frame is not None]
        for i, first in enumerate(bends):
            for second in bends[i + 1:]:
                if abs(float(first.axis @ second.axis)) < _PARALLEL:
                    continue
                g1 = next((f for f in first.flanges if f != flange.number), None)
                g2 = next((f for f in second.flanges if f != flange.number), None)
                if g1 is None or g2 is None or g1 == g2:
                    continue
                if float(analysis.flanges[g1].normal @ analysis.flanges[g2].normal) > -0.9:
                    continue
                base = by_side.get((first.number, flange.number))
                side1, side2 = by_side.get((first.number, g1)), by_side.get((second.number, g2))
                if not base or not side1 or not side2 or base.get("length_outside_mm") is None:
                    continue
                if side1.get("length_outside_mm") is None or side2.get("length_outside_mm") is None:
                    continue
                tangent2 = math.tan(math.radians(second.angle) / 2) if second.angle < 179 else 0.0
                base_length = base["length_tangent_mm"] + first.outside_radius * math.tan(math.radians(first.angle) / 2) \
                    + second.outside_radius * tangent2
                flange_length = max(side1["length_outside_mm"], side2["length_outside_mm"])
                items.append({"base_length_mm": _r(base_length), "flange_length_mm": _r(flange_length),
                              "base_to_flange_ratio": _r(base_length / flange_length if flange_length else None),
                              "location": analysis.ref(flange.faces[0]), "bends": [analysis.ref(first.inner[0]),
                                                                                    analysis.ref(second.inner[0])],
                              "xyz": base.get("xyz")})
    return items


def _in_zone(bend: _Bend, point: np.ndarray) -> bool:
    """Whether a point of the flat pattern lies in a bend's strip."""
    if bend.frame is None:
        return False
    origin, x, y = bend.frame
    rel = np.asarray(point) - origin
    xs, ws = float(rel @ x), float(rel @ y)
    return -1e-9 <= xs <= bend.allowance + 1e-9 and bend.w0 - 1e-9 <= ws <= bend.w1 + 1e-9


def _reliefs(analysis: _Analysis, material: list[plane.Loop]) -> list[dict]:
    items = []
    t = float(analysis.thickness)
    eps = max(1e-4, 0.005 * t)
    for bend in analysis.bends:
        if bend.frame is None:
            continue
        _, x, y = bend.frame
        for end, w_end, out in (("start", bend.w0, -1.0), ("end", bend.w1, 1.0)):
            beyond = w_end + out * eps
            for side, flange_number, x_side, sign in (("parent", bend.parent, 0.0, -1.0),
                                                      ("child", bend.child, bend.allowance, 1.0)):
                if flange_number is None:
                    continue
                probe_flange = _frame_points(bend, np.array([x_side + sign * eps]), np.array([beyond]))
                probe_zone = _frame_points(bend, np.array([bend.allowance / 2]), np.array([beyond]))
                continues = plane.inside(np.vstack([probe_flange, probe_zone]), material)
                where = _frame_points(bend, np.array([x_side]), np.array([w_end]))[0]
                ref, xyz = analysis.locate(where)
                corner = any(_in_zone(other, point) for other in analysis.bends if other is not bend
                             for point in np.vstack([probe_flange, probe_zone]))
                item = {"bend": analysis.ref(bend.inner[0]), "end": end, "side": side,
                        "kind": "corner" if corner else "bend", "location": ref, "xyz": xyz}
                if continues.any():
                    item.update(needed=True, present=False, width_mm=0.0, depth_tangent_mm=0.0,
                                depth_centerline_mm=0.0,
                                depth_centerline_minus_radius_mm=_r(-bend.inside_radius),
                                detail="another bend starts where this one ends: no corner relief" if corner else
                                "the flange's material runs on past the bend's end: no relief")
                    items.append(item)
                    continue
                hit, _, _ = plane.cast(probe_flange, (out * y)[None], material, skip=1e-9)
                if not np.isfinite(hit[0]) or hit[0] > 50.0 * t + 2 * (bend.w1 - bend.w0):
                    continue  # the flange ends with the bend: nothing to relieve
                width = float(hit[0]) + eps
                mid = _frame_points(bend, np.array([bend.allowance / 2]), np.array([w_end + out * width / 2]))
                depth, _, _ = plane.cast(mid, (sign * x)[None], material, skip=1e-9)
                depth_center = float(depth[0]) if np.isfinite(depth[0]) else None
                item.update(needed=True, present=True, width_mm=_r(width),
                            depth_centerline_mm=_r(depth_center),
                            depth_tangent_mm=_r(depth_center - bend.allowance / 2) if depth_center is not None else None,
                            depth_centerline_minus_radius_mm=_r(depth_center - bend.inside_radius)
                            if depth_center is not None else None)
                items.append(item)
    return items


def _holes(analysis: _Analysis, outer: list[plane.Loop]) -> tuple[list[dict], list[dict], list[dict]]:
    holes, spacing, to_bend = [], [], []
    for hole in analysis.holes:
        loop = hole.loop
        if getattr(loop, "through_diameter", None):
            kind, size, length = "round", loop.through_diameter, loop.through_diameter
        elif loop.circle is not None:
            kind, size, length = "round", 2.0 * loop.circle[2], 2.0 * loop.circle[2]
        else:
            size, length, _ = plane.feret(loop.points)
            kind = "slot" if length > 1.2 * size and not loop.straight.all() else "cutout"
        edge = min((plane.distance(loop, other)[0] for other in outer), default=None)
        item = {"kind": kind, "size_mm": _r(size), "diameter_mm": _r(size) if kind == "round" else None,
                "length_mm": _r(length), "edge_distance_mm": _r(edge), "in_bend": hole.in_bend,
                "countersunk": hole.countersink is not None, "countersink_diameter_mm": _r(hole.countersink),
                "location": analysis.ref(hole.location_faces[0]),
                "faces": [analysis.ref(a) for a in hole.location_faces], "xyz": _xyz(hole.xyz)}
        holes.append(item)
        best = None
        for bend in analysis.bends:
            if bend.frame is None:
                continue
            origin, x, y = bend.frame
            rel = loop.points - origin
            xs = rel @ x
            local = np.column_stack([xs, rel @ y])
            segment = lambda x0: (np.array([[x0, bend.w0]]), np.array([[x0, bend.w1]]))  # noqa: E731
            la, lb = local, np.roll(local, -1, axis=0)
            if xs.max() <= 1e-9:
                d_tangent = plane.segments_distance(la, lb, *segment(0.0))[0]
            elif xs.min() >= bend.allowance - 1e-9:
                d_tangent = plane.segments_distance(la, lb, *segment(bend.allowance))[0]
            else:
                inside_ws = (local[:, 1] >= bend.w0) & (local[:, 1] <= bend.w1)
                d_tangent = 0.0 if inside_ws.any() else min(plane.segments_distance(la, lb, *segment(0.0))[0],
                                                             plane.segments_distance(la, lb, *segment(bend.allowance))[0])
            d_center = plane.segments_distance(la, lb, *segment(bend.allowance / 2))[0]
            if best is None or d_tangent < best[0]:
                best = (d_tangent, d_center, bend)
        if best is not None:
            d_tangent, d_center, bend = best
            tangent = math.tan(math.radians(bend.angle) / 2) if bend.angle < 179.0 else None
            outside = d_tangent + bend.outside_radius * tangent if tangent is not None else None
            to_bend.append({
                "bend": analysis.ref(bend.inner[0]), "distance_tangent_mm": _r(d_tangent),
                "distance_centerline_mm": _r(d_center),
                "distance_inside_mm": _r(d_tangent + bend.inside_radius * tangent) if tangent is not None else None,
                "distance_outside_mm": _r(outside),
                "distance_outside_minus_radius_mm": _r(outside - bend.inside_radius) if outside is not None else None,
                "inside_radius_mm": _r(bend.inside_radius), "bend_angle_deg": _r(bend.angle),
                "location": item["location"], "xyz": item["xyz"]})
    pairs: dict[tuple[int, int], dict] = {}
    for i, first in enumerate(analysis.holes):
        nearest = None
        for j, second in enumerate(analysis.holes):
            if i == j:
                continue
            d = plane.distance(first.loop, second.loop)[0]
            if nearest is None or d < nearest[0]:
                nearest = (d, j)
        if nearest is not None:
            key = (min(i, nearest[1]), max(i, nearest[1]))
            pairs.setdefault(key, {"distance_mm": _r(nearest[0]), "location": holes[key[0]]["location"],
                                   "other": holes[key[1]]["location"], "xyz": holes[key[0]]["xyz"]})
    spacing = sorted(pairs.values(), key=lambda item: item["distance_mm"])
    return holes, spacing, to_bend


def _outline_features(analysis: _Analysis | None, loops: list[plane.Loop], thickness: float | None,
                      locate: Callable[[Any], tuple[str, list[float]]]) -> dict[str, list[dict]]:
    """Notches, tabs, webs and gaps of a flat outline (``loops``: outer loops labelled ``outer``, holes
    ``hole``), each located by ``locate`` (a flat point to a ref and a point)."""
    least = max(1e-3, 0.01 * (thickness or 0.1))
    notches, tabs, webs, gaps = [], [], [], []
    outer = [loop for loop in loops if loop.label == "outer"]
    for loop in outer:
        for pocket in plane.pockets(loop, least=least):
            ref, xyz = locate(pocket.deepest)
            notches.append({"width_mm": _r(pocket.width), "length_mm": _r(pocket.depth),
                            "length_to_width": _r(pocket.depth / pocket.width), "area_mm2": _r(pocket.area, 3),
                            "location": ref, "xyz": xyz})
        for tab in plane.tabs(loop, material_left=plane.area(loop) > 0):
            ref, xyz = locate(tab.tip)
            tabs.append({"width_mm": _r(tab.width), "length_mm": _r(tab.length),
                         "length_to_width": _r(tab.length / tab.width), "location": ref, "xyz": xyz})
    spacing = max(0.05, min(0.5, (thickness or 1.0) / 4))
    for width in plane.widths(loops, [loop.label == "outer" for loop in loops], spacing=spacing):
        a, b = width.loops
        if width.kind == "material":
            if a != b or loops[a].label != "outer":
                continue  # between two contours: hole_to_edge and hole_spacing measure it
            ref, xyz = locate(width.start)
            webs.append({"width_mm": _r(width.width), "location": ref, "xyz": xyz,
                         "across": [_r(v) for v in (*width.start, *width.end)]})
        else:
            ref, xyz = locate(width.start)
            gaps.append({"width_mm": _r(width.width), "location": ref, "xyz": xyz,
                         "between": "one contour" if a == b else "two contours"})
    return {"notches": notches, "tabs": tabs, "webs": webs, "gaps": gaps}


def _capped(items: list[dict], key: str | None, reverse: bool = False) -> list[dict]:
    if key is not None:
        items = sorted(items, key=lambda item: (item.get(key) is None, item.get(key) if item.get(key) is not None
                                                else 0.0), reverse=reverse)
    return items[:ITEM_CAP]


def _part(part: brep.Part, options: dict[str, Any]) -> dict[str, Any]:
    """Every family of one part: a list of items, or the exception that stopped it."""
    out: dict[str, Any] = {}
    analysis = _Analysis(part, options)
    analysis.probe()
    analysis.classify()
    t = analysis.thickness
    box = sorted([part.shape.bounding_box().size.X, part.shape.bounding_box().size.Y,
                  part.shape.bounding_box().size.Z])
    largest = max(analysis.skins, key=lambda a: analysis.areas[a - 1]) if analysis.skins else 1
    item: dict[str, Any] = {
        "name": part.name, "thickness_mm": _r(t), "given_thickness_mm": options.get("thickness"),
        "sheet_area_fraction": _r(analysis.sheet_fraction), "skin_faces": len(analysis.skins),
        "not_sheet_faces": len(analysis.not_sheet), "box_mm": [_r(v) for v in box[::-1]],
        "box_short_mm": _r(box[1]), "location": part.ref("face", largest),
    }
    is_sheet = t is not None and bool(analysis.skins) and analysis.sheet_fraction >= 0.5
    if t is not None and is_sheet:
        if t > 0.25 * box[1]:
            is_sheet = False
            analysis.why = f"its {t:.4g} mm thickness is no sheet's against its {box[1]:.4g} mm width"
    elif t is not None:
        analysis.why = analysis.why or f"only {100 * analysis.sheet_fraction:.0f}% of its area is a {t:.4g} mm sheet"
    item["is_sheet"] = is_sheet
    if analysis.why:
        item["why"] = analysis.why
    out["not_sheet"] = analysis.not_sheet
    out["parts"] = [item]
    if not is_sheet:
        for family in FAMILIES:
            out.setdefault(family, [])
        return out
    try:
        analysis.find_bends()
        out["bends"] = [_bend_item(analysis, bend) for bend in analysis.bends]
    except Exception as error:  # noqa: BLE001 - one family's failure is reported, the rest measured
        for family in ("bends", "flanges", "channels", "reliefs", "hems", "curls", "holes", "hole_spacing",
                       "hole_to_bend", "notches", "tabs", "webs", "gaps"):
            out[family] = error
        return out
    out["curls"] = [{"inside_radius_mm": b["inside_radius_mm"], "outside_radius_mm": b["outside_radius_mm"],
                     "angle_deg": b["angle_deg"], "location": b["location"], "xyz": b["xyz"]}
                    for b in out["bends"] if b["kind"] == "curl"]
    item["bend_count"] = len(analysis.bends)
    item["flange_count"] = len(analysis.flanges)
    try:
        analysis.unfold()
    except Exception as error:  # noqa: BLE001
        for family in ("flanges", "channels", "reliefs", "hems", "holes", "hole_spacing", "hole_to_bend",
                       "notches", "tabs", "webs", "gaps"):
            out[family] = error
        item["unfold_note"] = f"the part did not unfold: {error}"
        return out
    item["unfold_note"] = analysis.unfold_note or None
    outer = [loop for loop in analysis.flat_loops if loop.label == "outer"]
    if outer:
        points = np.vstack([loop.points for loop in outer])
        long, short, angle = plane.min_rectangle(points)
        item.update(flat_length_mm=_r(long), flat_width_mm=_r(short),
                    flat_area_mm2=_r(sum(abs(plane.area(loop)) for loop in analysis.flat_loops
                                         if loop.label == "outer") -
                                     sum(abs(plane.area(loop)) for loop in analysis.flat_loops if loop.label == "hole"), 3),
                    flat_overlap_mm2=_r(analysis.overlap, 3) or None,
                    neutral_area_ratio=_r(float(part.shape.volume) / t / analysis.flat.area
                                          if analysis.flat is not None and analysis.flat.area > 0 else None, 5),
                    flat_bend_lines=[[_r(v, 3) for v in (*_frame_points(b, np.array([b.allowance / 2] * 2),
                                                                       np.array([b.w0, b.w1]))[0],
                                                         *_frame_points(b, np.array([b.allowance / 2] * 2),
                                                                        np.array([b.w0, b.w1]))[1])]
                                     for b in analysis.bends if b.frame is not None])
    families: dict[str, Callable[[], Any]] = {}
    flange_sides: dict[tuple[int, int], dict] = {}

    def flanges() -> list[dict]:
        found, sides = _flanges(analysis, outer)
        flange_sides.update(sides)
        return found

    material = analysis.flat_loops
    families["flanges"] = flanges
    families["channels"] = lambda: _channels(analysis, flange_sides)
    families["reliefs"] = lambda: _reliefs(analysis, material)

    def hems() -> list[dict]:
        found = []
        for bend, record in zip(analysis.bends, out.get("bends") or []):
            if record["kind"] != "hem":
                continue
            lengths = [flange_sides[(bend.number, f)]["length_tangent_mm"] for f in bend.flanges
                       if (bend.number, f) in flange_sides]
            found.append({"inside_diameter_mm": _r(2 * bend.inside_radius), "gap_mm": _r(2 * bend.inside_radius),
                          "return_length_mm": _r(min(lengths)) if lengths else None, "angle_deg": record["angle_deg"],
                          "location": record["location"], "xyz": record["xyz"]})
        return found

    families["hems"] = hems
    hole_parts: dict[str, list[dict]] = {}

    def holes(name: str) -> list[dict]:
        if not hole_parts:
            found, spacing, to_bend = _holes(analysis, outer)
            hole_parts.update(holes=found, hole_spacing=spacing, hole_to_bend=to_bend)
        return hole_parts[name]

    for name in ("holes", "hole_spacing", "hole_to_bend"):
        families[name] = (lambda name=name: holes(name))
    features: dict[str, list[dict]] = {}

    def outline(name: str) -> list[dict]:
        if not features:
            features.update(_outline_features(analysis, analysis.flat_loops, t, analysis.locate))
        return features[name]

    for name in ("notches", "tabs", "webs", "gaps"):
        families[name] = (lambda name=name: outline(name))
    for name, run in families.items():
        try:
            out[name] = run()
        except Exception as error:  # noqa: BLE001 - one family's failure is reported, the rest measured
            out[name] = error
    return out


_SORT = {"not_sheet": ("deviation_mm", True), "bends": ("radius_to_thickness", False),
         "flanges": ("length_tangent_mm", False), "reliefs": ("width_mm", False), "holes": ("size_mm", False),
         "hole_spacing": ("distance_mm", False), "hole_to_bend": ("distance_tangent_mm", False),
         "notches": ("width_mm", False), "tabs": ("width_mm", False), "webs": ("width_mm", False),
         "gaps": ("width_mm", False), "channels": ("base_to_flange_ratio", False), "hems": ("inside_diameter_mm", False),
         "curls": ("inside_radius_mm", False), "parts": (None, False)}


def measure(document: brep.Document, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The sheet report of ``document``: facts alone, every family's ``items`` at a ref."""
    if not document.parts:
        raise Unmeasured("empty_document", "the document holds no part to measure")
    results = []
    for part in document.parts:
        try:
            results.append(_part(part, options))
        except Exception as error:  # noqa: BLE001 - a part that cannot be measured fails its families alone
            results.append({family: error for family in FAMILIES})
    report: dict[str, Any] = {}
    partial = []
    for family in FAMILIES:
        items: list[dict] = []
        failure = None
        for part, result in zip(document.parts, results):
            value = result.get(family, [])
            if isinstance(value, Exception):
                failure = failure or f"{part.owner or part.name}: {type(value).__name__}: {value}"
                continue
            items.extend(value)
        if failure is not None:
            report[family] = {"error": failure}
            partial.append(family)
            continue
        key, reverse = _SORT.get(family, (None, False))
        report[family] = {"items": _capped(items, key, reverse), "count": len(items)}
    report["bent"] = bool((report.get("bends") or {}).get("items"))
    report["partial"] = bool(partial)
    report["partial_sections"] = partial
    return report


# --- the public unfold -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Unfolded:
    """A part unfolded: its flat pattern (``face``, in the XY plane), each bend's centre line in it
    (``bend_lines``) and its tangent lines, the thickness and the K-factor of each bend."""

    face: Any
    bend_lines: tuple[Any, ...]
    tangent_lines: tuple[Any, ...]
    thickness: float
    k_factors: tuple[float, ...]
    note: str = ""


def _unfolded(shape: Any, thickness: float | None, k_factor: float | None, material: str | None,
              rules: str | None) -> list[Unfolded]:
    import build123d as bd

    from cad._internal.dfm import materials

    options = {"thickness": thickness, "k_factor": k_factor, "material": materials.resolve(material),
               "rules": rules}
    if k_factor is not None and not 0.0 < float(k_factor) <= 0.5:
        raise ValueError(f"k_factor is the neutral axis's place in the thickness, above 0 and at most 0.5, "
                         f"not {k_factor}")
    found = []
    for part in brep.parts_of(shape).parts:
        analysis = _Analysis(part, options)
        analysis.probe()
        analysis.classify()
        if analysis.thickness is None or not analysis.skins:
            raise ValueError(f"{part.name or 'the shape'} is not sheet metal: {analysis.why or 'no thickness'}")
        if thickness is not None and abs(analysis.thickness - float(thickness)) > max(0.01, 0.005 * float(thickness)):
            raise ValueError(f"{part.name or 'the shape'} is {analysis.thickness:.4g} mm thick, not {float(thickness):g}")
        analysis.find_bends()
        analysis.unfold()
        if analysis.flat is None:
            raise ValueError(f"{part.name or 'the shape'} did not unfold: {analysis.unfold_note}")
        lines, tangents = [], []
        for bend in analysis.bends:
            if bend.frame is None:
                continue
            for x, into in ((bend.allowance / 2, lines), (0.0, tangents), (bend.allowance, tangents)):
                a, b = _frame_points(bend, np.array([x, x]), np.array([bend.w0, bend.w1]))
                into.append(bd.Edge.make_line((float(a[0]), float(a[1]), 0.0), (float(b[0]), float(b[1]), 0.0)))
        found.append(Unfolded(analysis.flat, tuple(lines), tuple(tangents), float(analysis.thickness),
                              tuple(bend.k for bend in analysis.bends), analysis.unfold_note))
    return found


def unfold(shape: Any, *, thickness: float | None = None, k_factor: float | None = None,
           material: str | None = None, rules: str | None = None, bend_lines: bool = False) -> Any:
    """The flat pattern of a bent sheet metal part (a build123d ``Shape``): exact 2D geometry in the XY
    plane, ready to return from a ``@dxf`` model.

    Each flange is rotated flat about its bend and the bend replaced by a strip as wide as its bend
    allowance, ``BA = angle * (inside radius + K * thickness)``; holes and arcs stay exact. ``thickness``
    (mm) is checked against the part's measured one; ``k_factor`` is the neutral axis's place in the
    thickness (default: Hubs's generic chart by ``material`` and each bend's radius, or SendCutSend's
    calculator with ``rules="sendcutsend"``). One part gives its flat ``Face`` (or a ``Compound`` of the
    pieces that do not join); several parts, a ``Compound`` of each one's. With ``bend_lines`` the result
    is a ``Compound`` of the cut outline labelled ``CUT`` and the bends' centre lines labelled ``BEND``: a
    DXF writes each label as its own layer. ``ValueError`` for a shape that is not one thickness of sheet.
    """
    import build123d as bd

    found = _unfolded(shape, thickness, k_factor, material, rules)
    flats = [item.face for item in found]
    cut = flats[0] if len(flats) == 1 else bd.Compound(children=flats)
    if not bend_lines:
        return cut
    cut.label = "CUT"
    lines = [line for item in found for line in item.bend_lines]
    bends = bd.Compound(children=lines) if lines else bd.Compound()
    bends.label = "BEND"
    return bd.Compound(children=[cut, bends])
