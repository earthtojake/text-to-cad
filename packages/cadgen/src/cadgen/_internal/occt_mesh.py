"""One component's display mesh: OCCT's mesher on the exact BREP, as a GLB body.

cadgen's tessellator. ``BRepMesh_IncrementalMesh`` -- the mesher build123d's
own exporters use -- triangulates the component's exact faces at a chord
tolerance RELATIVE to the component's bounding diagonal and an angular one in
radians, discretizing every edge once so the faces either side share its
vertices. What it writes is one GLB body (``cadgen.store.meshes``): one triangle
primitive whose triangles run face by face, smooth normals from the exact
surfaces, and one polyline per model edge lying exactly on the mesh boundary.
The viewer, snapshots and mesh exports all draw these same bytes.

Face and edge ordinals are ``TopExp.MapShapes`` order on the unlocated
component -- the order its SURF index and every selector use -- and the SURF
index supplies what the triangles do not: each face's intrinsic colour and
each edge's display class. OCCT's mesher drops the odd tiny face at one
deflection and meshes it at the next, so a component whose pass leaves a face
empty that the mesh can resolve is meshed again, whole and finer, in a fixed
order. A face no whole pass meshes is one OCCT refuses -- it reads the face's
boundary as crossing itself or open, what a boolean's leftovers do to a valid face
-- and no setting or repair of OCCT's meshes it, so it is tessellated over its own
parameters as cadgen's earlier tessellator did (``face_fallback``), against the
meshed neighbours, and kept when its triangles cover the face's own area. A face
that still has none is left out of the component, which is drawn without it, and
the body names it (``unmeshedFaces``, ``cadgen.store.meshes``): one face no mesher
covers never fails a view, a list or an export of the whole document, and each of
them says which faces of which part it does not draw or write. A face smaller than
the mesh can resolve -- its area under the square of the chord tolerance, inside the
error every triangle may carry -- may have none and is not named, and such a face
earns no finer pass. Any failure inside OCCT is the component's error. A component
with no faces meshes nothing: its edges are sampled from their own curves.

The arrays leave OCCT through its own glTF writer (``RWGltf_CafWriter``, one
primitive per face), not one Python call per vertex: that is what keeps a large
component's extraction in milliseconds. A component whose faces cannot be
matched to the writer's primitives one for one (a face its explorer meets
twice, for instance) is read face by face instead, which is slower and the same:
both read normals OCCT computed onto the triangulation beforehand.
"""

from __future__ import annotations

import json
import math
import struct
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

# Two points closer than this, relative to the component's diagonal, are one
# point: the floor under the scale of a component with no extent.
_SCALE_FLOOR = 1e-6
# The deflections, as multiples of the component's, at which a component whose
# pass left a face empty is meshed again, whole: the first that leaves none wins.
_RETRY_SCALES = (0.5, 0.25)
# A face OCCT refuses is tessellated over its own parameters; its triangles are kept
# when they cover the face's own area to this share -- a chord across a curved
# boundary takes area off a small face, nothing near this much.
_FALLBACK_AREA_TOLERANCE = 0.25


class MeshProductionError(ValueError):
    """A component OCCT could not mesh completely."""


def _bounding_diagonal(topods) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(topods, box, False)
    if box.IsVoid():
        return _SCALE_FLOOR
    x0, y0, z0, x1, y1, z1 = box.Get()
    diagonal = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)
    return diagonal if math.isfinite(diagonal) and diagonal > _SCALE_FLOOR else _SCALE_FLOOR


def _maps(topods):
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    faces, edges = TopTools_IndexedMapOfShape(), TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
    TopExp.MapShapes_s(topods, TopAbs_EDGE, edges)
    return faces, edges


def _empty(face_map, ordinals: list[int]) -> list[int]:
    """Those of ``ordinals`` whose face the mesher left without triangles."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    empty = []
    for ordinal in ordinals:
        triangulation = BRep_Tool.Triangulation_s(TopoDS.Face_s(face_map.FindKey(ordinal)), TopLoc_Location())
        if triangulation is None or triangulation.NbTriangles() == 0:
            empty.append(ordinal)
    return empty


def _mesh(topods, face_map, required: list[int], deflection: float, angle: float) -> None:
    """Mesh the component, and while a face of ``required`` is left empty, mesh it all
    again, cleaned, at the retry deflections. A face no whole pass meshes is one OCCT
    refuses: the component is meshed at its own deflection once more, and each face
    still empty is tessellated over its own parameters against its meshed neighbours."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.Precision import Precision

    BRepMesh_IncrementalMesh(topods, deflection, False, angle, True)
    for scale in _RETRY_SCALES:
        if not _empty(face_map, required):
            return
        BRepTools.Clean_s(topods)
        # OCCT refuses a deflection under its confusion tolerance.
        BRepMesh_IncrementalMesh(topods, max(deflection * scale, Precision.Confusion_s()), False, angle, True)
    if not _empty(face_map, required):
        return
    BRepTools.Clean_s(topods)
    BRepMesh_IncrementalMesh(topods, deflection, False, angle, True)
    _tessellate_refused(topods, face_map, _empty(face_map, required), deflection, angle)


