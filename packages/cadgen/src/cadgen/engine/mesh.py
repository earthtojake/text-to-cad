"""Tessellation: one part as one buffer a renderer reads without parsing.

**The tolerance is FreeCAD's default, and nothing else.** A part is meshed with
``BRepMesh_IncrementalMesh`` at an absolute linear deflection of ``(Lx + Ly + Lz) / 300 *
DEVIATION`` of its own bounding box (``DEVIATION`` 0.5: FreeCAD's Deviation of 0.5 %) and an
angular deflection of ``ANGULAR`` (28.5 degrees), with the kernel's face parallelism on. The
constant pair is configurable nowhere. The call goes through ``IMeshTools_Parameters`` with
one knob set besides: ``EnableControlSurfaceDeflectionAllSurfaces``, which holds analytic
faces (torus, sphere, cone) to the deflection -- measured across nine large documents,
from 1.5-2x the deflection to under 1x, for 2-13 % more triangles on those parts. Every
other knob was measured to change nothing useful and stays at its default.

**BRepMesh as it is.** No check, no second pass, no finer retry, no other tessellator: the
same measurement found the faces left without triangles the same few hundredths of a per
cent at every tolerance, different faces each time, and a retry finer brought back half,
unreliably. A face the mesher leaves without triangles is left out of the buffer -- its
face-table row has no indices -- and named: ``Mesh.unmeshed`` maps its ordinal to the
verdict, the mesher's own status first (``GetStatusFlags`` of the part's mesh, e.g.
``SelfIntersectingWire``: the face's discretized wire crosses itself), then what
``BRepCheck_Analyzer`` says of that face (``check``), which called most such faces valid.

A part is meshed from its binary shape bytes (``shape_bytes``: geometry only, at the
identity), read into a fresh shape: the mesh is a function of those bytes alone -- the same
wherever they are meshed, in this process or in a pool process handed them -- never of a
triangulation some earlier call left on the shape, and the caller's shape is not written
to. (A topological copy is not enough: measured on a large document, a copy and the bytes
read back meshed 65 of 987 parts with other triangles on some planar faces. Nor is the
round trip idempotent: bytes read and written again differ, and so can their mesh. So a
caller hands a pool process the bytes, never a shape made from them.) The bytes are those
of the part as its document reads it back: a build's live shape is written and read once
first, so a worker and a daemon that only read the xbf mesh one key from the same bytes.

The buffer (``Mesh.to_bytes``, format ``XBM2``) holds float32 positions and surface normals,
uint32 triangle indices, a face table of (face ordinal, first index, index count), an edge
table of (edge ordinal, first point, point count, class) with the edges' polylines, and a
vertex table of (vertex ordinal, x, y, z) for every vertex of the part. Ordinals are
``TopExp.MapShapes`` ordinals of the part, the ordinals its element names are kept by.
Selecting a face is a range of the index buffer; an edge, a range of the polyline buffer.

An edge's class is read from the B-rep alone (``edge_class``): ``FEATURE`` between two
faces that meet at an angle, ``TANGENT`` between two that meet at least G1
(``BRep_Tool.Continuity``, after ``BRepLib.EncodeRegularity`` on the copy), ``SEAM`` where a
face closes on itself, ``BOUNDARY`` with one face, ``NONMANIFOLD`` with more than two.
Degenerate edges are not in the table. An edge's polyline is its polygon on the
triangulation of the first of its faces that has one.

The arrays are read from the kernel without a Python loop per node: the part's
triangulations and polygons are written, as triangulation-only faces and edges, into the
kernel's binary shape format in memory (``BinTools``) and read back with numpy from that
one buffer; a buffer that does not read back as expected falls back to the kernel's
accessors, one node at a time.

The header is 80 little-endian bytes: the magic ``XBM2``, the format version, the counts of
nodes, indices, faces, edges, edge points and vertices, the byte offset of each of the seven
arrays, the two deflections, and three reserved words; then the arrays, each 4-byte
aligned, at their offsets.
"""

from __future__ import annotations

import io
import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np
from OCP.BRep import BRep_Tool
from OCP.GeomAbs import GeomAbs_G1
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_ListOfShape

__all__ = ["ANGULAR", "BOUNDARY", "DEVIATION", "FEATURE", "HEADER", "MAGIC", "Mesh", "NONMANIFOLD", "SEAM",
           "TANGENT", "Topology", "check", "deflection", "mesh_shape"]

