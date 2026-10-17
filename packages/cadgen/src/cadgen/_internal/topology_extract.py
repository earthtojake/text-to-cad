"""A component's topology facts: what its selector table is built from.

The facts of one unlocated component's exact topology, read off the BREP with
OCCT and never meshed: each solid's ordinal and kind; each face's
surface type, a plane's oriented normal, its analytic parameters and its loops
as ordered edge ordinals; each edge's visibility class, continuity, dihedral
angle, flags, adjacent faces, exact length and centroid (GProps), curve type,
analytic parameters and, for a circle, its sweep. No box: a face's and an edge's
are its display mesh's, which the selector table takes from the mesher
(``tessellate``). No face's area or centroid: no part reads them -- a view
measures a face where it is shown (``store.parts.measure_face``), and the mesher
judges a face by its own triangles. Face and edge ordinals are the
``TopExp.MapShapes_s`` order the selector table joins an element's name to
(``store.parts.element_names``), and the component's mesh (``tessellate``) is
grouped by the same ordinals.

``extract_topology_facts`` returns them in memory as a plain structure -- the
three ordinal tables ``shapes``, ``faces`` and ``edges`` -- that the mesher reads
(each face's surface type, each edge's class) and the selector table
takes whole (``selector_table.build_selector_table``): every field it carries,
the table reads. Nothing stores them, except an eager-only
component's, which its tree pins as an object
(``topology_facts.topology_facts_bytes``, ``component_package``).

Nothing here tessellates: meshes are cadgen's, made by its tessellator from the
exact BREP itself, so the facts carry no tessellation input -- no trim curves,
control nets or basis curves.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_Orientation,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_WIRE,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)
from OCP.TopoDS import TopoDS

from cadgen._internal.entity_ordinals import shape_entities
from cadgen._internal.glb_topology import (
    STEP_EDGE_ANGULAR_TOLERANCE_DEG,
    STEP_EDGE_FLAGS,
    STEP_EDGE_VISIBILITY_CLASSES,
)
from cadgen._internal.step_scene_geometry import (
    _curve_params,
    _edge_continuity_name,
    _is_smooth_continuity,
    _sampled_edge_dihedral_deg,
    _surface_params,
    face_surface,
)
from cadgen._internal.step_scene_types import _enum_name

__all__ = ["extract_topology_facts"]


def _enum_name_geomabs(value) -> str:
    # The type names selector refs and the page read
    # (step_scene_loader._enum_name with the GeomAbs_ prefix stripped,
    # lowercased): "plane", "cylinder", "bsplinesurface", "line", ...
    return _enum_name(value, "GeomAbs_")


def _selector_surface_params(adaptor) -> dict[str, Any]:
    try:
        return _surface_params(adaptor, None)
    except Exception:
        return {}


def _selector_curve_params(adaptor) -> dict[str, Any]:
    try:
        return _curve_params(adaptor, None)
    except Exception:
        return {}


def _bnd_box(topo) -> list[float] | None:
    """The face's or edge's own bounding box, TIGHT.

    ``BRepBndLib::Add`` bounds a B-spline by its CONTROL POLYGON, which for a
    NURBS circle of radius r reaches r/cos(22.5 deg) = 1.082 r -- an 8% overshoot
    on every rounded surface. These boxes are what a geometric token's face
    signature rounds (``geometric_tokens``) and what a written STEP's verify
    compares (``step_verify``), so they must describe the surface, not its poles:
    ``AddOptimal`` subdivides instead.
    ``useTriangulation=False`` throughout, because meshing here would mutate the
    shared ``TShape`` and break content-addressed component dedup.
    """
    try:
        box = Bnd_Box()
        try:
            BRepBndLib.AddOptimal_s(topo, box, False, False)
        except Exception:
            box = Bnd_Box()
            BRepBndLib.Add_s(topo, box, False)
        if box.IsVoid():
            return None
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        return [xmin, ymin, zmin, xmax, ymax, zmax]
    except Exception:
        return None


# The exact metrics of a component's faces and edges a geometric token reads (``geometric_tokens``)
# -- the kernel's integrals, and the faces' tight boxes -- remembered per component in this
# process. Keyed by the component's BREP object; memory only, bounded. Each entry: the faces'
# integrals, the edges' integrals, and whether the faces' boxes have been measured and added to
# the faces' metrics. The topology facts measure their edges themselves and no face.
_METRICS_MEMO: OrderedDict[str, dict[str, Any]] = OrderedDict()
_METRICS_MEMO_SIZE = 256
_METRICS_LOCK = threading.Lock()


def component_metrics(shape, *, brep: str | None = None, face_boxes: bool = False) -> dict[str, list[dict[str, Any]]]:
    """Each face's ``area`` and ``center`` and each edge's ``length`` and ``center`` -- and, with
    ``face_boxes``, each face's tight ``bbox`` -- of the unlocated component ``shape``, in
    ``TopExp.MapShapes_s`` order; a key a measurement failed is absent: what the geometric
    tokens read. ``brep``, the component's BREP object hash, keys the process memo: the
    measurements an earlier caller took of the same component are returned, the faces' boxes
    are added to them the first time a caller asks, and None measures without the memo. The
    rows are the memo's own: a caller copies the keys it reads."""
    remembered = _remembered(brep)
    if remembered is None:
        face_map, edge_map = _element_maps(shape)
        remembered = {
            "faces": [_face_integrals(TopoDS.Face_s(face_map.FindKey(i))) for i in range(1, face_map.Extent() + 1)],
            "edges": [_edge_integrals(TopoDS.Edge_s(edge_map.FindKey(i))) for i in range(1, edge_map.Extent() + 1)],
            "faceBoxes": False,
        }
        _remember(brep, remembered)
    if face_boxes and not remembered["faceBoxes"]:
        face_map, _ = _element_maps(shape)
        for ordinal, metrics in enumerate(remembered["faces"], start=1):
            box = _bnd_box(TopoDS.Face_s(face_map.FindKey(ordinal)))
            if box is not None:
                metrics["bbox"] = box
        remembered["faceBoxes"] = True
    return {"faces": remembered["faces"], "edges": remembered["edges"]}