def _tessellate_refused(topods, face_map, ordinals: list[int], deflection: float, angle: float) -> None:
    """Give each face of ``ordinals`` the triangles ``face_fallback`` builds over its
    parameters, when they cover its own area to ``_FALLBACK_AREA_TOLERANCE``; a face
    left without stays empty, and the body names it."""
    from cadgen._internal import face_fallback
    from OCP.BRep import BRep_Builder
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS

    for ordinal in ordinals:
        face = TopoDS.Face_s(face_map.FindKey(ordinal))
        tessellated = face_fallback.tessellate_face(topods, face, deflection, angle)
        if tessellated is None:
            continue
        triangulation, covered = tessellated
        exact = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, exact)
        if abs(covered - exact.Mass()) <= _FALLBACK_AREA_TOLERANCE * exact.Mass():
            BRep_Builder().UpdateFace(face, triangulation)


def _triangulated_faces(topods, face_map) -> list[tuple[int, Any, Any, Any]]:
    """(ordinal, face, triangulation, location) in explorer order, as the glTF writer meets them.

    Each triangulation gets OCCT's normals first, from the exact surface where it
    has one and from the triangles around a node where it does not (a cone's apex,
    a revolved profile's pole): left to the writer, such a node's normal is a
    fixed axis, often pointing into the solid."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepLib import BRepLib_ToolTriangulatedShape
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    found = []
    explorer = TopExp_Explorer(topods, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None and triangulation.NbTriangles() > 0:
            if not triangulation.HasNormals():
                BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, triangulation)
            found.append((face_map.FindIndex(face), face, triangulation, location))
        explorer.Next()
    return found


def _faces_from_gltf(topods, triangulated) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] | None:
    """Each face's (positions, normals, local triangles), written by OCCT's glTF writer.

    None when the writer's primitives cannot be matched to ``triangulated`` one
    for one; the caller then reads the faces itself."""
    from OCP.Message import Message_ProgressRange
    from OCP.RWGltf import RWGltf_CafWriter
    from OCP.RWMesh import RWMesh_CoordinateSystem
    from OCP.TColStd import TColStd_IndexedDataMapOfStringString
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    document = TDocStd_Document(TCollection_ExtendedString("cadgen-mesh"))
    XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).AddShape(topods, False)
    with tempfile.TemporaryDirectory(prefix="cadgen-mesh-") as folder:
        path = Path(folder) / "component.glb"
        writer = RWGltf_CafWriter(TCollection_AsciiString(str(path)), True)
        writer.SetMergeFaces(False)
        converter = writer.ChangeCoordinateSystemConverter()
        converter.SetInputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
        converter.SetOutputCoordinateSystem(RWMesh_CoordinateSystem.RWMesh_CoordinateSystem_Zup)
        if not writer.Perform(document, TColStd_IndexedDataMapOfStringString(), Message_ProgressRange()):
            return None
        data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_length])
    binary = memoryview(data)[20 + json_length + 8:]

    def view(accessor_index: int, dtype, width: int) -> np.ndarray:
        accessor = gltf["accessors"][accessor_index]
        buffer_view = gltf["bufferViews"][accessor["bufferView"]]
        offset = buffer_view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        return np.frombuffer(binary, dtype, accessor["count"] * width, offset)

    # The writer puts a component's free edges and vertices beside its faces, as
    # LINES and POINTS primitives: the faces are its TRIANGLES (mode 4, the default).
    primitives = [primitive for mesh in gltf.get("meshes", []) for primitive in mesh["primitives"]
                  if primitive.get("mode", 4) == 4]
    if len(primitives) != len(triangulated):
        return None
    # The writer places a located shape with a node transform; the component is
    # unlocated, so every node must be the identity for the arrays to be its own.
    for node in gltf.get("nodes", []):
        if any(name in node for name in ("matrix", "translation", "rotation", "scale")):
            matrix = node.get("matrix")
            if matrix is None or not np.allclose(matrix, np.eye(4).ravel()):
                return None
    faces = {}
    for (ordinal, _face, triangulation, _location), primitive in zip(triangulated, primitives):
        positions = view(primitive["attributes"]["POSITION"], np.float32, 3).reshape(-1, 3)
        normals = view(primitive["attributes"]["NORMAL"], np.float32, 3).reshape(-1, 3)
        index_accessor = gltf["accessors"][primitive["indices"]]
        dtype = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}[index_accessor["componentType"]]
        triangles = view(primitive["indices"], dtype, 1).astype(np.uint32).reshape(-1, 3)
        if (len(positions) != triangulation.NbNodes() or len(triangles) != triangulation.NbTriangles()
                or ordinal in faces):
            return None
        faces[ordinal] = (positions, normals, triangles)
    return faces


def _faces_one_by_one(triangulated) -> dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """The same arrays read face by face: placed positions, normals turned to the face's
    orientation, and triangles wound to it -- and turned once more by a mirroring
    placement, which carries the normals itself, as the glTF writer does."""
    from OCP.TopAbs import TopAbs_REVERSED

    faces = {}
    for ordinal, face, triangulation, location in triangulated:
        if ordinal in faces:
            continue
        transform = location.Transformation()
        count = triangulation.NbNodes()
        positions = np.empty((count, 3), np.float32)
        normals = np.empty((count, 3), np.float32)
        flip = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
        turn = (flip < 0) != (transform.VectorialPart().Determinant() < 0)
        for node in range(1, count + 1):
            point = triangulation.Node(node).Transformed(transform)
            normal = triangulation.Normal(node).Transformed(transform)
            positions[node - 1] = (point.X(), point.Y(), point.Z())
            normals[node - 1] = (flip * normal.X(), flip * normal.Y(), flip * normal.Z())
        triangles = np.empty((triangulation.NbTriangles(), 3), np.uint32)
        for index in range(1, triangulation.NbTriangles() + 1):
            a, b, c = triangulation.Triangle(index).Get()
            triangles[index - 1] = (a - 1, c - 1, b - 1) if turn else (a - 1, b - 1, c - 1)
        faces[ordinal] = (positions, normals, triangles)
    return faces


def _edge_faces(topods, face_map, edge_map) -> list[list[int]]:
    """Each edge's adjacent face ordinals, deduplicated (a seam meets its face twice)."""
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    adjacent: list[list[int]] = [[] for _ in range(edge_map.Extent() + 1)]
    for face_ordinal in range(1, face_map.Extent() + 1):
        explorer = TopExp_Explorer(face_map.FindKey(face_ordinal), TopAbs_EDGE)
        while explorer.More():
            edge_ordinal = edge_map.FindIndex(explorer.Current())
            if edge_ordinal and face_ordinal not in adjacent[edge_ordinal]:
                adjacent[edge_ordinal].append(face_ordinal)
            explorer.Next()
    return adjacent


