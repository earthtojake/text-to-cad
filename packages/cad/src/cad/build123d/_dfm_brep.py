"""Exact geometry for the manufacturing checks: a document's parts, their faces and edges, read and measured
on the B-rep (OCP), never on a mesh.

**The parts.** A STEP or an xbf is read by the engine's own loader (``cad.engine.document.Loaded``), so a
part, its faces and their ordinals are the ones ``cad <type> inspect`` names: a finding's location is a ref
in its grammar (``plate/face 7``; ``bracket/face 3`` in a document of one part, under its name), which
``cad xbf inspect DOC REF`` resolves to the very face. A document the engine holds (its id, a model's
handle) is exported by the engine to an xbf in a temporary folder first. A live shape
(``cad.build123d.cnc(shape)``) is read by its labels, as the engine would name its document. Each part is
measured once, placed where its first occurrence stands; its other occurrences are counted.

**The measures.** A face's surface (``surface``: a plane's normal, a cylinder's or a cone's axis and
radius, which way the material lies); an edge between two faces (``edges``: concave or convex, the angle
inside the material, smooth where the faces are tangent); exact rays (``Rays``: the first hit, or every
crossing of a line); points sampled on a face with their outward normals (``samples``); the wall
thickness under a point (``Rays.thickness``); a point's place inside or outside a solid (``inside``).
Lengths are millimetres, angles degrees.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np

from cad._internal.dfm import Unmeasured

__all__ = ["Document", "Edge", "Part", "Rays", "Sample", "Surface", "edges", "inside", "parts_of", "read",
           "samples", "surface"]

# Two faces meeting at an edge within this many degrees of each other are tangent: a fillet's join.
SMOOTH_DEG = 1.0


@dataclass
class Part:
    """One part of a document: its geometry placed where its first occurrence stands, its canonical owner
    (the ref's text before ``/face N``) and its faces in their ordinals' order (1-based)."""

    name: str
    owner: str
    shape: Any                       # a build123d Shape, placed
    occurrences: int = 1
    paths: tuple[str, ...] = ()
    face_names: dict[int, str] = field(default_factory=dict)
    _faces: list[Any] | None = field(default=None, repr=False)
    _edges: list[Any] | None = field(default=None, repr=False)
    _face_map: Any = field(default=None, repr=False)
    _edge_map: Any = field(default=None, repr=False)

    def ref(self, kind: str, ordinal: int) -> str:
        """The ref of one element: ``plate/face 7`` (``face 7`` where the part is an unlabelled root)."""
        element = f"{kind} {ordinal}"
        return f"{self.owner}/{element}" if self.owner else element

    def _maps(self) -> None:
        if self._face_map is not None:
            return
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

        faces, edges = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.shape.wrapped, TopAbs_FACE, faces)
        TopExp.MapShapes_s(self.shape.wrapped, TopAbs_EDGE, edges)
        self._face_map, self._edge_map = faces, edges

    def faces(self) -> list[Any]:
        """Its faces as build123d ``Face``s, ``faces()[n - 1]`` the face ``face n`` names."""
        if self._faces is None:
            import build123d as bd
            from OCP.TopoDS import TopoDS

            self._maps()
            self._faces = [bd.Face(TopoDS.Face(self._face_map.FindKey(index)))
                           for index in range(1, self._face_map.Extent() + 1)]
        return self._faces

    def edges(self) -> list[Any]:
        """Its edges as build123d ``Edge``s, ``edges()[n - 1]`` the edge ``edge n`` names."""
        if self._edges is None:
            import build123d as bd
            from OCP.TopoDS import TopoDS

            self._maps()
            self._edges = [bd.Edge(TopoDS.Edge(self._edge_map.FindKey(index)))
                           for index in range(1, self._edge_map.Extent() + 1)]
        return self._edges

    def face_ordinal(self, face: Any) -> int:
        """The ordinal of a face of this part (a build123d ``Face`` or a ``TopoDS_Face``), 0 for none."""
        self._maps()
        return int(self._face_map.FindIndex(getattr(face, "wrapped", face)))

    def edge_ordinal(self, edge: Any) -> int:
        self._maps()
        return int(self._edge_map.FindIndex(getattr(edge, "wrapped", edge)))

    def solids(self) -> list[Any]:
        return list(self.shape.solids())

    def facts(self) -> dict[str, Any]:
        """What a report says of the part itself: its name, its ref's owner, its box, volume and counts."""
        box = self.shape.bounding_box()
        return {"name": self.name, "owner": self.owner, "occurrences": self.occurrences,
                "bbox_mm": [round(box.size.X, 4), round(box.size.Y, 4), round(box.size.Z, 4)],
                "bbox_min_mm": [round(box.min.X, 4), round(box.min.Y, 4), round(box.min.Z, 4)],
                "volume_mm3": round(float(self.shape.volume), 4), "area_mm2": round(float(self.shape.area), 4),
                "solid_count": len(self.solids()), "face_count": len(self.faces()),
                "edge_count": len(self.edges())}


@dataclass
class Document:
    """A document's parts, as the engine reads it."""

    name: str
    parts: list[Part]
    source: str | None = None

    def facts(self) -> dict[str, Any]:
        return {"name": self.name, "part_count": len(self.parts),
                "occurrence_count": sum(part.occurrences for part in self.parts), "units": "mm"}


# --- reading ---------------------------------------------------------------------------------------------


def _trsf(matrix: list[float]) -> Any:
    """A column-major 4x4 matrix (``Instance.matrix``) as a ``TopLoc_Location``."""
    from OCP.gp import gp_Trsf
    from OCP.TopLoc import TopLoc_Location

    m = [[matrix[column * 4 + row] for column in range(4)] for row in range(4)]
    trsf = gp_Trsf()
    trsf.SetValues(m[0][0], m[0][1], m[0][2], m[0][3], m[1][0], m[1][1], m[1][2], m[1][3],
                   m[2][0], m[2][1], m[2][2], m[2][3])
    return TopLoc_Location(trsf)


def _loaded(loaded: Any) -> Document:
    import build123d as bd

    from cad.engine import refs

    structure = loaded.structure()
    root = refs.structure_tree(structure)
    first: dict[int, Part] = {}
    order: list[Part] = []
    for node in root.parts():
        payload = node.payload
        prototype = int(payload["prototype"])
        path = refs.path_text(root, node)
        if prototype in first:
            first[prototype].occurrences += 1
            first[prototype].paths += (path,)
            continue
        proto = loaded.prototypes[prototype]
        instance = loaded.instances[int(payload["instance"])]
        placed = bd.Shape.cast(proto.shape.Moved(_trsf(instance.matrix)))
        part = Part(name=proto.name, owner=refs.owner_text(root, node), shape=placed, paths=(path,),
                    face_names=dict(proto.face_names))
        first[prototype] = part
        order.append(part)
    return Document(name=loaded.name, parts=order, source=str(loaded.path))


def read(document_type: str, source: Any) -> Document:
    """The parts of a STEP or an xbf (a path), or of a document the engine holds (its id or handle)."""
    from cad.engine.document import Loaded
    from cad.engine.ids import is_id

    if isinstance(source, (str, os.PathLike)) and not is_id(os.fspath(source)):
        path = Path(os.fspath(source)).expanduser().resolve()
        try:
            return _loaded(Loaded(path))
        except Exception as error:  # noqa: BLE001 - a file that does not read is the check's answer
            raise Unmeasured("document_unreadable", f"failed to read {path.name}: {error}") from None
    from cad.engine.api import export

    with tempfile.TemporaryDirectory(prefix="cad-check-") as folder:
        written = Path(folder) / "document.xbf"
        try:
            export(source, written, progress=False)  # the engine writes the document it holds
            return _loaded(Loaded(written))
        except Exception as error:  # noqa: BLE001
            raise Unmeasured("document_unreadable", f"failed to read the document: {error}") from None


def parts_of(shape: Any, name: str | None = None) -> Document:
    """A live build123d shape's parts, read by its labels as the engine would name its document: each leaf
    of its compound tree a part, placed where it stands."""
    import build123d as bd

    from cad.engine import refs

    leaves: list[tuple[Any, Any]] = []

    def visit(node: Any) -> dict[str, Any]:
        children = list(getattr(node, "children", ()) or ())
        entry: dict[str, Any] = {"name": str(getattr(node, "label", "") or "")}
        if children:
            entry["children"] = [visit(child) for child in children]
        else:
            entry["prototype"] = len(leaves)
            leaves.append((node, getattr(node, "global_location", None)))
        return entry

    tree = visit(shape)
    if not tree["name"]:
        tree["name"] = name or ""
    root = refs.structure_tree({"tree": tree})
    parts = []
    for node in root.parts():
        leaf, where = leaves[int(node.payload["prototype"])]
        placed = leaf if where is None or node is root else bd.Shape.cast(leaf.wrapped.Located(where.wrapped))
        parts.append(Part(name=node.label, owner=refs.owner_text(root, node), shape=placed,
                          paths=(refs.path_text(root, node),)))
    return Document(name=tree["name"], parts=parts)


# --- surfaces --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Surface:
    """A face's surface. ``kind``: plane, cylinder, cone, sphere, torus, bspline, revolution, extrusion,
    offset or other. A plane's ``normal`` is the outward one (the face's orientation applied); a
    cylinder's, cone's, sphere's or torus's ``axis`` (a unit vector) and ``origin``, ``radius`` (a cone's
    at ``origin``), ``half_angle_deg`` (a cone's), ``minor_radius`` (a torus's) and ``concave``: True where
    the material lies outside the surface -- a hole, an internal fillet -- False where it lies inside -- a
    boss, an outside round -- None where it cannot be told."""

    kind: str
    normal: tuple[float, float, float] | None = None
    origin: tuple[float, float, float] | None = None
    axis: tuple[float, float, float] | None = None
    radius: float | None = None
    half_angle_deg: float | None = None
    minor_radius: float | None = None
    concave: bool | None = None

    def as_data(self) -> dict[str, Any]:
        return {key: (list(value) if isinstance(value, tuple) else value) for key, value in self.__dict__.items()
                if value is not None}


def _xyz(value: Any) -> tuple[float, float, float]:
    return (float(value.X()), float(value.Y()), float(value.Z()))


def _kinds() -> dict[Any, str]:
    from OCP.GeomAbs import (GeomAbs_BezierSurface, GeomAbs_BSplineSurface, GeomAbs_Cone, GeomAbs_Cylinder,
                             GeomAbs_OffsetSurface, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_SurfaceOfExtrusion,
                             GeomAbs_SurfaceOfRevolution, GeomAbs_Torus)

    return {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder", GeomAbs_Cone: "cone", GeomAbs_Sphere: "sphere",
            GeomAbs_Torus: "torus", GeomAbs_BSplineSurface: "bspline", GeomAbs_BezierSurface: "bspline",
            GeomAbs_SurfaceOfRevolution: "revolution", GeomAbs_SurfaceOfExtrusion: "extrusion",
            GeomAbs_OffsetSurface: "offset"}


def _mid_uv(face: Any) -> tuple[float, float]:
    from OCP.BRepTools import BRepTools

    umin, umax, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
    return (umin + umax) / 2.0, (vmin + vmax) / 2.0


def point_normal(face: Any, u: float, v: float, props: Any = None) -> tuple[np.ndarray, np.ndarray]:
    """The point at ``(u, v)`` of ``face`` and its outward unit normal (the face's orientation applied).
    ``props``: the face's ``BRepGProp_Face``, made once by a caller that asks many points of one face."""
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.gp import gp_Pnt, gp_Vec

    props = props if props is not None else BRepGProp_Face(face.wrapped)
    point, normal = gp_Pnt(), gp_Vec()
    props.Normal(u, v, point, normal)
    length = normal.Magnitude()
    n = np.array(_xyz(normal)) / length if length > 1e-300 else np.zeros(3)
    return np.array(_xyz(point)), n


def surface(face: Any) -> Surface:
    """The surface of a face (see ``Surface``)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    adaptor = BRepAdaptor_Surface(face.wrapped, True)
    kind = _kinds().get(adaptor.GetType(), "other")
    if kind == "plane":
        u, v = _mid_uv(face)
        _, normal = point_normal(face, u, v)
        origin = _xyz(adaptor.Plane().Location())
        return Surface("plane", normal=tuple(float(value) for value in normal), origin=origin)  # type: ignore[arg-type]
    if kind in ("cylinder", "cone", "sphere", "torus"):
        geometry = {"cylinder": adaptor.Cylinder, "cone": adaptor.Cone, "sphere": adaptor.Sphere,
                    "torus": adaptor.Torus}[kind]()
        if kind == "sphere":
            origin = _xyz(geometry.Location())
            axis = _xyz(geometry.Position().Direction())
        else:
            origin = _xyz(geometry.Axis().Location())
            axis = _xyz(geometry.Axis().Direction())
        radius = float(geometry.MajorRadius() if kind == "torus" else geometry.Radius() if kind != "cone"
                       else geometry.RefRadius())
        u, v = _mid_uv(face)
        point, normal = point_normal(face, u, v)
        o, a = np.array(origin), np.array(axis)
        if kind == "sphere":
            radial = point - o
        elif kind == "torus":
            along = point - o
            ring = along - a * float(along @ a)
            ring = ring / (np.linalg.norm(ring) or 1.0) * radius
            radial = point - (o + ring)
        else:
            along = point - o
            radial = along - a * float(along @ a)
        size = float(np.linalg.norm(radial))
        concave = None if size < 1e-12 else bool(float(normal @ (radial / size)) < 0.0)
        return Surface(kind, origin=origin, axis=axis, radius=radius,
                       half_angle_deg=math.degrees(geometry.SemiAngle()) if kind == "cone" else None,
                       minor_radius=float(geometry.MinorRadius()) if kind == "torus" else None, concave=concave)
    return Surface(kind)


# --- edges -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Edge:
    """An edge between two faces of a part: their ordinals, whether the material's angle there is over 180
    degrees (``concave``: an internal corner) or under (convex: an outside one), that angle, and
    ``smooth`` where the faces are tangent (a fillet's join: neither corner)."""

    ordinal: int
    faces: tuple[int, int]
    concave: bool
    smooth: bool
    angle_deg: float          # the material's angle: 90 at a box's edge, 270 at a pocket's corner
    length: float
    midpoint: tuple[float, float, float]
    tangent: tuple[float, float, float]


def _orientations(face: Any) -> list[tuple[Any, Any]]:
    """The edges of a face as it bounds them, each with its orientation in the face."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    found = []
    explorer = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
    while explorer.More():
        current = explorer.Current()
        found.append((current, current.Orientation()))
        explorer.Next()
    return found


def _in_face_orientation(face: Any, edge: Any, walked: list[tuple[Any, Any]] | None = None) -> Any:
    """The orientation of ``edge`` in ``face`` (``walked``: the face's ``_orientations``, made once)."""
    for current, orientation in walked if walked is not None else _orientations(face):
        if current.IsSame(edge.wrapped):
            return orientation
    return None


def _edge_point(edge: Any) -> tuple[float, np.ndarray, np.ndarray]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.gp import gp_Pnt, gp_Vec

    curve = BRepAdaptor_Curve(edge.wrapped)
    t = (curve.FirstParameter() + curve.LastParameter()) / 2.0
    point, tangent = gp_Pnt(), gp_Vec()
    curve.D1(t, point, tangent)
    size = tangent.Magnitude()
    return t, np.array(_xyz(point)), (np.array(_xyz(tangent)) / size if size > 1e-300 else np.zeros(3))


def _normal_on(face: Any, edge: Any, t: float) -> np.ndarray:
    from OCP.BRepAdaptor import BRepAdaptor_Curve2d

    uv = BRepAdaptor_Curve2d(edge.wrapped, face.wrapped).Value(t)
    return point_normal(face, uv.X(), uv.Y())[1]


def edges(part: Part) -> list[Edge]:
    """Every edge of ``part`` that two of its faces share (a seam, which one face meets twice, is none)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.collections import (
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape)

    import build123d as bd

    ancestry = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(part.shape.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestry)
    found: list[Edge] = []
    walked: dict[int, list[tuple[Any, Any]]] = {}  # each face's edges walked once, not once an edge
    for index in range(1, ancestry.Extent() + 1):
        listed = ancestry.FindFromIndex(index)  # iterating an OCCT list from Python costs milliseconds an item
        owners = ([] if listed.Size() == 0 else [listed.First()] if listed.Size() == 1
                  else [listed.First(), listed.Last()] if listed.Size() == 2 else list(listed))
        distinct: list[Any] = []
        for owner in owners:
            if not any(owner.IsSame(other) for other in distinct):
                distinct.append(owner)
        if len(distinct) != 2:
            continue
        edge = bd.Edge(ancestry.FindKey(index))
        if edge.length < 1e-9:
            continue
        a, b = (bd.Face(face) for face in distinct)
        try:
            t, point, tangent = _edge_point(edge)
            na, nb = _normal_on(a, edge, t), _normal_on(b, edge, t)
        except Exception:  # noqa: BLE001 - a degenerate edge has no angle to give
            continue
        key = part.face_ordinal(a)
        if key not in walked:
            walked[key] = _orientations(a)
        orientation = _in_face_orientation(a, edge, walked[key])
        along = -tangent if orientation == TopAbs_REVERSED else tangent
        into_a = np.cross(na, along)  # the material of a face lies to the left of its edges, seen from outside
        between = math.degrees(math.acos(max(-1.0, min(1.0, float(na @ nb)))))
        smooth = between < SMOOTH_DEG
        concave = (not smooth) and float(nb @ into_a) > 0.0
        angle = 180.0 + between if concave else 180.0 - between
        found.append(Edge(part.edge_ordinal(edge), (part.face_ordinal(a), part.face_ordinal(b)), concave, smooth,
                          angle, float(edge.length), tuple(float(x) for x in point),  # type: ignore[arg-type]
                          tuple(float(x) for x in tangent)))  # type: ignore[arg-type]
    return found


# --- rays and points -------------------------------------------------------------------------------------


class Rays:
    """Exact rays against a shape: the first face a ray hits, every crossing of a line, the wall under a
    point. Each face the ray's line could cross, by its bounding box (a slab test over every box at once),
    is intersected exactly (``IntCurvesFace_Intersector``), nearest box first, until no nearer crossing can
    follow -- a ray costs the faces near it, not the shape's every face. A crossing is its distance and the
    ``TopoDS_Face`` crossed; ``ordinal`` is that face's in the shape (``TopExp.MapShapes``' order)."""

    def __init__(self, shape: Any, tolerance: float = 1e-7) -> None:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as FaceMap
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS

        self.shape = shape
        self._tolerance = tolerance
        faces = FaceMap()
        TopExp.MapShapes_s(shape.wrapped, TopAbs_FACE, faces)
        self.faces = [TopoDS.Face(faces.FindKey(index)) for index in range(1, faces.Extent() + 1)]
        whole = Bnd_Box()
        BRepBndLib.Add_s(shape.wrapped, whole, False)
        size = float(np.sqrt(whole.SquareExtent())) if not whole.IsVoid() else 1.0
        self.boxes = np.zeros((len(self.faces), 6))
        for index, face in enumerate(self.faces):
            box = Bnd_Box()
            BRepBndLib.Add_s(face, box, False)
            box.Enlarge(1e-4 * size + 1e-6)
            low, high = box.CornerMin(), box.CornerMax()
            self.boxes[index] = (low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z())
        self._intersectors: dict[int, Any] = {}

    def _candidates(self, o: np.ndarray, d: np.ndarray, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
        """The faces whose boxes the ray meets between ``start`` and ``end``, nearest first, and where it
        enters each."""
        lows, highs = self.boxes[:, :3], self.boxes[:, 3:]
        flat = np.abs(d) <= 1e-300
        with np.errstate(divide="ignore", invalid="ignore"):
            inverse = np.where(flat, 0.0, 1.0 / np.where(flat, 1.0, d))
            t1, t2 = (lows - o) * inverse, (highs - o) * inverse
        lo = np.where(flat, -np.inf, np.minimum(t1, t2))
        hi = np.where(flat, np.inf, np.maximum(t1, t2))
        across = np.all(~flat | ((lows <= o) & (o <= highs)), axis=1)
        enter, leave = lo.max(axis=1), hi.min(axis=1)
        mask = across & (enter <= leave) & (leave >= start) & (enter <= end)
        index = np.flatnonzero(mask)
        entries = np.maximum(enter[index], start)
        order = np.argsort(entries)
        return index[order], entries[order]

    def _intersector(self, index: int) -> Any:
        found = self._intersectors.get(index)
        if found is None:
            from OCP.IntCurvesFace import IntCurvesFace_Intersector

            found = self._intersectors[index] = IntCurvesFace_Intersector(self.faces[index], self._tolerance)
        return found

    def _crossings(self, origin: Iterable[float], direction: Iterable[float], start: float, end: float,
                   nearest: bool) -> list[tuple[float, int]]:
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        o = np.asarray(list(origin), dtype=float)
        d = np.asarray(list(direction), dtype=float)
        d = d / (np.linalg.norm(d) or 1.0)
        candidates, entries = self._candidates(o, d, start, end)
        if not len(candidates):
            return []
        line = gp_Lin(gp_Pnt(*o), gp_Dir(*d))
        found: list[tuple[float, int]] = []
        for index, entry in zip(candidates, entries):
            if nearest and found and entry > found[0][0]:
                break
            intersector = self._intersector(int(index))
            intersector.Perform(line, start, found[0][0] if nearest and found else end)
            if not intersector.IsDone():
                continue
            for k in range(1, intersector.NbPnt() + 1):
                w = float(intersector.WParameter(k))
                if start <= w <= end:
                    found.append((w, int(index)))
            if nearest and found:
                found = [min(found)]
        found.sort()
        return found

    def hits(self, origin: Iterable[float], direction: Iterable[float], start: float = 0.0,
             end: float = 1e9) -> list[tuple[float, Any]]:
        """Every crossing of the ray from ``origin`` along ``direction`` between ``start`` and ``end``: its
        distance and the ``TopoDS_Face`` it crosses, nearest first."""
        return [(w, self.faces[index]) for w, index in self._crossings(origin, direction, start, end, False)]

    def first(self, origin: Iterable[float], direction: Iterable[float], skip: float = 1e-5,
              end: float = 1e9) -> tuple[float, Any] | None:
        """The nearest crossing beyond ``skip``, or None."""
        found = self._crossings(origin, direction, skip, end, True)
        return (found[0][0], self.faces[found[0][1]]) if found else None

    def ordinal(self, face: Any) -> int:
        """The ordinal (1-based) of a face a crossing names, 0 for none of this shape's."""
        return next((index + 1 for index, mine in enumerate(self.faces) if mine.IsSame(face)), 0)

    def thickness(self, point: Iterable[float], normal: Iterable[float], skip: float = 1e-5) -> float | None:
        """The wall under ``point`` of a face whose outward normal there is ``normal``: the distance, into the
        material, to the next face the ray crosses; None where it crosses none (an open shell)."""
        n = np.asarray(list(normal), dtype=float)
        hit = self.first(np.asarray(list(point), dtype=float), -n, skip=skip)
        return None if hit is None else hit[0]

    def intervals(self, origin: Iterable[float], direction: Iterable[float], tolerance: float = 1e-6
                  ) -> list[tuple[float, float]]:
        """The stretches of the whole line through ``origin`` along ``direction`` that lie in the material,
        from its crossings taken in pairs (a closed solid's), as distances from ``origin``."""
        crossings: list[float] = []
        for distance, _ in self._crossings(origin, direction, -1e9, 1e9, False):
            if not crossings or distance - crossings[-1] > tolerance:
                crossings.append(distance)
        return [(crossings[i], crossings[i + 1]) for i in range(0, len(crossings) - 1, 2)]


def inside(solid: Any, points: Iterable[Iterable[float]], tolerance: float = 1e-6) -> list[bool]:
    """Whether each point lies inside ``solid`` (on its boundary is not inside)."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    classifier = BRepClass3d_SolidClassifier(solid.wrapped)
    found = []
    for point in points:
        classifier.Perform(gp_Pnt(*[float(value) for value in point]), tolerance)
        found.append(classifier.State() == TopAbs_IN)
    return found


@dataclass(frozen=True)
class Sample:
    """A point on a face, its outward normal there and the area it stands for."""

    point: np.ndarray
    normal: np.ndarray
    area: float


def _triangulated(shape: Any, deflection: float, angular: float = 0.5) -> None:
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    BRepMesh_IncrementalMesh(shape.wrapped, deflection, False, angular, True)


def samples(face: Any, count: int = 64, deflection: float | None = None) -> list[Sample]:
    """About ``count`` points spread evenly over ``face`` by area, each on the surface itself: the face's
    triangulation (made with ``deflection``, a fiftieth of the face's size by default) cut into triangles
    of about equal area, each sample the surface at one's middle, with its outward normal and its share
    of the face's area."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    if deflection is None:
        box = face.bounding_box(optimal=False)
        deflection = max(1e-3, 0.02 * max(box.size.X, box.size.Y, box.size.Z))
    _triangulated(face, deflection)
    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
    if triangulation is None or triangulation.NbTriangles() == 0:
        return []
    trsf = location.Transformation()
    nodes = np.array([_xyz(triangulation.Node(i).Transformed(trsf)) for i in range(1, triangulation.NbNodes() + 1)])
    uvs = (np.array([(triangulation.UVNode(i).X(), triangulation.UVNode(i).Y())
                     for i in range(1, triangulation.NbNodes() + 1)]) if triangulation.HasUVNodes() else None)
    corners = [tuple(value - 1 for value in triangulation.Triangle(index).Get())
               for index in range(1, triangulation.NbTriangles() + 1)]
    areas = [0.5 * float(np.linalg.norm(np.cross(nodes[b] - nodes[a], nodes[c] - nodes[a]))) for a, b, c in corners]
    total = sum(areas)
    if total <= 0.0:
        return []
    target = total / max(1, count)
    from OCP.BRepGProp import BRepGProp_Face

    props = BRepGProp_Face(face.wrapped)
    found: list[Sample] = []
    for (a, b, c), area in zip(corners, areas):
        if area <= 0.0:
            continue
        cuts = max(1, int(math.ceil(math.sqrt(area / target))))
        share = area / (cuts * cuts)
        for i in range(cuts):
            for j in range(cuts - i):
                # the sub-triangles of a triangle cut ``cuts`` times along each side, by their middles
                for wa, wb in (((i + 1 / 3) / cuts, (j + 1 / 3) / cuts), ((i + 2 / 3) / cuts, (j + 2 / 3) / cuts)):
                    if wa + wb > 1.0 + 1e-12:
                        continue
                    wc = 1.0 - wa - wb
                    if uvs is not None:
                        u, v = wa * uvs[a] + wb * uvs[b] + wc * uvs[c]
                        point, normal = point_normal(face, float(u), float(v), props)
                    else:
                        point = wa * nodes[a] + wb * nodes[b] + wc * nodes[c]
                        normal = np.cross(nodes[b] - nodes[a], nodes[c] - nodes[a])
                        normal = normal / (np.linalg.norm(normal) or 1.0)
                    found.append(Sample(point, normal, share))
    return found


def triangles(shape: Any, deflection: float, angular: float = 0.5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The shape triangulated: vertices (n, 3), triangles (m, 3) as vertex indices, and the ordinal of the
    face each triangle lies on (``TopExp.MapShapes``' order, 1-based) -- a mesh whose every triangle names its
    face, for the measures a mesh answers best (a projection, a voxel field)."""
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape

    _triangulated(shape, deflection, angular)
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape.wrapped, TopAbs_FACE, faces)
    vertices: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    owners: list[np.ndarray] = []
    offset = 0
    for ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face(faces.FindKey(ordinal))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None:
            continue
        trsf = location.Transformation()
        nodes = np.array([_xyz(triangulation.Node(i).Transformed(trsf))
                          for i in range(1, triangulation.NbNodes() + 1)])
        tri = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)]) - 1
        if face.Orientation() == TopAbs_REVERSED:
            tri = tri[:, ::-1]
        vertices.append(nodes)
        tris.append(tri + offset)
        owners.append(np.full(len(tri), ordinal))
        offset += len(nodes)
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int), np.zeros(0, dtype=int)
    return np.vstack(vertices), np.vstack(tris).astype(int), np.concatenate(owners).astype(int)


def walk_faces(document: Document) -> Iterator[tuple[Part, int, Any]]:
    """Every face of every part: its part, its ordinal and the face."""
    for part in document.parts:
        for ordinal, face in enumerate(part.faces(), start=1):
            yield part, ordinal, face


def rounded(values: Iterable[float], digits: int = 4) -> list[float]:
    return [round(float(value), digits) for value in values]