def _remembered(brep: str | None) -> dict[str, Any] | None:
    if brep is None:
        return None
    with _METRICS_LOCK:
        remembered = _METRICS_MEMO.get(brep)
        if remembered is not None:
            _METRICS_MEMO.move_to_end(brep)
        return remembered


def _remember(brep: str | None, metrics: dict[str, Any]) -> None:
    if brep is None:
        return
    with _METRICS_LOCK:
        _METRICS_MEMO[brep] = metrics
        _METRICS_MEMO.move_to_end(brep)
        while len(_METRICS_MEMO) > _METRICS_MEMO_SIZE:
            _METRICS_MEMO.popitem(last=False)


def _element_maps(shape) -> tuple[TopTools_IndexedMapOfShape, TopTools_IndexedMapOfShape]:
    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
    return face_map, edge_map


def _face_integrals(face) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    try:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        metrics["area"] = float(props.Mass())
        center = props.CentreOfMass()
        metrics["center"] = [center.X(), center.Y(), center.Z()]
    except Exception:
        pass
    return metrics


def _edge_integrals(edge) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    try:
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(edge, props)
        metrics["length"] = float(props.Mass())
        center = props.CentreOfMass()
        metrics["center"] = [center.X(), center.Y(), center.Z()]
    except Exception:
        pass
    return metrics