def _edge_polyline(edge, adjacent: list[int], face_map, faces, deflection: float, angle: float) -> np.ndarray | None:
    """The edge's points: its discretization on an adjacent face's mesh, else its own curve."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    if BRep_Tool.Degenerated_s(edge):
        return None
    for face_ordinal in adjacent:
        if face_ordinal not in faces:
            continue
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(TopoDS.Face_s(face_map.FindKey(face_ordinal)), location)
        polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location) if triangulation is not None else None
        if polygon is None:
            continue
        nodes = polygon.Nodes()
        indices = np.fromiter((nodes.Value(k) - 1 for k in range(nodes.Lower(), nodes.Upper() + 1)),
                              np.int64, nodes.Length())
        return faces[face_ordinal][0][indices]
    # A free edge, or one no face meshed along: sample its own exact curve.
    curve = BRepAdaptor_Curve(edge)
    sampler = GCPnts_TangentialDeflection(curve, angle, deflection)
    if sampler.NbPoints() < 2:
        return None
    return np.array([[(point := sampler.Value(k)).X(), point.Y(), point.Z()]
                     for k in range(1, sampler.NbPoints() + 1)], np.float32)


def mesh_component(topods, surf_index: dict, *, surface_input: str, surface_object: str,
                   chord: float, angle: float) -> bytes:
    """Mesh one unlocated component and return its GLB body.

    ``topods`` is a private decode of the component's BREP: meshing stores its
    triangulation on the shape, so it must not be a shape anything else holds.
    ``surf_index`` is the component's SURF index (its faces' colours and areas,
    its edges' classes), in the same ordinals. A failure inside OCCT is the
    component's ``MeshProductionError``.
    """
    try:
        return _mesh_component(topods, surf_index, surface_input=surface_input,
                               surface_object=surface_object, chord=chord, angle=angle)
    except Exception as error:  # noqa: BLE001 - OCCT's own, told apart below
        # OCP raises OCCT's exception classes, whose Python bases differ between
        # platform wheels (Standard_ConstructionError is no Standard_Failure): one is
        # known by the module its class comes from.
        if not type(error).__module__.startswith("OCP"):
            raise
        raise MeshProductionError(f"OCCT failed on the component: {type(error).__name__}: {error}") from error


def _mesh_component(topods, surf_index: dict, *, surface_input: str, surface_object: str,
                    chord: float, angle: float) -> bytes:
    from cadgen.store.meshes import encode_payload
    from OCP.Precision import Precision
    from OCP.TopoDS import TopoDS

    face_map, edge_map = _maps(topods)
    surf_faces, surf_edges = surf_index.get("faces", []), surf_index.get("edges", [])
    if len(surf_faces) != face_map.Extent() or len(surf_edges) != edge_map.Extent():
        raise MeshProductionError(
            f"the component's BREP has {face_map.Extent()} faces and {edge_map.Extent()} edges, "
            f"its SURF index {len(surf_faces)} and {len(surf_edges)}"
        )
    diagonal = _bounding_diagonal(topods)
    # OCCT refuses a deflection under its confusion tolerance, which a component of
    # next to no extent (a lone vertex) would otherwise ask for.
    deflection = max(chord * diagonal, Precision.Confusion_s())
    # Every face the mesh can resolve must have triangles; a smaller one may have none.
    # Only a face that must earns the finer passes: a watch case's 0.002 mm² sliver
    # left a 1,529-face case meshed three times over, fifteen times as long, for a
    # face under what the mesh can resolve.
    required = [row["ord"] for row in surf_faces if float(row.get("area") or 0.0) >= deflection * deflection]
    if face_map.Extent():
        _mesh(topods, face_map, required, deflection, angle)
    triangulated = _triangulated_faces(topods, face_map)
    faces = (_faces_from_gltf(topods, triangulated) if triangulated else {})
    if faces is None:
        faces = _faces_one_by_one(triangulated)
    # A face no mesher covered is left out, and the body names it: every reader says so.
    unmeshed = [ordinal for ordinal in required if ordinal not in faces]

    position_parts, normal_parts, index_parts, face_ranges = [], [], [], []
    vertex_base = index_start = 0
    for row in sorted(surf_faces, key=lambda row: row["ord"]):
        ordinal = row["ord"]
        positions, normals, triangles = faces.get(ordinal, (np.zeros((0, 3), np.float32),) * 2 + (np.zeros((0, 3), np.uint32),))
        position_parts.append(positions)
        normal_parts.append(normals)
        index_parts.append(triangles.reshape(-1) + np.uint32(vertex_base))
        color = row.get("color")
        face_ranges.append({"ord": ordinal, "color": [float(c) for c in color] if color else None,
                            "indexStart": index_start, "indexCount": int(triangles.size)})
        vertex_base += len(positions)
        index_start += int(triangles.size)
    positions = np.concatenate(position_parts).astype("<f4") if position_parts else np.zeros((0, 3), "<f4")
    normals = np.concatenate(normal_parts).astype("<f4") if normal_parts else np.zeros((0, 3), "<f4")
    indices = np.concatenate(index_parts).astype("<u4") if index_parts else np.zeros(0, "<u4")

    adjacent = _edge_faces(topods, face_map, edge_map)
    edges = []
    for row in sorted(surf_edges, key=lambda row: row["ord"]):
        ordinal, visibility = row["ord"], str(row.get("class") or "none")
        polyline = _edge_polyline(TopoDS.Edge_s(edge_map.FindKey(ordinal)), adjacent[ordinal],
                                  face_map, faces, deflection, angle)
        if polyline is not None and len(polyline) >= 2:
            edges.append((ordinal, visibility, np.ascontiguousarray(polyline, "<f4").reshape(-1, 3)))

    if len(positions):
        low, high = positions.min(axis=0), positions.max(axis=0)
    elif edges:
        points = np.concatenate([polyline for _, _, polyline in edges])
        low, high = points.min(axis=0), points.max(axis=0)
    else:
        low = high = np.zeros(3, np.float32)
    bounds = {"min": [float(v) for v in low], "max": [float(v) for v in high]}
    part_color = surf_index.get("partColor")
    return encode_payload(
        surface_input=surface_input, surface_object=surface_object, chord=chord, angle=angle,
        positions=positions, normals=normals, indices=indices, face_ranges=face_ranges, edges=edges,
        bounds=bounds, scale=float(diagonal),
        part_color=[float(c) for c in part_color] if part_color else None, unmeshed_faces=unmeshed,
    )