# FreeCAD's default tessellation: Deviation 0.5 (per cent of the box's summed sides, /300 as
# FreeCAD writes it) and an angular deflection of 28.5 degrees.
DEVIATION = 0.5
ANGULAR = math.radians(28.5)


_G1 = int(GeomAbs_G1)
# BRepMesh_Status bits, as the mesher's GetStatusFlags reports them.
_MESH_FLAGS = ((1, "Failure"), (2, "ReMesh"), (4, "SelfIntersectingWire"), (8, "UserBreak"))

from cadgen.engine.mesh_format import (BOUNDARY, CLASS_NAMES, FEATURE, HEADER, MAGIC,  # noqa: F401
                                        NONMANIFOLD, SEAM, TANGENT, VERSION, Mesh)


def deflection(shape: Any) -> float:
    """The linear deflection of ``shape``: FreeCAD's, ``(Lx + Ly + Lz) / 300 * DEVIATION`` of
    its bounding box, with a floor for a box that is void or a point."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return 0.1
    box.SetGap(0.0)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return max(((xmax - xmin) + (ymax - ymin) + (zmax - zmin)) / 300.0 * DEVIATION, 1e-4)


def _write(shape: Any) -> bytes:
    from OCP.BinTools import BinTools, BinTools_FormatVersion_VERSION_4
    from OCP.TopLoc import TopLoc_Location

    stream = io.BytesIO()
    BinTools.Write_s(shape.Located(TopLoc_Location()), stream, False, False, BinTools_FormatVersion_VERSION_4)
    return stream.getvalue()


# The bookkeeping flags of every sub-shape, as the canonical bytes hold them: (Free,
# Modified, Checked, Locked). They say what was done to a shape, not what it is: a read
# leaves the root free or not depending on the reader, a face maker leaves Checked set.
# Orientable, Closed, Infinite and Convex describe the geometry and are kept.
_BOOKKEEPING = (True, True, False, False)


@contextmanager
def _settled(shape: Any) -> Iterator[None]:
    """``shape`` with every sub-shape's bookkeeping flags at ``_BOOKKEEPING``, set back after."""
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, mapped)
    free, modified, checked, locked = _BOOKKEEPING
    changed = []
    for ordinal in range(1, mapped.Extent() + 1):
        tshape = mapped.FindKey(ordinal).TShape()
        held = (tshape.Free(), tshape.Modified(), tshape.Checked(), tshape.Locked())
        if held != _BOOKKEEPING:
            changed.append((tshape, held))
            tshape.Free(free)
            tshape.Modified(modified)
            tshape.Checked(checked)
            tshape.Locked(locked)
    try:
        yield
    finally:
        for tshape, (free, modified, checked, locked) in changed:
            tshape.Free(free)
            tshape.Modified(modified)
            tshape.Checked(checked)
            tshape.Locked(locked)


def shape_bytes(shape: Any, *, read: bool = False) -> bytes:
    """A part's shape as the kernel's binary shape bytes, geometry only (no triangulation),
    at the identity: the canonical form a part is meshed from, one per geometry key -- the
    part's bytes as its document reads it back, with its bookkeeping flags at one value.

    A part's mesh must be the same whether the shape comes from a build's memory or from
    its xbf read back by a process that never built it. Neither the shape nor the round
    trip is idempotent: reading a shape's bytes sets each sub-shape location from its
    matrix, which moves it by a last bit (``gp_Trsf.SetValues`` normalises and
    orthogonalises the matrix it is given), so each write and read moves it again and
    never settles -- measured on a 987-part document, a second round trip changed 171
    parts' bytes, and a third, a fourth and a seventh kept changing some; the live shape's
    bytes and the read-back shape's differed in all 987 and meshed 65 parts differently.
    But one read is one read: a live shape written and read once has, bit for bit, the
    bytes of the same shape read from the saved xbf (all 987 parts, and every mesh
    equal). So a live shape -- a build's part -- is written and read once here, as saving
    and reading its document does; a shape a document read (``read``, the served
    document's parts) already is, and is written as it is."""
    if read:
        with _settled(shape):
            return _write(shape)
    copy = read_shape(_write(shape))
    with _settled(copy):
        return _write(copy)


def read_shape(data: bytes) -> Any:
    """The shape of ``shape_bytes``: a fresh one, sharing nothing with any other."""
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(bytes(data)))
    return shape