def _edge_classification(edge, faces: list, surfaces: Callable[[], list]) -> dict[str, Any]:
    """Visibility class plus the classification columns the selector tables
    carry (continuity, dihedralDeg, flags, adjacentFaceCount), from the
    exact faces either side of the edge. ``surfaces()`` gives those faces'
    restricted surface adaptors (``step_scene_geometry.face_surface``), each
    made once per face by the caller: asked only for an edge whose angle is
    sampled."""
    F, C = STEP_EDGE_FLAGS, STEP_EDGE_VISIBILITY_CLASSES
    count = len(faces)
    result: dict[str, Any] = {
        "adjacentFaceCount": count,
        "dihedralDeg": None,
    }
    typed_faces = [TopoDS.Face_s(f) for f in faces]
    if BRep_Tool.Degenerated_s(edge):
        result.update(cls=C["DEGENERATE"], continuity="degenerate",
                      flags=F["DEGENERATE"])
        return result
    seam = any(BRep_Tool.IsClosed_s(edge, f) for f in typed_faces)
    if seam or (count == 1 and typed_faces
                and BRep_Tool.IsClosed_s(edge, typed_faces[0])):
        result.update(cls=C["SEAM"], continuity="seam", flags=F["SEAM"])
        return result
    if count == 0:
        result.update(cls=C["FEATURE"], continuity="unknown",
                      flags=F["NOT_REFERENCEABLE"] | F["UNKNOWN_CONTINUITY"])
        return result
    if count == 1:
        result.update(cls=C["BOUNDARY"], continuity="boundary",
                      flags=F["BOUNDARY"])
        return result
    if count > 2:
        result.update(cls=C["NON_MANIFOLD"], continuity="non_manifold",
                      flags=F["NON_MANIFOLD"])
        return result
    try:
        continuity = _edge_continuity_name(edge, typed_faces)
    except Exception:
        continuity = ""
    if continuity == "c0":
        dihedral = _sampled_edge_dihedral_deg(edge, typed_faces, surfaces())
        result.update(cls=C["FEATURE"], continuity="c0", flags=F["HARD"],
                      dihedralDeg=dihedral)
        return result
    if _is_smooth_continuity(continuity):
        dihedral = _sampled_edge_dihedral_deg(edge, typed_faces, surfaces())
        result.update(cls=C["TANGENT"], continuity=continuity,
                      flags=F["TANGENT"], dihedralDeg=dihedral)
        return result
    dihedral = _sampled_edge_dihedral_deg(edge, typed_faces, surfaces())
    if dihedral is not None:
        if dihedral > STEP_EDGE_ANGULAR_TOLERANCE_DEG:
            result.update(cls=C["FEATURE"], continuity="sampled_hard",
                          flags=F["HARD"], dihedralDeg=dihedral)
        else:
            result.update(cls=C["TANGENT"], continuity="sampled_tangent",
                          flags=F["TANGENT"], dihedralDeg=dihedral)
        return result
    result.update(cls=C["UNKNOWN"], continuity="unknown",
                  flags=F["UNKNOWN_CONTINUITY"])
    return result