def mesh_shape(shape: Any, *, parallel: bool = True) -> Mesh:
    """Mesh one part (a shape, or its ``shape_bytes``) at its own frame: its location is not
    applied. ``parallel`` is the kernel's face parallelism; it does not change the result."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IMeshTools import IMeshTools_Parameters

    local = read_shape(shape if isinstance(shape, (bytes, bytearray, memoryview)) else shape_bytes(shape))
    linear = deflection(local)
    parameters = IMeshTools_Parameters()
    parameters.Deflection, parameters.Angle, parameters.Relative, parameters.InParallel = linear, ANGULAR, False, parallel
    parameters.EnableControlSurfaceDeflectionAllSurfaces = True
    mesher = BRepMesh_IncrementalMesh(local, parameters)
    flags = mesher.GetStatusFlags()
    mesh = _extract(local, ", ".join(name for bit, name in _MESH_FLAGS if flags & bit) or "no status")
    mesh.linear, mesh.angular = linear, ANGULAR
    return mesh


# --- the B-rep's own facts -----------------------------------------------------------------


def _unique_faces(owners: Any) -> list[Any]:
    """The distinct faces of an ancestor list (a seam's face is in it twice). Read with
    ``First``/``Last``: the bound list's Python iterator costs milliseconds per list."""
    size = owners.Size()
    if size == 0:
        listed = []
    elif size <= 2:
        listed = [owners.First(), owners.Last()][:size]
    else:
        rest = TopTools_ListOfShape()
        rest.Assign(owners)
        listed = []
        while not rest.IsEmpty():
            listed.append(rest.First())
            rest.RemoveFirst()
    found: list[Any] = []
    for owner in listed:
        if not any(owner.IsSame(held) for held in found):
            found.append(owner)
    return [TopoDS.Face_s(face) for face in found]


def edge_class(edge: Any, faces: list[Any]) -> int:
    """One edge's class from its distinct faces (see the module docstring)."""
    if any(BRep_Tool.IsClosed_s(edge, face) for face in faces):
        return SEAM
    if len(faces) == 1:
        return BOUNDARY
    if len(faces) > 2:
        return NONMANIFOLD
    if len(faces) == 2 and int(BRep_Tool.Continuity_s(edge, faces[0], faces[1])) >= _G1:
        return TANGENT
    return FEATURE


def check(face: Any) -> str:
    """What ``BRepCheck_Analyzer`` says of one face: ``valid``, or each fault it finds on
    the face, its wires and its edges, the wires' first ("wire 1: SelfIntersectingWire;
    face: UnorientableShape")."""
    import OCP.BRepCheck as brepcheck
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer

    analyzer = BRepCheck_Analyzer(face)

    def faults(statuses: Any) -> list[str]:
        return [str(status).rsplit(".", 1)[-1].removeprefix("BRepCheck_") for status in statuses
                if status != brepcheck.BRepCheck_NoError]

    found: list[str] = []
    for kind, label in ((TopAbs_WIRE, "wire"), (TopAbs_EDGE, "edge")):
        explorer = TopExp_Explorer(face, kind)
        at = 0
        while explorer.More():
            at += 1
            result = analyzer.Result(explorer.Current())
            if result is not None:
                # A seam is met twice, once per orientation, and the analyzer keeps a
                # status in the face's context for one of them only: asked for the other,
                # StatusOnShape raises.
                on_face = faults(result.StatusOnShape(face)) if result.IsStatusOnShape(face) else []
                for text in dict.fromkeys(faults(result.Status()) + on_face):
                    found.append(f"{label} {at}: {text}")
            explorer.Next()
    result = analyzer.Result(face)
    if result is not None:
        found += [f"face: {text}" for text in dict.fromkeys(faults(result.Status()))]
    if not found:
        return "valid"
    shown = list(dict.fromkeys(found))
    return "; ".join(shown[:6]) + (f"; and {len(shown) - 6} more" if len(shown) > 6 else "")


def _kind(value: Any) -> str:
    return str(getattr(value, "name", value)).rsplit(".", 1)[-1].removeprefix("GeomAbs_").lower()


def _point(point: Any) -> list[float]:
    return [point.X(), point.Y(), point.Z()]


# How nearly two edges must run on through a vertex, opposed, to continue one chain where more
# than one could: a STEP's selector table's alignment.
CHAIN_ALIGNMENT_DEG = 3.0
CHAIN_ALIGNMENT_COS = -math.cos(math.radians(CHAIN_ALIGNMENT_DEG))


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    size = math.sqrt(sum(value * value for value in vector))
    return None if size < 1e-12 else (vector[0] / size, vector[1] / size, vector[2] / size)


class Topology:
    """A part's faces, edges and vertices by ordinal, and what the kernel measures of each
    when asked (``face``, ``edge``, ``vertex``): nothing is measured ahead. It reads the
    part as the mesher does, from its shape bytes, so continuity it encodes is written on
    no one else's shape."""

    def __init__(self, shape: Any) -> None:
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        self.shape = read_shape(shape if isinstance(shape, (bytes, bytearray, memoryview)) else shape_bytes(shape))
        self.maps = {}
        for name, kind in (("face", TopAbs_FACE), ("edge", TopAbs_EDGE), ("vertex", TopAbs_VERTEX)):
            found = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(self.shape, kind, found)
            self.maps[name] = found
        self._ancestors: Any = None

    def _get(self, kind: str, ordinal: int) -> Any:
        from OCP.TopoDS import TopoDS

        found = self.maps[kind]
        if not 1 <= ordinal <= found.Extent():
            raise KeyError(f"the part has no {kind} {ordinal} (it has {found.Extent()})")
        shape = found.FindKey(ordinal)
        return {"face": TopoDS.Face_s, "edge": TopoDS.Edge_s, "vertex": TopoDS.Vertex_s}[kind](shape)

    def face(self, ordinal: int) -> dict[str, Any]:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        face = self._get("face", ordinal)
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(face, box, False, False)
        bounds = list(box.Get()) if not box.IsVoid() else None
        surface = BRepAdaptor_Surface(face, False)
        kind = _kind(surface.GetType())
        found = {"kind": "face", "ordinal": ordinal, "area": props.Mass(), "centroid": _point(props.CentreOfMass()),
                 "surface": kind, "box": None if bounds is None else {"min": bounds[:3], "max": bounds[3:]}, "check": check(face)}
        # A round face's radii, as a STEP's pick data carries them: what its card reads.
        if kind == "cylinder":
            found["radius"] = surface.Cylinder().Radius()
        elif kind == "sphere":
            found["radius"] = surface.Sphere().Radius()
        elif kind == "torus":
            torus = surface.Torus()
            found["majorRadius"], found["minorRadius"] = torus.MajorRadius(), torus.MinorRadius()
        return found

    def edge(self, ordinal: int) -> dict[str, Any]:
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepLib import BRepLib
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

        edge = self._get("edge", ordinal)
        if self._ancestors is None:
            BRepLib.EncodeRegularity_s(self.shape, 1e-3)  # as the mesher classes edges
            self._ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
            TopExp.MapShapesAndAncestors_s(self.shape, TopAbs_EDGE, TopAbs_FACE, self._ancestors)
        degenerate = BRep_Tool.Degenerated_s(edge)
        at = self._ancestors.FindIndex(edge)
        faces = _unique_faces(self._ancestors.FindFromIndex(at)) if at else []
        kind = 0 if degenerate else (edge_class(edge, faces) if faces else BOUNDARY)
        props = GProp_GProps()
        BRepGProp.LinearProperties_s(edge, props)
        first, last = TopExp.FirstVertex_s(edge, True), TopExp.LastVertex_s(edge, True)
        vertices = self.maps["vertex"]
        curve = None if degenerate else BRepAdaptor_Curve(edge)
        found = {"kind": "edge", "ordinal": ordinal, "length": props.Mass(),
                 "curve": "degenerate" if degenerate else _kind(curve.GetType()),
                 "class": CLASS_NAMES.get(kind, "degenerate"), "classCode": kind,
                 "faces": [self.maps["face"].FindIndex(face) for face in faces],
                 "endpoints": [_point(BRep_Tool.Pnt_s(vertex)) for vertex in (first, last) if not vertex.IsNull()],
                 "vertices": [vertices.FindIndex(vertex) for vertex in (first, last) if not vertex.IsNull()]}
        # A circle's radius and the span it sweeps, as a STEP's pick data carries them.
        if found["curve"] == "circle":
            found["radius"] = curve.Circle().Radius()
            found["sweepRadians"] = abs(curve.LastParameter() - curve.FirstParameter())
        return found

    def groups(self) -> dict[str, dict[str, int]]:
        """How a pick of one face or edge grows, as a STEP's selector table says it: each face's
        tangent group (faces joined across tangent edges of one solid) and each edge's chain (edges
        that continue one another at a shared vertex: two edges of a common face of one solid,
        where more than one could continue the one that runs on within ``CHAIN_ALIGNMENT_DEG``,
        and only when each is the other's choice). Keyed by ordinal, as text; a group is the
        smallest ordinal in it."""
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepLib import BRepLib
        from OCP.gp import gp_Pnt, gp_Vec
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

        faces_map, edges_map, vertices_map = self.maps["face"], self.maps["edge"], self.maps["vertex"]
        BRepLib.EncodeRegularity_s(self.shape, 1e-3)
        ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(self.shape, TopAbs_EDGE, TopAbs_FACE, ancestors)
        # Each face's solid (the first that holds it): neither grouping crosses solids.
        solid_of: dict[int, int] = {}
        solids = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.shape, TopAbs_SOLID, solids)
        for at in range(1, solids.Extent() + 1):
            held = TopTools_IndexedMapOfShape()
            TopExp.MapShapes_s(solids.FindKey(at), TopAbs_FACE, held)
            for index in range(1, held.Extent() + 1):
                solid_of.setdefault(faces_map.FindIndex(held.FindKey(index)), at)

        parent = {ordinal: ordinal for ordinal in range(1, faces_map.Extent() + 1)}

        def root(table: dict[int, int], item: int) -> int:
            while table[item] != item:
                table[item] = table[table[item]]
                item = table[item]
            return item

        edge_faces: dict[int, set[int]] = {}
        tangents: dict[int, tuple[Any, Any]] = {}
        ends: dict[int, tuple[int, int]] = {}
        for ordinal in range(1, edges_map.Extent() + 1):
            edge = TopoDS.Edge_s(edges_map.FindKey(ordinal))
            at = ancestors.FindIndex(edge)
            faces = _unique_faces(ancestors.FindFromIndex(at)) if at else []
            owners = {faces_map.FindIndex(face) for face in faces}
            edge_faces[ordinal] = owners
            if BRep_Tool.Degenerated_s(edge):
                continue
            if len(faces) == 2 and edge_class(edge, faces) == TANGENT:
                one, two = sorted(owners)
                if solid_of.get(one) == solid_of.get(two):
                    parent[root(parent, one)] = root(parent, two)
            first, last = TopExp.FirstVertex_s(edge, False), TopExp.LastVertex_s(edge, False)
            if first.IsNull() or last.IsNull():
                continue
            ends[ordinal] = (vertices_map.FindIndex(first), vertices_map.FindIndex(last))
            if ends[ordinal][0] == ends[ordinal][1]:
                continue
            try:
                curve, point, vector = BRepAdaptor_Curve(edge), gp_Pnt(), gp_Vec()
                curve.D1(curve.FirstParameter(), point, vector)
                into_first = _unit((vector.X(), vector.Y(), vector.Z()))
                curve.D1(curve.LastParameter(), point, vector)
                into_last = _unit((-vector.X(), -vector.Y(), -vector.Z()))
            except Exception:  # noqa: BLE001 - an edge with no tangent is in no chain
                continue
            if into_first is not None and into_last is not None:
                tangents[ordinal] = (into_first, into_last)

        at_vertex: dict[int, list[tuple[int, int]]] = {}
        for ordinal, pair in tangents.items():
            for end, vertex in enumerate(ends[ordinal]):
                at_vertex.setdefault(vertex, []).append((ordinal, end))
        solid_of_edge = {ordinal: min((solid_of.get(face, 0) for face in owners), default=0) for ordinal, owners in edge_faces.items()}
        choice: dict[tuple[int, int], tuple[int, int]] = {}
        for here in at_vertex.values():
            for ordinal, end in here:
                candidates = [(other, other_end) for other, other_end in here if other != ordinal
                              and solid_of_edge[other] == solid_of_edge[ordinal] and edge_faces[other] & edge_faces[ordinal]]
                if len(candidates) > 1:
                    direction = tangents[ordinal][end]
                    candidates = [(other, other_end) for other, other_end in candidates
                                  if sum(a * b for a, b in zip(direction, tangents[other][other_end])) < CHAIN_ALIGNMENT_COS]
                if len(candidates) == 1:
                    choice[(ordinal, end)] = candidates[0]
        chains = {ordinal: ordinal for ordinal in tangents}
        for here, there in choice.items():
            if choice.get(there) == here:
                chains[root(chains, here[0])] = root(chains, there[0])
        # A group is named by its smallest member, so the answer does not hang on the union's order.
        def named(table: dict[int, int]) -> dict[str, int]:
            smallest: dict[int, int] = {}
            for item in table:
                top = root(table, item)
                smallest[top] = min(smallest.get(top, item), item)
            return {str(item): smallest[root(table, item)] for item in sorted(table)}
        return {"faces": named(parent), "edges": named(chains)}

    def vertex(self, ordinal: int) -> dict[str, Any]:
        from OCP.BRep import BRep_Tool

        vertex = self._get("vertex", ordinal)
        return {"kind": "vertex", "ordinal": ordinal, "position": _point(BRep_Tool.Pnt_s(vertex)),
                "tolerance": BRep_Tool.Tolerance_s(vertex)}

    def volume(self) -> dict[str, Any]:
        """The part's volume in cubic millimetres, of its solids (``BRepGProp``), and how many it
        has: a part of faces or wires alone has none, and no volume to weigh."""
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        solids = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.shape, TopAbs_SOLID, solids)
        total = 0.0
        for at in range(1, solids.Extent() + 1):
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(solids.FindKey(at), props)
            total += abs(props.Mass())
        return {"volume": total, "solids": solids.Extent()}


# --- extraction ----------------------------------------------------------------------------


@dataclass
class _Face:
    ordinal: int
    triangulation: int  # its index among the distinct triangulations, -1 for none
    transform: np.ndarray | None  # 3x4, or None at the identity
    reversed: bool


def _transform(location: Any) -> np.ndarray | None:
    if location.IsIdentity():
        return None
    value = location.Transformation().Value
    return np.array([[value(row, column) for column in (1, 2, 3, 4)] for row in (1, 2, 3)])


def _extract(shape: Any, mesher_status: str = "no status") -> Mesh:
    from OCP.BinTools import BinTools, BinTools_FormatVersion_VERSION_4
    from OCP.BRep import BRep_Builder, BRep_Tool
    from OCP.BRepLib import BRepLib, BRepLib_ToolTriangulatedShape
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Edge, TopoDS_Face
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape, TopTools_IndexedMapOfShape

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
    builder = BRep_Builder()
    holder = TopoDS_Compound()
    builder.MakeCompound(holder)
    triangulations: dict[Any, int] = {}
    held: list[Any] = []
    face_rows: list[_Face] = []
    by_face: dict[Any, int] = {}
    unmeshed: dict[int, str] = {}
    for ordinal in range(1, faces.Extent() + 1):
        face = TopoDS.Face_s(faces.FindKey(ordinal))
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is None or triangulation.NbTriangles() == 0:
            face_rows.append(_Face(ordinal, -1, None, False))
            unmeshed[ordinal] = f"BRepMesh: {mesher_status}; BRepCheck: {check(face)}"
            continue
        tshape = face.TShape()
        index = triangulations.get(tshape)
        if index is None:
            BRepLib_ToolTriangulatedShape.ComputeNormals_s(face, triangulation)
            index = triangulations[tshape] = len(held)
            held.append(triangulation)
            bare = TopoDS_Face()
            builder.MakeFace(bare, triangulation)
            builder.Add(holder, bare)
        face_rows.append(_Face(ordinal, index, _transform(location), face.Orientation() == TopAbs_REVERSED))
        by_face[tshape] = index

    BRepLib.EncodeRegularity_s(shape, 1e-3)  # the copy's own edges: continuity for the classes
    edges = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edges)
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ancestors)
    polygons: dict[tuple, int] = {}
    polygon_list: list[Any] = []
    # ordinal, class, polygon (-1 for none), its face's transform
    edge_rows: list[tuple[int, int, int, np.ndarray | None]] = []
    for ordinal in range(1, edges.Extent() + 1):
        edge = TopoDS.Edge_s(edges.FindKey(ordinal))
        if BRep_Tool.Degenerated_s(edge):
            continue
        at = ancestors.FindIndex(edge)
        owners = _unique_faces(ancestors.FindFromIndex(at)) if at else []
        kind = edge_class(edge, owners) if owners else BOUNDARY
        found = None
        for face in owners:
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)
            index = by_face.get(face.TShape()) if triangulation is not None else None
            if index is None:
                continue
            polygon = BRep_Tool.PolygonOnTriangulation_s(edge, triangulation, location)
            if polygon is not None:
                found = (polygon, triangulation, index, location)
                break
        if found is None:
            edge_rows.append((ordinal, kind, -1, None))
            continue
        polygon, triangulation, face_index, location = found
        # An extrusion's far cap shares its edges' TShapes with the near cap's, moved by a
        # location: the same face holds a polygon for each, so the edge's location is the key's too.
        key = (edge.TShape(), edge.Location().HashCode(), face_index)
        index = polygons.get(key)
        if index is None:
            index = polygons[key] = len(polygon_list)
            polygon_list.append((polygon, face_index))
            bare = TopoDS_Edge()
            builder.MakeEdge(bare)
            builder.UpdateEdge(bare, polygon, triangulation)
            builder.Add(holder, bare)
        edge_rows.append((ordinal, kind, index, _transform(location)))

    vertex_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_VERTEX, vertex_map)
    vertices = np.zeros((vertex_map.Extent(), 4), dtype=np.float32)
    for ordinal in range(1, vertex_map.Extent() + 1):
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertex_map.FindKey(ordinal)))
        vertices[ordinal - 1] = (ordinal, point.X(), point.Y(), point.Z())

    stream = io.BytesIO()
    BinTools.Write_s(holder, stream, True, True, BinTools_FormatVersion_VERSION_4)
    read = _read_dump(stream.getvalue(), len(held), len(polygon_list))
    if read is None:
        read = _read_accessors(held, [polygon for polygon, _index in polygon_list])
    mesh = _assemble(face_rows, edge_rows, polygon_list, *read, vertices)
    mesh.unmeshed = unmeshed
    return mesh