def extract_topology_facts(shape) -> dict[str, Any]:
    """The topology facts of one unlocated component shape (a ``TopoDS_Shape``):
    ``{"shapes": [...], "faces": [...], "edges": [...]}``, each a table in
    ordinal order, holding exactly what the mesher and the selector table read.

    Geometry only: the part-level colour and the intrinsic face colours ride the
    tree, so two occurrences of one part in different colours share one
    component."""
    # The identity the scene loader joins ordinals by.
    from cadgen._internal.step_scene_loader import _shape_hash

    face_map = TopTools_IndexedMapOfShape()
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, face_map)
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_faces)

    edge_ord_by_hash = {
        _shape_hash(edge_map.FindKey(i)): i
        for i in range(1, edge_map.Extent() + 1)
    }

    # Shape (solid/shell) membership: the selector tables group faces/edges
    # by solid; record each solid's ordinal and kind and every face/edge's
    # owning solid. Mirrors the prototype extraction's decomposition.
    shapes: list[dict[str, Any]] = []
    shape_by_face: dict[int, int] = {}
    shape_by_edge: dict[int, int] = {}
    face_ord_by_hash = {
        _shape_hash(face_map.FindKey(i)): i
        for i in range(1, face_map.Extent() + 1)
    }

    def _record_shape(sub, kind: str) -> None:
        ordinal = len(shapes) + 1
        shapes.append({"ord": ordinal, "kind": kind})
        sub_faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(sub, TopAbs_FACE, sub_faces)
        for i in range(1, sub_faces.Extent() + 1):
            face_ord = face_ord_by_hash.get(_shape_hash(sub_faces.FindKey(i)))
            if face_ord is not None:
                shape_by_face.setdefault(face_ord, ordinal)
        sub_edges = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(sub, TopAbs_EDGE, sub_edges)
        for i in range(1, sub_edges.Extent() + 1):
            edge_ord = edge_ord_by_hash.get(_shape_hash(sub_edges.FindKey(i)))
            if edge_ord is not None:
                shape_by_edge.setdefault(edge_ord, ordinal)

    for sub in shape_entities(shape):
        kind = {TopAbs_SOLID: "solid", TopAbs_SHELL: "shell"}.get(sub.ShapeType(), "shape")
        _record_shape(sub, kind)

    faces: list[dict[str, Any]] = []
    for ordinal in range(1, face_map.Extent() + 1):
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        adaptor = BRepAdaptor_Surface(face)
        kind = adaptor.GetType()
        entry: dict[str, Any] = {
            "ord": ordinal,
            "shape": shape_by_face.get(ordinal, 1),
            # Selector-table columns (surfaceType/params, spelled as
            # _enum_name_geomabs spells them) -- reading, not meshing.
            "surfaceType": _enum_name_geomabs(kind),
        }
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
            # The plane's normal, oriented as the face is.
            direction = adaptor.Plane().Position().Direction()
            sign = -1.0 if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED else 1.0
            entry["normal"] = [sign * c for c in (direction.X(), direction.Y(), direction.Z())]
        params = _selector_surface_params(adaptor)
        if params:
            entry["params"] = params
        # Each loop as the ordered edge ordinals a wire walk visits (0 for an
        # edge the map does not hold).
        loops: list[list[int]] = []
        wire_explorer = TopExp_Explorer(face, TopAbs_WIRE)
        while wire_explorer.More():
            wire = TopoDS.Wire_s(wire_explorer.Current())
            loop: list[int] = []
            walker = BRepTools_WireExplorer(wire, face)
            while walker.More():
                loop.append(edge_ord_by_hash.get(_shape_hash(walker.Current()), 0))
                walker.Next()
            if loop:
                loops.append(loop)
            wire_explorer.Next()
        entry["loops"] = loops
        faces.append(entry)

    # Each face's restricted surface adaptor, made the first time an edge of the face has its
    # angle sampled: restricting runs over every edge of the face, so it is made once a face.
    surfaces: dict[int, Any] = {}

    def surface(face_ord: int, face) -> Any:
        found = surfaces.get(face_ord) if face_ord else None
        if found is None and face_ord not in surfaces:
            try:
                found = face_surface(TopoDS.Face_s(face))
            except Exception:  # noqa: BLE001 - a face whose surface cannot be read gives no angle
                found = None
            if face_ord:
                surfaces[face_ord] = found
        return found

    edges: list[dict[str, Any]] = []
    for ordinal in range(1, edge_map.Extent() + 1):
        edge = TopoDS.Edge_s(edge_map.FindKey(ordinal))
        # NB: list(TopTools_ListOfShape) costs ~2ms/call in OCP (its Python
        # iteration protocol unwinds C++ exceptions); First/Last/iterator
        # access is ~1000x cheaper and this loop runs once per edge.
        adjacent = []
        if edge_faces.Contains(edge):
            face_list = edge_faces.FindFromKey(edge)
            extent = face_list.Extent()
            if extent == 1:
                adjacent = [face_list.First()]
            elif extent == 2:
                adjacent = [face_list.First(), face_list.Last()]
            elif extent > 2:
                # Rare (non-manifold); the slow generic path is fine here.
                adjacent = list(face_list)
        # A seam edge appears under its single face TWICE in the ancestor
        # map; adjacency and faceOrds carry DEDUPED faces (matching the
        # selector tables), and a duplicate implies seam classification.
        unique_faces = []
        deduped_ords = []
        seen_face_ords = set()
        for f in adjacent:
            face_ord = face_ord_by_hash.get(_shape_hash(f), 0)
            if face_ord not in seen_face_ords:
                seen_face_ords.add(face_ord)
                unique_faces.append(f)
                deduped_ords.append(face_ord)
        classification = _edge_classification(
            edge, unique_faces,
            lambda: [surface(face_ord, face) for face_ord, face in zip(deduped_ords, unique_faces)])
        if len(unique_faces) != len(adjacent):
            classification["cls"] = STEP_EDGE_VISIBILITY_CLASSES["SEAM"]
            classification["continuity"] = "seam"
            classification["flags"] = STEP_EDGE_FLAGS["SEAM"]
        curve_adaptor = BRepAdaptor_Curve(edge)
        curve_kind = curve_adaptor.GetType()
        entry = {
            "ord": ordinal,
            "shape": shape_by_edge.get(ordinal, 1),
            "class": classification["cls"],
            "continuity": classification["continuity"],
            "dihedralDeg": classification["dihedralDeg"],
            "flags": int(classification["flags"]),
            "adjacentFaceCount": len(unique_faces),
            "curveType": _enum_name_geomabs(curve_kind),
            "faceOrds": deduped_ords,
            **_edge_integrals(edge),
        }
        params = _selector_curve_params(curve_adaptor)
        if params:
            entry["params"] = params
        if curve_kind == GeomAbs_CurveType.GeomAbs_Circle and not BRep_Tool.Degenerated_s(edge):
            # The arc's sweep, in radians: its parameter range on the circle.
            entry["sweepRadians"] = abs(curve_adaptor.LastParameter() - curve_adaptor.FirstParameter())
        edges.append(entry)

    return {"shapes": shapes, "faces": faces, "edges": edges}