def _section(data: bytes, name: bytes, start: int) -> tuple[int, int]:
    at = data.find(b"\n" + name + b" ", start)
    if at < 0:
        raise ValueError(name)
    end = data.index(b"\n", at + 1)
    return int(data[at + len(name) + 2:end]), end + 1


def _read_dump(data: bytes, expected: int, expected_polygons: int) -> tuple[list, list] | None:
    """The triangulations and polygons of a ``BinTools`` dump (format 4), or None when the
    dump does not read as one: the counts differ, or the shapes section is not where the
    arrays end."""
    try:
        count, at = _section(data, b"PolygonOnTriangulations", 0)
        if count != expected_polygons:
            return None
        polygons = []
        for _ in range(count):
            n = int(np.frombuffer(data, "<i4", 1, at)[0])
            at += 4
            polygons.append(np.frombuffer(data, "<i4", n, at))
            at += 4 * n + 8  # the indices, the deflection
            has_parameters = data[at]
            at += 1
            if has_parameters:
                at += 8 * n
        count, at = _section(data, b"Triangulations", at)
        if count != expected:
            return None
        triangulations = []
        for _ in range(count):
            nodes, triangles = (int(value) for value in np.frombuffer(data, "<i4", 2, at))
            has_uv, has_normals = data[at + 8], data[at + 9]
            at += 18  # the counts, the two flags, the deflection
            points = np.frombuffer(data, "<f8", 3 * nodes, at).reshape(-1, 3)
            at += 24 * nodes
            if has_uv:
                at += 16 * nodes
            corners = np.frombuffer(data, "<i4", 3 * triangles, at).reshape(-1, 3)
            at += 12 * triangles
            normals = None
            if has_normals:
                normals = np.frombuffer(data, "<f4", 3 * nodes, at).reshape(-1, 3)
                at += 12 * nodes
            triangulations.append((points, corners, normals))
        if not data.startswith(b"\nTShapes ", at):
            return None
        return triangulations, polygons
    except (ValueError, IndexError):
        return None


def _read_accessors(held: list, polygons: list) -> tuple[list, list]:
    """The same arrays read one node at a time, through the kernel's accessors."""
    triangulations = []
    for triangulation in held:
        nodes = triangulation.NbNodes()
        points = np.array([triangulation.Node(i).Coord() for i in range(1, nodes + 1)], dtype=float).reshape(-1, 3)
        corners = np.array([triangulation.Triangle(i).Get() for i in range(1, triangulation.NbTriangles() + 1)],
                           dtype=np.int32).reshape(-1, 3)
        normals = None
        if triangulation.HasNormals():
            normals = np.array([(lambda d: (d.X(), d.Y(), d.Z()))(triangulation.Normal(i))
                                for i in range(1, nodes + 1)], dtype=np.float32).reshape(-1, 3)
        triangulations.append((points, corners, normals))
    found = [np.array([polygon.Node(i) for i in range(1, polygon.NbNodes() + 1)], dtype=np.int32)
             for polygon in polygons]
    return triangulations, found


def _assemble(face_rows: list[_Face], edge_rows: list, polygon_list: list, triangulations: list,
              polygons: list, vertices: np.ndarray) -> Mesh:
    """The part's arrays from its faces' triangulations, joined first and computed on as one:
    a part of a thousand faces costs a few array operations, not a few per face."""
    face_table = np.zeros((len(face_rows), 3), dtype=np.uint32)
    face_table[:, 0] = [face.ordinal for face in face_rows]
    meshed = [(row, face) for row, face in enumerate(face_rows) if face.triangulation >= 0]
    points_list, corners_list, normals_list = [], [], []
    node_counts, triangle_counts, stored_flags, reversed_flags = [], [], [], []
    for _row, face in meshed:
        points, corners, stored = triangulations[face.triangulation]
        has = stored is not None and len(stored) == len(points)
        normals = stored if has else np.zeros((len(points), 3), dtype=np.float32)
        if face.transform is not None:
            points = points @ face.transform[:, :3].T + face.transform[:, 3]
            normals = normals @ face.transform[:, :3].T
        points_list.append(points)
        corners_list.append(corners)
        normals_list.append(normals)
        node_counts.append(len(points))
        triangle_counts.append(len(corners))
        stored_flags.append(has)
        reversed_flags.append(face.reversed)
    if meshed:
        nodes = np.asarray(node_counts)
        triangles = np.asarray(triangle_counts)
        positions = np.concatenate(points_list).astype(np.float64, copy=False)
        normals = np.concatenate(normals_list).astype(np.float64)
        bases = np.concatenate(([0], np.cumsum(nodes)[:-1]))
        corners = np.concatenate(corners_list).astype(np.int64) - 1 + np.repeat(bases, triangles)[:, None]
        flipped = np.repeat(np.asarray(reversed_flags), triangles)
        corners[flipped] = corners[flipped][:, [0, 2, 1]]
        a, b, c = positions[corners[:, 0]], positions[corners[:, 1]], positions[corners[:, 2]]
        geometric = np.cross(b - a, c - a)
        stored = np.asarray(stored_flags)
        starts = np.concatenate(([0], np.cumsum(triangles)[:-1]))
        # A triangulation is shared by both orientations of its face: its normals point
        # whichever way the first one to compute them faced.
        facing = np.add.reduceat(np.einsum("ij,ij->i", geometric, normals[corners[:, 0]]), starts)
        normals[np.repeat(stored & (facing < 0), nodes)] *= -1
        if not stored.all():
            mine = np.repeat(~stored, triangles)
            summed = np.zeros_like(positions)
            for column in range(3):
                np.add.at(summed, corners[mine, column], geometric[mine])
            lengths = np.linalg.norm(summed, axis=1, keepdims=True)
            computed = np.repeat(~stored, nodes)
            normals[computed] = (summed / np.where(lengths > 0, lengths, 1))[computed]
        counts = np.zeros(len(face_rows), dtype=np.int64)
        counts[[row for row, _face in meshed]] = triangles * 3
        face_table[:, 2] = counts
        face_table[:, 1] = np.concatenate(([0], np.cumsum(counts)[:-1]))
        positions32, normals32 = positions.astype(np.float32), normals.astype(np.float32)
        indices = corners.astype(np.uint32).ravel()
    else:
        positions32 = normals32 = np.zeros((0, 3), dtype=np.float32)
        indices = np.zeros(0, dtype=np.uint32)
    edge_table = np.zeros((len(edge_rows), 4), dtype=np.uint32)
    lines = []
    point_base = 0
    for row, (ordinal, kind, index, transform) in enumerate(edge_rows):
        if index < 0:
            edge_table[row] = (ordinal, point_base, 0, kind)
            continue
        polygon = polygons[index]
        points, _corners, _normals = triangulations[polygon_list[index][1]]
        line = points[polygon.astype(np.int64) - 1]
        if transform is not None:
            line = line @ transform[:, :3].T + transform[:, 3]
        lines.append(line.astype(np.float32))
        edge_table[row] = (ordinal, point_base, len(line), kind)
        point_base += len(line)

    def joined(items: list, width: int, dtype: Any) -> np.ndarray:
        return np.concatenate(items) if items else np.zeros((0, width) if width > 1 else 0, dtype=dtype)

    return Mesh(positions32, normals32, indices, face_table, edge_table, joined(lines, 3, np.float32), vertices)
